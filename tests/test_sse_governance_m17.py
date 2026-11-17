from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor
import subprocess
import sys
import time
import uuid

import pytest
import redis

import radui as gx
from radui.core.config import ConfigurationError, RadUIConfig
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


def _concurrent_admit_worker(args: tuple[str, str, str, str, int, int]) -> int:
    redis_url, prefix, session_id, client_ip, max_sess, attempts = args
    client = redis.from_url(redis_url, decode_responses=True)
    gov = RedisSSEGovernance(client=client, prefix=prefix, lease_ttl_seconds=30.0)
    broker = EventBroker(
        governance=gov,
        max_connections_per_session=max_sess,
        max_connections_per_ip=100,
        connect_rate_limit=1000,
        connect_rate_window_seconds=60.0,
    )
    admitted = 0
    for _ in range(attempts):
        ok, _, _ = broker.try_acquire_connection(session_id, client_ip)
        if ok:
            admitted += 1
    client.close()
    return admitted


# ---------------------------------------------------------------------------
# Unit & Configuration Tests (no live Redis required)
# ---------------------------------------------------------------------------


def test_sse_governance_config_validation():
    cfg = RadUIConfig.from_env(
        env={
            "RADUI_SSE_LEASE_TTL_SECONDS": "20",
            "RADUI_SSE_HEARTBEAT_INTERVAL_SECONDS": "5",
            "RADUI_SSE_GOVERNANCE_FAIL_OPEN": "false",
        }
    )
    assert cfg.sse_lease_ttl_seconds == 20.0
    assert cfg.sse_heartbeat_interval_seconds == 5.0
    assert cfg.sse_governance_fail_open is False

    with pytest.raises(ConfigurationError):
        RadUIConfig.from_env(env={"RADUI_SSE_LEASE_TTL_SECONDS": "2.0"})

    with pytest.raises(ConfigurationError):
        RadUIConfig.from_env(
            env={
                "RADUI_SSE_LEASE_TTL_SECONDS": "10.0",
                "RADUI_SSE_HEARTBEAT_INTERVAL_SECONDS": "10.0",
            }
        )


def test_redis_sse_governance_fails_closed_by_default():
    gov = RedisSSEGovernance(client=None, prefix="test:fc:", fail_open=False)
    broker = EventBroker(governance=gov, max_connections_per_session=4)
    ok, reason, status = broker.try_acquire_connection("s1", "10.0.0.1")
    assert ok is False
    assert status == 503
    assert "unavailable" in (reason or "").lower()
    assert broker.metrics()["backend_errors"] >= 1
    assert broker.metrics()["rejected_connections"] == 1


def test_redis_sse_governance_fail_open_fallback():
    gov = RedisSSEGovernance(client=None, prefix="test:fo:", fail_open=True)
    broker = EventBroker(governance=gov, max_connections_per_session=2, connect_rate_limit=10)
    assert broker.try_acquire_connection("s1", "10.0.0.1")[0] is True
    assert broker.try_acquire_connection("s1", "10.0.0.1")[0] is True
    ok, _, status = broker.try_acquire_connection("s1", "10.0.0.1")
    assert ok is False
    assert status == 429


def test_redis_sse_governance_worker_capacity_cap():
    class _StubRedis:
        def eval(self, *_args, **_kwargs):
            return [1, "ok"]

    gov = RedisSSEGovernance(client=_StubRedis(), prefix="test:cap:", max_owned_connections=2)
    broker = EventBroker(governance=gov, max_connections_per_session=10, max_connections_per_ip=10, connect_rate_limit=100)
    assert broker.try_acquire_connection("s1", "10.0.0.1")[0] is True
    assert broker.try_acquire_connection("s2", "10.0.0.2")[0] is True
    ok, reason, status = broker.try_acquire_connection("s3", "10.0.0.3")
    assert ok is False
    assert status == 503
    assert "capacity" in (reason or "").lower()


