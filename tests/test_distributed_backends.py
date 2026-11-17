from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest
from starlette.testclient import TestClient

import radui as gx
from radui.core.auth import User
from radui.core.config import ConfigurationError, RadUIConfig
from radui.jobs.redis import JobBackendUnavailableError, RedisJobBackend
from radui.jobs.runtime import JobDefinition, JobStatus
from radui.state.backend import RedisStateBackend, SQLiteStateBackend, StateBackendUnavailableError
from radui.transport.events import EventBroker, RedisEventBackend, SQLiteEventBackend


def _check_live_redis() -> bool:
    try:
        import redis
        r = redis.from_url("redis://127.0.0.1:6379/0", socket_connect_timeout=0.2, socket_timeout=0.2)
        return bool(r.ping())
    except Exception:
        return False


LIVE_REDIS_AVAILABLE = _check_live_redis()


class _FakeRedisPubSub:
    def __init__(self, server: "_FakeRedisServer") -> None:
        self.server = server
        self.channels: set[str] = set()
        self.messages: list[dict[str, str]] = []
        self._lock = threading.Lock()

    def subscribe(self, channel: str) -> None:
        with self.server._lock:
            self.channels.add(channel)
            self.server._pubsubs.setdefault(channel, []).append(self)

    def unsubscribe(self, channel: str) -> None:
        with self.server._lock:
            self.channels.discard(channel)
            subs = self.server._pubsubs.get(channel, [])
            if self in subs:
                subs.remove(self)

    def get_message(self, timeout: float = 0.1) -> dict[str, str] | None:
        with self._lock:
            if self.messages:
                return self.messages.pop(0)
        return None

    def close(self) -> None:
        for ch in list(self.channels):
            self.unsubscribe(ch)


class _FakeRedisPipeline:
    def __init__(self, server: "_FakeRedisServer") -> None:
        self.server = server
        self.ops: list[tuple[str, tuple[Any, ...]]] = []
        self._watching = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def watch(self, key: str) -> None:
        self._watching = True

    def unwatch(self) -> None:
        self._watching = False

    def multi(self) -> None:
        pass

    def hget(self, hkey: str, field: str) -> str | None:
        return self.server.hget(hkey, field)

    def hset(self, hkey: str, field: str, val: str) -> None:
        self.ops.append(("hset", (hkey, field, val)))

    def expire(self, key: str, ttl: int) -> None:
        self.ops.append(("expire", (key, ttl)))

    def zadd(self, key: str, mapping: dict[str, int]) -> None:
        self.ops.append(("zadd", (key, mapping)))

    def zremrangebyrank(self, key: str, start: int, stop: int) -> None:
        self.ops.append(("zremrangebyrank", (key, start, stop)))

    def publish(self, channel: str, msg: str) -> None:
        self.ops.append(("publish", (channel, msg)))

    def delete(self, key: str) -> None:
        self.ops.append(("delete", (key,)))

    def execute(self) -> list[Any]:
        results = []
        for op, args in self.ops:
            results.append(getattr(self.server, op)(*args))
        self.ops.clear()
        return results


