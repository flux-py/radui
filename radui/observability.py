from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
import socket
import threading
from typing import Any, Callable, Mapping, Sequence

_LOGGER = logging.getLogger("radui.observability")

LATENCY_BUCKET_LABELS: tuple[str, ...] = ("<1ms", "<5ms", "<20ms", "<100ms", "<500ms", ">=500ms")
LATENCY_BUCKET_BOUNDS_MS: tuple[tuple[float, float], ...] = (
    (0.0, 1.0),
    (1.0, 5.0),
    (5.0, 20.0),
    (20.0, 100.0),
    (100.0, 500.0),
    (500.0, 1000.0),
)
MAX_SNAPSHOT_BYTES = 32768


@dataclass(frozen=True)
class WorkerIdentity:
    """Standardized worker identity shared across state, event, SSE, and job subsystems."""

    worker_id: str
    hostname: str
    pid: int
    started_at: str
    environment: str
    backend_mode: str

    @classmethod
    def create(
        cls,
        *,
        worker_id: str,
        environment: str = "development",
        backend_mode: str = "memory",
    ) -> WorkerIdentity:
        return cls(
            worker_id=worker_id,
            hostname=socket.gethostname(),
            pid=os.getpid(),
            started_at=datetime.now(timezone.utc).isoformat(),
            environment=environment,
            backend_mode=backend_mode,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "hostname": self.hostname,
            "pid": self.pid,
            "started_at": self.started_at,
            "environment": self.environment,
            "backend_mode": self.backend_mode,
        }


class LatencyTracker:
    """Thread-safe, bounded latency tracker with rolling samples and fixed histogram buckets."""

    def __init__(self, sample_capacity: int = 512) -> None:
        if sample_capacity < 1:
            raise ValueError("sample_capacity must be at least 1")
        self.sample_capacity = int(sample_capacity)
        self._lock = threading.RLock()
        self._samples: deque[float] = deque(maxlen=self.sample_capacity)
        self._count: int = 0
        self._errors: int = 0
        self._max_ms: float = 0.0
        self._buckets: list[int] = [0, 0, 0, 0, 0, 0]

    def record(self, duration_ms: float, *, error: bool = False) -> None:
        ms = max(0.0, float(duration_ms))
        if ms < 1.0:
            b_idx = 0
        elif ms < 5.0:
            b_idx = 1
        elif ms < 20.0:
            b_idx = 2
        elif ms < 100.0:
            b_idx = 3
        elif ms < 500.0:
            b_idx = 4
        else:
            b_idx = 5
        with self._lock:
            self._count += 1
            if error:
                self._errors += 1
            if ms > self._max_ms:
                self._max_ms = ms
            self._buckets[b_idx] += 1
            self._samples.append(ms)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            samples = sorted(self._samples)
            p50 = _percentile_from_sorted(samples, 0.50)
            p95 = _percentile_from_sorted(samples, 0.95)
            return {
                "count": self._count,
                "errors": self._errors,
                "p50_ms": round(p50, 3) if p50 is not None else None,
                "p95_ms": round(p95, 3) if p95 is not None else None,
                "max_ms": round(self._max_ms, 3) if self._count > 0 else None,
                "buckets": {label: self._buckets[i] for i, label in enumerate(LATENCY_BUCKET_LABELS)},
                "sample_capacity": self.sample_capacity,
            }


def _percentile_from_sorted(sorted_samples: list[float], q: float) -> float | None:
    if not sorted_samples:
        return None
    if len(sorted_samples) == 1:
        return sorted_samples[0]
    idx = q * (len(sorted_samples) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_samples) - 1)
    frac = idx - lo
    return sorted_samples[lo] * (1.0 - frac) + sorted_samples[hi] * frac


def _percentile_from_buckets(bucket_counts: list[int], q: float) -> float | None:
    total = sum(bucket_counts)
    if total <= 0:
        return None
    target = q * total
    cumulative = 0
    for idx, count in enumerate(bucket_counts):
        if count <= 0:
            continue
        prev = cumulative
        cumulative += count
        if cumulative >= target:
            lo, hi = LATENCY_BUCKET_BOUNDS_MS[idx]
            frac = (target - prev) / count
            return round(lo + frac * (hi - lo), 3)
    return round(LATENCY_BUCKET_BOUNDS_MS[-1][1], 3)


