# RADUI Framework: Architecture Decision Records (ADR) — Final Approved Specifications

**Document:** Architecture Decision Records (ADRs) for RADUI Core Architecture  
**Status:** APPROVED FOR IMPLEMENTATION PLANNING  
**Target:** RADUI Core (`RADUI-ui`) v1.0.0 Architecture  
**Review Board:** Principal Software Architect, Staff Engineer, Security & Product Review Board

---

## ADR 001: Registry-Driven Component Extensibility & Dynamic Typed AST Validation

### Status: IMPLEMENTED & VERIFIED

### Context & Problem Statement
In RADUI v0.9.0, `RADUI/components/nodes.py:2287-2357` statically defines `Element` as a closed Pydantic discriminated union of 68 built-in components:
```python
Element = Annotated[Union[Text, Heading, ..., Tag], Field(discriminator="kind")]
```
All layout and container components (`Column`, `Row`, `Card`, `Container`, `Tabs`, `Grid`, `Form`) declare:
```python
children: tuple[Element, ...] = ()
```
While `ComponentRegistry.register(kind, model, renderer)` exists, any third-party component registered in the registry cannot be placed inside any built-in container. Pydantic immediately rejects the instance at runtime with `ValidationError: union_tag_invalid`. This locks RADUI into a closed ecosystem and blocks third-party UI component development.

Furthermore, naive solutions (such as changing `children: tuple[Any, ...]` or injecting `raw_html`) undermine RADUI's typed AST, allow arbitrary non-component objects into the tree, break Intermediate Representation (IR) serialization, and introduce severe XSS vulnerabilities.

### Decision
1. **Model Contract & Typed Base:**
   - Update all built-in container components to type `children: tuple[Component, ...] = ()` (where `Component` is the abstract Pydantic base class).
   - Every custom component subclass must inherit from `Component` and declare a unique `kind: Literal["..."]` or `kind: str`.
2. **Registry-Driven Dynamic Validation:**
   - Instead of compile-time discriminated union checking in Pydantic, tree validation is performed dynamically by `ComponentRegistry.validate(root)` during AST assembly (`App._build_root`).
   - For every node encountered during traversal:
     - The registry verifies `kind` is present.
     - It retrieves the registered definition via `definition = self.get(node.kind)`.
     - It asserts `isinstance(node, definition.model)`.
     - If `node.kind` is unregistered, it raises a descriptive `UnregisteredComponentError(f"Component kind '{node.kind}' is not registered in the application's ComponentRegistry. Register it via app.registry.register('{node.kind}', Model, renderer) before using it in UI trees.")`.
     - Recursively validates all items in `node.children`.
3. **Lossless IR Serialization and Deserialization:**
   - **Serialization (`to_dict` / JSON dump):** `node.model_dump(mode="json")` preserves all custom subclass attributes, extra fields, and nested children.
   - **Deserialization (`from_dict`):** The IR parser reads `kind = data.get("kind")`, queries the application-specific `ComponentRegistry.get(kind)`, and dispatches parsing directly to the registered class: `definition.model.model_validate(data)`.
   - This ensures custom subclass fields (e.g. `syntax_theme`, `chart_series`, `columns`, `metadata`) survive serialization round-trips without field dropping.
4. **Scoping & Multi-App Registry Isolation:**
   - Validation and deserialization must bind to the *current application's* registry instance (`app.registry`), preventing registry pollution or cross-app collisions when multiple `App` instances run in the same Python process.
   - Registering a duplicate `kind` with a different model raises `DuplicateComponentRegistrationError`.
5. **Explicit Rejections:**
   - **Reject `tuple[Any, ...] `:** Defeats type safety, allows arbitrary non-component objects into the AST, and prevents recursive validation.
   - **Reject Unrestricted `raw_html`:** Bypassing typed nodes with raw HTML strings breaks semantic AST serialization, disables DOM morphing keys, and creates serious XSS vulnerabilities (especially with LLM/AI generated UI).

