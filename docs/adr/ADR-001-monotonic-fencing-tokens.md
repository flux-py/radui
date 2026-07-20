# ADR-001: Monotonic Fencing Tokens, Failover Guarantees & Resource-Level Fencing

## Status
Accepted (v1.0.0 Production Engineering Specification)

## Context
In distributed multi-worker deployments, a worker processing an idempotency reservation may pause due to GC pauses, CPU starvation, or network partitions. If its lease expires in Redis or PostgreSQL, another worker might acquire the lease for the same action ID.

If the first worker subsequently wakes up and attempts to commit its results without fencing, it can overwrite newer state, causing split-brain anomalies and phantom overwrites.

Validating `owner_id` and `fence_token` exclusively inside the idempotency backend only protects the reservation record itself. It does not automatically prevent a delayed worker from mutating downstream business databases (such as orders, accounts, or inventory tables).

Furthermore, in distributed caching systems like Redis, standard asynchronous replication does not guarantee monotonicity across failover: if a primary crashes before replicating an `INCR` command to its replica, the newly promoted replica may re-allocate the same sequence number.

## Decision

### 1. Authoritative Monotonic Token Allocation
- **PostgreSQL (Authoritative Monotonic Backend):** For multi-worker deployments requiring strict linearizable monotonicity across failovers, PostgreSQL native database sequences (`CREATE SEQUENCE gx_fence_seq; SELECT nextval('gx_fence_seq')`) serve as the authoritative allocator. Sequence increments are atomic, non-transactional, and strictly monotonic, ensuring tokens never decrement or repeat even across node crashes or rolled-back transactions.
- **Redis (Best-Effort Steady-State Backend):** In Redis, sequence numbers are allocated using atomic `INCR` operations on cluster keys (`gx:seq:fencing`). Under standard asynchronous replication, Redis provides monotonicity during steady-state operation, but does not guarantee monotonicity across unacknowledged failover unless configured with synchronous replication (`WAIT`) or linearizable consensus (e.g. Redis Raft).
- **SQLite (Single-Host WAL Backend):** Increments are serialized using atomic database transactions and WAL write locks.

### 2. Token Scoping
RADUI distinguishes two scopes of fencing tokens:
- **Global Cluster Fencing Counter:** Monotonically increasing counter providing a total ordering across all cluster events and worker claims.
- **Action Lease Generation Token:** Monotonically increasing generation number scoped to a specific action reservation (`action_id`), incremented on each initial acquisition or lease reclaim.

### 3. Resource-Level Fencing Pattern
Fencing tokens are propagated to application code via `CommandContext.fence_token`. To prevent stale workers from mutating business resources while allowing an active worker holding a valid lease to perform multiple sequential operations within one transaction, application SQL queries MUST use the dual-condition pattern:

```sql
UPDATE orders
SET status = :status,
    total_cents = :total,
    last_fence_token = :fence_token,
    owner_id = :owner_id
WHERE id = :order_id
  AND (
      last_fence_token < :fence_token 
      OR (last_fence_token = :fence_token AND owner_id = :owner_id)
  );
```

- If `cursor.rowcount == 0`, the worker detects that its write has been superseded by another worker, immediately rolls back its transaction, and raises `StaleLeaseError`.
- If `cursor.rowcount == 1`, the write succeeds. Subsequent updates by the same worker within the same active lease remain valid under `last_fence_token = :fence_token AND owner_id = :owner_id`.

## Consequences
- **Positive:** Eliminates split-brain overwrites and duplicate execution anomalies within RADUI's idempotency management.
- **Positive:** Allows sequential multi-statement mutations within a single valid worker lease while strictly fencing superseded workers.
- **Boundaries:** Redis `INCR` does not survive unacknowledged failover; deployments requiring hard monotonic durability across failover must standardize on PostgreSQL sequences.
- **Trade-off:** Workers experiencing execution stalls will fail with `StaleLeaseError` and must discard local state changes.
