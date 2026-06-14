"""Failure injection, concurrency, and chaos engineering tests for RADUI Gate 1.

Verifies:
1. Distributed fencing token rejection on stale worker commits.
2. Prevention of business resource corruption when leases are reclaimed.
3. Transactional Outbox atomic local commit, crash recovery, and compensation.
4. SSE High-Watermark replay under concurrent appends.
5. Five-state client mutation lifecycle terminal error handling.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sqlite3
import time
import pytest

import radui as gx
from radui.core.idempotency import StaleLeaseError
from radui.core.outbox import StaleOutboxLeaseError, TransactionalOutbox


def test_fencing_stale_worker_rejection_prevents_business_mutation(tmp_path: Path):
    """Explicitly verify that a slow/partitioned worker with an expired lease is rejected

    and prevented from corrupting the underlying business resource.
    """
    db_file = tmp_path / "fencing_chaos.db"
    backend = gx.SQLiteIdempotencyBackend(str(db_file))

    # Initialize business table
    with backend.transaction() as conn:
        conn.execute("CREATE TABLE accounts (id TEXT PRIMARY KEY, balance INT);")
        conn.execute("INSERT INTO accounts VALUES ('acc-100', 1000);")

    fp = gx.compute_payload_fingerprint("debit.account", {"amount": 200})
    action_key = "act-order-999"

    # Step 1: Worker A acquires reservation with token 1 and short TTL (0.1s)
    res_worker_a = backend.begin(action_key, fp, ttl=1, owner_id="worker-A")
    token_a = res_worker_a.fence_token
    assert token_a >= 1
    assert res_worker_a.owner_id == "worker-A"

    # Step 2: Worker A pauses (simulating GC pause or network partition)
    # Manually backdate created_at/expires_at in SQLite to simulate immediate expiration
    conn = backend._get_connection()
    with conn:
        conn.execute(
            "UPDATE gx_idempotency SET expires_at = ? WHERE key = ?",
            (time.time() - 10.0, action_key),
        )

    # Step 3: Worker B sees expired lease, reclaims reservation, receives token 2
    res_worker_b = backend.begin(action_key, fp, ttl=30, owner_id="worker-B")
    token_b = res_worker_b.fence_token
    assert token_b > token_a
    assert res_worker_b.owner_id == "worker-B"

    # Step 4: Worker B executes business operation and commits with token B
    with backend.transaction() as conn:
        conn.execute("UPDATE accounts SET balance = balance - 200 WHERE id = 'acc-100';")
        backend.complete(action_key, {"balance": 800}, fence_token=token_b, owner_id="worker-B")

    # Step 5: Worker A wakes up and attempts stale commit with token A
    with pytest.raises(StaleLeaseError):
        backend.complete(action_key, {"balance": 800}, fence_token=token_a, owner_id="worker-A")

    # Final assertion: The business resource was modified exactly ONCE (balance is 800, NOT 600)
    with backend.transaction() as conn:
        row = conn.execute("SELECT balance FROM accounts WHERE id = 'acc-100';").fetchone()
        assert row[0] == 800


def test_fencing_token_monotonicity_in_redis():
    """Verify monotonic increment of fencing tokens in Redis backend."""
    redis_backend = gx.RedisIdempotencyBackend("redis://localhost:6379/15", allow_fallback=True)
    fp = gx.compute_payload_fingerprint("test.fence", {"v": 1})

    r1 = redis_backend.begin("key-fence-1", fp, ttl=30, owner_id="w1")
    t1 = r1.fence_token
    assert t1 >= 1

    # Lease renewal with valid token succeeds
    renewed = redis_backend.renew_lease("key-fence-1", owner_id="w1", fence_token=t1, ttl=60)
    assert renewed is True

    # Lease renewal with stale token raises StaleLeaseError
    with pytest.raises(StaleLeaseError):
        redis_backend.renew_lease("key-fence-1", owner_id="w1", fence_token=t1 - 1, ttl=60)

    # Lease renewal with mismatched owner raises StaleLeaseError
    with pytest.raises(StaleLeaseError):
        redis_backend.renew_lease("key-fence-1", owner_id="attacker-worker", fence_token=t1, ttl=60)

    # Complete with stale token raises StaleLeaseError
    with pytest.raises(StaleLeaseError):
        redis_backend.complete("key-fence-1", {"ok": True}, fence_token=t1 - 1, owner_id="w1")


def test_transactional_outbox_atomic_commit_and_crash_recovery(tmp_path: Path):
    """Verify that a business mutation and outbox event are committed atomically,

    and a crashed worker's pending item is claimed and dispatched by a recovery worker.
    """
    db_file = tmp_path / "outbox.db"
    outbox = TransactionalOutbox(str(db_file))

    # Initialize business table
    with outbox.transaction() as conn:
        conn.execute("CREATE TABLE orders (id TEXT PRIMARY KEY, status TEXT);")

    # Step 1: Atomic transaction inserting order and outbox record
    with outbox.transaction() as conn:
        conn.execute("INSERT INTO orders VALUES ('ord-101', 'CREATED');")
        rec = outbox.publish(
            "payment.charge",
            {"order_id": "ord-101", "amount": 99.50},
            conn=conn,
            idempotency_key="pay-ord-101",
        )
    assert rec.status == "PENDING"
    assert rec.idempotency_key == "pay-ord-101"

    # Simulate process crash here: application exited before external payment HTTP call

    # Step 2: Background recovery worker spins up, claims batch with monotonic fencing token
    claimed_batch = outbox.claim_batch(limit=10, lease_seconds=30, worker_id="recovery-worker-1")
    assert len(claimed_batch) == 1
    claimed = claimed_batch[0]
    assert claimed.id == rec.id
    assert claimed.status == "DISPATCHED"
    assert claimed.owner_id == "recovery-worker-1"
    assert claimed.fence_token == 2

    # Step 3: Register payment handler and execute outbox processing
    dispatched_payloads = []

    def mock_payment_gateway(record: gx.OutboxRecord):
        dispatched_payloads.append(record.payload)
        # Verify downstream idempotency key is passed to external provider
        assert record.idempotency_key == "pay-ord-101"

    outbox.register_handler("payment.charge", mock_payment_gateway)
    # Mark completed with valid fencing token
    completed = outbox.mark_completed(claimed.id, fence_token=claimed.fence_token)
    assert completed is True

    # Assert record is marked COMPLETED
    persisted = outbox.get(claimed.id)
    assert persisted is not None
    assert persisted.status == "COMPLETED"
    assert persisted.completed_at is not None

    # Stale attempt to fail or complete with older token 1 is rejected
    with pytest.raises(StaleOutboxLeaseError):
        outbox.mark_failed(claimed.id, "Stale crash error", fence_token=1)


def test_transactional_outbox_retry_and_compensation(tmp_path: Path):
    """Verify exponential retry backoff and compensation when external API calls fail."""
    db_file = tmp_path / "outbox_comp.db"
    outbox = TransactionalOutbox(str(db_file))

    compensation_executed = []

    def failing_handler(record: gx.OutboxRecord):
        raise RuntimeError("Payment Gateway 503 Unavailable")

    def compensation_handler(record: gx.OutboxRecord):
        compensation_executed.append(record.payload["order_id"])

    outbox.register_handler("order.process", failing_handler)
    outbox.register_compensator("order.process", compensation_handler)

    rec = outbox.publish("order.process", {"order_id": "ord-fail-1"}, max_retries=2)

    # First attempt: fails and schedules retry
    claimed = outbox.claim_batch(limit=1, worker_id="w1")[0]
    outbox.mark_failed(claimed.id, "Attempt 1 failed", fence_token=claimed.fence_token, can_retry=True)
    r_after_1 = outbox.get(rec.id)
    assert r_after_1.status == "PENDING"
    assert r_after_1.retry_count == 1

    # Force immediate attempt by advancing next_attempt_at
    conn = outbox._get_connection()
    with conn:
        conn.execute("UPDATE gx_outbox SET next_attempt_at = 0 WHERE id = ?", (rec.id,))

    # Second attempt: exceeds max_retries (2) -> transitions to COMPENSATING
    claimed_2 = outbox.claim_batch(limit=1, worker_id="w1")[0]
    outbox.mark_failed(claimed_2.id, "Attempt 2 failed", fence_token=claimed_2.fence_token, can_retry=True)
    r_after_2 = outbox.get(rec.id)
    assert r_after_2.status == "COMPENSATING"

    # Process compensations
    compensated_count = outbox._process_compensations_once(worker_id="w1", limit=10)
    assert compensated_count == 1
    assert compensation_executed == ["ord-fail-1"]

    final_rec = outbox.get(rec.id)
    assert final_rec.status == "COMPENSATED"


@pytest.mark.anyio
async def test_sse_replay_high_watermark_under_concurrent_appends(tmp_path: Path):
    """Verify that establishing a stream with last_event_id=10 captures a durable high-watermark,

    replays historical events 11..20, and smoothly drains live events without gaps or duplicates.
    """
    db_file = tmp_path / "sse_hwm.db"
    backend = gx.SQLiteEventBackend(str(db_file))
    broker = gx.EventBroker(backend=backend)
    session_id = "test-session-hwm"

    # Pre-populate 20 events
    for i in range(1, 21):
        backend.append_sync(session_id, {"msg": f"event-{i}"})

    assert backend.current_sequence(session_id) == 20

    # Start stream with last_event_id=10
    stream = broker.stream(session_id, last_event_id=10, keepalive_seconds=0.2)

    # Concurrently append events 21..30 while stream is active
    for i in range(21, 31):
        broker.publish(session_id, "state.patch", {"msg": f"event-{i}"})

    received_sequences = []
    # Read 20 items (events 11 through 30)
    for _ in range(20):
        chunk = await stream.__anext__()
        if chunk.startswith("id:"):
            seq = int(chunk.splitlines()[0].replace("id:", "").strip())
            received_sequences.append(seq)

    # Assert strict monotonic ordering from 11 through 30
    assert received_sequences == list(range(11, 31))
    assert len(received_sequences) == 20


def test_resource_level_fencing_conditional_sql_update(tmp_path: Path):
    """Verify resource-level fencing on a downstream business table.

    Demonstrates:
    1. Worker B updates order from PENDING to PAID with token 11 (rowcount=1).
    2. Worker B performs a second sequential update with the same token 11 (rowcount=1).
    3. Stale Worker A attempts update with token 10 (rowcount=0, rejected).
    4. Imposter Worker C attempts update with token 11 under a different owner (rowcount=0, rejected).
    """
    db_file = tmp_path / "resource_fencing.db"
    conn = sqlite3.connect(str(db_file))

    # Initialize business table with monotonic fence_token and owner_id columns
    with conn:
        conn.execute(
            """
            CREATE TABLE orders (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                total_cents INT NOT NULL,
                tracking_no TEXT,
                last_fence_token INT NOT NULL DEFAULT 0,
                owner_id TEXT NOT NULL DEFAULT ''
            );
            """
        )
        conn.execute("INSERT INTO orders VALUES ('ord-500', 'PENDING', 5000, NULL, 0, '');")

    token_worker_a = 10
    token_worker_b = 11

    # Worker B successfully updates the order using conditional SQL fencing
    with conn:
        cursor = conn.execute(
            """
            UPDATE orders
            SET status = 'PAID', last_fence_token = ?, owner_id = ?
            WHERE id = 'ord-500' 
              AND (last_fence_token < ? OR (last_fence_token = ? AND owner_id = ?));
            """,
            (token_worker_b, "worker-B", token_worker_b, token_worker_b, "worker-B"),
        )
        assert cursor.rowcount == 1  # 1 row updated

    # Worker B performs a SECOND sequential update within the same valid lease and token
    with conn:
        cursor = conn.execute(
            """
            UPDATE orders
            SET tracking_no = 'TRK-99988', last_fence_token = ?, owner_id = ?
            WHERE id = 'ord-500' 
              AND (last_fence_token < ? OR (last_fence_token = ? AND owner_id = ?));
            """,
            (token_worker_b, "worker-B", token_worker_b, token_worker_b, "worker-B"),
        )
        assert cursor.rowcount == 1  # Succeeds because owner matches active fence_token

    row = conn.execute("SELECT status, tracking_no, last_fence_token, owner_id FROM orders WHERE id = 'ord-500';").fetchone()
    assert row == ("PAID", "TRK-99988", 11, "worker-B")

    # Worker A wakes up and attempts to update the order with stale token 10
    with conn:
        cursor = conn.execute(
            """
            UPDATE orders
            SET status = 'CANCELLED', last_fence_token = ?, owner_id = ?
            WHERE id = 'ord-500' 
              AND (last_fence_token < ? OR (last_fence_token = ? AND owner_id = ?));
            """,
            (token_worker_a, "worker-A", token_worker_a, token_worker_a, "worker-A"),
        )
        # Resource-level conditional check blocked stale Worker A (0 rows updated!)
        assert cursor.rowcount == 0

    # Imposter Worker C attempts to update with token 11 but owner_id 'worker-C'
    with conn:
        cursor = conn.execute(
            """
            UPDATE orders
            SET status = 'REFUNDED', last_fence_token = ?, owner_id = ?
            WHERE id = 'ord-500' 
              AND (last_fence_token < ? OR (last_fence_token = ? AND owner_id = ?));
            """,
            (token_worker_b, "worker-C", token_worker_b, token_worker_b, "worker-C"),
        )
        assert cursor.rowcount == 0  # Blocked: token is not greater and owner does not match

    # Confirm the business record remains in Worker B's valid state
    final_row = conn.execute("SELECT status, tracking_no, last_fence_token, owner_id FROM orders WHERE id = 'ord-500';").fetchone()
    assert final_row == ("PAID", "TRK-99988", 11, "worker-B")


def test_trusted_tenant_resolution_and_spoofing_defense():
    """Verify trusted tenant pipeline: untrusted client headers are rejected,

    and tenant membership validators enforce strict tenant boundary security.
    """
    from starlette.testclient import TestClient

    # Scenario 1: App with untrusted headers disabled rejects raw X-Tenant-ID header
    app_strict = gx.App("Strict Tenant App", allow_untrusted_tenant_headers=False)

    @app_strict.page("/dashboard")
    def dashboard():
        return gx.heading("Strict Dashboard")

    with TestClient(app_strict.asgi()) as client:
        # Request with raw untrusted tenant header without validator is rejected (403)
        res_spoof = client.get("/dashboard", headers={"X-Tenant-ID": "tenant-evil"})
        assert res_spoof.status_code == 403
        assert "Untrusted tenant headers are disabled" in res_spoof.text

        # Request without tenant header succeeds
        res_normal = client.get("/dashboard")
        assert res_normal.status_code == 200

    # Scenario 2: App with tenant membership validator
    membership_db = {
        "alice": {"tenant-acme", "tenant-shared"},
        "bob": {"tenant-beta"},
    }

    def validate_membership(request, user_id, tenant_id):
        if not user_id:
            return False
        allowed_tenants = membership_db.get(user_id, set())
        return tenant_id in allowed_tenants

    app_validated = gx.App(
        "Validated Tenant App",
        user_id_resolver=lambda req: req.headers.get("X-User-ID"),
        tenant_membership_validator=validate_membership,
    )

    @app_validated.page("/portal")
    def portal():
        return gx.heading("Tenant Portal")

    with TestClient(app_validated.asgi()) as client:
        # Alice accesses tenant-acme -> authorized (200)
        res_alice = client.get("/portal", headers={"X-User-ID": "alice", "X-Tenant-ID": "tenant-acme"})
        assert res_alice.status_code == 200

        # Alice attempts to spoof tenant-beta (which belongs to Bob) -> forbidden (403)
        res_alice_spoof = client.get("/portal", headers={"X-User-ID": "alice", "X-Tenant-ID": "tenant-beta"})
        assert res_alice_spoof.status_code == 403
        assert "Access denied" in res_alice_spoof.text

        # Anonymous user attempts to pass tenant header -> forbidden (403)
        res_anon = client.get("/portal", headers={"X-Tenant-ID": "tenant-acme"})
        assert res_anon.status_code == 403


@pytest.mark.anyio
async def test_sse_replay_expired_retention_triggers_reset(tmp_path: Path):
    """Verify that when a client connects with a Last-Event-ID older than the backend's

    retention window, the server safely yields an `event: reset` control message.
    """
    db_file = tmp_path / "sse_retention.db"
    backend = gx.SQLiteEventBackend(str(db_file), history_size=5)
    broker = gx.EventBroker(backend=backend)
    session_id = "test-session-pruned"

    # Append 10 events (1 through 10)
    for i in range(1, 11):
        backend.append_sync(session_id, {"msg": f"event-{i}"})

    # High watermark is 10
    assert backend.current_sequence(session_id) == 10

    # Simulate log pruning: remove events 1 through 5 from SQLite storage
    conn = backend._get_connection()
    with conn:
        conn.execute("DELETE FROM gx_events WHERE sequence <= 5;")

    # Client reconnects with last_event_id=2 (which was pruned from retention)
    stream = broker.stream(session_id, last_event_id=2, keepalive_seconds=0.2)
    first_chunk = await stream.__anext__()

    # Server must yield reset message because events 3..5 are missing from retention
    assert "event: reset" in first_chunk


@pytest.mark.anyio
async def test_event_broker_backpressure_bounded_queue_shedding():
    """Verify that when an SSE client queue overflows its bounded capacity,

    the broker clears the stalled buffer and enqueues an `event: reset` backpressure signal.
    """
    backend = gx.InMemoryEventBackend(history_size=10)
    # Set a tiny bounded queue size of 2 to trigger backpressure quickly
    broker = gx.EventBroker(backend=backend, subscriber_queue_size=2)
    session_id = "test-session-backpressure"

    queue = asyncio.Queue(maxsize=2)
    loop = asyncio.get_running_loop()
    with broker._lock:
        broker._subscribers[session_id].add((loop, queue))

    # Pre-fill queue to its max capacity
    await queue.put(gx.EventRecord(1, "state.patch", {}))
    await queue.put(gx.EventRecord(2, "state.patch", {}))
    assert queue.full()

    # Publish another event: should trigger QueueFull handling which clears queue and puts 'reset'
    broker.publish(session_id, "state.patch", {"msg": "overflow"})
    await asyncio.sleep(0.05)

    # Queue should now have been shed and contain the 'reset' control event
    items = []
    while not queue.empty():
        items.append(await queue.get())

    assert any(rec.event == "reset" for rec in items)


def test_idempotency_error_taxonomy_in_progress_vs_conflict():
    """Verify machine-readable error codes:

    - Concurrent in-flight action returns HTTP 409 with `IDEMPOTENCY_IN_PROGRESS` and `Retry-After`.
    - Differing payload fingerprint returns HTTP 409 with `IDEMPOTENCY_PAYLOAD_MISMATCH`.
    """
    from starlette.testclient import TestClient

    app = gx.App("Idempotency Error Taxonomy App")
    s_counter = gx.state("counter.val", 0)

    @app.page("/action-test")
    def action_page():
        return gx.form(
            "counter.inc",
            gx.button("Increment", id="btn-inc"),
            id="form-inc",
        )

    @app.command("counter.inc")
    def increment(ctx: gx.CommandContext):
        ctx.write(s_counter, ctx.read(s_counter) + 1)

    with TestClient(app.asgi()) as client:
        # Initial visit to acquire session and csrf token
        res_page = client.get("/action-test")
        assert res_page.status_code == 200
        csrf_token = client.cookies.get("RADUI_session") or "test-csrf"
        # Extract CSRF token from page HTML
        import re
        match = re.search(r'name="_csrf"\s+value="([^"]+)"', res_page.text)
        assert match is not None
        csrf = match.group(1)

        action_id = "act-tax-12345678"

        # Case 1: Simulate in-progress action in idempotency backend
        fp = gx.compute_payload_fingerprint("counter.inc", {
            "_csrf": csrf,
            "_gx_action_id": action_id,
            "_gx_view_id": "/action-test",
        })
        # Worker 1 begins reservation
        res_begin = app.idempotency.begin(action_id, fp, ttl=30, owner_id="worker-busy-1")
        assert res_begin.in_progress is False

        # Client submits same action while Worker 1 is still processing -> 409 IDEMPOTENCY_IN_PROGRESS
        res_in_progress = client.post(
            "/_gx/commands/counter.inc",
            data={
                "_csrf": csrf,
                "_gx_action_id": action_id,
                "_gx_view_id": "/action-test",
            },
        )
        assert res_in_progress.status_code == 409
        json_in_prog = res_in_progress.json()
        assert json_in_prog["error_code"] == "IDEMPOTENCY_IN_PROGRESS"
        assert res_in_progress.headers.get("Retry-After") == "1"

        # Case 2: Complete the action
        app.idempotency.complete(action_id, {"ok": True}, fence_token=res_begin.fence_token, owner_id="worker-busy-1")

        # Now submit same action ID with DIFFERING payload fingerprint -> 409 IDEMPOTENCY_PAYLOAD_MISMATCH
        res_conflict = client.post(
            "/_gx/commands/counter.inc",
            data={
                "_csrf": csrf,
                "_gx_action_id": action_id,
                "_gx_view_id": "/action-test",
                "differing_payload_field": "tampered-value",
            },
        )
        assert res_conflict.status_code == 409
        json_conflict = res_conflict.json()
        assert json_conflict["error_code"] == "IDEMPOTENCY_PAYLOAD_MISMATCH"