### Alternatives Considered
- *Alternative A: Dynamic Union Rebuilding via `create_model`.* Dynamically update `Column.model_fields['children'].annotation` on registration. **Rejected:** Fragile in Pydantic v2; causes concurrency races, cache thrashing, and thread-safety issues across workers.
- *Alternative B: Untyped `dict` tree representation.* **Rejected:** Discards Python type hinting, autocompletion, IDE validation, and Pydantic field validation.

### Acceptance Test Matrix
- [x] `test_custom_component_nested_in_column_succeeds`: Custom registered component renders inside `gx.column(gx.card(CustomTerminal()))`.
- [x] `test_multiple_third_party_types_in_same_tree`: Tree containing built-ins and two distinct third-party custom components validates and renders cleanly.
- [x] `test_custom_subclass_fields_preserved_in_ir_roundtrip`: Custom component with 5+ unique attributes (strings, dicts, lists, booleans) serializes to JSON and deserializes through `ComponentRegistry.deserialize()` without dropping any field.
- [x] `test_recursive_custom_children_validation`: Custom container component with custom child components validates recursively.
- [x] `test_unregistered_component_fails_fast_with_actionable_error`: Unregistered component class raises `UnregisteredComponentError` with troubleshooting hints.
- [x] `test_duplicate_kind_registration_rejection`: Registering the same `kind` twice with differing models raises `DuplicateComponentRegistrationError`.
- [x] `test_concurrent_multi_app_registry_isolation`: Two independent `gx.App` instances maintain distinct component registries without cross-contamination.
- [x] `test_built_in_strict_typing_preserved`: Passing invalid properties to built-in components (e.g. invalid `variant="invalid"`) still triggers Pydantic validation errors.

---

## ADR 002: Reactive Layout Execution & Independent Subtree Invalidation

### Status: IMPLEMENTED & VERIFIED

### Context & Problem Statement
In RADUI v0.9.0, `App._build_root` (`RADUI/core/app.py:560-584`) isolates the active state context strictly to the page handler:
```python
with state_context.activate(), state_context.track_component(_PAGE_COMPONENT_ID):
    root = page.handler()

for _, layout_fn in matching_layouts:
    root = layout_fn(outlet=root) # BUG: Runs outside state_context.activate()!
```
Reading `StateRef.value` inside a layout shell raises `RuntimeError: StateRef can only be read inside an active StateContext`. Developers cannot build state-aware navigation headers, notification bells, or user profile shells in layouts.

Furthermore, simply wrapping layouts inside `state_context.activate()` without separate tracking would associate all layout state reads with `_PAGE_COMPONENT_ID`. As a result, updating layout state (e.g. a notification counter) would force the entire page body to re-render, destroying RADUI's surgical DOM morphing advantage.

### Decision
1. **Encapsulate Layout Execution in Active StateContext:**
   Execute both page handlers and matching layout functions within the active `StateContext`.
2. **Deterministic Layout Component Identities:**
   Assign a deterministic, stable component identifier to each layout wrapper:
   ```python
   layout_id = getattr(layout_fn, "_gx_layout_id", f"gx-layout-{prefix.strip('/') or 'root'}")
   ```
3. **Independent Subtree Dependency Tracking:**
   Track reactive state reads independently per layout level:
   ```python
   with state_context.activate():
       with state_context.track_component(_PAGE_COMPONENT_ID):
           root = page.handler()

       for prefix, layout_fn in matching_layouts:
           layout_id = getattr(layout_fn, "_gx_layout_id", f"gx-layout-{prefix.strip('/') or 'root'}")
           with state_context.track_component(layout_id):
               if "outlet" in inspect.signature(layout_fn).parameters:
                   root = layout_fn(outlet=root)
               else:
                   root = layout_fn(root)
               # Ensure layout container root node carries stable layout_id
               if root.id is None:
                   root = root.model_copy(update={"id": layout_id})
               elif root.id != layout_id:
                   state_context.runtime.dependencies.remap_component_id(state_context.identity, layout_id, root.id)
   ```
