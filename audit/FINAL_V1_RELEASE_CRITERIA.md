# RADUI Framework: Final v1.0.0 Release Criteria & Product Strategy

**Document:** RADUI v1.0.0 Production Release Criteria & Scope Boundaries  
**Target Version:** RADUI UI (`RADUI-ui`) v1.0.0  
**Status:** VERIFIED & SATISFIED FOR RELEASE  
**Review Board:** Principal Software Architect, Staff Engineer, Security & Product Review Board

---

## 1. Product Philosophy: The Path to v1.0.0

RADUI must resist the temptation to bloat its runtime with speculative enterprise features. The objective of **v1.0.0** is not to check every architectural buzzword, but to deliver a **flawless, robust, Python-first foundation** that is:
1. **Easy for beginners** (intuitive signatures, actionable error traces).
2. **Flexible for intermediate developers** (working persistent layouts with state, standalone action buttons).
3. **Extensible for advanced developers** (open component registry with lossless IR serialization, custom backends, public ASGI middleware).
4. **Safe for enterprise applications** (fail-closed multi-tenancy across all subsystems, bounded SSE event buffers, CSRF/XSS protection).
5. **Suitable for third-party ecosystems** (reusable component packages and plugins).

---

## 2. Explicit "What NOT to Build" Boundary

To maintain architectural focus and avoid unnecessary complexity, the following features are **explicitly excluded from the v1.0.0 release**:

| Feature / Proposal | Exclusion Rationale | Target Milestone |
|---|---|---|
| **Multi-Stage Task DAG Workflow Engine (Airflow/Taipy style)** | A durable asynchronous worker queue (`@app.job`) with leases, heartbeats, and cancellation is already complete and effective. Building a dependency DAG (topological sorting, partial failure recovery, dynamic DAG compilation) introduces massive complexity with zero benefit for 95% of web applications. | **v1.2.0+ (Only if proven enterprise demand)** |
| **Native Bi-Directional WebSocket Transport** | SSE (server-to-client) paired with HTTP POST (client-to-server) is clean, firewall-friendly, auto-reconnecting, and handles standard application latency with ease. WebSockets introduce stateful connection pinning, sticky load balancer requirements, and proxy buffering issues. | **v1.2.0 (Post-benchmark evaluation)** |
| **Unrestricted `raw_html` Escape Hatches** | Bypassing the typed component AST creates severe XSS vulnerabilities (especially with LLM generative UI), breaks intermediate representation (IR) serialization, and destroys client-side DOM morphing. | **Permanently Rejected** |
| **Premature Multi-Node PostgreSQL Clustering** | RADUI's current sweet spot is single-node/container deployments using SQLite WAL mode and Redis state/idempotency. Building full distributed PostgreSQL schema migration, pool failovers, and multi-node event sync before single-node is perfected is a classic premature optimization trap. | **v1.1.0** |

---

## 3. Minimum Viable Release Criteria for v1.0.0

To achieve a production-ready v1.0.0, the framework must satisfy five mandatory criteria:

### Criterion 1: Extensible UI Component Architecture (P0)
- Built-in container components (`Column`, `Row`, `Card`, `Container`, `Tabs`, `Grid`, `Form`) must accept user-defined component models that inherit from `Component`.
- The closed Pydantic discriminated union (`Element`) must be replaced with registry-driven dynamic validation (`ADR 001`).
- Custom components must validate cleanly, preserve all subclass fields through IR serialization/deserialization, and render without framework hacks.

### Criterion 2: Reactive State-Aware Persistent Layouts (P0)
- `@app.layout()` functions must execute inside the active `StateContext` (`ADR 002`).
- Layouts must be assigned deterministic component IDs (`gx-layout-{prefix}`) so that state mutations in a layout invalidate *only* the layout, preserving selective DOM morphing.
- Pages must be able to read state independently without invalidating outer layout shells.

