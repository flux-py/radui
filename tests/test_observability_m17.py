from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys
import time
import uuid

import pytest
import redis

import radui as gx
from radui.core.config import RadUIConfig
from radui.observability import (
    LATENCY_BUCKET_LABELS,
    LatencyTracker,
    MAX_SNAPSHOT_BYTES,
    WorkerIdentity,
    WorkerObservabilityPublisher,
    aggregate_latency_histograms,
    collect_cluster_snapshot,
)
from radui.jobs.redis import RedisJobBackend
from radui.state.backend import RedisStateBackend
from radui.transport.events import EventBroker, RedisEventBackend
from radui.transport.governance import RedisSSEGovernance

REDIS_URL = "redis://127.0.0.1:6379/14"


def _live_redis_available() -> bool:
    try:
        r = redis.from_url(REDIS_URL, socket_connect_timeout=0.5, socket_timeout=0.5)
        return bool(r.ping())
    except Exception:
        return False


def _cleanup_prefix(prefix: str) -> None:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    keys = list(r.scan_iter(f"{prefix}*"))
    if keys:
        r.delete(*keys)
    r.close()


# ---------------------------------------------------------------------------
# Unit Tests: Bounded LatencyTracker, Histogram Aggregation, Secret Safety
# ---------------------------------------------------------------------------


def test_latency_tracker_is_bounded_and_thread_safe():
    tracker = LatencyTracker(sample_capacity=64)
    assert tracker.snapshot()["sample_capacity"] == 64

    def worker(offset: int) -> None:
        for i in range(250):
            tracker.record(0.5 + (i % 6) * 20.0, error=(i % 25 == 0))

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(worker, range(4)))

    snap = tracker.snapshot()
    assert len(tracker._samples) == 64
    assert snap["count"] == 1000
    assert snap["errors"] == 40
    assert snap["p50_ms"] is not None
    assert snap["p95_ms"] is not None
    assert snap["max_ms"] is not None
    assert set(snap["buckets"].keys()) == set(LATENCY_BUCKET_LABELS)
    assert sum(snap["buckets"].values()) == 1000


def test_cluster_histogram_aggregation_does_not_average_worker_percentiles():
    # Worker A: 100 fast requests (<1ms) -> p95 ~ 0.9ms
    w_a = LatencyTracker()
    for _ in range(100):
        w_a.record(0.5)

    # Worker B: 10 slow requests (>=500ms) -> p95 ~ 800ms
    w_b = LatencyTracker()
    for _ in range(10):
        w_b.record(800.0)

    snap_a = w_a.snapshot()
    snap_b = w_b.snapshot()
    naive_avg_p95 = (snap_a["p95_ms"] + snap_b["p95_ms"]) / 2.0

    agg = aggregate_latency_histograms([snap_a, snap_b])
    assert agg["count"] == 110
    assert agg["buckets"]["<1ms"] == 100
    assert agg["buckets"][">=500ms"] == 10
    # 95th percentile of 110 items is at rank 104.5 -> falls in >=500ms bucket, NOT ~400ms naive average
    assert agg["p95_ms"] >= 500.0
    assert abs(agg["p95_ms"] - naive_avg_p95) > 50.0


def test_observability_snapshot_excludes_secrets_and_handles_outages():
    secret = "super-secret-value-at-least-32-characters!"
    cfg = RadUIConfig(
        environment="testing",
        backend="memory",
        session_secret=secret,
        redis_url="redis://user:topsecretpass@localhost:6379/0",
    )
    app = gx.App("ObsSecretTest", config=cfg)
    raw = app.observability.build_snapshot()
    encoded = json.dumps(raw)
    assert secret not in encoded
    assert "topsecretpass" not in encoded

    # Unavailable Redis client -> fails gracefully without crashing
    pub = WorkerObservabilityPublisher(
        app.worker_identity,
        app._collect_worker_observability,
        client=None,
        prefix="test:obs:none:",
    )
    assert pub.publish_snapshot() is False
    assert pub.publish_errors == 1

    # Oversized snapshot -> dropped safely
    big_pub = WorkerObservabilityPublisher(
        app.worker_identity,
        lambda: {"blob": "x" * (MAX_SNAPSHOT_BYTES + 100)},
        client=object(),
        prefix="test:obs:big:",
    )
    assert big_pub.publish_snapshot() is False
    assert big_pub.publish_errors == 1

    # Cluster snapshot distinguishes unavailable vs genuine zero workers
    unavail = collect_cluster_snapshot(None)
    assert unavail["available"] is False
    assert unavail["active_workers"] == 0


def test_cluster_snapshot_ignores_malformed_worker_entries():
    class _StubRedis:
        def scan_iter(self, match: str, count: int = 200):
            return iter(["k1", "k2", "k3"])

        def mget(self, keys):
            valid = json.dumps(
                {
                    "worker": WorkerIdentity.create(worker_id="w-ok").to_dict(),
                    "status": "active",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "subsystems": {
                        "state": {"operations": {"get": 3}, "latencies": {}},
                        "events": {"operations": {"published": 2}, "latencies": {}},
                        "sse": {"operations": {"admitted": 1}, "latencies": {}},
                        "jobs": {"operations": {"enqueue": 4}, "queue_depth": 2, "latencies": {}},
                    },
                }
            )
            return [valid, "{not-json", json.dumps({"unexpected": True})]

    cluster = collect_cluster_snapshot(_StubRedis(), prefix="test:obs:")
    assert cluster["available"] is True
    assert cluster["active_workers"] == 1
    assert cluster["malformed_snapshots"] == 2
    assert cluster["aggregated"]["state"]["operations"]["get"] == 3
    assert cluster["aggregated"]["jobs"]["queue_depth"] == 2