class _FakeRedisServer:
    """In-memory RESP-subset simulator for deterministic multi-client Redis contract tests."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.kv: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.lists: dict[str, list[str]] = {}
        self.sets: dict[str, set[str]] = {}
        self.zsets: dict[str, list[tuple[int, str]]] = {}
        self.ttls: dict[str, int] = {}
        self._pubsubs: dict[str, list[_FakeRedisPubSub]] = {}

    def ping(self) -> bool:
        return True

    def pipeline(self) -> _FakeRedisPipeline:
        return _FakeRedisPipeline(self)

    def pubsub(self, ignore_subscribe_messages: bool = True) -> _FakeRedisPubSub:
        return _FakeRedisPubSub(self)

    def get(self, key: str) -> str | None:
        with self._lock:
            return self.kv.get(key)

    def set(self, key: str, val: str, *, nx: bool = False, ex: int | None = None) -> bool:
        with self._lock:
            if nx and key in self.kv:
                return False
            self.kv[key] = val
            if ex is not None:
                self.ttls[key] = ex
            return True

    def incr(self, key: str) -> int:
        with self._lock:
            val = int(self.kv.get(key, "0")) + 1
            self.kv[key] = str(val)
            return val

    def delete(self, key: str) -> int:
        with self._lock:
            removed = 0
            if key in self.kv:
                del self.kv[key]
                removed += 1
            if key in self.hashes:
                del self.hashes[key]
                removed += 1
            return removed

    def hget(self, hkey: str, field: str) -> str | None:
        with self._lock:
            return self.hashes.get(hkey, {}).get(field)

    def hset(self, hkey: str, field: str, val: str) -> int:
        with self._lock:
            self.hashes.setdefault(hkey, {})[field] = val
            return 1

    def hdel(self, hkey: str, field: str) -> int:
        with self._lock:
            return 1 if self.hashes.get(hkey, {}).pop(field, None) is not None else 0

    def hgetall(self, hkey: str) -> dict[str, str]:
        with self._lock:
            return dict(self.hashes.get(hkey, {}))

    def expire(self, key: str, ttl: int) -> bool:
        with self._lock:
            self.ttls[key] = ttl
            return True

    def lpush(self, key: str, val: str) -> int:
        with self._lock:
            lst = self.lists.setdefault(key, [])
            lst.insert(0, val)
            return len(lst)

    def rpush(self, key: str, val: str) -> int:
        with self._lock:
            lst = self.lists.setdefault(key, [])
            lst.append(val)
            return len(lst)

    def rpop(self, key: str) -> str | None:
        with self._lock:
            lst = self.lists.get(key, [])
            return lst.pop() if lst else None

    def llen(self, key: str) -> int:
        with self._lock:
            return len(self.lists.get(key, []))

    def zadd(self, key: str, mapping: dict[str, int]) -> int:
        with self._lock:
            z = self.zsets.setdefault(key, [])
            for member, score in mapping.items():
                z.append((int(score), member))
            z.sort(key=lambda x: x[0])
            return len(mapping)

    def zremrangebyrank(self, key: str, start: int, stop: int) -> int:
        with self._lock:
            z = self.zsets.get(key, [])
            n = len(z)
            if n == 0:
                return 0
            s = start if start >= 0 else max(0, n + start)
            e = stop if stop >= 0 else n + stop
            if e >= s:
                del z[s : e + 1]
            return n - len(z)

    def zrangebyscore(self, key: str, min_s: str, max_s: str, start: int = 0, num: int = 128) -> list[str]:
        with self._lock:
            z = self.zsets.get(key, [])
            exclusive = isinstance(min_s, str) and min_s.startswith("(")
            thresh = int(min_s[1:]) if exclusive else int(min_s)
            filtered = [m for sc, m in z if (sc > thresh if exclusive else sc >= thresh)]
            return filtered[start : start + num]

    def publish(self, channel: str, msg: str) -> int:
        with self._lock:
            subs = list(self._pubsubs.get(channel, []))
        for sub in subs:
            with sub._lock:
                sub.messages.append({"type": "message", "data": msg})
        return len(subs)

    def eval(self, _script: str, numkeys: int, *args: str) -> int:
        key = args[0]
        expected = args[numkeys]
        with self._lock:
            if self.kv.get(key) == expected:
                del self.kv[key]
                return 1
            return 0

    def sadd(self, key: str, member: str) -> int:
        with self._lock:
            s = self.sets.setdefault(key, set())
            before = len(s)
            s.add(member)
            return len(s) - before

    def srem(self, key: str, member: str) -> int:
        with self._lock:
            s = self.sets.get(key, set())
            if member in s:
                s.remove(member)
                return 1
            return 0

    def smembers(self, key: str) -> set[str]:
        with self._lock:
            return set(self.sets.get(key, set()))

    def exists(self, key: str) -> int:
        with self._lock:
            return 1 if (key in self.kv or key in self.hashes or key in self.lists or key in self.sets) else 0


def test_cross_process_state_and_event_coordination_via_sqlite_wal(tmp_path: Path):
    """Verify genuine multi-OS-process state visibility and event replay via shared SQLite WAL."""
    db_path = tmp_path / "shared_cluster.db"
    s_count = gx.state("cluster.counter", 0, scope="session")
    s_tenant = gx.state("tenant.flag", "init", scope="tenant")

    # Worker Process A writes state and publishes an event
    worker_a_code = f"""
import radui as gx
from radui.state.backend import SQLiteStateBackend
from radui.transport.events import SQLiteEventBackend, EventBroker

