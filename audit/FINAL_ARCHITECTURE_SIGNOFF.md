# RADUI Framework: Final Architecture Sign-Off & Implementation Roadmap

**Document:** RADUI Core Architecture Formal Sign-Off  
**Target Milestone:** RADUI UI (`RADUI-ui`) v1.0.0 Production Release  
**Status:** APPROVED FOR IMPLEMENTATION PLANNING — Pre-Implementation Sign-Off  
**Review Board:** Principal Software Architect, Staff Systems Engineer, Security & Product Review Board  
**Date:** November 2026

---

## 1. Executive Summary of Final Accepted Architectural Decisions

The comprehensive audit and reconciliation phase is complete. The review board has officially signed off on the following five foundational Architecture Decision Records (ADRs):

### Decision 1: Registry-Driven Component Extensibility & Dynamic Typed AST Validation (ADR 001)
- **Problem Solved:** Resolves `BUG-COMP-REG-01`. In v0.9.0, built-in container nodes (`Column`, `Row`, `Card`, `Container`) typed `children` as a closed Pydantic union of 68 built-ins (`Element`), causing any third-party component registered in `ComponentRegistry` to crash on instantiation.
- **Architectural Solution:** Container `children` are updated to `tuple[Component, ...] = ()`. Compile-time union checking is replaced by dynamic, typed allowlist validation inside `ComponentRegistry.validate(root)`. Unregistered components fail fast with `UnregisteredComponentError`.
- **Lossless IR Roundtrip:** Custom subclass attributes (e.g. specialized theme configs, data series, custom columns) survive JSON serialization and deserialization via registry-directed model validation (`definition.model.model_validate(data)`).
- **Safety Boundary:** Explicitly rejects unrestricted `Any` (destroys typing) and `raw_html` (creates catastrophic XSS vulnerabilities).

### Decision 2: Reactive Persistent Layout Execution & Subtree Invalidation (ADR 002)
- **Problem Solved:** Resolves `BUG-LAYOUT-CTX-01`. Layout shells executed outside `state_context.activate()`, crashing state reads in navigation bars and application shells.
- **Architectural Solution:** Encapsulate layout execution within the active `StateContext`. Each layout shell is assigned a deterministic component ID (`gx-layout-{prefix}`). Dependencies read by a layout are tracked independently from `_PAGE_COMPONENT_ID`.
- **Surgical Morphing Preserved:** Mutating layout-bound state updates only the layout DOM over SSE; mutating page-bound state updates only the page body. Nested layouts maintain independent dependency tracking.

### Decision 3: Framework-Level Multi-Tenant Security & 5-Tier Scope Hierarchy (ADR 003)
- **Problem Solved:** Multi-tenancy in v0.9.0 only prefixed state keys, leaving cache, jobs, chat, outbox, and events unpartitioned and failing open. Furthermore, `app` scope was ambiguous.
- **Architectural Solution:** Formalize the 5-tier scope hierarchy:
  * `view`: Ephemeral component instance.
  * `session`: Per-browser session.
  * `user`: Scoped to `(tenant_id, user_id)` to prevent cross-organization privilege escalation. Fails closed if unauthenticated.
  * `tenant`: Shared across all sessions/users within one tenant. Fails closed (`TenantRequiredError` / HTTP 403) if `tenant_id` is missing.
  * `app`: Application-global singleton across all tenants. Read-only for tenant sessions; mutable only via admin/startup. Consistency is backend-dependent (process-local on Memory, single-host on SQLite, distributed only on Redis).
- **Universal Framework-Level Partitioning:** The framework itself derives and enforces tenant namespaces internally across:
  * State storage keys
  * `QueryCache` entries and invalidation tags
  * Background jobs (`JobSnapshot.tenant_id`) and `JobPanel` access/cancellation
  * Idempotency reservations
  * `SQLiteChatRepository` thread and message queries
  * `TransactionalOutbox` event dispatch
  * `EventBroker` SSE subscriptions and replay streams
  * Inspector traces
- **Zero Developer Prefix Burden:** Developers call standard APIs (`gx.query("kpis")`); RADUI partitions namespaces internally.
- **Safe DB Migration:** Historical chat and outbox records migrate to `tenant_id = '_default'` via automated schema migration.