# ---------------------------------------------------------------------------
# Live Redis 7.4.11 Multi-Process Observability Tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _live_redis_available(), reason="NOT EXECUTED: live Redis server unavailable")
def test_live_redis_multiprocess_observability_aggregation_and_deregister():
    ns = f"test:obs:{uuid.uuid4().hex[:8]}:"
    obs_prefix = f"{ns}obs:worker:"
    client = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        # Process A performs state, event, and SSE operations and publishes its snapshot
        code_a = f"""
import redis
from radui.observability import WorkerIdentity, WorkerObservabilityPublisher
from radui.state.backend import RedisStateBackend
from radui.transport.events import EventBroker, RedisEventBackend

c = redis.from_url("{REDIS_URL}", decode_responses=True)
sb = RedisStateBackend("{REDIS_URL}", prefix="{ns}st:", client=c)
eb = RedisEventBackend("{REDIS_URL}", prefix="{ns}ev:", client=c)
broker = EventBroker(backend=eb, worker_id="obs-worker-a")
sb.set("session", "s1", "k1", 10)
assert sb.get("session", "s1", "k1") == 10
broker.publish("s1", "ui.patch", {{"n": 1}})
ident = WorkerIdentity.create(worker_id="obs-worker-a", environment="testing", backend_mode="redis")
pub = WorkerObservabilityPublisher(
    ident,
    lambda: {{
        "state": sb.observability_snapshot(),
        "events": broker.observability_snapshot()["events"],
        "sse": broker.observability_snapshot()["sse"],
        "jobs": {{"operations": {{}}, "latencies": {{}}}},
    }},
    client=c,
    prefix="{obs_prefix}",
    ttl_seconds=10,
)
assert pub.publish_snapshot() is True
c.close()
"""
        subprocess.run([sys.executable, "-c", code_a], check=True)

        # Process B publishes its own independent snapshot
        sb_b = RedisStateBackend(REDIS_URL, prefix=f"{ns}st:", client=client)
        sb_b.set("session", "s1", "k2", 20)
        sb_b.get("session", "s1", "k2")
        ident_b = WorkerIdentity.create(worker_id="obs-worker-b", environment="testing", backend_mode="redis")
        pub_b = WorkerObservabilityPublisher(
            ident_b,
            lambda: {
                "state": sb_b.observability_snapshot(),
                "events": {"operations": {}, "latencies": {}},
                "sse": {"operations": {}, "latencies": {}},
                "jobs": {"operations": {}, "latencies": {}},
            },
            client=client,
            prefix=obs_prefix,
            ttl_seconds=10,
        )
        assert pub_b.publish_snapshot() is True

        cluster = collect_cluster_snapshot(client, prefix=obs_prefix)
        assert cluster["available"] is True
        assert cluster["active_workers"] == 2
        assert cluster["aggregated"]["state"]["operations"]["get"] == 2
        assert cluster["aggregated"]["state"]["operations"]["set"] == 2
        assert cluster["aggregated"]["state"]["latencies"]["get"]["count"] == 2
        assert cluster["aggregated"]["events"]["operations"]["published"] == 1

        # Clean deregistration removes worker B immediately
        assert pub_b.deregister() is True
        cluster_after = collect_cluster_snapshot(client, prefix=obs_prefix)
        assert cluster_after["active_workers"] == 1
    finally:
        client.close()
        _cleanup_prefix(ns)


@pytest.mark.skipif(not _live_redis_available(), reason="NOT EXECUTED: live Redis server unavailable")
def test_live_redis_worker_snapshot_ttl_expiration_and_recovery():
    ns = f"test:obsttl:{uuid.uuid4().hex[:8]}:"
    obs_prefix = f"{ns}obs:worker:"
    client = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        ident = WorkerIdentity.create(worker_id="obs-worker-ttl", environment="testing", backend_mode="redis")
        pub = WorkerObservabilityPublisher(
            ident,
            lambda: {"state": {}, "events": {}, "sse": {}, "jobs": {}},
            client=client,
            prefix=obs_prefix,
            ttl_seconds=3,
        )
        assert pub.publish_snapshot() is True
        assert collect_cluster_snapshot(client, prefix=obs_prefix)["active_workers"] == 1

        # Simulate crashed worker failing to heartbeat -> TTL expires
        time.sleep(3.3)
        after_ttl = collect_cluster_snapshot(client, prefix=obs_prefix)
        assert after_ttl["available"] is True
        assert after_ttl["active_workers"] == 0

        # Simulate Redis outage then recovery on publisher
        pub._client = None
        assert pub.publish_snapshot() is False
        assert pub.publish_errors == 1
        pub._client = client
        assert pub.publish_snapshot() is True
        assert collect_cluster_snapshot(client, prefix=obs_prefix)["active_workers"] == 1
    finally:
        client.close()
        _cleanup_prefix(ns)
