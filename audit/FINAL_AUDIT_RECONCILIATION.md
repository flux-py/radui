# RADUI Framework: Final Audit Reconciliation & Ground-Truth Verification

**Audit Date:** November 2026  
**Status:** Final Pre-Implementation Reconciliation  
**Auditor:** Principal Software Architect, Staff Systems Engineer & SRE Review Board  
**Target:** RADUI UI (`RADUI-ui`) v0.9.0

---

## 1. Resolution of Contradictory Backend Findings

Previous audit drafts contained conflicting statements regarding the implementation status of distributed storage backends (Redis, PostgreSQL, SQLite) across state, jobs, idempotency, and events. This section presents the verified empirical status based on direct inspection of source code, imports, constructors, and test behaviors.

### 1.1. Backend Implementation Status Matrix

| Subsystem Category | Implementation Class | Actual File Location | External Dependency | Actual Storage Mechanism | Operational Reality & Failure Behavior | Final Status |
|---|---|---|---|---|---|---|
| **State Storage** | `InMemoryStateBackend` | `RADUI/state/backend.py:43` | None | Python `dict` + `threading.RLock` | In-memory only. Fast, thread-safe. Cleared on restart. Not multi-worker safe. | **Verified Implemented** |
| **State Storage** | `SQLiteStateBackend` | `RADUI/state/backend.py:76` | `sqlite3` (Stdlib) | SQLite table `RADUI_state` (WAL mode) | ACID durable. Multi-process safe on a single host. Retries on busy lock. | **Verified Implemented** |
| **State Storage** | `RedisStateBackend` | `RADUI/state/backend.py:177` | `redis` (Optional) | Redis Hashes (`HSET`/`HGET`/`HDEL`) | True Redis client. If `allow_fallback=False` (default) and Redis unreachable, raises `StateBackendUnavailableError`. If `allow_fallback=True`, uses `_fallback_store` dict. | **Verified Implemented** |
| **State Storage** | `PostgreSQLStateBackend` | `RADUI/state/backend.py:287` | None | **In-memory SQLite (`:memory:`)** | **PURE STUB.** Instantiates `SQLiteStateBackend(":memory:")`. Contains zero PostgreSQL/psycopg code, zero connection attempts. | **Not Implemented (Stub/Shim)** |
| **Job Execution** | `LocalJobBackend` | `RADUI/jobs/runtime.py:23` | `asyncio` (Stdlib) | In-memory `dict[str, JobSnapshot]` + `Semaphore` | In-process asyncio tasks. Clean worker pool, cancellation, and progress updates. Lost on restart. | **Verified Implemented** |
| **Job Execution** | `SQLiteJobBackend` | `RADUI/jobs/sqlite.py:25` | `sqlite3` (Stdlib) | SQLite table `RADUI_jobs` (WAL mode) | Persistent queue on disk. Multi-worker safe on single host. Fencing and leases persist. | **Verified Implemented** |
| **Job Execution** | `RedisJobBackend` | `RADUI/jobs/redis.py:30` | `redis` (Optional) | In-memory `LocalJobBackend` + Redis Lease Keys | **HYBRID/PARTIAL.** Subclasses `LocalJobBackend`. Job queue/tasks execute in local process memory. Only lease acquisition (`acquire_lease`/`validate_fence`) attempts to contact Redis. Falls back to local counter if Redis missing. | **Partially Implemented (Lease Only)** |
| **Idempotency** | `InMemoryIdempotencyBackend`| `RADUI/core/idempotency.py:102`| None | Python `dict` + `RLock` | In-memory fingerprint and response cache with lease expiration. | **Verified Implemented** |
| **Idempotency** | `SQLiteIdempotencyBackend` | `RADUI/core/idempotency.py:214`| `sqlite3` (Stdlib) | SQLite table `gx_idempotency` (WAL mode) | Full ACID deduplication, fencing tokens, and lease renewal. | **Verified Implemented** |
| **Idempotency** | `RedisIdempotencyBackend` | `RADUI/core/idempotency.py:442`| `redis` (Optional) | Redis Hashes + Atomic Lua Scripts | True Redis implementation. Contains `LUA_COMPLETE`, `LUA_FAIL`, `LUA_RENEW` scripts for atomic lease validation. Raises if unreachable and no fallback. | **Verified Implemented** |
| **Idempotency** | `PostgreSQLIdempotencyBackend`| `RADUI/core/idempotency.py:726`| `psycopg[pool]>=3.2` | PostgreSQL table + `AsyncConnectionPool` | True PostgreSQL implementation using psycopg 3. Requires PostgreSQL server. Raises `IdempotencyBackendUnavailableError` if driver or DB missing. | **Verified Implemented** |
| **Transport Events**| `InMemoryEventBackend` | `RADUI/transport/events.py:48` | None | Python `deque` per session/topic | In-memory SSE dispatch. Unbounded queue growth risk under slow clients. | **Verified Implemented** |
| **Transport Events**| `SQLiteEventBackend` | `RADUI/transport/events.py:146`| `sqlite3` (Stdlib) | SQLite table `RADUI_events` (WAL mode) | Persistent events. Poll-based SSE dispatch. Multi-process safe on single host. | **Verified Implemented** |
| **Transport Events**| `RedisEventBackend` | `RADUI/transport/events.py:260`| `redis` (Optional) | Redis Streams / PubSub | Implemented using Redis client. Fans out across workers. Falls back if configured. | **Verified Implemented** |
| **Transport Events**| `PostgreSQLEventBackend` | `RADUI/transport/events.py:380`| None | **SQLite (`:memory:`)** | **PURE STUB.** Subclasses `SQLiteEventBackend` and defaults to `:memory:`. No PostgreSQL connectivity. | **Not Implemented (Stub/Shim)** |
| **Transactional Outbox**| `TransactionalOutbox` | `RADUI/core/outbox.py:69` | `sqlite3` (Stdlib) | SQLite table `gx_outbox` (WAL mode) | ACID outbox insert in active transaction. Background polling thread, exponential backoff, compensation callbacks. **Provides at-least-once delivery, NOT exactly-once.** | **Verified Implemented (SQLite Only)** |