4. **Surgical DOM Invalidation Contract:**
   - **Page State Mutation:** When state read by `page.handler()` mutates, the dependency tracker invalidates strictly `_PAGE_COMPONENT_ID`. The emitted SSE patch targets `id="_gx_page_root"`. The layout shell remains untouched.
   - **Layout State Mutation:** When state read by a layout mutates, the dependency tracker invalidates strictly `layout_id`. The emitted SSE patch targets `layout_id`. The page body is not recomputed.
   - **Nested Layouts:** For chains (`/` -> `/app` -> `/app/settings`), each layout function tracks dependencies under its own identity (`gx-layout-root`, `gx-layout-app`, `gx-layout-settings`).
5. **Exception Handling & Cleanup:**
   If a layout function raises an exception during rendering, the active state context tracking frame is popped cleanly via `try...finally`, preventing state context leakage to subsequent requests.

### Alternatives Considered
- *Alternative A: Invalidate entire document on any layout change.* **Rejected:** Destroys performance and causes UI flicker/scroll-loss on navigation shells.
- *Alternative B: Prohibit state reads in layouts; force pages to pass data.* **Rejected:** Violates fundamental DRY principles and forces duplicate layout code across pages.

### Acceptance Test Matrix
- [x] `test_layout_reads_state_ref_cleanly`: Persistent layout reads `user_name.value` and `active_env.value` without runtime errors.
- [x] `test_layout_state_change_emits_layout_patch_only`: Mutating layout-bound state generates an SSE patch targeting `layout_id`, leaving `_PAGE_COMPONENT_ID` un-invalidated.
- [x] `test_page_state_change_emits_page_patch_only`: Mutating page-bound state generates an SSE patch targeting `_PAGE_COMPONENT_ID`, leaving `layout_id` un-invalidated.
- [x] `test_nested_layouts_multi_tier_invalidation`: Two nested layouts (root shell + section sidebar) update independently when their respective state references change.
- [x] `test_layout_exception_cleans_up_context`: An exception raised inside a layout handler leaves the `StateContext` stack clean for subsequent requests.

---

## ADR 003: Comprehensive Multi-Tenant Security & 5-Tier Scope Architecture

### Status: IMPLEMENTED & VERIFIED

### Context & Problem Statement
In RADUI v0.9.0:
- `app` scope is ambiguous: it is prefixed by `tenant_id` when present (`{tenant_id}:key`), but becomes a shared global process singleton when `tenant_id` is None.
- There is no distinct `tenant` scope.
- Subsystems outside state (`QueryCache`, `JobBackend`, `SQLiteChatRepository`, `TransactionalOutbox`, `EventBroker`, `Inspector`) have **zero tenant partitioning**.
- When `tenant_id` is omitted, the framework does not fail closed; it defaults to an unpartitioned shared global namespace, creating cross-tenant data leakage risks.
- Pushing tenant key construction onto developers (`gx.query(f"tenant:{context.tenant_id}:{key}")`) is unacceptable; it inevitably results in developer oversight and catastrophic leaks.

### Decision
1. **Explicit 5-Tier Scope Hierarchy:**
   Update `StateScope` to:
   ```python
   StateScope = Literal["view", "session", "user", "tenant", "app"]
   ```
   - **`view`:** Ephemeral component/page instance.
   - **`session`:** Per-browser-session state, tied strictly to `session_id`.
   - **`user`:** Per-authenticated-user state. **User identity in multi-tenancy is scoped to `(tenant_id, user_id)` by default** to prevent cross-organization privilege escalation. Fails closed (raises `UserRequiredError`) if unauthenticated.
   - **`tenant`:** Shared across all users and sessions within a single tenant. **Fails closed** (raises `TenantRequiredError`) if `tenant_id` is None.
   - **`app`:** Explicitly application-global, shared across all tenants.
     * *Visibility:* Globally visible across the application.
     * *Mutation Policy:* Read-only from tenant sessions; can only be written during application startup, by background administrative workers, or by users holding the `system_admin` RBAC role.
     * *Consistency Guarantee:* **Backend-dependent.** Process-local with `InMemoryStateBackend`; single-host multi-worker consistent with `SQLiteStateBackend`; cluster-wide distributed consistent only with `RedisStateBackend`.
