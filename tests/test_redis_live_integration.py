from __future__ import annotations

import asyncio
import subprocess
import sys
import time
import uuid

import pytest
import redis

import radui as gx
from radui.jobs.redis import JobBackendUnavailableError, RedisJobBackend
from radui.jobs.runtime import JobDefinition, JobStatus
from radui.state.backend import RedisStateBackend, StateBackendUnavailableError
from radui.transport.events import EventBroker, RedisEventBackend

REDIS_URL = "redis://127.0.0.1:6379/14"


def _live_redis_available() -> bool:
    try:
        r = redis.from_url(REDIS_URL, socket_connect_timeout=0.5, socket_timeout=0.5)
        return bool(r.ping())
    except Exception:
        return False


LIVE_REDIS = _live_redis_available()
pytestmark = pytest.mark.skipif(not LIVE_REDIS, reason="NOT EXECUTED: live Redis server unavailable")


def _cleanup_prefix(prefix: str) -> None:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    keys = list(r.scan_iter(f"{prefix}*"))
    if keys:
        r.delete(*keys)
    r.close()


def test_live_redis_multiprocess_state_cas_ttl_isolation_and_serialization():
    ns = f"test:st:{uuid.uuid4().hex[:8]}:"
    try:
        # Process A writes session + tenant state with ample TTL so Process B startup cannot race
        code_a = f"""
import radui as gx
from radui.state.backend import RedisStateBackend
sb = RedisStateBackend("{REDIS_URL}", prefix="{ns}", ttl_seconds=30)
rt = gx.StateRuntime("live-app", backend=sb)
ctx = rt.context(session_id="s1", tenant_id="t1")
s_val = gx.state("live.count", 0, scope="session")
t_val = gx.state("live.plan", "free", scope="tenant")
with ctx.activate():
    s_val.value = 101
    t_val.value = "pro"
sb.close()
"""
        subprocess.run([sys.executable, "-c", code_a], check=True)

        # Process B reads Process A's state and verifies tenant/session isolation
        code_b = f"""
import radui as gx
from radui.state.backend import RedisStateBackend
sb = RedisStateBackend("{REDIS_URL}", prefix="{ns}")
rt = gx.StateRuntime("live-app", backend=sb)
ctx = rt.context(session_id="s1", tenant_id="t1")
ctx_other = rt.context(session_id="s1", tenant_id="t2")
s_val = gx.state("live.count", 0, scope="session")
t_val = gx.state("live.plan", "free", scope="tenant")
with ctx.activate():
    assert s_val.value == 101, f"got {{s_val.value}}"
    assert t_val.value == "pro"
with ctx_other.activate():
    assert t_val.value == "free"
sb.close()
"""
        subprocess.run([sys.executable, "-c", code_b], check=True)

        # Real Redis CAS optimistic concurrency + serialization safety (ample TTL)
        sb1 = RedisStateBackend(REDIS_URL, prefix=ns, ttl_seconds=30)
        sb2 = RedisStateBackend(REDIS_URL, prefix=ns, ttl_seconds=30)
        sb1.set("session", "cas", "k", "v1")
        _, ver = sb1.get_versioned("session", "cas", "k")
        assert ver == 1
        assert sb1.compare_and_set("session", "cas", "k", 1, "v2") == (True, 2)
        assert sb2.compare_and_set("session", "cas", "k", 1, "v3") == (False, 2)
        assert sb2.get("session", "cas", "k") == "v2"

        # Serialization error fails safely without corrupting stored value
        with pytest.raises(ValueError):
            sb1.set("session", "cas", "k", float("nan"))
        assert sb1.get("session", "cas", "k") == "v2"

        # Dedicated TTL expiration with deadline-based polling
        sb1.set("session", "ttl", "exp_k", "ephemeral", ttl_seconds=1)
        assert sb1.get("session", "ttl", "exp_k") == "ephemeral"
        deadline = time.monotonic() + 5.0
        expired = False
        while time.monotonic() < deadline:
            if sb1.get("session", "ttl", "exp_k") is None:
                expired = True
                break
            time.sleep(0.1)
        assert expired is True
        sb1.close()
        sb2.close()
    finally:
        _cleanup_prefix(ns)


