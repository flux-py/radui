from __future__ import annotations

import asyncio
import subprocess
import time
import uuid

import pytest
import redis

from radui.jobs.redis import RedisJobBackend
from radui.jobs.runtime import JobContext, JobDefinition, JobStatus
from radui.state.backend import RedisStateBackend, StateBackendUnavailableError
from radui.state.runtime import StateRuntime
from radui.transport.events import EventBroker, RedisEventBackend
from radui.transport.governance import RedisSSEGovernance
from tests.chaos_harness import (
    DEFAULT_REDIS_URL,
    DisposableRedisContainer,
    WorkerProcessManager,
    cleanup_prefix,
    live_redis_available,
    poll_until,
)


def _docker_available() -> bool:
    try:
        res = subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3.0)
        return res.returncode == 0
    except Exception:
        return False


@pytest.mark.skipif(not _docker_available(), reason="NOT EXECUTED: Docker daemon unavailable")
def test_final_redis_job_operation_failures():
    container = DisposableRedisContainer()
    redis_url = container.start()
    ns = f"final:jbfail:{uuid.uuid4().hex[:8]}:"
    try:
        rt = StateRuntime("final-jb")
        ctx = rt.context(session_id="s-jb")
        jb = RedisJobBackend(redis_url, prefix=ns, lease_ttl_seconds=2, max_retries=1, worker_id="w-1")

        # 1. Interrupt Redis during job enqueue -> must fail loudly, not return false success
        container.stop()
        async def noop_handler(jctx: JobContext) -> str:
            return "ok"
        defn_noop = JobDefinition(name="noop", handler=noop_handler, backend=jb)
        with pytest.raises(Exception):
            asyncio.run(jb.submit(defn_noop, ctx, (), {}))

        container.restart()
        jb.reconnect()

        # 2. Interrupt Redis during job completion (inside running handler)
        async def stop_during_complete(jctx: JobContext) -> str:
            container.stop()
            return "done"

        defn_comp = JobDefinition(name="comp", handler=stop_during_complete, backend=jb)
        snap_comp = asyncio.run(jb.submit(defn_comp, ctx, (), {}))
        with pytest.raises(Exception):
            asyncio.run(jb.process_once({"comp": defn_comp}, rt))

        container.restart()
        jb.reconnect()
        # Job must NOT be marked SUCCEEDED and must still be recoverable from active set after lease expiry
        assert jb.get_snapshot(snap_comp.id, "s-jb").status == JobStatus.RUNNING
        r = redis.from_url(redis_url, decode_responses=True)
        poll_until(lambda: r.exists(f"{ns}lock:{snap_comp.id}") == 0, timeout=6.0, interval=0.2, description="lock expiry")
        jb2 = RedisJobBackend(redis_url, prefix=ns, lease_ttl_seconds=5, max_retries=1, worker_id="w-2")
        assert jb2.recover_stale_jobs() == 1
        assert asyncio.run(jb2.process_once({"comp": defn_noop}, rt)) is True
        assert jb2.get_snapshot(snap_comp.id, "s-jb").status == JobStatus.SUCCEEDED

        # 3. Interrupt Redis during retry/DLQ transition (failing handler stops Redis before retry write)
        async def stop_during_fail(jctx: JobContext) -> None:
            container.stop()
            raise RuntimeError("handler boom")

        defn_fail = JobDefinition(name="fail", handler=stop_during_fail, backend=jb2)
        snap_fail = asyncio.run(jb2.submit(defn_fail, ctx, (), {}))
        with pytest.raises(Exception):
            asyncio.run(jb2.process_once({"fail": defn_fail}, rt))

        container.restart()
        jb2.reconnect()
        r.close()
        r = redis.from_url(redis_url, decode_responses=True)
        poll_until(lambda: r.exists(f"{ns}lock:{snap_fail.id}") == 0, timeout=8.0, interval=0.2, description="fail lock expiry")
        assert jb2.recover_stale_jobs() == 1
        assert jb2.get_snapshot(snap_fail.id, "s-jb").status == JobStatus.QUEUED
        r.close()
    finally:
        container.remove()


