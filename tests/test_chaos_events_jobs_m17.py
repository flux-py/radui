from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor
import uuid

import pytest
import redis

from radui.core.idempotency import RedisIdempotencyBackend
from radui.jobs.redis import RedisJobBackend
from radui.jobs.runtime import JobContext, JobDefinition, JobStatus
from radui.state.runtime import StateRuntime
from radui.transport.events import EventBroker, RedisEventBackend
from tests.chaos_harness import (
    DEFAULT_REDIS_URL,
    cleanup_prefix,
    live_redis_available,
)

pytestmark = pytest.mark.skipif(
    not live_redis_available(),
    reason="NOT EXECUTED: live Redis server unavailable",
)


def _publish_events_worker(args: tuple[str, str, str, int, int]) -> list[int]:
    redis_url, prefix, session_id, worker_idx, count = args
    client = redis.from_url(redis_url, decode_responses=True)
    eb = RedisEventBackend(redis_url, prefix=prefix, history_size=128, client=client)
    seqs = []
    for i in range(count):
        ev = eb.append_sync(session_id, {"worker": worker_idx, "i": i}, event_type="ui.patch")
        seqs.append(ev.sequence)
    client.close()
    return seqs


def test_chaos_concurrent_event_publish_replay_exhaustion_and_overflow():
    ns = f"chaos:ev:{uuid.uuid4().hex[:8]}:"
    client = redis.from_url(DEFAULT_REDIS_URL, decode_responses=True)
    try:
        # 1. 4 OS processes concurrently publish 20 events each = 80 total within history_size=128
        tasks = [(DEFAULT_REDIS_URL, ns, "s-ev", w, 20) for w in range(4)]
        with ProcessPoolExecutor(max_workers=4) as pool:
            all_seqs = [s for sub in pool.map(_publish_events_worker, tasks) for s in sub]
        assert sorted(all_seqs) == list(range(1, 81))

        eb = RedisEventBackend(DEFAULT_REDIS_URL, prefix=ns, history_size=10, client=client)
        broker = EventBroker(backend=eb, history_size=10, subscriber_queue_size=3)

        # 2. Slow subscriber queue overflow -> emits reset & increments queue_overflows
        async def test_overflow_and_exhaustion() -> None:
            stream_it = broker.stream("s-ev", keepalive_seconds=0.2)
            first_task = asyncio.create_task(stream_it.__anext__())
            await asyncio.sleep(0.05)
            # Flood 6 events into queue_size=3
            for i in range(6):
                broker.publish("s-ev", "ui.patch", {"flood": i})
            first_msg = await asyncio.wait_for(first_task, timeout=2.0)
            # Either receives reset or drained event; close cleanly on disconnect
            assert "event:" in first_msg
            await stream_it.aclose()

            # 3. Replay history exhaustion: publish beyond history_size=10 then replay from 1 -> emits reset
            for i in range(15):
                eb.append_sync("s-exhaust", {"i": i}, event_type="ui.patch")
            exhaust_it = broker.stream("s-exhaust", last_event_id=1, keepalive_seconds=0.2)
            reset_frame = await asyncio.wait_for(exhaust_it.__anext__(), timeout=2.0)
            assert "event: reset" in reset_frame
            await exhaust_it.aclose()

        asyncio.run(test_overflow_and_exhaustion())
        ev_snap = broker.observability_snapshot()["events"]["operations"]
        assert ev_snap["replay_gaps"] >= 1
        assert ev_snap["resets_sent"] >= 1
        assert ev_snap["queue_overflows"] >= 1
    finally:
        client.close()
        cleanup_prefix(ns)


def test_chaos_jobs_concurrent_claims_retry_dlq_cancel_timeout_and_fencing():
    ns = f"chaos:jb:{uuid.uuid4().hex[:8]}:"
    client = redis.from_url(DEFAULT_REDIS_URL, decode_responses=True)
    try:
        rt = StateRuntime("chaos-jobs")
        ctx = rt.context(session_id="s-jb")
        jb_a = RedisJobBackend(DEFAULT_REDIS_URL, prefix=ns, client=client, max_retries=1, default_timeout_seconds=0.15, worker_id="w-a")
        jb_b = RedisJobBackend(DEFAULT_REDIS_URL, prefix=ns, client=client, max_retries=1, default_timeout_seconds=0.15, worker_id="w-b")

        async def always_fail(jctx: JobContext) -> None:
            raise ValueError("boom")

        async def hang_forever(jctx: JobContext) -> None:
            await asyncio.sleep(5.0)

        async def ok_job(jctx: JobContext, x: int) -> int:
            return x + 1

        defs = {
            "fail": JobDefinition(name="fail", handler=always_fail, backend=jb_a),
            "hang": JobDefinition(name="hang", handler=hang_forever, backend=jb_a),
            "ok": JobDefinition(name="ok", handler=ok_job, backend=jb_a),
        }

        async def run_all() -> None:
            # 1. Idempotent enqueue
            s1 = await jb_a.submit(defs["ok"], ctx, (10,), {}, idempotency_key="idem-1")
            s2 = await jb_b.submit(defs["ok"], ctx, (99,), {}, idempotency_key="idem-1")
            assert s1.id == s2.id

            # Concurrent process_once from A and B on single queued job -> only one succeeds in claiming
            res_ab = await asyncio.gather(jb_a.process_once(defs, rt), jb_b.process_once(defs, rt))
            assert res_ab.count(True) == 1

            # 2. Retry exhaustion -> DLQ
            sf = await jb_a.submit(defs["fail"], ctx, (), {})
            await jb_a.process_once(defs, rt)  # attempt 1 -> retry
            await jb_b.process_once(defs, rt)  # attempt 2 -> DLQ
            assert client.llen(f"{ns}dlq") == 1
            assert jb_b.get_snapshot(sf.id, "s-jb").status == JobStatus.FAILED

            # 3. Timeout
            st = await jb_a.submit(defs["hang"], ctx, (), {})
            await jb_a.process_once(defs, rt)  # attempt 1 timeout -> retry
            await jb_a.process_once(defs, rt)  # attempt 2 timeout -> DLQ
            assert client.llen(f"{ns}dlq") == 2
            assert jb_a.get_snapshot(st.id, "s-jb").error_type == "TimeoutError"

            # 4. Cancellation before execution
            sc = await jb_a.submit(defs["ok"], ctx, (1,), {})
            assert await jb_a.cancel(sc.id, "s-jb") is True
            assert jb_a.get_snapshot(sc.id, "s-jb").status == JobStatus.CANCELLED

        asyncio.run(run_all())

        # 5. Fencing-token enforcement in RedisIdempotencyBackend
        idem = RedisIdempotencyBackend(DEFAULT_REDIS_URL, prefix=f"{ns}idem:")
        r1 = idem.begin("act-1", "fp-1", ttl=1, owner_id="w-old")
        assert r1.fence_token is not None
        import time
        time.sleep(1.2)
        r2 = idem.begin("act-1", "fp-1", ttl=10, owner_id="w-new")
        assert r2.fence_token > r1.fence_token
        # Stale fence token from w-old is rejected
        with pytest.raises(Exception):
            idem.complete("act-1", {"ok": True}, fence_token=r1.fence_token, owner_id="w-old")
    finally:
        client.close()
        cleanup_prefix(ns)