def aggregate_latency_histograms(histograms: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate worker histogram buckets and derive cluster percentiles from the combined histogram."""
    total_count = 0
    total_errors = 0
    max_ms: float | None = None
    agg_buckets = [0, 0, 0, 0, 0, 0]

    for hist in histograms:
        if not isinstance(hist, Mapping):
            continue
        total_count += int(hist.get("count", 0) or 0)
        total_errors += int(hist.get("errors", 0) or 0)
        h_max = hist.get("max_ms")
        if h_max is not None:
            val = float(h_max)
            max_ms = val if max_ms is None else max(max_ms, val)
        buckets = hist.get("buckets")
        if isinstance(buckets, Mapping):
            for i, label in enumerate(LATENCY_BUCKET_LABELS):
                agg_buckets[i] += int(buckets.get(label, 0) or 0)

    return {
        "count": total_count,
        "errors": total_errors,
        "p50_ms": _percentile_from_buckets(agg_buckets, 0.50),
        "p95_ms": _percentile_from_buckets(agg_buckets, 0.95),
        "max_ms": round(max_ms, 3) if max_ms is not None else None,
        "buckets": {label: agg_buckets[i] for i, label in enumerate(LATENCY_BUCKET_LABELS)},
    }


class WorkerObservabilityPublisher:
    """Publishes bounded per-worker observability snapshots to Redis with TTL expiration."""

    def __init__(
        self,
        identity: WorkerIdentity,
        snapshot_collector: Callable[[], dict[str, Any]],
        *,
        client: Any | None = None,
        backend: Any | None = None,
        prefix: str = "gx:obs:worker:",
        ttl_seconds: float = 30.0,
    ) -> None:
        self.identity = identity
        self._collector = snapshot_collector
        self._client = client
        self._backend = backend
        self.prefix = prefix
        self.ttl_seconds = max(3, int(ttl_seconds))
        self._lock = threading.RLock()
        self.publish_count: int = 0
        self.publish_errors: int = 0
        self.last_published_at: str | None = None

    def _key(self) -> str:
        return f"{self.prefix}{self.identity.worker_id}"

    def _get_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        if self._backend is not None:
            return getattr(self._backend, "_client", None) or getattr(self._backend, "_redis_client", None)
        return None

    def build_snapshot(self, *, status: str = "active") -> dict[str, Any]:
        payload = {
            "worker": self.identity.to_dict(),
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "subsystems": self._collector(),
        }
        return payload

    def publish_snapshot(self, *, status: str = "active") -> bool:
        client = self._get_client()
        if client is None:
            with self._lock:
                self.publish_errors += 1
            return False
        try:
            snapshot = self.build_snapshot(status=status)
            encoded = json.dumps(snapshot, separators=(",", ":"), allow_nan=False)
            if len(encoded.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
                _LOGGER.warning("Worker observability snapshot exceeded %d bytes; dropping", MAX_SNAPSHOT_BYTES)
                with self._lock:
                    self.publish_errors += 1
                return False
            client.set(self._key(), encoded, ex=self.ttl_seconds)
            with self._lock:
                self.publish_count += 1
                self.last_published_at = snapshot["timestamp"]
            return True
        except Exception as exc:
            with self._lock:
                self.publish_errors += 1
            _LOGGER.warning("Failed to publish worker observability snapshot: %s", type(exc).__name__)
            return False

    def deregister(self) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            client.delete(self._key())
            return True
        except Exception as exc:
            _LOGGER.warning("Failed to deregister worker observability snapshot: %s", type(exc).__name__)
            return False


def collect_cluster_snapshot(
    client: Any | None,
    *,
    prefix: str = "gx:obs:worker:",
    max_workers: int = 500,
) -> dict[str, Any]:
    """Read live worker snapshots from Redis and aggregate metrics + histogram percentiles."""
    if client is None:
        return {
            "available": False,
            "active_workers": 0,
            "malformed_snapshots": 0,
            "workers": [],
            "aggregated": {},
        }

    workers: list[dict[str, Any]] = []
    malformed = 0
    try:
        keys = []
        for k in client.scan_iter(match=f"{prefix}*", count=200):
            keys.append(k)
            if len(keys) >= max_workers:
                break
        if keys:
            raw_values = client.mget(keys)
            for raw in raw_values:
                if raw is None:
                    continue
                try:
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    parsed = json.loads(raw)
                    if not isinstance(parsed, dict) or "worker" not in parsed or "subsystems" not in parsed:
                        malformed += 1
                        continue
                    workers.append(parsed)
                except Exception:
                    malformed += 1
    except Exception as exc:
        _LOGGER.warning("Cluster observability collection failed: %s", type(exc).__name__)
        return {
            "available": False,
            "active_workers": 0,
            "malformed_snapshots": malformed,
            "workers": [],
            "aggregated": {},
        }

    state_latencies: dict[str, list[Mapping[str, Any]]] = {op: [] for op in ("get", "set", "cas", "delete")}
    event_latencies: dict[str, list[Mapping[str, Any]]] = {op: [] for op in ("publish", "replay")}
    sse_latencies: list[Mapping[str, Any]] = []
    job_latencies: dict[str, list[Mapping[str, Any]]] = {op: [] for op in ("enqueue", "claim", "execution")}

    state_ops: dict[str, int] = {}
    event_ops: dict[str, int] = {}
    sse_ops: dict[str, int] = {}
    job_ops: dict[str, int] = {}
    job_depths: dict[str, int] = {}

    for snap in workers:
        subs = snap.get("subsystems", {})
        st = subs.get("state", {})
        for k, v in st.get("operations", {}).items():
            state_ops[k] = state_ops.get(k, 0) + int(v or 0)
        for op in state_latencies:
            h = st.get("latencies", {}).get(op)
            if isinstance(h, Mapping):
                state_latencies[op].append(h)

        ev = subs.get("events", {})
        for k, v in ev.get("operations", {}).items():
            event_ops[k] = event_ops.get(k, 0) + int(v or 0)
        for op in event_latencies:
            h = ev.get("latencies", {}).get(op)
            if isinstance(h, Mapping):
                event_latencies[op].append(h)

        sse = subs.get("sse", {})
        for k, v in sse.get("operations", {}).items():
            sse_ops[k] = sse_ops.get(k, 0) + int(v or 0)
        sse_h = sse.get("latencies", {}).get("admit")
        if isinstance(sse_h, Mapping):
            sse_latencies.append(sse_h)

        jb = subs.get("jobs", {})
        for k, v in jb.get("operations", {}).items():
            job_ops[k] = job_ops.get(k, 0) + int(v or 0)
        # Queue/active/dlq depths are shared Redis cluster gauges: take latest/max rather than summing per worker
        for k in ("queue_depth", "active_count", "dlq_depth"):
            if k in jb:
                job_depths[k] = max(job_depths.get(k, 0), int(jb.get(k, 0) or 0))
        for op in job_latencies:
            h = jb.get("latencies", {}).get(op)
            if isinstance(h, Mapping):
                job_latencies[op].append(h)

    return {
        "available": True,
        "active_workers": len(workers),
        "malformed_snapshots": malformed,
        "workers": [w.get("worker", {}) for w in workers],
        "aggregated": {
            "state": {
                "operations": state_ops,
                "latencies": {op: aggregate_latency_histograms(hs) for op, hs in state_latencies.items()},
            },
            "events": {
                "operations": event_ops,
                "latencies": {op: aggregate_latency_histograms(hs) for op, hs in event_latencies.items()},
            },
            "sse": {
                "operations": sse_ops,
                "latencies": {"admit": aggregate_latency_histograms(sse_latencies)},
            },
            "jobs": {
                "operations": job_ops,
                **job_depths,
                "latencies": {op: aggregate_latency_histograms(hs) for op, hs in job_latencies.items()},
            },
        },
    }
