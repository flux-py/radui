from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import json
import time
import uuid

import pytest
import redis

from radui.jobs.redis import RedisJobBackend
from radui.jobs.runtime import JobDefinition, JobStatus
from radui.state.runtime import StateRuntime
from radui.transport.events import EventBroker
from radui.transport.governance import RedisSSEGovernance
from tests.chaos_harness import (
    DEFAULT_REDIS_URL,
    WorkerProcessManager,
    cleanup_prefix,
    live_redis_available,
    poll_until,
)

pytestmark = pytest.mark.skipif(
    not live_redis_available(),
    reason="NOT EXECUTED: live Redis server unavailable",
)


def _storm_admit_and_release_worker(args: tuple[str, str, str, str, int, int, int, int]) -> tuple[int, int, int]:
    redis_url, prefix, session_id, client_ip, max_sess, max_ip, rate_limit, attempts = args
    client = redis.from_url(redis_url, decode_responses=True)
    gov = RedisSSEGovernance(client=client, prefix=prefix, lease_ttl_seconds=30.0)
    broker = EventBroker(
        governance=gov,
        max_connections_per_session=max_sess,
        max_connections_per_ip=max_ip,
        connect_rate_limit=rate_limit,
        connect_rate_window_seconds=30.0,
    )
    admitted = 0
    rejected_limit = 0
    rejected_rate = 0
    for _ in range(attempts):
        ok, reason, status = broker.try_acquire_connection(session_id, client_ip, is_reconnect=True)
        if ok:
            admitted += 1
        elif status == 429 and "rate limit" in (reason or "").lower():
            rejected_rate += 1
        elif status == 429:
            rejected_limit += 1
    client.close()
    return admitted, rejected_limit, rejected_rate


def test_chaos_sse_connection_storm_and_rate_limit_across_processes():
    ns = f"chaos:storm:{uuid.uuid4().hex[:8]}:"
    try:
        # 4 OS processes x 10 attempts = 40 simultaneous attempts; rate_limit=20, max_sess=8, max_ip=12
        tasks = [(DEFAULT_REDIS_URL, ns, "s-storm", "10.10.1.1", 8, 12, 20, 10) for _ in range(4)]
        with ProcessPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(_storm_admit_and_release_worker, tasks))

        total_admitted = sum(r[0] for r in results)
        total_rejected_limit = sum(r[1] for r in results)
        total_rejected_rate = sum(r[2] for r in results)
        assert total_admitted == 8
        assert total_admitted + total_rejected_limit + total_rejected_rate == 40
        assert total_rejected_rate >= 20  # global rate limit enforced across all 4 processes

        # Separate session on same IP can only admit up to max_ip - 8 = 4 more slots (with high rate limit)
        tasks_ip = [(DEFAULT_REDIS_URL, ns, "s-storm-2", "10.10.1.1", 10, 12, 500, 5) for _ in range(2)]
        with ProcessPoolExecutor(max_workers=2) as pool:
            res_ip = list(pool.map(_storm_admit_and_release_worker, tasks_ip))
        assert sum(r[0] for r in res_ip) == 4
    finally:
        cleanup_prefix(ns)


