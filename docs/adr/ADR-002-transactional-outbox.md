# ADR-002: Transactional Outbox Pattern, At-Least-Once Delivery & Forward Compensation

## Status
Accepted (v1.0.0 Production Engineering Specification)

## Context
When a user command mutates local business records and produces external side-effects (e.g. charging an external payment gateway, publishing webhooks, sending transactional emails), executing network requests directly inside the synchronous request handler creates dual-write vulnerabilities.

If the database commits but the network call fails, or if the network call succeeds but the local transaction rolls back, the system enters an inconsistent state.

Furthermore, a local database transaction (`ctx.transaction()`) cannot roll back an external network operation that has already executed over the wire. Local ACID rollback is strictly bounded to database-level changes.

Finally, an outbox guarantees at-least-once dispatch, NOT exactly-once external execution. If a network blip occurs after the downstream service processes the request but before RADUI receives the response, retrying the outbox record can execute duplicate side effects unless the downstream provider enforces idempotency keys.

## Decision

### 1. Separation of Concerns: Local Transactions vs Outbox
- **Local State Scope:** `ctx.transaction()` guarantees atomicity for local database tables and local reactive state. If an exception occurs before commit, changes within that transaction boundary are rolled back by the database engine.
- **Distributed Side-Effects:** External operations must never be executed directly inside `ctx.transaction()`. Instead, command handlers publish an outbox intent record (`ctx.outbox.publish(...)`) within the SAME local database transaction:

```python
with ctx.outbox.transaction() as conn:
    # 1. Update local business records
    conn.execute("UPDATE orders SET status = 'PLACED' WHERE id = :id", {"id": order_id})
    # 2. Persist outbound intent atomically in the same transaction
    ctx.outbox.publish(
        "payment.charge",
        {"order_id": order_id, "amount_cents": 4900},
        conn=conn,
        idempotency_key=f"pay-{order_id}",
        tenant_id=ctx.tenant_id,
    )
```

### 2. At-Least-Once Delivery & Downstream Idempotency
- The outbox engine provides **at-least-once external event dispatch**.
- To prevent duplicate external side-effects during network retries, all external calls MUST propagate RADUI's deterministic `idempotency_key` to the external provider:
  ```python
  def charge_payment_handler(record: gx.OutboxRecord):
      stripe.PaymentIntent.create(
          amount=record.payload["amount_cents"],
          currency="usd",
          idempotency_key=record.idempotency_key,  # Downstream deduplication
      )
  ```
- RADUI does NOT claim exactly-once external execution; downstream provider cooperation is an explicit architectural dependency.

### 3. Outbox Record Lifecycle State Machine
Outbox records transition through explicit, audited lifecycle states:

```
[ PENDING ] ------------> [ PROCESSING ] ------------> [ COMPLETED ]
                                | (retries exhausted)
                                v
                            [ DEAD ]
                                |
                                v
                         [ COMPENSATING ]
                           /          \
                          v            v
                   [ COMPENSATED ]   [ COMPENSATION_FAILED ]
```

1. `PENDING`: Outbox record written atomically with local business data.
2. `PROCESSING`: Claimed by a worker via `claim_batch()` under a leased fencing token (`fence_token`).
3. `COMPLETED`: External call succeeded; record marked complete with valid `fence_token`.
4. `DEAD`: Retries exceeded `max_retries` due to persistent external failures. Stored in dead-letter table for inspection and manual operator replay via `outbox.replay_dead_letter(record_id)`.
5. `COMPENSATING`: Forward compensation workflow has been triggered.
6. `COMPENSATED`: Forward compensation succeeded (e.g. order marked cancelled, alerting operations).
7. `COMPENSATION_FAILED`: Compensation handler failed; flagged for immediate human operational review.

### 4. Tenant Isolation & Handler Version Compatibility
- Outbox records carry `tenant_id: str | None`. Workers claiming batches filter and process records within tenant boundaries.
- Payloads carry `version: int` (default 1) enabling forward and backward schema evolution across rolling application deployments.

## Consequences
- **Positive:** Guarantees at-least-once external event dispatch without dual-write inconsistencies.
- **Positive:** Clear boundary between local ACID rollback and asynchronous forward compensation.
- **Positive:** Dead-letter auditing and manual replay tooling for failed operations.
- **Boundaries:** Downstream external endpoints must support and enforce idempotency keys to eliminate duplicate operations on network retries.
- **Trade-off:** High-volume outbox tables require periodic pruning of records in terminal `COMPLETED` or `COMPENSATED` states.