2. **Framework-Level Internal Tenant Propagation (Zero Developer Burden):**
   The framework itself derives and enforces tenant namespaces internally from trusted server-side context. Application developers call standard APIs (`gx.query("recent_orders")`, `app.job("rebalance")`), and RADUI automatically partitions the underlying resource:

   | Subsystem | Internal Namespace / Partitioning Mechanism | Enforcement & Isolation Behavior |
   |---|---|---|
   | **State Storage** | `(scope, identity_key, state_key)` where `identity_key` is `f"{tenant_id}"` for tenant scope and `f"{tenant_id}:{user_id}"` for user scope. | Fail closed if tenant missing on `tenant` scope. |
   | **Query Cache** | Cache entries partitioned internally: `_entries[(tenant_id or "_global", key)]`. Invalidation by prefix (`invalidate_query("orders")`) scopes strictly to current tenant. | Zero cross-tenant cache hits. |
   | **Background Jobs** | `JobSnapshot` schema includes `tenant_id: str | None`. Worker queries, `JobPanel`, and `job_cancel` enforce `job.tenant_id == ctx.tenant_id`. | Tenants cannot inspect, list, or cancel other tenants' jobs. |
   | **Idempotency** | Partitioned key: `(tenant_id or "_global", action_id, fingerprint)`. | Action ID reuse across tenants does not conflict. |
   | **Chat Persistence** | `RADUI_chat_messages` table schema updated with `tenant_id TEXT NOT NULL`. All repository queries filter by `tenant_id`. | Complete thread and message isolation. |
   | **Transactional Outbox** | `gx_outbox` table schema updated with `tenant_id TEXT`. Sweeper records tenant context for auditing. | Outbox events are tenant-audited. |
   | **Event Broker (SSE)** | `EventRecord` includes `tenant_id: str | None`. `EventBroker.subscribe(topic)` strictly delivers events matching client's `tenant_id` or `tenant_id is None` (broadcast). | Cross-tenant event eavesdropping blocked. |
   | **Event Replay (Redis/SQLite)** | Event replay streams filter by `tenant_id`. | Disconnected clients replay only their own tenant's events. |
   | **Inspector / Telemetry** | Traces tagged with `tenant_id`. `/_gx/inspect/traces` requires admin auth and filters by tenant. | Tenants cannot view global telemetry traces. |

3. **Resolution, Validation & Propagation Pipeline:**
   - **Resolution:** `tenant_id` is resolved exclusively server-side via `tenant_id_resolver(request)` (e.g. from validated JWT claims, verified subdomain, or authenticated session).
   - **Untrusted Headers Blocked:** Raw `X-Tenant-ID` headers are rejected unless cryptographically signed or explicitly validated by `tenant_membership_validator(request, user_id, tenant_id)`.
   - **Propagation:** When a command schedules a background job (`@app.job`), the active `tenant_id` is captured into the `JobContext` and propagated automatically to all downstream operations.
4. **Safe Database Migration Strategy:**
   - Schema migration scripts for `RADUI_chat_messages` and `gx_outbox`:
     ```sql
     ALTER TABLE RADUI_chat_messages ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '_default';
     ALTER TABLE gx_outbox ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '_default';
     ```
   - Historical records are assigned to `_default` tenant. **No historical record is ever made globally accessible without tenant filtering.**

### Alternatives Considered
- *Alternative A: Developer manual key prefixing.* **Permanently Rejected:** Human error inevitably causes data leakage.
- *Alternative B: Separate database file per tenant.* **Deferred:** Clean for SQLite, but heavy for single-process architectures. Namespace partitioning is required first.