sb = SQLiteStateBackend(r"{db_path}")
eb = SQLiteEventBackend(r"{db_path}")
rt = gx.StateRuntime("cluster-app", backend=sb)
ctx = rt.context(session_id="sess-shared", tenant_id="acme")
s_count = gx.state("cluster.counter", 0, scope="session")
s_tenant = gx.state("tenant.flag", "init", scope="tenant")
with ctx.activate():
    s_count.value = 42
    s_tenant.value = "enabled"
broker = EventBroker(backend=eb)
broker.publish("sess-shared", "gx:patch", {{"from": "worker-a"}})
sb.close()
"""
    proc_a = subprocess.run([sys.executable, "-c", worker_a_code], capture_output=True, text=True, check=True)
    assert proc_a.returncode == 0

    # Worker Process B (separate OS process) reads Worker A's state and replays Worker A's event
    worker_b_code = f"""
import asyncio
import radui as gx
from radui.state.backend import SQLiteStateBackend
from radui.transport.events import SQLiteEventBackend, EventBroker

sb = SQLiteStateBackend(r"{db_path}")
eb = SQLiteEventBackend(r"{db_path}")
rt = gx.StateRuntime("cluster-app", backend=sb)
ctx = rt.context(session_id="sess-shared", tenant_id="acme")
ctx_other = rt.context(session_id="sess-shared", tenant_id="other-tenant")
s_count = gx.state("cluster.counter", 0, scope="session")
s_tenant = gx.state("tenant.flag", "init", scope="tenant")
with ctx.activate():
    assert s_count.value == 42, f"expected 42, got {{s_count.value}}"
    assert s_tenant.value == "enabled"
with ctx_other.activate():
    assert s_tenant.value == "init"

async def check_event():
    broker = EventBroker(backend=eb)
    stream = broker.stream("sess-shared", last_event_id=0)
    ev = await anext(stream)
    await stream.aclose()
    assert '"from":"worker-a"' in ev, ev