# ---------------------------------------------------------------------------
# Live Redis 7.4.11 Multi-Process Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _live_redis_available(), reason="NOT EXECUTED: live Redis server unavailable")
def test_live_redis_worker_identity_consistency():
    ns = f"test:wid:{uuid.uuid4().hex[:8]}:"
    try:
        cfg = RadUIConfig(
            environment="testing",
            backend="redis",
            redis_url=REDIS_URL,
            session_secret="super-secret-key-at-least-32-chars-long!",
        )
        app = gx.App("WorkerIDTest", config=cfg)
        assert app.worker_id
        assert app.jobs.worker_id == app.worker_id
        assert app.events.worker_id == app.worker_id
        assert isinstance(app.events.governance, RedisSSEGovernance)
        assert app.events.governance.worker_id == app.worker_id
        assert app.events.governance_metrics()["worker_id"] == app.worker_id
        assert app.events.governance_metrics()["mode"] == "redis"
    finally:
        _cleanup_prefix(ns)


@pytest.mark.skipif(not _live_redis_available(), reason="NOT EXECUTED: live Redis server unavailable")
def test_live_redis_global_session_ip_and_rate_limits_across_processes():
    ns = f"test:gov:{uuid.uuid4().hex[:8]}:"
    try:
        # Process A acquires 2 connections on session s1, IP 10.1.1.1
        code_a = f"""
import redis
from radui.transport.events import EventBroker
from radui.transport.governance import RedisSSEGovernance
c = redis.from_url("{REDIS_URL}", decode_responses=True)
gov = RedisSSEGovernance(client=c, prefix="{ns}", worker_id="worker-a", lease_ttl_seconds=30.0)
b = EventBroker(governance=gov, max_connections_per_session=3, max_connections_per_ip=4, connect_rate_limit=5, connect_rate_window_seconds=30.0)
assert b.try_acquire_connection("s1", "10.1.1.1")[0] is True
assert b.try_acquire_connection("s1", "10.1.1.1")[0] is True
c.close()
"""
        subprocess.run([sys.executable, "-c", code_a], check=True)

        # Process B sees Process A's 2 active slots: can take 1 more for s1, 4th fails with session_limit
        code_b = f"""
import redis
from radui.transport.events import EventBroker
from radui.transport.governance import RedisSSEGovernance
c = redis.from_url("{REDIS_URL}", decode_responses=True)
gov = RedisSSEGovernance(client=c, prefix="{ns}", worker_id="worker-b", lease_ttl_seconds=30.0)
b = EventBroker(governance=gov, max_connections_per_session=3, max_connections_per_ip=4, connect_rate_limit=5, connect_rate_window_seconds=30.0)
assert b.try_acquire_connection("s1", "10.1.1.1")[0] is True
ok, reason, status = b.try_acquire_connection("s1", "10.1.1.1")
assert ok is False and status == 429 and "session" in (reason or "").lower(), (ok, reason, status)
# Different session s2 from same IP 10.1.1.1 takes 4th IP slot
assert b.try_acquire_connection("s2", "10.1.1.1")[0] is True
# 6th attempt from same IP hits global rate limit (5 per 30s across workers)
ok_rl, reason_rl, status_rl = b.try_acquire_connection("s3", "10.1.1.1")
assert ok_rl is False and status_rl == 429 and "rate limit" in (reason_rl or "").lower(), (ok_rl, reason_rl, status_rl)
c.close()
"""
        subprocess.run([sys.executable, "-c", code_b], check=True)
    finally:
        _cleanup_prefix(ns)


@pytest.mark.skipif(not _live_redis_available(), reason="NOT EXECUTED: live Redis server unavailable")
def test_live_redis_concurrent_admission_storm_exact_global_cap():
    ns = f"test:storm:{uuid.uuid4().hex[:8]}:"
    max_sess = 6
    try:
        tasks = [(REDIS_URL, ns, "storm-sess", "10.2.2.2", max_sess, 5) for _ in range(4)]
        with ProcessPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(_concurrent_admit_worker, tasks))
        assert sum(results) == max_sess
    finally:
        _cleanup_prefix(ns)