@pytest.mark.skipif(not live_redis_available(), reason="NOT EXECUTED: live Redis server unavailable")
def test_final_worker_crash_during_renewal_obs_and_job_exec():
    ns = f"final:crash:{uuid.uuid4().hex[:8]}:"
    obs_prefix = f"{ns}obs:worker:"
    mgr = WorkerProcessManager()
    client = redis.from_url(DEFAULT_REDIS_URL, decode_responses=True)
    try:
        rt = StateRuntime("final-crash")
        ctx = rt.context(session_id="s-crash")
        jb_init = RedisJobBackend(DEFAULT_REDIS_URL, prefix=f"{ns}jb:", client=client, lease_ttl_seconds=2, worker_id="init")

        async def slow_exec(jctx: JobContext) -> str:
            await asyncio.sleep(30.0)
            return "victim-result"

        defn = JobDefinition(name="slow_exec", handler=slow_exec, backend=jb_init)
        snap = asyncio.run(jb_init.submit(defn, ctx, (), {}))

        # Spawn real OS worker that holds SSE + renews leases + publishes obs + executes job, then emits READY inside handler
        worker_code = f"""
import asyncio, redis
from radui.jobs.redis import RedisJobBackend
from radui.jobs.runtime import JobContext, JobDefinition
from radui.observability import WorkerIdentity, WorkerObservabilityPublisher
from radui.state.runtime import StateRuntime
from radui.transport.events import EventBroker
from radui.transport.governance import RedisSSEGovernance

c = redis.from_url("{DEFAULT_REDIS_URL}", decode_responses=True)
gov = RedisSSEGovernance(client=c, prefix="{ns}sse:", worker_id="w-victim", lease_ttl_seconds=2.0)
broker = EventBroker(governance=gov, worker_id="w-victim", max_connections_per_session=1, connect_rate_limit=100)
assert broker.try_acquire_connection("s-crash", "10.0.0.1", connection_id="vc1")[0]
ident = WorkerIdentity.create(worker_id="w-victim", environment="testing", backend_mode="redis")
pub = WorkerObservabilityPublisher(ident, lambda: {{"sse": gov.observability_snapshot()}}, client=c, prefix="{obs_prefix}", ttl_seconds=2.0)
pub.publish_snapshot()

jb = RedisJobBackend("{DEFAULT_REDIS_URL}", prefix="{ns}jb:", client=c, lease_ttl_seconds=2, worker_id="w-victim")
rt = StateRuntime("final-crash")

async def slow_exec(jctx: JobContext) -> str:
    gov.renew_leases()
    pub.publish_snapshot()
    print("READY", flush=True)
    await asyncio.sleep(30.0)
    return "victim-result"

defn = JobDefinition(name="slow_exec", handler=slow_exec, backend=jb)
asyncio.run(jb.process_once({{"slow_exec": defn}}, rt))
"""
        victim = mgr.spawn_python(worker_code, name="crash-victim", ready_timeout=10.0)
        # Kill victim abruptly while it is actively inside slow_exec (mid-job, post-renewal & obs publish)
        mgr.kill_abruptly(victim)

        # Wait for 2s TTL/lease expiration
        poll_until(lambda: client.exists(f"{ns}jb:lock:{snap.id}") == 0, timeout=6.0, interval=0.2, description="job lease expiry")
        poll_until(lambda: client.get(f"{obs_prefix}w-victim") is None, timeout=5.0, interval=0.2, description="obs TTL expiry")

        # Worker B recovers and claims the job
        jb_b = RedisJobBackend(DEFAULT_REDIS_URL, prefix=f"{ns}jb:", client=client, lease_ttl_seconds=10, worker_id="w-survivor")
        assert jb_b.recover_stale_jobs() == 1

        # Simulate stale victim attempting to release/complete after Worker B takes the lock
        assert client.set(f"{ns}jb:lock:{snap.id}", "w-survivor", nx=True, ex=10)
        jb_stale = RedisJobBackend(DEFAULT_REDIS_URL, prefix=f"{ns}jb:", client=client, lease_ttl_seconds=2, worker_id="w-victim")
        assert jb_stale._owns_lease(snap.id) is False
        lua_rel = "if redis.call('get', KEYS[1]) == ARGV[1] then redis.call('del', KEYS[1]); return 1 else return 0 end"
        assert client.eval(lua_rel, 1, f"{ns}jb:lock:{snap.id}", "w-victim") == 0
        assert client.get(f"{ns}jb:lock:{snap.id}") == "w-survivor"
        client.delete(f"{ns}jb:lock:{snap.id}")

        # Complete cleanly on Worker B
        async def fast_exec(jctx: JobContext) -> str:
            return "survivor-result"

        defn_fast = JobDefinition(name="slow_exec", handler=fast_exec, backend=jb_b)
        assert asyncio.run(jb_b.process_once({"slow_exec": defn_fast}, rt)) is True
        final = jb_b.get_snapshot(snap.id, "s-crash")
        assert final.status == JobStatus.SUCCEEDED
        assert final.result_text == "survivor-result"

        # SSE capacity from crashed victim is also reclaimed
        gov_b = RedisSSEGovernance(client=client, prefix=f"{ns}sse:", worker_id="w-survivor", lease_ttl_seconds=10.0)
        broker_b = EventBroker(governance=gov_b, worker_id="w-survivor", max_connections_per_session=1, connect_rate_limit=100)
        assert broker_b.try_acquire_connection("s-crash", "10.0.0.1", connection_id="sb1")[0] is True
        broker_b.close_all()
    finally:
        mgr.cleanup_all()
        client.close()
        cleanup_prefix(ns)


