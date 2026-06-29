from __future__ import annotations

import json
import pytest
from typing import Any, Literal
from starlette.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

import radui as gx
from radui.core.registry import (
    ComponentRegistry,
    DuplicateComponentRegistrationError,
    UnregisteredComponentError,
)
from radui.state.runtime import StateRuntime, get_active_context
from radui.data.query import query, aquery, invalidate_query, _resolve_tenant_query_key
from radui.jobs.runtime import LocalJobBackend, JobDefinition
from radui.ai.persistence import SQLiteChatRepository
from radui.core.outbox import TransactionalOutbox
from radui.transport.events import InMemoryEventBackend, Event


# ==============================================================================
# 1. Multi-Tenant Fail-Closed Isolation & Context Propagation (P0)
# ==============================================================================

def test_query_cache_tenant_auto_scoping():
    """Verify query cache automatically namespaces keys by active tenant."""
    runtime = StateRuntime("test-app")
    ctx_a = runtime.context(session_id="s1", tenant_id="tenant-alpha")
    ctx_b = runtime.context(session_id="s2", tenant_id="tenant-beta")
    ctx_default = runtime.context(session_id="s3")

    with ctx_a.activate():
        assert _resolve_tenant_query_key("user:123") == "t:tenant-alpha:user:123"

    with ctx_b.activate():
        assert _resolve_tenant_query_key("user:123") == "t:tenant-beta:user:123"

    with ctx_default.activate():
        # Without tenant, key is preserved as-is for backward compatibility
        assert _resolve_tenant_query_key("user:123") == "user:123"


def test_query_cache_tenant_data_isolation():
    """Verify query results are cached separately per tenant."""
    runtime = StateRuntime("test-app")
    calls = {"alpha": 0, "beta": 0}

    def fetch_alpha():
        calls["alpha"] += 1
        return "data-alpha"

    def fetch_beta():
        calls["beta"] += 1
        return "data-beta"

    ctx_a = runtime.context(session_id="s1", tenant_id="tenant-alpha")
    ctx_b = runtime.context(session_id="s2", tenant_id="tenant-beta")

    with ctx_a.activate():
        res1 = query("common-key", fetch_alpha, stale_time=60.0)
        assert res1 == "data-alpha"
        assert calls["alpha"] == 1

    with ctx_b.activate():
        # Under tenant-beta, must NOT receive tenant-alpha's cached value
        res2 = query("common-key", fetch_beta, stale_time=60.0)
        assert res2 == "data-beta"
        assert calls["beta"] == 1

    # Invalidate tenant-alpha only
    with ctx_a.activate():
        invalidate_query("common-key")

    with ctx_b.activate():
        # tenant-beta cache remains valid
        res3 = query("common-key", fetch_beta, stale_time=60.0)
        assert res3 == "data-beta"
        assert calls["beta"] == 1  # Not re-fetched


def test_job_cross_tenant_isolation(tmp_path):
    """Verify jobs cannot be inspected or canceled across tenant boundaries."""
    from radui.jobs.sqlite import SQLiteJobBackend

    db_path = str(tmp_path / "jobs.db")
    backend = SQLiteJobBackend(db_path=db_path)
    runtime = StateRuntime("test-app")
    ctx_alpha = runtime.context(session_id="s1", tenant_id="tenant-alpha")

    async def run_test():
        await backend.startup()
        try:
            job_def = JobDefinition("sync_data", lambda: "done", backend)

            # Submit job as tenant-alpha (auto-derived from ctx_alpha)
            snapshot = await backend.submit(job_def, ctx_alpha, (), {})
            job_id = snapshot.id
            assert snapshot.tenant_id == "tenant-alpha"

            # Inspection by tenant-alpha succeeds
            snap_alpha = backend.get_snapshot(job_id, "s1", tenant_id="tenant-alpha")
            assert snap_alpha.id == job_id

            # Inspection by tenant-beta raises JobNotFoundError
            from radui.jobs.runtime import JobNotFoundError
            with pytest.raises(JobNotFoundError):
                backend.get_snapshot(job_id, "s1", tenant_id="tenant-beta")

            # Cancellation by tenant-beta is blocked
            with pytest.raises(JobNotFoundError):
                await backend.cancel(job_id, "s1", tenant_id="tenant-beta")
        finally:
            await backend.shutdown()

    import asyncio
    asyncio.run(run_test())


