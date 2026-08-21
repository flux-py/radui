# RADUI Framework: Prioritized Improvement & Evolution Roadmap

**Audit Date:** November 2026  
**Auditor:** Principal Software Architect & Product Roadmap Steering Committee  
**Target:** RADUI UI (`RADUI-ui`) Evolution Strategy (v0.9.1 → v1.2.0)

---

## 1. Prioritized Defect & Gap Registry

### Priority P0: Critical Architectural Blockers (Must Fix Immediately)

#### Issue `P0-01`: Open Component Union to Enable Custom UI Extensions (`BUG-COMP-REG-01`)
- **Problem Statement:** Custom components registered via `ComponentRegistry.register()` crash with Pydantic `ValidationError` when placed inside any built-in container (`Column`, `Row`, `Card`, `Container`).
- **Root Cause:** `RADUI/components/nodes.py:2287-2357` defines `Element` as a closed discriminated union of only the 68 built-in types.
- **Proposed Architectural Fix:**  
  Change `children: tuple[Element, ...]` on container models to `children: tuple[Component, ...]`. Replace compile-time discriminated union checking with runtime registry validation in `ComponentRegistry.validate()`. Add an escape hatch `raw_html` / `custom_node` fallback.
- **Affected Modules:** `RADUI/components/nodes.py`, `RADUI/core/registry.py`
- **Estimated Effort:** 2 Engineer-Days
- **Breaking Change:** No (strictly broadens accepted types)

#### Issue `P0-02`: Wrap Layout Execution in Active StateContext (`BUG-LAYOUT-CTX-01`)
- **Problem Statement:** Shells and navigation headers defined via `@app.layout()` crash with `RuntimeError` if they read reactive state (`StateRef.value`).
- **Root Cause:** `RADUI/core/app.py:560-584` closes `with state_context.activate():` before calling `layout_fn(outlet=root)`.
- **Proposed Architectural Fix:**  
  Encapsulate both `page.handler()` and `matching_layouts` inside the `with state_context.activate():` context manager block.
- **Affected Modules:** `RADUI/core/app.py`
- **Estimated Effort:** 0.5 Engineer-Days
- **Breaking Change:** No

---

### Priority P1: Usability & Architectural Gaps (v0.9.1 - v1.0.0)

#### Issue `P1-01`: Relax Forced Form Encapsulation for Action Buttons (`ARCH-FORM-ENFORCEMENT-01`)
- **Problem Statement:** Placing a `Button` outside a `Form` raises `ValueError: Button must be placed inside a Form`, forcing boilerplate forms for simple click actions.
- **Root Cause:** `RADUI/core/app.py:609-614` strictly rejects non-form buttons during tree validation.
- **Proposed Architectural Fix:**  
  Allow standalone buttons with `command="..."` to render with `data-gx-command` and auto-dispatch action requests without requiring an explicit `<form>` DOM element.
- **Affected Modules:** `RADUI/core/app.py`, `RADUI/renderers/html.py`, `client.js`
- **Estimated Effort:** 3 Engineer-Days
- **Breaking Change:** No

#### Issue `P1-02`: Graceful Unauthenticated Handling for `scope="user"`
- **Problem Statement:** Accessing `scope="user"` state in unauthenticated sessions raises an unhandled `RuntimeError: state '...' requires an authenticated user_id`.
- **Root Cause:** `RADUI/state/refs.py:125` raises a hard exception if `context.user_id is None`.
- **Proposed Architectural Fix:**  
  Return the declared default value when `context.user_id is None`, or provide a configurable parameter `unauthenticated="default" | "raise"`.
- **Affected Modules:** `RADUI/state/refs.py`, `RADUI/state/runtime.py`
- **Estimated Effort:** 1 Engineer-Day
- **Breaking Change:** Potential minor behavioral change

#### Issue `P1-03`: Expose Public HTTP ASGI Middleware Registration (`FEAT-MIDDLEWARE-HTTP-01`)
- **Problem Statement:** Developers cannot attach standard Starlette/ASGI middleware (CORS, Prometheus, GZip, Auth) through `App`.
- **Root Cause:** `RADUI/core/app.py:734` hardcodes `middleware = [Middleware(SessionMiddleware, ...)]`.
- **Proposed Architectural Fix:**  
  Add `app.add_middleware(middleware_class, **options)` which appends to an internal list compiled in `App.asgi()`.