@pytest.mark.skipif(not _live_redis_available(), reason="NOT EXECUTED: live Redis server unavailable")
def test_live_redis_worker_crash_lease_expiration_and_graceful_release():
    ns = f"test:crash:{uuid.uuid4().hex[:8]}:"
    try:
        # Worker A acquires 2/2 slots with 3s lease TTL and exits WITHOUT releasing (crash simulation)
        code_crash = f"""
import redis
from radui.transport.events import EventBroker
from radui.transport.governance import RedisSSEGovernance
c = redis.from_url("{REDIS_URL}", decode_responses=True)
gov = RedisSSEGovernance(client=c, prefix="{ns}", worker_id="worker-dead", lease_ttl_seconds=3.0)
b = EventBroker(governance=gov, max_connections_per_session=2, max_connections_per_ip=10, connect_rate_limit=100)
assert b.try_acquire_connection("s-crash", "10.3.3.3")[0] is True
assert b.try_acquire_connection("s-crash", "10.3.3.3")[0] is True
c.close()
"""
        subprocess.run([sys.executable, "-c", code_crash], check=True)

        client = redis.from_url(REDIS_URL, decode_responses=True)
        gov_b = RedisSSEGovernance(client=client, prefix=ns, worker_id="worker-live", lease_ttl_seconds=3.0)
        broker_b = EventBroker(governance=gov_b, max_connections_per_session=2, max_connections_per_ip=10, connect_rate_limit=100)

        # Immediately blocked while dead worker's lease is still valid
        ok_before, _, status_before = broker_b.try_acquire_connection("s-crash", "10.3.3.3")
        assert ok_before is False and status_before == 429

        # Wait for Redis server TIME lease expiration
        time.sleep(3.3)
        assert broker_b.try_acquire_connection("s-crash", "10.3.3.3")[0] is True
        assert broker_b.try_acquire_connection("s-crash", "10.3.3.3")[0] is True

        # Graceful shutdown via close_all() immediately frees slots
        broker_b.close_all()
        assert gov_b.active_count() == 0
        assert broker_b.try_acquire_connection("s-crash", "10.3.3.3")[0] is True
        broker_b.close_all()
        client.close()
    finally:
        _cleanup_prefix(ns)


@pytest.mark.skipif(not _live_redis_available(), reason="NOT EXECUTED: live Redis server unavailable")
def test_live_redis_bounded_lease_renewal_keeps_slots_alive():
    ns = f"test:renew:{uuid.uuid4().hex[:8]}:"
    client = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        gov_a = RedisSSEGovernance(client=client, prefix=ns, worker_id="worker-renew", lease_ttl_seconds=3.0)
        broker_a = EventBroker(governance=gov_a, max_connections_per_session=3, max_connections_per_ip=10, connect_rate_limit=100)
        for _ in range(3):
            assert broker_a.try_acquire_connection("s-renew", "10.4.4.4")[0] is True

        # Sleep 1.8s, renew in batches of 2 (< 3 total owned), sleep another 1.8s (total 3.6s > 3.0s TTL)
        time.sleep(1.8)
        renewed = gov_a.renew_leases(batch_size=2)
        assert renewed == 3
        assert broker_a.governance_metrics()["leases_renewed"] == 3
        time.sleep(1.8)

        gov_b = RedisSSEGovernance(client=client, prefix=ns, worker_id="worker-other", lease_ttl_seconds=3.0)
        broker_b = EventBroker(governance=gov_b, max_connections_per_session=3, max_connections_per_ip=10, connect_rate_limit=100)
        ok, _, status = broker_b.try_acquire_connection("s-renew", "10.4.4.4")
        assert ok is False and status == 429

        broker_a.close_all()
    finally:
        client.close()
        _cleanup_prefix(ns)
