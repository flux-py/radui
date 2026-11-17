from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
import time
import tracemalloc
import uuid

import pytest
import redis
from starlette.testclient import TestClient

import radui as gx
from radui.core.auth import User
from radui.core.config import RadUIConfig
from radui.jobs.redis import RedisJobBackend
from radui.jobs.runtime import JobContext, JobDefinition
from radui.observability import MAX_SNAPSHOT_BYTES, WorkerIdentity, WorkerObservabilityPublisher
from radui.state.backend import RedisStateBackend
from radui.state.runtime import StateRuntime
from radui.transport.events import EventBroker, RedisEventBackend
from radui.transport.governance import RedisSSEGovernance
from tests.chaos_harness import (
    DEFAULT_REDIS_URL,
    cleanup_prefix,
    live_redis_available,
    snapshot_redis_resources,
    summarize_latencies,
)


def test_security_and_resource_exhaustion_bounds():
    inspector = User(id="insp", username="insp", roles=("inspector",))
    viewer = User(id="v1", username="viewer", roles=("viewer",))
    current_user: list[User | None] = [None]
    app = gx.App(
        "SecExhaust",
        config=RadUIConfig(environment="testing", session_secret="s" * 32),
        user_resolver=lambda _r: current_user[0],
    )

    @app.page("/")
    def index():
        return gx.text("ok")

    with TestClient(app.asgi()) as client:
        # 1. Malformed session cookie on /_gx/events -> 401
        r_bad_sess = client.get("/_gx/events", cookies={"radui_session": "tampered.bad-sig"})
        assert r_bad_sess.status_code == 401

        # 2. Valid session, invalid Last-Event-ID -> 400
        client.get("/")
        assert client.get("/_gx/events", headers={"last-event-id": "-5"}).status_code == 400
        assert client.get("/_gx/events", headers={"last-event-id": "not-an-int"}).status_code == 400

        # 3. Unauthorized diagnostics -> 401 then 403
        assert client.get("/_gx/inspect/runtime").status_code == 401
        current_user[0] = viewer
        assert client.get("/_gx/inspect/runtime").status_code == 403
        assert client.get("/_gx/inspect/jobs").status_code == 403

        # 4. Oversized pagination bounded to 100
        current_user[0] = inspector
        r_pg = client.get("/_gx/inspect/jobs?limit=999999&offset=0")
        assert r_pg.status_code == 200
        assert r_pg.json()["pagination"]["limit"] == 100

    # 5. Telemetry snapshot exceeding MAX_SNAPSHOT_BYTES is dropped cleanly
    pub = WorkerObservabilityPublisher(
        WorkerIdentity.create(worker_id="w-big"),
        lambda: {"oversized": "A" * (MAX_SNAPSHOT_BYTES + 512)},
        client=object(),
        prefix="test:sec:big:",
    )
    assert pub.publish_snapshot() is False
    assert pub.publish_errors == 1


