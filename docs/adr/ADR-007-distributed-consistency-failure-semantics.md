# ADR-007: Distributed Consistency & Failure Semantics

## Status
Accepted (v1.0.0 Production Engineering Specification)

## Context
A distributed application runtime composed of web workers, background dispatchers, state stores (Redis/PostgreSQL), and network streams can experience partial or total failure across any individual subsystem.

Without explicit contracts for failure modes, distributed systems suffer from split-brain state, silent data loss, cascading latency spikes, or phantom updates.

## Decision

### 1. Subsystem Failure Matrix

| Subsystem | Failure Mode | Default Policy | Behavior & Recovery Contract |
| :--- | :--- | :--- | :--- |
| **State Backend (Redis)** | Connection dropped / timeout | **Fail-Closed** | Raises `StateBackendUnavailableError`. Rejects mutations to prevent split-brain. (Optional `allow_fallback=True` for single-node dev only). |
| **Idempotency Backend** | Node crash / network partition | **Fail-Closed** | Raises `IdempotencyBackendUnavailableError`. Returns HTTP 503 with `Retry-After: 2`. Mutations are safely preserved in client IndexedDB. |
| **PostgreSQL Pool** | Connection exhaustion (`max_size`) | **Fail-Fast** | Waits up to `timeout=30.0s`. If exhausted, raises `PoolTimeout` and returns HTTP 503 rather than queuing indefinitely. |
| **Outbox Dispatcher** | External downstream service 5xx / timeout | **Retry & Compensate** | Retries with exponential backoff and jitter. If retries exceed `max_retries`, transitions to `DEAD` and triggers forward compensation workflows. |
| **SSE Stream** | Redis Pub/Sub dropped notification | **Self-Healing** | Durable storage is authoritative. Stream performs periodic sync checks every 15s against durable high-watermark, self-healing dropped wakeup signals. |
| **Worker Process** | Sudden SIGKILL / OOM crash | **Lease Recovery** | Other workers reclaim uncompleted outbox and idempotency leases upon TTL expiry using monotonic fencing tokens. |

### 2. Split-Brain Prevention Guarantees
- **Lease Fencing:** Monotonic fencing tokens (`fence_token`) ensure that a partition-isolated worker cannot commit state or complete an outbox record once its lease has expired and been reclaimed by another worker.
- **Fail-Closed State Updates:** Redis state partitions refuse in-memory fallback during production outages, preventing diverging state across separate worker nodes.

### 3. Consistency Tiers by Backend Configuration
RADUI classifies runtime consistency into three deployment tiers:
- **Tier 1 (Single Host / SQLite):** Full ACID consistency for local state, outbox, and jobs via SQLite WAL mode and serialized transactions.
- **Tier 2 (PostgreSQL Production Cluster):** Linearizable monotonic sequence allocation, row-level locking (`SELECT ... FOR UPDATE`), transaction-local Row-Level Security, and atomic outbox commits.
- **Tier 3 (Redis Hybrid Cluster):** High-throughput reactive caching and distributed Pub/Sub notifications with fail-closed lease fencing. Strict failover monotonicity requires PostgreSQL sequence pairing or synchronous replication (`WAIT`).

## Consequences
- **Positive:** Deterministic failure handling across all infrastructure dependencies.
- **Positive:** Eliminates silent data divergence through fail-closed policies on shared state.
- **Positive:** Automatic lease reclamation and self-healing stream delivery after worker or network recovery.
- **Trade-off:** High-availability deployments require redundant PostgreSQL and Redis topologies with health check monitoring.