### Decision 4: Standalone Action Buttons Decoupled from Forms (ADR 004)
- **Problem Solved:** Standalone buttons outside `<form>` raised runtime validation errors, forcing boilerplate forms for simple click actions.
- **Architectural Solution:** Standalone `Button` components with `command="..."` are valid AST nodes. They render with `data-gx-command` and `data-gx-csrf`. Clicks dispatch commands directly to the server via `client.js`. Input fields retain mandatory form encapsulation for coherent batch submission.

### Decision 5: Public ASGI Middleware Pipeline & Bounded Event Buffers (ADR 005)
- **Problem Solved:** Hardcoded `SessionMiddleware` in `App.asgi()` provided zero public API for CORS, Prometheus, GZip, or security headers. In-memory SSE queues were unbounded.
- **Architectural Solution:** Add `app.add_middleware(middleware_class, **options)`. Enforce a bounded ring-buffer (500 events per session) with drop-oldest semantics in `InMemoryEventBackend` to eliminate memory leak risks from slow clients.

---

## 2. Explicit "What NOT to Build" Scope Boundaries

To prevent architectural scope creep, the following features are **strictly excluded from v1.0.0**:

| Excluded Feature | Strategic Rationale | Target Milestone |
|---|---|---|
| **Multi-Stage Task DAG Workflow Engine (Airflow/Taipy style)** | Asynchronous worker queues (`@app.job`) with leases and heartbeats are fully sufficient for 95% of web platforms. Workflow DAGs introduce massive graph resolution complexity with minimal initial value. | **v1.2.0+ (Only if proven demand)** |
| **Native Bi-Directional WebSocket Transport** | SSE paired with HTTP POST is clean, firewall-friendly, and lightweight. WebSockets introduce stateful proxy pinning, connection recovery headaches, and load balancer friction. | **v1.2.0 (Post-benchmark evaluation)** |
| **Unrestricted `raw_html` Escape Hatches** | Bypassing the typed component AST destroys type safety, breaks IR parsing, and creates severe XSS vulnerabilities with LLM generative UI. | **Permanently Rejected** |
| **Premature PostgreSQL Clustering Infrastructure** | RADUI's immediate market strength is single-node/container deployments using SQLite WAL mode and Redis state/idempotency. Completing full distributed PostgreSQL failovers before single-node is perfected is a classic premature optimization trap. | **v1.1.0** |

---

## 3. Implementation Sequence & Task Dependencies

Implementation must proceed in strict dependency order:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   v1.0.0 IMPLEMENTATION SEQUENCE                       │
├────────────────────────────────────────────────────────────────────────┤
│ STEP 1: Tenant Security & Context Propagation Foundation (P0)          │
│  ├── 1.1: Implement 5-tier scope hierarchy (refs.py, runtime.py)       │
│  ├── 1.2: Enforce fail-closed resolution & blocked untrusted headers   │
│  ├── 1.3: Framework-level internal partitioning in QueryCache         │
│  ├── 1.4: Partition JobBackend, chat schema, outbox, and EventBroker   │
│  └── 1.5: Safe DB migration scripts for historical records             │
├────────────────────────────────────────────────────────────────────────┤
│ STEP 2: Registry-Driven Component Extensibility (ADR 001) (P0)         │
│  ├── 2.1: Update container children to tuple[Component, ...]          │
│  ├── 2.2: Dynamic registry allowlist validation in registry.py        │
│  ├── 2.3: Lossless IR serialization/deserialization of custom fields   │
│  └── 2.4: Multi-app registry isolation & duplicate kind rejection      │
├────────────────────────────────────────────────────────────────────────┤
│ STEP 3: Reactive Persistent Layouts & Subtree Invalidation (ADR 002) (P0)│
│  ├── 3.1: Encapsulate layouts inside StateContext execution            │
│  ├── 3.2: Deterministic layout IDs (gx-layout-{prefix})                │
│  ├── 3.3: Independent layout subtree dependency tracking in runtime.py │
│  └── 3.4: Verify selective SSE patch emission (layout vs page)        │
├────────────────────────────────────────────────────────────────────────┤
│ STEP 4: Developer Experience & Signature Normalization (ADR 004) (P1)   │
│  ├── 4.1: Standalone Button with command attribute outside Form        │
│  ├── 4.2: Client.js click dispatcher for standalone buttons            │
│  └── 4.3: Normalize input, select, and form positional/keyword args    │
├────────────────────────────────────────────────────────────────────────┤
│ STEP 5: Middleware Pipeline & Transport Reliability (ADR 005) (P1)     │
│  ├── 5.1: Expose app.add_middleware() on App and compile into asgi()   │
│  └── 5.2: Implement bounded ring-buffer (500 events) for SSE queues    │
├────────────────────────────────────────────────────────────────────────┤
│ STEP 6: Final Release Validation & Quality Gate Verification (v1.0)    │
│  ├── 6.1: Run 201 core unit/integration tests (zero regressions)       │
│  ├── 6.2: Run multi-tenant concurrent isolation attack test suite      │
│  ├── 6.3: Run custom component lossless IR roundtrip test suite        │
│  ├── 6.4: Run selective layout SSE patch roundtrip test suite          │
│  └── 6.5: Publish standardized benchmark harness and memory soak test  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Acceptance Criteria & Release Blockers