def test_live_redis_cross_process_pubsub_replay_and_slow_consumer():
    ns = f"test:ev:{uuid.uuid4().hex[:8]}:"
    try:
        eb_sub = RedisEventBackend(REDIS_URL, prefix=ns, history_size=8)
        broker_sub = EventBroker(backend=eb_sub, history_size=8, subscriber_queue_size=2)

        async def run():
            # Two subscribers on the same session receive cross-process event
            s1 = broker_sub.stream("sess-live", last_event_id=None, keepalive_seconds=3.0)
            s2 = broker_sub.stream("sess-live", last_event_id=None, keepalive_seconds=3.0)
            w1 = asyncio.create_task(anext(s1))
            w2 = asyncio.create_task(anext(s2))
            await asyncio.sleep(0.15)

            # Separate OS process publishes event to Redis
            pub_code = f"""
from radui.transport.events import RedisEventBackend
eb = RedisEventBackend("{REDIS_URL}", prefix="{ns}", history_size=8)
eb.append_sync("sess-live", {{"origin": "proc-pub", "n": 1}}, event_type="gx:patch")
eb.close()
"""
            await asyncio.to_thread(subprocess.run, [sys.executable, "-c", pub_code], check=True)

            ev1 = await asyncio.wait_for(w1, timeout=3.0)
            ev2 = await asyncio.wait_for(w2, timeout=3.0)
            assert "proc-pub" in ev1 and "id: 1" in ev1
            assert "proc-pub" in ev2 and "id: 1" in ev2
            await s1.aclose()
            await s2.aclose()

            # Last-Event-ID replay after disconnect
            eb_sub.append_sync("sess-live", {"origin": "replay", "n": 2}, event_type="gx:patch")
            s_replay = broker_sub.stream("sess-live", last_event_id=1, keepalive_seconds=1.0)
            ev_rep = await asyncio.wait_for(anext(s_replay), timeout=2.0)
            assert "id: 2" in ev_rep and "replay" in ev_rep
            await s_replay.aclose()

            # Slow consumer overflow triggers reset
            s_slow = broker_sub.stream("sess-slow", last_event_id=None, keepalive_seconds=2.0)
            w_slow = asyncio.create_task(anext(s_slow))
            await asyncio.sleep(0.05)
            for i in range(5):
                broker_sub.publish("sess-slow", "gx:patch", {"i": i})
            await asyncio.sleep(0.05)
            first = await asyncio.wait_for(w_slow, timeout=2.0)
            if "event: reset" not in first:
                second = await asyncio.wait_for(anext(s_slow), timeout=2.0)
                assert "event: reset" in second
            await s_slow.aclose()

        asyncio.run(run())
        eb_sub.close()
    finally:
        _cleanup_prefix(ns)


def test_live_redis_multiprocess_jobs_atomic_claim_retry_dlq_idempotency_cancel_timeout():
    ns = f"test:jb:{uuid.uuid4().hex[:8]}:"
    try:
        # Process A submits 4 jobs (including idempotent duplicate), Process B executes them
        submit_code = f"""
import asyncio
import radui as gx
from radui.jobs.redis import RedisJobBackend
from radui.jobs.runtime import JobDefinition
from radui.state.backend import RedisStateBackend

async def main():
    jb = RedisJobBackend("{REDIS_URL}", prefix="{ns}", allow_fallback=False, max_retries=1)
    rt = gx.StateRuntime("japp", backend=RedisStateBackend("{REDIS_URL}", prefix="{ns}st:"))
    ctx = rt.context(session_id="s-mp")
    async def noop(jctx): return "ok"
    d = JobDefinition("work", noop, jb)
    j1 = await jb.submit(d, ctx, (), {{}}, idempotency_key="k1")
    j2 = await jb.submit(d, ctx, (), {{}}, idempotency_key="k1")
    assert j1.id == j2.id
    print(j1.id)
    await jb.shutdown()

asyncio.run(main())
"""
        sub_out = subprocess.run([sys.executable, "-c", submit_code], capture_output=True, text=True, check=True)
        job_id = sub_out.stdout.strip().splitlines()[-1]

        # Separate Worker Process B claims and executes the job
        worker_code = f"""
import asyncio
import radui as gx
from radui.jobs.redis import RedisJobBackend
from radui.jobs.runtime import JobDefinition
from radui.state.backend import RedisStateBackend

async def main():
    jb = RedisJobBackend("{REDIS_URL}", prefix="{ns}", allow_fallback=False, max_retries=1)
    rt = gx.StateRuntime("japp", backend=RedisStateBackend("{REDIS_URL}", prefix="{ns}st:"))
    async def work(jctx): return "worker-b-done"
    defs = {{"work": JobDefinition("work", work, jb)}}
    ran = await jb.process_once(defs, rt)
    assert ran is True
    assert jb.get_result("{job_id}", "s-mp") == "worker-b-done"
    assert await jb.process_once(defs, rt) is False
    await jb.shutdown()

asyncio.run(main())
"""
        subprocess.run([sys.executable, "-c", worker_code], check=True)

        # Verify retry -> DLQ, cancellation, and timeout on live Redis
        jb = RedisJobBackend(REDIS_URL, prefix=ns, allow_fallback=False, max_retries=1)
        rt = gx.StateRuntime("japp", backend=RedisStateBackend(REDIS_URL, prefix=f"{ns}st:"))
        ctx = rt.context(session_id="s-mp")

        async def fail_fn(_jctx):
            raise RuntimeError("fail")

        async def slow_fn(_jctx):
            await asyncio.sleep(2.0)
            return "late"

        jb_to = RedisJobBackend(REDIS_URL, prefix=ns, allow_fallback=False, max_retries=1, default_timeout_seconds=0.05)
        defs = {
            "fail": JobDefinition("fail", fail_fn, jb),
            "slow": JobDefinition("slow", slow_fn, jb_to),
        }

        async def run_edge():
            sf = await jb.submit(defs["fail"], ctx, (), {})
            await jb.process_once(defs, rt)
            assert jb.get_snapshot(sf.id, "s-mp").status == JobStatus.QUEUED
            await jb.process_once(defs, rt)
            assert jb.get_snapshot(sf.id, "s-mp").status == JobStatus.FAILED
            assert jb.metrics()["dead_lettered"] >= 1

            sc = await jb.submit(defs["fail"], ctx, (), {})
            assert await jb.cancel(sc.id, "s-mp") is True
            assert jb.get_snapshot(sc.id, "s-mp").status == JobStatus.CANCELLED

            st = await jb_to.submit(defs["slow"], ctx, (), {})
            while await jb_to.process_once(defs, rt):
                pass
            assert jb_to.get_snapshot(st.id, "s-mp").status == JobStatus.FAILED
            await jb_to.shutdown()
            await jb.shutdown()

        asyncio.run(run_edge())
    finally:
        _cleanup_prefix(ns)