---

## 2. Tenant Isolation and State Scope Semantics Audit

### 2.1. The Ambiguity of `app` Scope and the Missing `tenant` Scope
In RADUI v0.9.0, `RADUI/state/refs.py` defines:
```python
StateScope = Literal["view", "session", "user", "app"]
```
Key derivation in `StateRef._state_key(context)` behaves as follows:
```python
prefix = f"{context.tenant_id}:" if context.tenant_id else ""
if self.scope == "app":
    return f"{prefix}{self.key}"
```
This produces an architectural contradiction:
1. When `tenant_id` is present, `app` scope is **partitioned by tenant** (`tenant-1:app_setting`).
2. When `tenant_id` is `None`, `app` scope is **shared globally** (`app_setting`).
3. There is **no distinct scope** for state that should truly be shared globally across the entire cluster (e.g. system maintenance mode, global feature toggles, platform telemetry) versus state that should be shared across all users within a single tenant.

### 2.2. Failure to Fail Closed When `tenant_id` is Omitted or Spoofed
In `App._state_context` (`RADUI/core/app.py:800-822`):
- If `_tenant_id_resolver` is configured, it resolves `tenant_id`.
- If untrusted headers are allowed or no resolver is set, a request without a tenant header gets `tenant_id = None`.
- **Vulnerability:** When `tenant_id` is `None`, the application does not fail closed. Instead, it reads and writes to the **unpartitioned global namespace**. A malicious or misconfigured tenant client omitting the tenant header can accidentally overwrite or read unpartitioned baseline state.

### 2.3. Systemic Lack of Tenant Partitioning Across Subsystems
Multi-tenancy in RADUI v0.9.0 was implemented **only in `StateRef._state_key`**. It is completely absent from all other data and execution subsystems:

| Subsystem | File & Class | Tenant Partitioning Status | Security Risk / Cross-Tenant Leakage Vector |
|---|---|---|---|
| **Data Query Cache** | `RADUI/data/query.py:45` (`QueryCache`) | **Zero Partitioning** | `QueryCache.get(key)` uses raw string keys. If Tenant Alpha queries `gx.query("recent_orders", ...)`, Tenant Beta querying `"recent_orders"` receives Tenant Alpha's cached data! |
| **Background Jobs** | `RADUI/jobs/contracts.py:42` (`JobSnapshot`) | **Zero Partitioning** | `JobSnapshot` has no `tenant_id` field. Jobs run in a shared global worker pool. A tenant can view or cancel another tenant's background jobs by ID. |
| **Chat Persistence** | `RADUI/ai/persistence.py:32` (`RADUI_chat_messages`) | **Zero Partitioning** | SQLite table schema has `(id, thread_id, role, content, metadata_json, created_at)`. No `tenant_id` column. Any tenant guessing or sharing a `thread_id` accesses other tenants' conversations. |
| **Transactional Outbox** | `RADUI/core/outbox.py:98` (`gx_outbox`) | **Zero Partitioning** | `gx_outbox` table has no `tenant_id` column. Cross-tenant event dispatch cannot be audited or scoped. |
| **Event Broker** | `RADUI/transport/events.py:48` (`EventBroker`) | **Zero Partitioning** | Topics are global. Broadcast events are visible to any client subscribed to that topic across tenants. |