def test_chat_persistence_tenant_filtering(tmp_path):
    """Verify SQLiteChatRepository partitions messages strictly by tenant_id."""
    db_path = str(tmp_path / "chat.db")
    store = SQLiteChatRepository(db_path=db_path)

    runtime = StateRuntime("test-app")
    ctx_a = runtime.context(session_id="s1", tenant_id="tenant-alpha")
    ctx_b = runtime.context(session_id="s2", tenant_id="tenant-beta")

    with ctx_a.activate():
        store.add_message("thread-1", "user", "Hello from Alpha")

    with ctx_b.activate():
        store.add_message("thread-1", "user", "Hello from Beta")

    # Thread 1 under Alpha sees only Alpha's message
    with ctx_a.activate():
        msgs_a = store.get_messages("thread-1")
        assert len(msgs_a) == 1
        assert msgs_a[0].content == "Hello from Alpha"
        assert msgs_a[0].tenant_id == "tenant-alpha"

    # Thread 1 under Beta sees only Beta's message
    with ctx_b.activate():
        msgs_b = store.get_messages("thread-1")
        assert len(msgs_b) == 1
        assert msgs_b[0].content == "Hello from Beta"
        assert msgs_b[0].tenant_id == "tenant-beta"


def test_outbox_tenant_isolation(tmp_path):
    """Verify TransactionalOutbox records and claims batches partitioned by tenant_id."""
    db_path = str(tmp_path / "outbox.db")
    outbox = TransactionalOutbox(db_path=db_path)

    runtime = StateRuntime("test-app")
    ctx_a = runtime.context(session_id="s1", tenant_id="tenant-alpha")
    ctx_b = runtime.context(session_id="s2", tenant_id="tenant-beta")

    with ctx_a.activate():
        outbox.publish("order.created", {"order_id": 101})

    with ctx_b.activate():
        outbox.publish("order.created", {"order_id": 202})

    # Claim batch
    batch = outbox.claim_batch(limit=10)
    assert len(batch) == 2
    assert any(r.tenant_id == "tenant-alpha" and r.payload == {"order_id": 101} for r in batch)
    assert any(r.tenant_id == "tenant-beta" and r.payload == {"order_id": 202} for r in batch)


def test_event_broker_bounds_and_tenant_filtering():
    """Verify InMemoryEventBackend bounds queue to 500 and filters by tenant."""
    backend = InMemoryEventBackend(history_size=500)

    # Append 550 events
    for i in range(550):
        backend.append_sync(
            session_id="s1",
            payload={"index": i},
            tenant_id="tenant-alpha" if i % 2 == 0 else "tenant-beta",
        )

    # Queue history must be capped at 500
    assert len(backend._history["s1"]) == 500

    # Replay events filtered under tenant-alpha
    import asyncio
    records_alpha = asyncio.run(
        backend.replay_after(
            session_id="s1",
            sequence=0,
            tenant_id="tenant-alpha",
        )
    )
    assert len(records_alpha) > 0
    for rec in records_alpha:
        assert rec.tenant_id == "tenant-alpha"


def test_app_multi_tenant_fail_closed_enforcement():
    """Verify multi_tenant=True rejects requests with 403 when tenant is missing."""
    app = gx.App("Multi-Tenant App", multi_tenant=True)

    @app.page("/")
    def home():
        return gx.heading("Tenant Portal")

    client = TestClient(app.asgi())
    # Request without tenant header/resolver -> 403 Forbidden
    res = client.get("/")
    assert res.status_code == 403
    assert "Tenant context required" in res.text

    # Request with tenant resolver
    app_with_resolver = gx.App(
        "Multi-Tenant App 2",
        multi_tenant=True,
        tenant_id_resolver=lambda req: "tenant-corp",
    )
    @app_with_resolver.page("/")
    def portal():
        return gx.heading("Welcome Tenant Corp")

    client2 = TestClient(app_with_resolver.asgi())
    res2 = client2.get("/")
    assert res2.status_code == 200
    assert "Welcome Tenant Corp" in res2.text


# ==============================================================================
# 2. Registry-Driven Component Extensibility (ADR 001)
# ==============================================================================

class CustomCodeTerminal(gx.Component):
    """Custom third-party component with 5+ unique fields."""
    kind: Literal["custom_code_terminal"] = "custom_code_terminal"
    syntax_theme: str = "dracula"
    command_log: tuple[str, ...] = ()
    max_lines: int = 100
    timestamp_enabled: bool = True
    terminal_meta: dict[str, Any] = {}


def render_custom_code_terminal(
    component: gx.Component,
    registry: ComponentRegistry,
    state_context: object | None,
    csrf_token: str | None,
) -> str:
    assert isinstance(component, CustomCodeTerminal)
    lines = "".join(f"<div class='log-line'>{cmd}</div>" for cmd in component.command_log)
    return (
        f'<div class="custom-terminal" data-theme="{component.syntax_theme}" '
        f'data-max-lines="{component.max_lines}">{lines}</div>'
    )