@pytest.mark.skipif(not _docker_available(), reason="NOT EXECUTED: Docker daemon unavailable")
def test_final_existing_sse_connections_and_reconnection_semantics():
    container = DisposableRedisContainer()
    redis_url = container.start()
    try:
        # Establish active SSE connections before outage
        eb = RedisEventBackend(redis_url, prefix="final:sse:", allow_fallback=False, socket_timeout=0.5)
        gov_closed = RedisSSEGovernance(backend=eb, worker_id="w-sse", lease_ttl_seconds=5.0, fail_open=False)
        broker_closed = EventBroker(backend=eb, governance=gov_closed, worker_id="w-sse", max_connections_per_session=2, connect_rate_limit=100)

        assert broker_closed.try_acquire_connection("s1", "10.0.0.1", connection_id="c1")[0] is True
        assert gov_closed.active_count() == 1

        sb = RedisStateBackend(redis_url, prefix="final:st:", allow_fallback=False, socket_timeout=0.5)
        sb.set("session", "s1", "k", "before")

        # Stop Redis mid-stream
        container.stop()

        # 1. Existing SSE connection state & lease renewal during outage
        assert gov_closed.active_count() == 1
        assert gov_closed.renew_leases() == 0
        assert gov_closed.observability_snapshot()["operations"]["renewal_failures"] >= 1

        # 2. New admission fails closed (503) when fail_open=False
        ok_new, _, st_new = broker_closed.try_acquire_connection("s1", "10.0.0.1", connection_id="c2")
        assert ok_new is False and st_new == 503

        # 3. Release during outage cleans local _owned safely without crashing
        broker_closed.release_connection("s1", "10.0.0.1", connection_id="c1")
        assert gov_closed.active_count() == 0

        # 4. fail_open=True falls back to local limits during outage
        gov_open = RedisSSEGovernance(client=None, worker_id="w-open", lease_ttl_seconds=5.0, fail_open=True)
        broker_open = EventBroker(governance=gov_open, worker_id="w-open", max_connections_per_session=1, connect_rate_limit=100)
        assert broker_open.try_acquire_connection("s2", "10.0.0.2", connection_id="o1")[0] is True
        assert broker_open.try_acquire_connection("s2", "10.0.0.2", connection_id="o2")[1:] == ("Too many concurrent SSE connections for session", 429)

        # 5. Readiness probe during outage
        assert sb.ping() is False
        assert eb.ping() is False

        # Restart Redis and test reconnection semantics
        container.restart()

        # Idle backend whose _client was preserved on StateBackend recovers on next operation OR reconnect()
        # Note: eb._client was cleared to None by RedisSSEGovernance error handler, so eb.reconnect() is required
        assert eb.reconnect() is True
        assert eb.ping() is True
        assert sb.reconnect() is True
        assert sb.get("session", "s1", "k") == "before"

        # New SSE admission & renewal succeed after recovery
        assert broker_closed.try_acquire_connection("s1", "10.0.0.1", connection_id="c3")[0] is True
        assert gov_closed.renew_leases() == 1
        broker_closed.close_all()
    finally:
        container.remove()