### Acceptance Test Matrix
- [x] `test_tenant_scope_fails_closed_without_tenant_id`: Attempting to read/write `scope="tenant"` without `tenant_id` raises `TenantRequiredError` (HTTP 403).
- [x] `test_query_cache_auto_partitioned_by_tenant`: `gx.query("kpi", ...)` called by Tenant A and Tenant B caches separate results without manual key prefixing.
- [x] `test_query_cache_invalidation_scoped_to_tenant`: `gx.invalidate_query("kpi")` in Tenant A leaves Tenant B's cached KPI intact.
- [x] `test_job_access_strictly_tenant_isolated`: Tenant B cannot view status or cancel a job submitted by Tenant A.
- [x] `test_idempotency_key_isolated_by_tenant`: Same `action_id` submitted by Tenant A and Tenant B executes independently without collision.
- [x] `test_chat_repository_tenant_isolated`: SQL queries for thread messages enforce `tenant_id = ?`. Cross-tenant thread access returns empty/forbidden.
- [x] `test_event_broker_tenant_filtering`: Events published for Tenant A are not received by Tenant B's SSE connection.
- [x] `test_app_scope_mutation_rb_ac_enforced`: Non-admin user cannot mutate `scope="app"` state.
- [x] `test_untrusted_tenant_header_rejected`: Unauthenticated `X-Tenant-ID` header injection rejected with HTTP 403.

---

## ADR 004: Action Button Decoupling from Form Encapsulation

### Status: IMPLEMENTED & VERIFIED

### Context & Problem Statement
In `RADUI/core/app.py:610`, `App._validate_commands` strictly enforces:
```python
if isinstance(node, Button) and not inside_form:
    raise ValueError("Button must be placed inside a Form")
```
This forces developers to wrap every simple clickable button (toolbar actions, modal toggles, tabs, pagination controls) in an explicit `gx.form("command.name", gx.button(...))` element. This creates immense boilerplate and violates standard developer expectations.

### Decision
1. **Permit Standalone Action Buttons:**
   Allow `Button` nodes outside of `Form` provided they declare a `command` attribute:
   ```python
   gx.button("Refresh Telemetry", command="telemetry.refresh", variant="primary")
   ```
2. **Rendering & Dispatch Contract:**
   - Standalone buttons render with `data-gx-command="{command}"` and `data-gx-csrf="{csrf_token}"`.
   - `client.js` listens for clicks on `[data-gx-command]` and dispatches an HTTP POST to `/_gx/commands/{command_id}`.
   - Preserves CSRF protection and command registration validation.
3. **Form Controls Retain Encapsulation:**
   Input fields (`Input`, `Select`, `Textarea`, `Checkbox`, `RadioGroup`) must remain inside a `Form` to ensure coherent form serialization.

### Acceptance Test Matrix
- [x] `test_standalone_button_with_command_renders_cleanly`: Standalone button with `command` renders without raising `ValueError`.
- [x] `test_standalone_button_without_command_fails_validation`: Standalone button without `command` or form wrapper fails validation with clear troubleshooting advice.
- [x] `test_standalone_button_click_dispatches_sse_update`: Clicking standalone button dispatches command and applies surgical SSE patch.

---

## ADR 005: Public ASGI Middleware Pipeline

### Status: IMPLEMENTED & VERIFIED

### Context & Problem Statement
In `RADUI/core/app.py:734-744`, `App.asgi()` instantiates Starlette with a hardcoded middleware array containing only `SessionMiddleware`. `App` provides **zero public API** for standard ASGI HTTP middleware (e.g. CORS, Prometheus, GZip, OpenTelemetry HTTP tracing, security headers).

### Decision
1. **Public API Contract:**
   Add `app.add_middleware(middleware_class, **options)` to `App`:
   ```python
   app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])
   app.add_middleware(GZipMiddleware, minimum_size=1000)
   ```
2. **Pipeline Compilation:**
   Store user-registered middleware in `self._custom_middleware: list[Middleware]`. In `App.asgi()`, compile:
   ```python
   middleware = [
       Middleware(SessionMiddleware, secret_key=self._session_secret, ...),
       *self._custom_middleware,
   ]
   ```
3. **Ordering Semantics:**
   `SessionMiddleware` remains at the root so that session data is decoded before user middleware and application routes execute.

### Acceptance Test Matrix
- [x] `test_add_middleware_applies_to_asgi_pipeline`: Adding custom CORS/header middleware modifies response headers across all routes.
- [x] `test_session_middleware_executes_first`: Custom middleware can access `request.session` populated by `SessionMiddleware`.