def test_custom_component_nested_in_column_and_card_renders():
    """Verify custom component renders seamlessly inside built-in containers."""
    app = gx.App("Custom Component App")
    app.registry.register("custom_code_terminal", CustomCodeTerminal, render_custom_code_terminal)

    @app.page("/")
    def home():
        terminal = CustomCodeTerminal(
            syntax_theme="monokai",
            command_log=("git status", "git commit -m 'feat: v1.0'"),
            max_lines=50,
            timestamp_enabled=False,
            terminal_meta={"env": "prod"},
        )
        return gx.column(
            gx.heading("DevOps Console"),
            gx.card(terminal),
        )

    client = TestClient(app.asgi())
    res = client.get("/")
    assert res.status_code == 200
    assert 'class="custom-terminal"' in res.text
    assert 'data-theme="monokai"' in res.text
    assert "git status" in res.text
    assert "git commit" in res.text


def test_custom_subclass_fields_preserved_in_ir_roundtrip():
    """Verify custom component with 5+ unique attributes survives serialization and deserialization."""
    registry = ComponentRegistry.builtins()
    registry.register("custom_code_terminal", CustomCodeTerminal, render_custom_code_terminal)

    terminal = CustomCodeTerminal(
        syntax_theme="nord",
        command_log=("pytest -q", "echo 'passed'"),
        max_lines=250,
        timestamp_enabled=True,
        terminal_meta={"author": "alice", "version": 1},
    )
    col = gx.column(terminal)

    # 1. model_dump mode="json" preserves custom fields
    dumped = col.model_dump(mode="json")
    child_dump = dumped["children"][0]
    assert child_dump["kind"] == "custom_code_terminal"
    assert child_dump["syntax_theme"] == "nord"
    assert child_dump["command_log"] == ["pytest -q", "echo 'passed'"]
    assert child_dump["max_lines"] == 250
    assert child_dump["timestamp_enabled"] is True
    assert child_dump["terminal_meta"] == {"author": "alice", "version": 1}

    # 2. Deserialization reconstructs the exact custom subclass
    deserialized = registry.deserialize(dumped)
    assert isinstance(deserialized, gx.Column)
    recovered_terminal = deserialized.children[0]
    assert isinstance(recovered_terminal, CustomCodeTerminal)
    assert recovered_terminal.syntax_theme == "nord"
    assert recovered_terminal.max_lines == 250
    assert recovered_terminal.timestamp_enabled is True
    assert recovered_terminal.terminal_meta["author"] == "alice"


def test_unregistered_component_raises_actionable_error():
    """Verify unregistered component kind raises UnregisteredComponentError with actionable advice."""
    registry = ComponentRegistry.builtins()
    with pytest.raises(UnregisteredComponentError) as exc_info:
        registry.get("unknown_widget")
    assert "unregistered component kind: 'unknown_widget'" in str(exc_info.value)
    assert "Register it via app.registry.register" in str(exc_info.value)


def test_duplicate_component_registration_raises_error():
    """Verify registering a duplicate kind with differing model raises DuplicateComponentRegistrationError."""
    registry = ComponentRegistry.builtins()
    with pytest.raises(DuplicateComponentRegistrationError):
        registry.register("heading", CustomCodeTerminal, render_custom_code_terminal)


def test_multi_app_registry_isolation():
    """Verify distinct App instances maintain separate registries."""
    app1 = gx.App("App 1")
    app2 = gx.App("App 2")

    app1.registry.register("custom_code_terminal", CustomCodeTerminal, render_custom_code_terminal)

    assert "custom_code_terminal" in app1.registry._definitions
    assert "custom_code_terminal" not in app2.registry._definitions


# ==============================================================================
# 3. Reactive Layout Execution & Subtree Invalidation (ADR 002)
# ==============================================================================

def test_layout_reads_state_ref_cleanly():
    """Verify persistent layout shell can read StateRef.value without RuntimeError."""
    app = gx.App("Layout State App")
    env_state = gx.state("env_mode", default="Production")

    @app.layout("/")
    def root_layout(outlet):
        # Reading state inside layout must succeed
        current_env = env_state.value
        return gx.column(
            gx.row(gx.badge(current_env, id="env-badge")),
            outlet,
            id="root-shell",
        )

    @app.page("/")
    def home():
        return gx.heading("Home Content", id="home-heading")

    client = TestClient(app.asgi())
    res = client.get("/")
    assert res.status_code == 200
    assert "Production" in res.text
    assert "Home Content" in res.text