@pytest.mark.skipif(not _docker_available(), reason="NOT EXECUTED: Docker daemon unavailable")
def test_closure_application_event_recovery_behavior():
    from starlette.testclient import TestClient
    import radui as gx
    from radui.core.config import RadUIConfig

    container = DisposableRedisContainer()
    redis_url = container.start()
    try:
        cfg = RadUIConfig(
            environment="testing",
            backend="redis",
            redis_url=redis_url,
            session_secret="r" * 32,
        )
        app = gx.App("EventRecoveryApp", config=cfg)
        app.page("/")(lambda: gx.text("ok"))

        with TestClient(app.asgi()) as client:
            assert client.get("/ready").status_code == 200

            # Start an active SSE subscriber stream in-process
            delivered: list[str] = []

            async def _test_stream():
                it = app.events.stream("sess-rec", keepalive_seconds=0.3)
                t_read = asyncio.create_task(anext(it))
                await asyncio.sleep(0.1)
                app.events.publish("sess-rec", "ui.patch", {"step": 1})
                frame1 = await asyncio.wait_for(t_read, timeout=2.0)
                delivered.append(frame1)
                assert '"step":1' in frame1

                # Interrupt Redis while subscriber is active
                container.stop()
                # Wait briefly so subscribe_remote _reader thread hits socket error and exits
                await asyncio.sleep(0.6)

                # /ready automatically detects Redis outage -> 503 (liveness /health stays 200)
                assert client.get("/health").status_code == 200
                assert client.get("/ready").status_code == 503
                # Existing ping() returns False during outage
                assert app.events.backend.ping() is False

                # Restart Redis and let /ready probe restore cleared backend clients
                container.restart()
                await asyncio.sleep(0.6)
                assert client.get("/ready").status_code == 200

                # Existing SSE stream recovers via keepalive replay reconciliation and delivers step 2!
                app.events.publish("sess-rec", "ui.patch", {"step": 2})
                frame2 = await asyncio.wait_for(anext(it), timeout=2.0)
                delivered.append(frame2)
                assert '"step":2' in frame2
                await it.aclose()

            asyncio.run(_test_stream())
            assert len(delivered) == 2

            # Now test when governance failure sets backend._client = None (e.g. failed try_acquire during outage)
            container.stop()
            ok, _, status = app.events.try_acquire_connection("sess-rec", "10.0.0.9")
            assert ok is False and status == 503
            assert app.events.backend._client is None
            assert client.get("/ready").status_code == 503

            container.restart()
            time.sleep(0.6)  # wait past 0.5s reconnect cooldown
            # /ready automatically restores cleared _client=None on both state and event backends -> 200
            assert client.get("/ready").status_code == 200
            assert app.events.backend.ping() is True
            assert app.state_runtime.backend.ping() is True
            # Publish and SSE admission both succeed without worker restart
            ev3 = app.events.publish("sess-rec", "ui.patch", {"step": 3})
            assert ev3.sequence >= 3
            ok_rec, _, st_rec = app.events.try_acquire_connection("sess-rec", "10.0.0.9", connection_id="rec-1")
            assert ok_rec is True and st_rec == 200
            app.events.release_connection("sess-rec", "10.0.0.9", connection_id="rec-1")
    finally:
        container.remove()


@pytest.mark.skipif(not _docker_available(), reason="NOT EXECUTED: Docker daemon unavailable")
def test_final_automatic_redis_readiness_and_user_checks():
    from starlette.testclient import TestClient
    import radui as gx
    from radui.core.config import RadUIConfig

    container = DisposableRedisContainer()
    redis_url = container.start()
    try:
        user_ready = [True]
        cfg = RadUIConfig(
            environment="testing",
            backend="redis",
            redis_url=redis_url,
            session_secret="a" * 32,
        )
        app = gx.App("AutoReadyApp", config=cfg)
        app.add_readiness_check(lambda: user_ready[0])
        app.page("/")(lambda: gx.text("ok"))

        # Repeated asgi() calls do not duplicate the default Redis readiness check
        app.asgi()
        app.asgi()
        assert app._readiness_checks.count(app._default_redis_readiness_check) == 1

        with TestClient(app.asgi()) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/ready").status_code == 200

            # User-defined readiness check remains functional
            user_ready[0] = False
            assert client.get("/ready").status_code == 503
            user_ready[0] = True
            assert client.get("/ready").status_code == 200

            # Stop Redis -> /health remains 200, /ready returns 503
            container.stop()
            assert client.get("/health").status_code == 200
            assert client.get("/ready").status_code == 503

            # Restart Redis -> /ready recovers to 200 and state/events resume
            t_rec = time.perf_counter()
            container.restart()
            time.sleep(0.6)
            assert client.get("/ready").status_code == 200
            rec_ms = round((time.perf_counter() - t_rec) * 1000.0, 2)

            app.state_runtime.backend.set("session", "s-ready", "k", "alive")
            assert app.state_runtime.backend.get("session", "s-ready", "k") == "alive"
            ev = app.events.publish("s-ready", "ui.patch", {"ok": True})
            assert ev.sequence == 1
            print(f"READINESS_RECOVERY_MS={rec_ms}")
    finally:
        container.remove()