@pytest.mark.skipif(not live_redis_available(), reason="NOT EXECUTED: live Redis server unavailable")
def test_sustained_load_and_resource_leak_measurements():
    ns = f"load:m17:{uuid.uuid4().hex[:8]}:"
    client = redis.from_url(DEFAULT_REDIS_URL, decode_responses=True)
    tracemalloc.start()
    try:
        sb = RedisStateBackend(DEFAULT_REDIS_URL, prefix=f"{ns}st:", client=client)
        eb = RedisEventBackend(DEFAULT_REDIS_URL, prefix=f"{ns}ev:", history_size=64, client=client)
        gov = RedisSSEGovernance(client=client, prefix=f"{ns}sse:", worker_id="load-w1", lease_ttl_seconds=30.0)
        broker = EventBroker(
            backend=eb,
            governance=gov,
            worker_id="load-w1",
            max_connections_per_session=50,
            max_connections_per_ip=100,
            connect_rate_limit=5000,
            connect_rate_window_seconds=60.0,
        )
        jb = RedisJobBackend(DEFAULT_REDIS_URL, prefix=f"{ns}jb:", client=client, worker_id="load-w1")
        rt = StateRuntime("load-app", backend=sb)
        ctx = rt.context(session_id="s-load")

        async def noop_job(jctx: JobContext, n: int) -> int:
            return n

        defn = JobDefinition(name="noop", handler=noop_job, backend=jb)

        # Warm-up window (20 ops each)
        for i in range(20):
            sb.set("session", "s-load", "k", i)
            sb.get("session", "s-load", "k")
            assert broker.try_acquire_connection("s-load", "10.0.0.1", connection_id=f"w-{i}")[0]
            broker.release_connection("s-load", "10.0.0.1", connection_id=f"w-{i}")
            eb.append_sync("s-load", {"w": i}, event_type="ui.patch")

        res_before = snapshot_redis_resources(client, ns)
        mem_before, _ = tracemalloc.get_traced_memory()
        cpu_before = time.process_time()

        # Measured window 1: SSE connect/disconnect (150 cycles)
        sse_lat: list[float] = []
        t0 = time.perf_counter()
        for i in range(150):
            op_t0 = time.perf_counter()
            cid = f"sse-{i}"
            ok, _, _ = broker.try_acquire_connection("s-load", "10.0.0.2", connection_id=cid)
            assert ok is True
            broker.release_connection("s-load", "10.0.0.2", connection_id=cid)
            sse_lat.append((time.perf_counter() - op_t0) * 1000.0)
        sse_stats = summarize_latencies(sse_lat, time.perf_counter() - t0)

        # Measured window 2: State set/get/CAS (150 ops)
        st_lat: list[float] = []
        t1 = time.perf_counter()
        for i in range(150):
            op_t0 = time.perf_counter()
            sb.set("session", "s-load", "counter", i)
            assert sb.get("session", "s-load", "counter") == i
            st_lat.append((time.perf_counter() - op_t0) * 1000.0)
        st_stats = summarize_latencies(st_lat, time.perf_counter() - t1)

        # Measured window 3: Event publish + replay (100 cycles)
        ev_lat: list[float] = []
        t2 = time.perf_counter()

        async def run_ev_and_jobs():
            for i in range(100):
                op_t0 = time.perf_counter()
                ev = eb.append_sync("s-load", {"n": i}, event_type="ui.patch")
                await eb.replay_after("s-load", max(0, ev.sequence - 5), limit=5)
                ev_lat.append((time.perf_counter() - op_t0) * 1000.0)

        asyncio.run(run_ev_and_jobs())
        ev_stats = summarize_latencies(ev_lat, time.perf_counter() - t2)

        # Measured window 4: Job enqueue + complete (60 cycles)
        jb_lat: list[float] = []
        t3 = time.perf_counter()

        async def run_jobs():
            for i in range(60):
                op_t0 = time.perf_counter()
                await jb.submit(defn, ctx, (i,), {})
                assert await jb.process_once({"noop": defn}, rt) is True
                jb_lat.append((time.perf_counter() - op_t0) * 1000.0)

        asyncio.run(run_jobs())
        jb_stats = summarize_latencies(jb_lat, time.perf_counter() - t3)

        # Measured window 5: Concurrent diagnostic refreshes (App lifecycle + shutdown)
        inspector = User(id="insp", username="insp", roles=("inspector",))
        app = gx.App(
            "LoadDiag",
            config=RadUIConfig(environment="testing", backend="redis", redis_url=DEFAULT_REDIS_URL, session_secret="l" * 32),
            state_backend=sb,
            event_backend=eb,
            job_backend=jb,
            user_resolver=lambda _r: inspector,
        )
        app.page("/")(lambda: gx.text("ok"))
        diag_lat: list[float] = []
        with TestClient(app.asgi()) as tc:
            tc.get("/")
            t4 = time.perf_counter()

            def hit_diag(_i: int) -> float:
                d0 = time.perf_counter()
                assert tc.get("/_gx/inspect/runtime").status_code == 200
                return (time.perf_counter() - d0) * 1000.0

            with ThreadPoolExecutor(max_workers=4) as pool:
                diag_lat = list(pool.map(hit_diag, range(24)))
            diag_stats = summarize_latencies(diag_lat, time.perf_counter() - t4)
            assert len(app._background_tasks) >= 1

        # After shutdown, background tasks are cleaned up
        assert len(app._background_tasks) == 0

        res_after = snapshot_redis_resources(client, ns)
        mem_after, mem_peak = tracemalloc.get_traced_memory()
        cpu_elapsed = time.process_time() - cpu_before

        # Assertions on bounded resources and zero leaks
        assert gov.active_count() == 0
        assert jb.metrics()["queue_depth"] == 0
        assert len(sb._lat_set._samples) <= 512
        assert len(eb._lat_publish._samples) <= 512
        assert res_after["key_count"] < 120  # bounded keys (no per-op key leak)
        assert (mem_after - mem_before) < 5 * 1024 * 1024  # < 5 MB growth

        print(
            "LOAD_METRICS="
            + json.dumps(
                {
                    "sse_connect_disconnect": sse_stats,
                    "state_set_get": st_stats,
                    "event_publish_replay": ev_stats,
                    "job_enqueue_complete": jb_stats,
                    "diag_concurrent": diag_stats,
                    "redis_before": res_before,
                    "redis_after": res_after,
                    "python_mem_delta_bytes": mem_after - mem_before,
                    "python_mem_peak_bytes": mem_peak,
                    "cpu_seconds": round(cpu_elapsed, 3),
                }
            )
        )
    finally:
        tracemalloc.stop()
        client.close()
        cleanup_prefix(ns)