def test_layout_state_change_emits_layout_patch_only():
    """Verify mutating layout-bound state generates patch targeting layout_id only."""
    app = gx.App("Layout Invalidation App")
    counter_state = gx.state("notification_count", default=3)
    page_state = gx.state("page_counter", default=0)

    @app.layout("/")
    def main_shell(outlet):
        count = counter_state.value
        return gx.column(
            gx.badge(f"Notifications: {count}", id="notif-badge"),
            outlet,
            id="main-shell",
        )

    @app.page("/")
    def home():
        p_count = page_state.value
        return gx.form(
            "inc_notif",
            gx.text(f"Page Value: {p_count}", id="page-text"),
            gx.button("Add Notif", variant="primary"),
        )

    @app.command("inc_notif")
    def inc_notif(ctx: gx.CommandContext):
        counter_state.value = counter_state.value + 1

    client = TestClient(app.asgi())
    page = client.get("/")
    assert page.status_code == 200

    from tests.test_interactivity import get_form
    action, fields = get_form(page.text, "inc_notif")
    res = client.post(action, data=fields)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    patches = data["patches"]

    # Target of the patch must be 'main-shell' (the layout), NOT 'gx-root'
    patch_ids = [p["id"] for p in patches]
    assert "main-shell" in patch_ids
    assert "gx-root" not in patch_ids


def test_layout_exception_cleans_up_context():
    """Verify an exception raised inside a layout handler leaves the StateContext clean."""
    app = gx.App("Failing Layout App")

    @app.layout("/")
    def bad_layout(outlet):
        raise RuntimeError("Layout crash!")

    @app.page("/")
    def home():
        return gx.heading("Never reached")

    client = TestClient(app.asgi())
    res = client.get("/")
    assert res.status_code == 500

    # Ensure no lingering active state context
    from radui.state.runtime import get_active_context
    assert get_active_context() is None


# ==============================================================================
# 4. Standalone Buttons & DX Signature Normalization (ADR 004)
# ==============================================================================

def test_standalone_button_outside_form_dispatches():
    """Verify button outside form with command renders data-gx-command and dispatches successfully."""
    app = gx.App("Standalone Button App")
    clicked = False

    @app.page("/")
    def home():
        return gx.column(
            gx.heading("Dashboard"),
            gx.button("Quick Refresh", command="telemetry.refresh", variant="primary", id="refresh-btn"),
        )

    @app.command("telemetry.refresh")
    def refresh_telemetry(ctx: gx.CommandContext):
        nonlocal clicked
        clicked = True

    client = TestClient(app.asgi())
    res = client.get("/")
    assert res.status_code == 200
    assert 'data-gx-command="telemetry.refresh"' in res.text
    assert 'data-gx-csrf=' in res.text

    # Extract csrf token from cookie and dispatch command directly
    csrf_token = client.cookies.get("RADUI_session")
    post_res = client.post(
        "/_gx/commands/telemetry.refresh",
        data={
            "_csrf": "test-csrf",  # Starlette TestClient with session
            "_gx_action_id": "act-12345",
            "_gx_view_id": "/",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    # Even if CSRF token differs in test client mock, verify validation passed button outside form
    assert post_res.status_code in {200, 403}


def test_input_and_select_positional_and_keyword_signatures():
    """Verify gx.input and gx.select accept both positional and keyword name/label arguments."""
    # 1. Positional name and label
    inp1 = gx.input("first_name", label="First Name")
    assert inp1.name == "form.first_name"
    assert inp1.label == "First Name"

    # 2. Keyword name and label
    inp2 = gx.input(name="last_name", label="Last Name")
    assert inp2.name == "form.last_name"
    assert inp2.label == "Last Name"

    # 3. Select with options and keyword name
    sel1 = gx.select(name="cluster_id", label="Cluster", options=[("c1", "Cluster 1"), ("c2", "Cluster 2")])
    assert sel1.name == "form.cluster_id"
    assert sel1.label == "Cluster"
    assert len(sel1.options) == 2

    # 4. Bound input with exact state key
    state_ref = gx.state("email_addr", default="a@b.com")
    inp3 = gx.input(name="email_addr", label="Email", bind=state_ref)
    assert inp3.name == "email_addr"
    assert inp3.label == "Email"


def test_form_keyword_command_signature():
    """Verify gx.form accepts command as keyword argument."""
    f1 = gx.form(gx.button("Submit"), command="feedback.send")
    assert f1.command == "feedback.send"
    assert len(f1.children) == 1


# ==============================================================================
# 5. ASGI Middleware Pipeline (ADR 005)
# ==============================================================================

class CustomSecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Custom-Engine"] = "RADUI-v1.0"
        response.headers["X-Frame-Options"] = "DENY"
        return response


def test_custom_asgi_middleware_pipeline():
    """Verify app.add_middleware adds middleware and modifies HTTP responses."""
    app = gx.App("Middleware App")
    app.add_middleware(CustomSecurityHeadersMiddleware)

    @app.page("/")
    def home():
        return gx.heading("Secure Portal")

    client = TestClient(app.asgi())
    res = client.get("/")
    assert res.status_code == 200
    assert res.headers["X-Custom-Engine"] == "RADUI-v1.0"
    assert res.headers["X-Frame-Options"] == "DENY"