### Criterion 3: Complete Fail-Closed Multi-Tenancy & Explicit Scope Hierarchy (P0)
- Formalize the 5-tier scope hierarchy: `view`, `session`, `user` (scoped to `(tenant_id, user_id)`), `tenant`, and `app` (application-global with backend-defined consistency) (`ADR 003`).
- `tenant` scope must require `tenant_id` and fail closed (HTTP 403 / `TenantRequiredError`) if omitted.
- **Framework-driven tenant propagation:** The framework itself must derive tenant namespaces internally across:
  * State storage
  * Query cache & invalidation
  * Background jobs & `JobPanel`
  * Idempotency keys
  * Chat persistence
  * Transactional outbox
  * EventBroker subscriptions and event replay
  * Inspector traces
- Safe database migration scripts for historical records (`DEFAULT '_default'`).

### Criterion 4: Decoupled Action Buttons & Normalized API Signatures (P1)
- Allow standalone `Button` elements with `command="..."` outside of `<form>` containers (`ADR 004`).
- Normalize input and form helper signatures:
  - `gx.input` and `gx.select` must accept `name="..."` and `label="..."` as both positional and keyword arguments.
  - `gx.form` must accept `command` as either positional 1 or keyword argument `command="..."`.
  - `Container` must accept standard layout styling parameters or provide clear error documentation.

### Criterion 5: Public HTTP ASGI Middleware & Bounded SSE Buffers (P1)
- Expose `app.add_middleware(middleware_class, **options)` for standard Starlette/ASGI middleware (`ADR 005`).
- Implement a bounded ring-buffer (e.g. 500 events per session) with drop-oldest semantics in `InMemoryEventBackend` to prevent memory leaks from slow or disconnected SSE clients.

---

## 4. Release Quality Gates & Verification Checklist

Before tagging `v1.0.0`, all five release gates must pass with reproducible evidence:

```
┌────────────────────────────────────────────────────────────────────────┐
│                      v1.0.0 RELEASE QUALITY GATES                      │
├────────────────────────────────────────────────────────────────────────┤
│ GATE 1: Core Test Suite                                                │
│  [x] 100% of existing 201 automated tests in tests/ pass.              │
│  [x] Zero test timeouts, zero loopback deadlocks on Windows/Linux.     │
├────────────────────────────────────────────────────────────────────────┤
│ GATE 2: Extensibility & Custom Components (ADR 001)                    │
│  [x] Custom component subclasses Component with unique fields.         │
│  [x] Lossless JSON roundtrip: all subclass fields survive IR parsing.  │
│  [x] Unregistered component fails fast with UnregisteredComponentError│
│  [x] Strict typing and validation preserved on all 68 built-in nodes.  │
├────────────────────────────────────────────────────────────────────────┤
│ GATE 3: Reactive Layouts & Surgical Morphing (ADR 002)                 │
│  [x] Layout reads StateRef.value without RuntimeError.                 │
│  [x] Layout state change updates layout DOM only (not page body).      │
│  [x] Page state change updates page DOM only (not layout shell).       │
│  [x] Full interaction-to-SSE-patch execution verified.                 │
├────────────────────────────────────────────────────────────────────────┤
│ GATE 4: Comprehensive Multi-Tenant Security & Fail-Closed (ADR 003)    │
│  [x] tenant scope fails closed when tenant_id is missing.              │
│  [x] QueryCache, Jobs, Chat, Events, and Outbox partitioned internally.│
│  [x] Zero cross-tenant data leakage under concurrent test clients.     │
│  [x] Safe DB migration script for chat and outbox schemas.             │
├────────────────────────────────────────────────────────────────────────┤
│ GATE 5: Reproducible Benchmark & Stability Baseline                    │
│  [x] Standardized benchmark suite verified in tests/ and benchmarks.   │
│  [x] Documented hardware, concurrency, percentiles (p50, p95, p99).    │
│  [x] Memory leak soak test: verified flat memory profile.              │
└────────────────────────────────────────────────────────────────────────┘
```