def test_live_redis_restart_and_reconnection():
    ns = f"test:rst:{uuid.uuid4().hex[:8]}:"
    try:
        sb = RedisStateBackend(REDIS_URL, prefix=ns, allow_fallback=False)
        sb.set("session", "r1", "k", "before-restart")
        assert sb.ping() is True

        # Restart live Redis container
        subprocess.run(["docker", "restart", "radui-test-redis"], check=True, capture_output=True)
        reconnected = False
        for _ in range(20):
            if sb.reconnect() and sb.ping():
                reconnected = True
                break
            time.sleep(0.2)
        assert reconnected is True
        sb.set("session", "r1", "k2", "after-restart")
        assert sb.get("session", "r1", "k2") == "after-restart"
        sb.close()
    finally:
        _cleanup_prefix(ns)


def test_live_redis_event_replay_race_concurrent_publishing():
    """Verify zero event loss and zero duplicates during historical replay + concurrent publishing."""
    ns = f"test:race:{uuid.uuid4().hex[:8]}:"
    try:
        eb_pub = RedisEventBackend(REDIS_URL, prefix=ns, history_size=64)
        eb_sub = RedisEventBackend(REDIS_URL, prefix=ns, history_size=64)
        broker = EventBroker(backend=eb_sub, history_size=64, subscriber_queue_size=64)

        for i in range(1, 6):
            eb_pub.append_sync("s-race", {"seq": i}, event_type="gx:patch")

        async def run():
            stream = broker.stream("s-race", last_event_id=0, keepalive_seconds=2.0)

            def concurrent_pub():
                time.sleep(0.02)
                for i in range(6, 16):
                    eb_pub.append_sync("s-race", {"seq": i}, event_type="gx:patch")

            pub_task = asyncio.create_task(asyncio.to_thread(concurrent_pub))
            received_ids: list[int] = []
            while len(received_ids) < 15:
                chunk = await asyncio.wait_for(anext(stream), timeout=3.0)
                if chunk.startswith("id: "):
                    eid = int(chunk.splitlines()[0].split(": ", 1)[1])
                    received_ids.append(eid)
            await pub_task
            await stream.aclose()
            assert received_ids == list(range(1, 16))

        asyncio.run(run())
        eb_pub.close()
        eb_sub.close()
    finally:
        _cleanup_prefix(ns)


