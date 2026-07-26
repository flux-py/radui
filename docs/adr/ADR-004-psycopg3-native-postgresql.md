# ADR-004: Standardizing Native PostgreSQL on psycopg 3

## Status
Accepted (v1.0.0 Production Engineering Specification)

## Context
Production multi-worker deployments require a high-performance PostgreSQL driver supporting both synchronous execution (CLI migrations, startup verification, synchronous workers) and asynchronous execution (high-concurrency ASGI request handling and SSE event streaming).

Using separate drivers (such as `asyncpg` for async and `psycopg2` for sync) introduces incompatible connection types, duplicated pooling logic, and diverging dialect quirks.

## Decision

### 1. Unified Standard on psycopg 3
- Standardize all PostgreSQL backends (`PostgreSQLStateBackend`, `PostgreSQLEventBackend`, `PostgreSQLIdempotencyBackend`) on `psycopg 3` (`psycopg>=3.1` and `psycopg_pool>=3.1`).
- Provide distinct synchronous (`psycopg.Connection`) and asynchronous (`psycopg.AsyncConnection`) access paths derived from the same library.
- SQLite (`sqlite3`) and Redis (`redis-py`) remain standalone backends with distinct implementations.

### 2. Async Connection Pooling & Lifecycle Management
- Async ASGI handlers utilize `psycopg_pool.AsyncConnectionPool`:
  ```python
  AsyncConnectionPool(
      conninfo=dsn,
      min_size=2,
      max_size=20,
      timeout=30.0,
      check=AsyncConnectionPool.check_connection,
      open=False,
  )
  ```
- Connection pools are opened explicitly during application startup (`@app.on_startup`) and drained cleanly during shutdown (`@app.on_shutdown`).

### 3. Pool Exhaustion & Fail-Fast Behavior
- If concurrent demand exhausts `max_size` connections, incoming acquisition attempts wait up to `timeout=30.0s`.
- If the timeout expires without an available connection, `psycopg_pool.PoolTimeout` is raised.
- Request handlers catch `PoolTimeout` and return HTTP 503 (Service Unavailable) with `Retry-After: 1` headers to prevent server-side request stacking and deadlocks.

### 4. Connection Recovery & Health Checks
- The pool verifies connection health via `check=AsyncConnectionPool.check_connection` before leasing sockets.
- Severed or reset connections during PostgreSQL restarts or network blips are discarded and transparently reconnected without leaking pool slots.

### 5. Row-Level Concurrency Control
- PostgreSQL backends use native row-level locking:
  ```sql
  SELECT fence_token, owner_id, expires_at
  FROM gx_idempotency
  WHERE key = %s
  FOR UPDATE;
  ```
- Sequences for monotonic fencing tokens utilize PostgreSQL native sequences (`nextval('gx_fence_seq')`), ensuring strictly monotonic incrementation that never rolls back or decrements.

## Consequences
- **Positive:** Single, unified driver dependency for sync and async PostgreSQL operations.
- **Positive:** Resilient connection lifecycle with automatic healing on connection resets.
- **Positive:** Clean fail-fast degradation on pool exhaustion avoiding unbounded queue latency.
- **Trade-off:** Applications deploying distributed PostgreSQL require `psycopg[binary]>=3.1` and `psycopg-pool>=3.1`.