def test_chaos_sse_ownership_isolation_and_repeated_cycles():
    ns = f"chaos:own:{uuid.uuid4().hex[:8]}:"
    client = redis.from_url(DEFAULT_REDIS_URL, decode_responses=True)
    try:
        gov_a = RedisSSEGovernance(client=client, prefix=ns, worker_id="worker-a", lease_ttl_seconds=20.0)
        gov_b = RedisSSEGovernance(client=client, prefix=ns, worker_id="worker-b", lease_ttl_seconds=20.0)
        broker_a = EventBroker(governance=gov_a, worker_id="worker-a", max_connections_per_session=2, connect_rate_limit=1000)
        broker_b = EventBroker(governance=gov_b, worker_id="worker-b", max_connections_per_session=2, connect_rate_limit=1000)

        # Worker A acquires 2/2 slots with explicit connection IDs
        assert broker_a.try_acquire_connection("s-own", "10.20.1.1", connection_id="cid-1")[0] is True
        assert broker_a.try_acquire_connection("s-own", "10.20.1.1", connection_id="cid-2")[0] is True

        # Worker B cannot release Worker A's connection IDs
        assert gov_b.release("s-own", "10.20.1.1", connection_id="cid-1") is True  # Lua runs, removes 0 members
        assert broker_b.try_acquire_connection("s-own", "10.20.1.1")[0] is False

        # Worker B cannot renew Worker A's connections either
        gov_b._owned["cid-1"] = ("s-own", "10.20.1.1")
        assert gov_b.renew_leases() == 0
        gov_b._owned.clear()

        # Worker A releases cid-1 -> Worker B can now acquire 1 slot
        broker_a.release_connection("s-own", "10.20.1.1", connection_id="cid-1")
        assert broker_b.try_acquire_connection("s-own", "10.20.1.1", connection_id="cid-b1")[0] is True

        broker_a.close_all()
        broker_b.close_all()

        # 200 repeated connect/disconnect cycles leave 0 active connections
        for i in range(200):
            cid = f"cycle-{i}"
            assert broker_a.try_acquire_connection("s-cycle", "10.20.2.2", connection_id=cid)[0] is True
            broker_a.release_connection("s-cycle", "10.20.2.2", connection_id=cid)
        assert gov_a.active_count() == 0
        assert client.zcard(f"{ns}session:s-cycle") == 0
        assert client.zcard(f"{ns}worker:worker-a") == 0
    finally:
        client.close()
        cleanup_prefix(ns)


def test_chaos_abrupt_worker_kill_reclaims_sse_and_observability_leases():
    ns = f"chaos:kill:{uuid.uuid4().hex[:8]}:"
    obs_prefix = f"{ns}obs:worker:"
    mgr = WorkerProcessManager()
    client = redis.from_url(DEFAULT_REDIS_URL, decode_responses=True)
    try:
        # Spawn Worker A holding 2/2 SSE slots + observability snapshot with 3s TTL, then block
        worker_code = f"""
import time, redis
from radui.observability import WorkerIdentity, WorkerObservabilityPublisher
from radui.transport.events import EventBroker
from radui.transport.governance import RedisSSEGovernance

c = redis.from_url("{DEFAULT_REDIS_URL}", decode_responses=True)
gov = RedisSSEGovernance(client=c, prefix="{ns}sse:", worker_id="worker-victim", lease_ttl_seconds=3.0)
b = EventBroker(governance=gov, worker_id="worker-victim", max_connections_per_session=2, connect_rate_limit=100)
assert b.try_acquire_connection("s-kill", "10.30.1.1", connection_id="v1")[0]
assert b.try_acquire_connection("s-kill", "10.30.1.1", connection_id="v2")[0]
ident = WorkerIdentity.create(worker_id="worker-victim", environment="testing", backend_mode="redis")
pub = WorkerObservabilityPublisher(ident, lambda: {{"sse": gov.observability_snapshot()}}, client=c, prefix="{obs_prefix}", ttl_seconds=3.0)
assert pub.publish_snapshot()
print("READY", flush=True)
while True:
    time.sleep(0.5)
"""
        victim = mgr.spawn_python(worker_code, name="victim-worker")

        # Worker B keeps its own sustained connection alive via renewal while victim is killed
        gov_b = RedisSSEGovernance(client=client, prefix=f"{ns}sse:", worker_id="worker-survivor", lease_ttl_seconds=3.0)
        broker_b = EventBroker(governance=gov_b, worker_id="worker-survivor", max_connections_per_session=3, connect_rate_limit=100)
        assert broker_b.try_acquire_connection("s-kill", "10.30.1.1", connection_id="surv-1")[0] is True
        # Now 3/3 slots are taken; next admission must fail
        assert broker_b.try_acquire_connection("s-kill", "10.30.1.1")[0] is False

        # Abruptly kill victim without running shutdown hooks
        mgr.kill_abruptly(victim)

        # Keep survivor alive across victim's lease expiration
        def _reclaimed_and_renewed() -> bool:
            gov_b.renew_leases()
            ok, _, _ = broker_b.try_acquire_connection("s-kill", "10.30.1.1", connection_id="reclaimed-1")
            if ok:
                return True
            return False

        poll_until(_reclaimed_and_renewed, timeout=8.0, interval=0.3, description="victim SSE lease expiration")
        # Victim's observability snapshot also expired cleanly
        poll_until(
            lambda: client.get(f"{obs_prefix}worker-victim") is None,
            timeout=5.0,
            interval=0.2,
            description="victim observability TTL expiration",
        )
        # Survivor's renewed connection is still active, plus reclaimed-1 = 2/3, 3rd succeeds, 4th fails
        assert broker_b.try_acquire_connection("s-kill", "10.30.1.1", connection_id="reclaimed-2")[0] is True
        assert broker_b.try_acquire_connection("s-kill", "10.30.1.1")[0] is False

        broker_b.close_all()
        assert client.zcard(f"{ns}sse:session:s-kill") == 0
    finally:
        mgr.cleanup_all()
        client.close()
        cleanup_prefix(ns)