### 4.1. Absolute Release Blockers (Any Occurrence Halts Release)
1. **Any Cross-Tenant Leakage:** Any test where Tenant B accesses Tenant A's state, query cache, jobs, chat threads, or events immediately halts the release.
2. **Custom Component Subclass Field Loss:** Any custom component subclass that loses attributes during IR serialization/deserialization halts the release.
3. **Layout State Context Crash:** Any `RuntimeError: StateRef can only be read inside an active StateContext` in a layout shell halts the release.
4. **Core Regression:** Any failure in the baseline 201 automated tests halts the release.

### 4.2. Acceptance Test Matrix Summary
- **Multi-Tenant Security:** 10+ concurrent test scenarios verifying fail-closed behavior, untrusted header rejection, cache partition isolation, job isolation, and event broker topic filtering.
- **Component Extensibility:** Custom components with 5+ custom fields render inside nested `Column`/`Row` containers and survive IR JSON round-trips.
- **Layout Reactivity:** Verified that updating layout state emits an SSE patch targeting strictly the layout ID, leaving the page root untouched.
- **Standalone Actions:** Standalone buttons dispatch commands and update reactive state without form wrappers.
- **Middleware:** Custom ASGI middleware executes cleanly after `SessionMiddleware`.

---

## 5. Remaining Risks & Unresolved Technical Questions

### 5.1. Remaining Operational Risks
1. **SQLite Write Contention Under High Load:** SQLite WAL mode handles concurrent readers gracefully, but high write bursts (>500 writes/sec) can cause `busy_timeout` errors. For high-scale deployments, single-node architectures must use Redis state/idempotency backends.
2. **Distributed Runtime Maturity:** While single-node SQLite WAL mode is mature and rock-solid, distributed multi-node clustering (PostgreSQL state/events) remains a stubbed target for v1.1.0.
3. **WAN Latency on Server-Driven Roundtrips:** Because RADUI executes interactions on the server, high-latency WAN links (>150ms) cause perceptible button lag unless `optimistic=True` is configured.

### 5.2. Unresolved Technical Questions (Deferred to v1.1.0/v1.2.0)
1. **Distributed Event Fan-Out:** When scaling to multiple server nodes, what is the optimal event distribution backbone? (Redis Streams vs. NATS vs. Kafka).
2. **Client-Side Micro-Interactions:** Should simple client-side toggles (accordion expand, modal open) be handled via Alpine.js integration or declarative attributes in `client.js`? (Deferred to v1.2.0).

---

## 6. Pre-Implementation Sign-Off

The audit, reconciliation, ADR specifications, and release criteria are **fully reconciled, aligned, and approved**. 

**No framework code has been modified.** 

Implementation can now begin according to the v1.0.0 implementation sequence, starting with **Step 1 (Tenant Security & Context Propagation Foundation)** and **Step 2 (Registry-Driven Component Extensibility)**.