def test_live_redis_worker_crash_lease_expiry_and_recovery():
    """Kill Worker A mid-job, wait for 1s lease expiry, verify Worker B recovers and executes."""
    ns = f"test:lease:{uuid.uuid4().hex[:8]}:"
    try:
        jb_sub = RedisJobBackend(REDIS_URL, prefix=ns, allow_fallback=False, max_retries=2, lease_ttl_seconds=1)
        rt = gx.StateRuntime("lease-app", backend=RedisStateBackend(REDIS_URL, prefix=f"{ns}st:"))
        ctx = rt.context(session_id="s-lease")

        async def slow_work(_jctx):
            return "recovered-ok"

        defn = JobDefinition("slow_work", slow_work, jb_sub)
        snap = asyncio.run(jb_sub.submit(defn, ctx, (), {}, idempotency_key="lease-idem-1"))

        # Spawn Worker A in a separate OS process that claims the job and sleeps until killed
        crash_code = f"""
import asyncio, time
import radui as gx
from radui.jobs.redis import RedisJobBackend
from radui.jobs.runtime import JobDefinition
from radui.state.backend import RedisStateBackend

async def main():
    jb = RedisJobBackend("{REDIS_URL}", prefix="{ns}", allow_fallback=False, max_retries=2, lease_ttl_seconds=1)
    rt = gx.StateRuntime("lease-app", backend=RedisStateBackend("{REDIS_URL}", prefix="{ns}st:"))
    async def hang(jctx):
        print("CLAIMED", flush=True)
        await asyncio.sleep(30)
    await jb.process_once({{"slow_work": JobDefinition("slow_work", hang, jb)}}, rt)

asyncio.run(main())
"""
        proc = subprocess.Popen([sys.executable, "-c", crash_code], stdout=subprocess.PIPE, text=True)
        line = proc.stdout.readline()  # type: ignore[union-attr]
        assert "CLAIMED" in line
        proc.kill()
        proc.wait(timeout=3)

        # Wait for 1s lease TTL to expire
        time.sleep(1.3)

        # Worker B recovers the orphaned job and completes it
        jb_b = RedisJobBackend(REDIS_URL, prefix=ns, allow_fallback=False, max_retries=2, lease_ttl_seconds=5)
        ran = asyncio.run(jb_b.process_once({"slow_work": defn}, rt))
        assert ran is True
        assert jb_b.get_result(snap.id, "s-lease") == "recovered-ok"

        # Stale Worker A cannot overwrite or release Worker B's lock
        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.set(f"{ns}lock:{snap.id}", jb_b.worker_id, ex=10)
        stale_a = RedisJobBackend(REDIS_URL, prefix=ns, allow_fallback=False)
        assert stale_a._owns_lease(snap.id) is False
        lua = "if redis.call('get', KEYS[1]) == ARGV[1] then redis.call('del', KEYS[1]); return 1 else return 0 end"
        assert r.eval(lua, 1, f"{ns}lock:{snap.id}", stale_a.worker_id) == 0
        assert r.get(f"{ns}lock:{snap.id}") == jb_b.worker_id
        r.close()
        asyncio.run(jb_b.shutdown())
        asyncio.run(jb_sub.shutdown())
    finally:
        _cleanup_prefix(ns)


def test_live_redis_idempotency_fencing_token_zero_and_ownership():
    from radui.core.idempotency import RedisIdempotencyBackend, StaleLeaseError, compute_payload_fingerprint

    ns = f"test:fence:{uuid.uuid4().hex[:8]}:"
    try:
        ib = RedisIdempotencyBackend(REDIS_URL, prefix=ns, allow_fallback=False)
        fp = compute_payload_fingerprint("cmd.test", {"a": 1})
        res = ib.begin("k-zero", fp, ttl=30, owner_id="worker-1")
        t = res.fence_token
        assert t >= 1

        # Token 0 is distinct from None and is rejected as stale when current_fence >= 1
        with pytest.raises(StaleLeaseError):
            ib.renew_lease("k-zero", owner_id="worker-1", fence_token=0, ttl=30)
        with pytest.raises(StaleLeaseError):
            ib.complete("k-zero", {"ok": True}, fence_token=0, owner_id="worker-1")
        with pytest.raises(StaleLeaseError):
            ib.fail("k-zero", "err", fence_token=0, owner_id="worker-1")

        # Mismatched owner cannot renew or complete even with valid token
        with pytest.raises(StaleLeaseError):
            ib.renew_lease("k-zero", owner_id="worker-2", fence_token=t, ttl=30)
        with pytest.raises(StaleLeaseError):
            ib.complete("k-zero", {"ok": True}, fence_token=t, owner_id="worker-2")

        # Valid owner + token succeeds
        ib.complete("k-zero", {"ok": True}, fence_token=t, owner_id="worker-1")
        assert ib.get("k-zero").status == "COMPLETED"
    finally:
        _cleanup_prefix(ns)