asyncio.run(check_event())
sb.close()
print("CROSS_PROCESS_OK")
"""
    proc_b = subprocess.run([sys.executable, "-c", worker_b_code], capture_output=True, text=True, check=True)
    assert "CROSS_PROCESS_OK" in proc_b.stdout


def test_redis_state_cas_ttl_serialization_and_outage():
    srv = _FakeRedisServer()
    w1 = RedisStateBackend("redis://user:secretpass@127.0.0.1:6379/0", ttl_seconds=120, client=srv)
    w2 = RedisStateBackend("redis://user:secretpass@127.0.0.1:6379/0", ttl_seconds=120, client=srv)

    w1.set("session", "s1", "theme", "dark")
    assert w2.get("session", "s1", "theme") == "dark"
    assert srv.ttls["gx:state:session:s1"] == 120

    # Optimistic concurrency CAS
    val, ver = w1.get_versioned("session", "s1", "theme")
    assert (val, ver) == ("dark", 1)
    ok1, ver2 = w1.compare_and_set("session", "s1", "theme", 1, "light")
    assert (ok1, ver2) == (True, 2)
    # Stale version from w2 must conflict
    ok2, cur_ver = w2.compare_and_set("session", "s1", "theme", 1, "blue")
    assert (ok2, cur_ver) == (False, 2)
    assert w2.metrics()["cas_conflicts"] == 1

    # Strict JSON rejects NaN
    with pytest.raises(ValueError):
        w1.set("session", "s1", "bad", float("nan"))

    # Outage with allow_fallback=False fails closed
    down = RedisStateBackend("redis://127.0.0.1:6399/0", allow_fallback=False, socket_timeout=0.05)
    assert down.ping() is False
    with pytest.raises(StateBackendUnavailableError):
        down.get("session", "s1", "theme")


def test_redis_event_pubsub_cross_worker_and_replay():
    srv = _FakeRedisServer()
    eb1 = RedisEventBackend("redis://127.0.0.1:6379/0", history_size=4, client=srv)
    eb2 = RedisEventBackend("redis://127.0.0.1:6379/0", history_size=4, client=srv)

    broker1 = EventBroker(backend=eb1, history_size=4)
    broker2 = EventBroker(backend=eb2, history_size=4)

    async def run():
        stream2 = broker2.stream("s-cross", last_event_id=None, keepalive_seconds=2.0)
        waiter = asyncio.create_task(anext(stream2))
        await asyncio.sleep(0.05)
        broker1.publish("s-cross", "gx:patch", {"msg": "hello-from-w1"})
        ev = await asyncio.wait_for(waiter, timeout=2.0)
        await stream2.aclose()
        assert "hello-from-w1" in ev

    asyncio.run(run())
    assert broker1.metrics()["events_published"] == 1
    assert broker2.metrics()["events_delivered"] == 1


def test_redis_job_queue_locking_retries_dlq_idempotency_and_outage():
    srv = _FakeRedisServer()
    j1 = RedisJobBackend("redis://127.0.0.1:6379/0", max_retries=1, client=srv)
    j2 = RedisJobBackend("redis://127.0.0.1:6379/0", max_retries=1, client=srv)

    rt = gx.StateRuntime("job-app", backend=RedisStateBackend(client=srv))
    ctx = rt.context(session_id="s-job")

    executed: list[str] = []

    async def ok_job(_job_ctx, label: str):
        executed.append(label)
        return f"done:{label}"

    async def fail_job(_job_ctx):
        raise RuntimeError("transient-err")

    defs = {
        "ok": JobDefinition("ok", ok_job, j1),
        "fail": JobDefinition("fail", fail_job, j1),
    }

    async def run():
        # Idempotency deduplicates duplicate submission
        s1 = await j1.submit(defs["ok"], ctx, ("alpha",), {}, idempotency_key="idem-1")
        s2 = await j1.submit(defs["ok"], ctx, ("alpha",), {}, idempotency_key="idem-1")
        assert s1.id == s2.id

        # Worker 2 pops and executes; Worker 1 finds queue empty (no duplicate execution)
        assert await j2.process_once(defs, rt) is True
        assert await j1.process_once(defs, rt) is False
        assert executed == ["alpha"]
        assert j1.get_result(s1.id, "s-job") == "done:alpha"

        # Retry + Dead-Letter Queue (max_retries=1 -> 1 initial + 1 retry -> DLQ)
        sf = await j1.submit(defs["fail"], ctx, (), {})
        await j2.process_once(defs, rt)  # attempt 1 -> requeued
        assert j2.get_snapshot(sf.id, "s-job").status == JobStatus.QUEUED
        await j2.process_once(defs, rt)  # attempt 2 -> DLQ
        assert j2.get_snapshot(sf.id, "s-job").status == JobStatus.FAILED
        assert j2.metrics()["dead_lettered"] == 1
        assert j2.metrics()["retried"] == 1

    asyncio.run(run())

    # Outage with allow_fallback=False raises JobBackendUnavailableError
    down_jobs = RedisJobBackend("redis://127.0.0.1:6399/0", allow_fallback=False, socket_timeout=0.05)
    with pytest.raises(JobBackendUnavailableError):
        asyncio.run(down_jobs.startup())


def test_backend_config_validation_and_inspect_backends_rbac():
    with pytest.raises(ConfigurationError, match="RADUI_REDIS_URL"):
        RadUIConfig.from_env({"RADUI_BACKEND": "redis"})

    current_user: list[User | None] = [None]
    app = gx.App(
        "Backends Inspect",
        session_secret="super-secret-key-at-least-32-chars-long!",
        user_resolver=lambda _req: current_user[0],
    )
    app.page("/")(lambda: gx.text("ok"))

    with TestClient(app.asgi()) as client:
        assert client.get("/_gx/inspect/backends").status_code == 401
        client.get("/")
        current_user[0] = User(id="u1", username="alice", roles=("viewer",))
        assert client.get("/_gx/inspect/backends").status_code == 403
        current_user[0] = User(id="adm", username="root", roles=("admin",))
        r = client.get("/_gx/inspect/backends")
        assert r.status_code == 200
        assert r.json()["backends"]["state"]["type"] == "InMemoryStateBackend"


@pytest.mark.skipif(not LIVE_REDIS_AVAILABLE, reason="NOT EXECUTED: live Redis server unavailable")
def test_live_redis_integration():
    rb = RedisStateBackend("redis://127.0.0.1:6379/0", allow_fallback=False)
    rb.set("session", "live-s1", "k", "v")
    assert rb.get("session", "live-s1", "k") == "v"
    rb.delete("session", "live-s1")
    rb.close()
