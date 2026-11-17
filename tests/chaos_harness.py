from __future__ import annotations

from dataclasses import dataclass
import os
import socket
import subprocess
import sys
import time
from typing import Any, Callable
import uuid

import redis

DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/14"


def live_redis_available(redis_url: str = DEFAULT_REDIS_URL) -> bool:
    try:
        r = redis.from_url(redis_url, socket_connect_timeout=0.5, socket_timeout=0.5)
        return bool(r.ping())
    except Exception:
        return False


def cleanup_prefix(prefix: str, redis_url: str = DEFAULT_REDIS_URL) -> int:
    r = redis.from_url(redis_url, decode_responses=True)
    deleted = 0
    try:
        keys = list(r.scan_iter(f"{prefix}*", count=500))
        if keys:
            deleted = int(r.delete(*keys) or 0)
    finally:
        r.close()
    return deleted


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def poll_until(
    predicate: Callable[[], bool],
    *,
    timeout: float = 10.0,
    interval: float = 0.1,
    description: str = "condition",
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError(f"Timed out after {timeout:.1f}s waiting for {description}")


def summarize_latencies(samples_ms: list[float], elapsed_s: float) -> dict[str, float | int]:
    if not samples_ms:
        return {"count": 0, "throughput_ops_s": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "max_ms": 0.0}
    ordered = sorted(samples_ms)
    n = len(ordered)

    def pct(q: float) -> float:
        idx = min(n - 1, max(0, int(round(q * (n - 1)))))
        return round(ordered[idx], 3)

    return {
        "count": n,
        "throughput_ops_s": round(n / max(elapsed_s, 1e-6), 2),
        "p50_ms": pct(0.50),
        "p95_ms": pct(0.95),
        "p99_ms": pct(0.99),
        "max_ms": round(ordered[-1], 3),
    }


def snapshot_redis_resources(client: Any, prefix: str) -> dict[str, int]:
    info_mem = client.info("memory")
    info_cli = client.info("clients")
    key_count = sum(1 for _ in client.scan_iter(f"{prefix}*", count=500))
    return {
        "key_count": key_count,
        "used_memory_bytes": int(info_mem.get("used_memory", 0) or 0),
        "connected_clients": int(info_cli.get("connected_clients", 0) or 0),
    }


@dataclass
class ManagedWorker:
    proc: subprocess.Popen[str]
    name: str


class WorkerProcessManager:
    """Manages independent OS worker subprocesses with deterministic readiness and guaranteed cleanup."""

    def __init__(self) -> None:
        self._workers: list[ManagedWorker] = []

    def spawn_python(
        self,
        code: str,
        *,
        name: str = "worker",
        ready_marker: str | None = "READY",
        ready_timeout: float = 10.0,
        env: dict[str, str] | None = None,
    ) -> ManagedWorker:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        proc = subprocess.Popen(
            [sys.executable, "-u", "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=merged_env,
        )
        worker = ManagedWorker(proc=proc, name=name)
        self._workers.append(worker)

        if ready_marker is not None:
            assert proc.stdout is not None
            deadline = time.monotonic() + ready_timeout
            lines: list[str] = []
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    err = proc.stderr.read() if proc.stderr else ""
                    raise RuntimeError(f"Worker {name} exited prematurely ({proc.returncode}): {err}")
                line = proc.stdout.readline()
                if line:
                    lines.append(line.strip())
                    if ready_marker in line:
                        return worker
                else:
                    time.sleep(0.05)
            raise TimeoutError(f"Worker {name} did not emit {ready_marker!r}; saw {lines}")
        return worker

    def kill_abruptly(self, worker: ManagedWorker) -> None:
        if worker.proc.poll() is None:
            worker.proc.kill()
            worker.proc.wait(timeout=5.0)

    def terminate_gracefully(self, worker: ManagedWorker) -> None:
        if worker.proc.poll() is None:
            worker.proc.terminate()
            try:
                worker.proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                worker.proc.kill()
                worker.proc.wait(timeout=5.0)

    def cleanup_all(self) -> None:
        for w in self._workers:
            try:
                if w.proc.poll() is None:
                    w.proc.kill()
                    w.proc.wait(timeout=3.0)
                if w.proc.stdout:
                    w.proc.stdout.close()
                if w.proc.stderr:
                    w.proc.stderr.close()
            except Exception:
                pass
        self._workers.clear()


class DisposableRedisContainer:
    """Starts an isolated disposable Redis 7.4.11 Docker container on an ephemeral port for outage tests."""

    def __init__(self, image: str = "redis:7-alpine") -> None:
        self.image = image
        self.name = f"radui-chaos-{uuid.uuid4().hex[:8]}"
        self.port = free_port()
        self.url = f"redis://127.0.0.1:{self.port}/0"
        self._started = False

    def start(self, *, timeout: float = 15.0) -> str:
        subprocess.run(
            ["docker", "run", "-d", "--name", self.name, "-p", f"{self.port}:6379", self.image],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._started = True
        poll_until(
            lambda: live_redis_available(self.url),
            timeout=timeout,
            interval=0.2,
            description=f"disposable Redis on port {self.port}",
        )
        return self.url

    def stop(self) -> None:
        subprocess.run(
            ["docker", "stop", "-t", "1", self.name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def restart(self, *, timeout: float = 15.0) -> None:
        subprocess.run(
            ["docker", "start", self.name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        poll_until(
            lambda: live_redis_available(self.url),
            timeout=timeout,
            interval=0.2,
            description=f"disposable Redis restart on port {self.port}",
        )

    def remove(self) -> None:
        if self._started:
            subprocess.run(
                ["docker", "rm", "-f", self.name],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self._started = False