def test_chaos_worker_killed_during_job_recovery_and_restart():
    ns = f"chaos:jobkill:{uuid.uuid4().hex[:8]}:"
    mgr = WorkerProcessManager()
    client = redis.from_url(DEFAULT_REDIS_URL, decode_responses=True)
    try:
        # Enqueue job with 2s lease TTL
        jb_init = RedisJobBackend(DEFAULT_REDIS_URL, prefix=ns, client=client, lease_ttl_seconds=2, worker_id="init-w")

        async def slow_job(ctx: JobContext, val: int) -> int:
            return val * 2

        defn = JobDefinition(name="slow_job", handler=slow_job, backend=jb_init)
        rt_init = StateRuntime("chaos-app")
        import asyncio
        snap = asyncio.run(jb_init.submit(defn, rt_init.context(session_id="s-job"), (21,), {}))

        # Worker A claims lock + marks job running + adds to active set, then gets killed abruptly
        victim_code = f"""
import time, redis
from radui.jobs.redis import RedisJobBackend
from radui.jobs.runtime import JobStatus
c = redis.from_url("{DEFAULT_REDIS_URL}", decode_responses=True)
jb = RedisJobBackend("{DEFAULT_REDIS_URL}", prefix="{ns}", client=c, lease_ttl_seconds=2, worker_id="job-victim")
assert c.set("{ns}lock:{snap.id}", "job-victim", nx=True, ex=2)
c.sadd("{ns}active", "{snap.id}")
rec = jb._load_job("{snap.id}")
rec["status"] = JobStatus.RUNNING.value
rec["attempt"] = 1
jb._save_job(rec)
print("READY", flush=True)
while True:
    time.sleep(0.5)
"""
        victim = mgr.spawn_python(victim_code, name="job-victim")
        mgr.kill_abruptly(victim)

        # Restarted worker with new worker_id waits for 2s lease expiration and recovers orphaned job
        jb_new = RedisJobBackend(DEFAULT_REDIS_URL, prefix=ns, client=client, lease_ttl_seconds=10, worker_id="job-restarted")
        poll_until(
            lambda: client.exists(f"{ns}lock:{snap.id}") == 0,
            timeout=6.0,
            interval=0.2,
            description="orphaned job lock expiration",
        )
        recovered = jb_new.recover_stale_jobs()
        assert recovered == 1

        import asyncio
        executed = asyncio.run(jb_new.process_once({"slow_job": defn}, rt_init))
        assert executed is True
        final = jb_new.get_snapshot(snap.id, "s-job")
        assert final.status == JobStatus.SUCCEEDED
        assert jb_new.observability_snapshot()["operations"]["stale_recovered"] == 1
    finally:
        mgr.cleanup_all()
        client.close()
        cleanup_prefix(ns)