- **Affected Modules:** `RADUI/core/app.py`
- **Estimated Effort:** 1 Engineer-Day
- **Breaking Change:** No

#### Issue `P1-04`: Normalize Form and Input API Signatures (`FEAT-INPUT-KWARG-01`)
- **Problem Statement:** `gx.form` takes `command` positionally; `gx.input` rejects `name="..."` keyword argument.
- **Root Cause:** Positional parameter ordering in helper factory functions.
- **Proposed Architectural Fix:**  
  Accept both positional and keyword arguments for `name`, `label`, and `command`.
- **Affected Modules:** `RADUI/components/nodes.py`
- **Estimated Effort:** 1 Engineer-Day
- **Breaking Change:** No

---

### Priority P2: Enterprise & Feature Expansions (v1.1.0)

#### Issue `P2-01`: True Multi-Stage Task DAG Execution Graph
- **Problem Statement:** The advertised "three-graph architecture" lacks task dependency edges; jobs are isolated worker items.
- **Proposed Architectural Fix:**  
  Introduce `@app.pipeline` and task dependency contracts (`job_b.depends_on(job_a)`), providing topological sort execution and pipeline status tracking.
- **Affected Modules:** `RADUI/jobs/contracts.py`, `RADUI/jobs/runtime.py`
- **Estimated Effort:** 8 Engineer-Days
- **Breaking Change:** No

#### Issue `P2-02`: Real-World PostgreSQL Async Driver Integration
- **Problem Statement:** `PostgreSQLStateBackend` currently uses an in-memory test shim rather than true `asyncpg`/`psycopg3` pool management.
- **Proposed Architectural Fix:**  
  Implement robust connection pooling with automated migration schemas and reconnection backoff.
- **Affected Modules:** `RADUI/state/backend.py`
- **Estimated Effort:** 4 Engineer-Days
- **Breaking Change:** No

#### Issue `P2-03`: Client-Side Event Buffer Capping (Drop-Oldest Policy)
- **Problem Statement:** Unbounded memory growth in `InMemoryEventBackend` if slow SSE clients accumulate patches.
- **Proposed Architectural Fix:**  
  Enforce a ring buffer (e.g. max 500 events per session) with drop-oldest semantics and a client re-sync event.
- **Affected Modules:** `RADUI/transport/events.py`
- **Estimated Effort:** 2 Engineer-Days
- **Breaking Change:** No

---

### Priority P3: Developer Delights & Optimizations (v1.2.0)

#### Issue `P3-01`: Client-Side Micro-Interactivity (Alpine / Custom JS Hooks)
- **Problem Statement:** Simple UI toggles (dropdowns, accordions, modals) should not require roundtrip HTTP requests.
- **Proposed Architectural Fix:**  
  Provide client-side declarative attributes (e.g. `client_toggle=True`) handled directly in `client.js`.
- **Estimated Effort:** 5 Engineer-Days

#### Issue `P3-02`: Fast WebSocket Bi-Directional Transport
- **Problem Statement:** High-frequency bi-directional messaging over HTTP POST has overhead compared to persistent WebSockets.
- **Proposed Architectural Fix:**  
  Add optional WebSocket transport endpoint (`/_gx/ws`) falling back to SSE.
- **Estimated Effort:** 6 Engineer-Days

---

## 2. Phased Evolution Roadmap Timeline

```
v0.9.1 (Patch Release - Stabilization & Bug Fixes)
  ├── P0-01: Open Component Union (tuple[Component, ...])
  ├── P0-02: Fix Layout StateContext execution
  ├── P1-02: Fix unauthenticated scope="user" handling
  └── P1-04: Normalize input and form keyword arguments

v1.0.0 (Major Release - Production Extensibility)
  ├── P1-01: Allow standalone action buttons (relax Form constraint)
  ├── P1-03: Add app.add_middleware() for ASGI plugins
  ├── Full Web Component & Custom Component SDK documentation
  └── Real PostgreSQL asyncpg driver integration

v1.1.0 (Minor Release - Three-Graph Realization)
  ├── P2-01: Implement True Task DAG Pipelines
  ├── P2-03: Ring-buffer SSE backpressure protection
  └── Enhanced Inspector with Live Pipeline Visualizer

v1.2.0 (Minor Release - Performance & Interactivity)
  ├── P3-01: Client-side micro-interactivity engine
  └── P3-02: Native bi-directional WebSocket transport
```