### 2.4. Definitive Scope Architecture Recommendation
To achieve enterprise multi-tenancy, RADUI must establish an explicit 5-scope model and a strict fail-closed contract:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        DEFINITIVE SCOPE HIERARCHY                      │
├───────────┬──────────────────────────────────┬─────────────────────────┤
│ Scope     │ Intended Semantics               │ Fail-Closed Contract    │
├───────────┼──────────────────────────────────┼─────────────────────────┤
│ view      │ Ephemeral component/page state   │ None (always permitted) │
│ session   │ Per-browser-session state        │ Requires session_id     │
│ user      │ Per-authenticated-user state     │ Requires user_id        │
│ tenant    │ Shared within single tenant      │ Requires tenant_id      │
│ app       │ Globally shared process/cluster  │ Cluster-wide singleton  │
└───────────┴──────────────────────────────────┴─────────────────────────┘
```
**Fail-Closed Rule:** Any attempt to read or write a `tenant`-scoped state reference, query, job, or chat thread when `context.tenant_id is None` must immediately raise `TenantRequiredError` (HTTP 403 Forbidden).

---

## 3. Component Verification & Rule Inventory Correction

Previous reports contained inconsistent counts regarding components subject to structural validation rules. The exact ground truth from `RADUI/core/app.py:600-640` is:

### 3.1. Components Required to be Inside `<Form>` (7 Types)
The following **7 component types** will raise `ValueError("... must be placed inside a Form")` if rendered outside a `Form` node:
1. `Button` (`RADUI/core/app.py:610`)
2. `Input` (via `_FORM_CONTROL_TYPES`)
3. `Checkbox` (via `_FORM_CONTROL_TYPES`)
4. `Textarea` (via `_FORM_CONTROL_TYPES`)
5. `Select` (via `_FORM_CONTROL_TYPES`)
6. `Switch` (via `_FORM_CONTROL_TYPES`)
7. `RadioGroup` (via `_FORM_CONTROL_TYPES`)

*Note:* `_FORM_CONTROL_TYPES = (Input, Checkbox, Textarea, Select, Switch, RadioGroup)` (`RADUI/core/app.py:47`). Including `Button`, exactly **7 component types** require form encapsulation.

### 3.2. Components Requiring Registered Commands or Stable IDs (5 Types)
The following **5 component types** undergo command registry validation during `App._validate_commands`:
1. `Form`: Command must exist in `self._commands`; nested forms forbidden (`app.py:604-608`).
2. `JobPanel`: `job_name` must exist in `self._jobs`; requires stable `id` (`app.py:614-617`).
3. `ActionCard`: `approve_command` (and `reject_command` if present) must exist in `self._commands` (`app.py:618-621`).
4. `Diagram`: `on_node_click` (if present) must exist in `self._commands` (`app.py:622-624`).
5. `TreeView`: `on_select_command` (if present) must exist in `self._commands` (`app.py:625-627`).

---

## 4. Reclassification of Unsupported Claims

Every promotional or unverified statement from earlier audit drafts has been audited against reproducible benchmark code and hard evidence.

| Claim | Initial Audit Phrasing | Ground-Truth Finding | Reclassified Status |
|---|---|---|---|
| **Single-Node Readiness** | "A- Production Ready" | SQLite WAL mode and local jobs work well, but memory event buffer is unbounded, SQLite write contention spikes under >500 writes/sec, and in-memory session loss occurs on default backend. | **Partially Verified (Conditional on SQLite WAL & Low-Write Workloads)** |
| **Multi-Node Scalability** | "C+ Production Readiness" | `PostgreSQLStateBackend` and `PostgreSQLEventBackend` are in-memory SQLite stubs. `RedisJobBackend` only manages leases, keeping task queues in local memory. Cross-worker SSE sync is unverified. | **Unverified / Incomplete (Stubbed Infrastructure)** |
| **Cross-Tenant Security** | "Mathematical isolation prevents leaks" | State key prefixing works when `tenant_id` is supplied, but omitting tenant ID writes to unpartitioned space. QueryCache, Jobs, Chat, Outbox, and Events have **zero** tenant partitioning. | **Partially Verified (State Keys Only); Incorrect (Subsystems Unpartitioned)** |
| **Initial Load TTI (<20ms)** | "< 20ms initial TTI" | Measured on local loopback via TestClient on modern multicore CPU. Does not account for real WAN latency, TLS negotiation, or client browser rendering. | **Unverified (Local TestClient Probe Only)** |
| **State Patch Compute (<10ms)** | "< 10ms state patch computation" | Microbenchmark Tier 5 measures AST diffing at 0.25 - 0.90 ms server compute. True on server; ignores network transit. | **Verified (Server-Side Microbenchmark Only)** |
| **Memory per Session (~15KB)** | "~15KB per active session" | Estimated based on small session dictionary sizes in tests. No systematic memory heap profiling under 1,000+ active browser sessions. | **Unverified (Lacks Heap Profiling)** |
| **10,000-Request Soak Test** | "10,000-request soak test stability" | `test_gate4_benchmarks_soak.py` contains 50 concurrent idempotency lease workers and 500-iteration microbenchmarks. **No 10,000-request sustained load test exists.** | **Incorrect (Extrapolated From 500-Iteration Microbenchmarks)** |
| **Competitor Superiority** | "Vastly outperforms Streamlit, Reflex, FastHTML" | Architectural comparisons are valid conceptually, but no identical hardware, pinned version, or side-by-side benchmark runs were conducted. | **Qualitative Architectural Comparison (Not Formally Benchmarked)** |
| **Exactly-Once Delivery** | "Guarantees exactly-once mutation delivery" | `TransactionalOutbox` provides at-least-once delivery with retries. True exactly-once requires downstream consumer deduplication. | **Incorrect (At-Least-Once Delivery Only)** |
| **Developer Productivity** | "97 LOC in 10 mins, 258 LOC in 45 mins" | Represents informal authoring speed of an experienced framework architect during this audit session. Not a controlled user study. | **Informal Authoring Case Study (Not Controlled Metric)** |

---

## 5. Summary of Pre-Implementation Resolutions

1. **Backends:** Stop claiming distributed PostgreSQL support. Acknowledge that RADUI is currently a single-node SQLite-first platform with partial Redis leasing.
2. **Multi-Tenancy:** Shift from advertising multi-tenant security to implementing a strict, fail-closed contract that partitions QueryCache, Jobs, Chat, and Outbox.
3. **Components:** Replace the closed Pydantic union with registry-driven dynamic validation; do NOT resort to unrestricted `Any` or `raw_html`.
4. **Layouts:** Wrap layout execution in `StateContext` with distinct layout component IDs to preserve surgical DOM diffing.
5. **Benchmarks:** Retire informal performance claims (<20ms, 10k soak) until a standardized, reproducible load harness is published.
