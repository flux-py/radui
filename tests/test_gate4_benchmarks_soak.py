from __future__ import annotations

import asyncio
import concurrent.futures
import pytest
from starlette.testclient import TestClient

import radui as gx
from radui.benchmarks import BenchmarkSuite


def test_gate4_stratified_6tier_benchmarks_execute():
    suite = BenchmarkSuite()
    results = suite.run_all(verbose=False)
    assert len(results) == 6

    # Verify each tier passed its latency assertion
    for r in results:
        assert r.passed is True, f"Benchmark {r.tier} ({r.description}) failed: median {r.median_ms}ms"
        assert r.median_ms > 0
        assert r.p95_ms >= r.median_ms
        assert r.p99_ms >= r.p95_ms


def test_multi_worker_failure_soak_concurrency():
    """Simulate 50 concurrent worker operations racing on shared idempotency leases."""
    backend = gx.InMemoryIdempotencyBackend()

    def worker_task(worker_id: str, action_num: int):
        action_id = f"soak-action-{action_num % 10}"  # 10 distinct actions attacked by 50 workers
        fp = f"fingerprint-{action_num % 10}"
        res = backend.begin(action_id, fp, owner_id=worker_id, ttl=10)
        if res.is_new:
            try:
                backend.complete(action_id, {"result": "ok", "worker": worker_id}, fence_token=res.fence_token, owner_id=worker_id)
                return "completed"
            except gx.StaleLeaseError:
                return "stale"
        elif res.completed:
            return "cached"
        elif res.in_progress:
            return "in_progress"
        elif res.conflict:
            return "conflict"
        return "other"

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(worker_task, f"worker-{i}", i) for i in range(50)]
        results = [f.result() for f in futures]

    completed_count = results.count("completed")
    cached_count = results.count("cached")
    in_progress_count = results.count("in_progress")
    stale_count = results.count("stale")

    # Exactly 10 actions should have completed; the rest were in_progress or cached
    assert completed_count == 10
    assert completed_count + cached_count + in_progress_count + stale_count == 50


def test_sustained_outbox_batch_dispatch_under_load():
    """Verify outbox claiming, dispatching, and compensation under high batch concurrency."""
    outbox = gx.TransactionalOutbox()

    # Publish 100 outbox records
    for i in range(100):
        outbox.publish(
            "billing.charge",
            {"order_id": f"ord-{i}", "amount": 99.0},
            idempotency_key=f"idemp-outbox-{i}",
        )

    dispatched_count = 0

    def handle_dispatch(batch):
        nonlocal dispatched_count
        for rec in batch:
            dispatched_count += 1
            outbox.mark_completed(rec.id, fence_token=rec.fence_token)

    # Multi-worker claiming
    def outbox_worker(worker_id: str):
        while True:
            batch = outbox.claim_batch(limit=10, lease_seconds=5, worker_id=worker_id)
            if not batch:
                break
            handle_dispatch(batch)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(outbox_worker, [f"outbox-worker-{i}" for i in range(4)]))

    assert dispatched_count == 100
    pending = outbox.claim_batch(limit=10, lease_seconds=5, worker_id="verifier")
    assert len(pending) == 0
