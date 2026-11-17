from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import pytest

import radui as gx
from radui.cli import cmd_audit, cmd_export


def test_v09_component_registry_count():
    reg = gx.ComponentRegistry.builtins()
    assert len(reg._definitions) >= 60
    assert len(reg._definitions) == 72


def test_v09_new_components_rendering():
    app = gx.App("Test v0.9 Components", app_id="test-v09")
    ctx = app.state_context(session_id="s1")
    s_date = gx.state("date_val", "2026-11-15", scope="session")
    s_time = gx.state("time_val", "12:00", scope="session")
    s_slider = gx.state("slider_val", 42.0, scope="session")

    comp = gx.column(
        gx.toast("Saved successfully", title="Success", variant="success"),
        gx.toast_container(gx.toast("Item deleted", variant="danger")),
        gx.tooltip("Tooltip text", gx.button("Hover me")),
        gx.popover("Popover Title", gx.text("Popover body"), trigger_label="Click info"),
        gx.accordion(
            gx.accordion_item("Section 1", gx.text("Content 1"), open=True),
            gx.accordion_item("Section 2", gx.text("Content 2")),
        ),
        gx.drawer("Settings Drawer", gx.text("Drawer contents"), trigger_label="Open Settings"),
        gx.breadcrumb(
            gx.breadcrumb_item("Home", href="/"),
            gx.breadcrumb_item("Dashboard", href="/dashboard"),
            gx.breadcrumb_item("Settings", active=True),
        ),
        gx.pagination(current_page=2, total_pages=5, command="change.page"),
        gx.progress_bar(value=75.0, max_value=100.0, variant="primary", striped=True, animated=True),
        gx.progress_circle(value=60.0, size=64, stroke_width=6, variant="success"),
        gx.avatar(name="Jane Doe", size="lg", status="online"),
        gx.avatar_group(
            gx.avatar(name="Alice"),
            gx.avatar(name="Bob"),
            gx.avatar(name="Charlie"),
            gx.avatar(name="Dave"),
            gx.avatar(name="Eve"),
            max_visible=3,
        ),
        gx.date_picker("Select Date", bind=s_date),
        gx.time_picker("Select Time", bind=s_time),
        gx.slider("Volume", bind=s_slider, min_value=0.0, max_value=100.0, step=1.0),
        gx.split_panel(gx.text("Left Pane"), gx.text("Right Pane"), direction="horizontal", initial_ratio=0.4),
        gx.dropdown_menu(
            trigger_label="Actions",
            items=[
                gx.dropdown_menu_item("Profile", href="/profile"),
                gx.dropdown_menu_item("Delete", command="item.delete", danger=True),
            ],
        ),
        gx.kbd("Ctrl", "K"),
        gx.container(gx.text("Centered container"), max_width="960px"),
        gx.stack(gx.badge("Tag 1"), gx.badge("Tag 2"), direction="horizontal", gap=8),
        gx.tag("Beta Feature", variant="warning", removable=True),
        gx.download_button("Export Report", "report.txt", "Report contents", mime_type="text/plain"),
    )

    html = app.renderer.render_component(comp, state_context=ctx)
    assert "gx-toast-success" in html
    assert "Saved successfully" in html
    assert "gx-tooltip-content" in html
    assert "gx-popover-panel" in html
    assert "gx-accordion-item" in html
    assert "gx-drawer-panel" in html
    assert "gx-breadcrumb" in html
    assert "gx-pagination" in html
    assert "gx-progress-bar" in html
    assert "gx-progress-circle" in html
    assert "gx-avatar" in html
    assert "gx-avatar-more" in html  # Overflow avatar +2
    assert "gx-datepicker" in html or "type=\"date\"" in html
    assert "gx-timepicker" in html or "type=\"time\"" in html
    assert "gx-slider" in html
    assert "gx-split-panel" in html
    assert "gx-dropdown-menu" in html
    assert "gx-kbd" in html
    assert "gx-container" in html
    assert "gx-stack" in html
    assert "gx-tag" in html
    assert "Export Report" in html


def test_data_engine_query_swr_and_cache():
    fetch_count = 0

    def fetch_data():
        nonlocal fetch_count
        fetch_count += 1
        return {"users": ["Alice", "Bob"], "count": fetch_count}

    gx.invalidate_query("test_users")

    # First fetch: cache miss
    res1 = gx.query("test_users", fetch_data, stale_time=1.0)
    assert res1["count"] == 1
    assert fetch_count == 1

    # Second fetch immediately: cache hit
    res2 = gx.query("test_users", fetch_data, stale_time=1.0)
    assert res2["count"] == 1
    assert fetch_count == 1

    # Invalidate query
    gx.invalidate_query("test_users")
    res3 = gx.query("test_users", fetch_data, stale_time=1.0)
    assert res3["count"] == 2
    assert fetch_count == 2

    # Async fetcher passed to synchronous gx.query (runs in worker thread without deadlocking)
    async def async_fetch():
        return {"mode": "async_fn_in_sync_query"}

    res_async_in_sync = gx.query("test_async_fn", async_fetch)
    assert res_async_in_sync["mode"] == "async_fn_in_sync_query"

    # Native async gx.aquery
    import asyncio
    async def native_async_test():
        async def fetch_coro():
            return {"status": "ok_coro"}
        res = await gx.aquery("test_native_coro", fetch_coro)
        assert res["status"] == "ok_coro"

    asyncio.run(native_async_test())


def test_data_engine_cached_decorator():
    call_count = 0

    @gx.cached(ttl=60.0)
    def compute_sum(a: int, b: int) -> int:
        nonlocal call_count
        call_count += 1
        return a + b

    assert compute_sum(2, 3) == 5
    assert call_count == 1

    # Call with same arguments: cached
    assert compute_sum(2, 3) == 5
    assert call_count == 1

    # Call with different arguments: recomputed
    assert compute_sum(4, 5) == 9
    assert call_count == 2


def test_data_engine_paginate_helper():
    items = list(range(1, 26))  # 25 items
    page_items, total_pages, total_items = gx.paginate(items, page=2, page_size=10)
    assert total_items == 25
    assert total_pages == 3
    assert page_items == [11, 12, 13, 14, 15, 16, 17, 18, 19, 20]


def test_persistent_nested_layouts():
    app = gx.App("Nested Layout App")

    @app.layout("/dashboard")
    def dashboard_shell(outlet: gx.Component):
        return gx.column(
            gx.heading("Dashboard Shell", level=1, id="dash-hdr"),
            outlet,
            id="dash-shell",
        )

    @app.page("/dashboard/metrics")
    def metrics_page():
        return gx.card(gx.text("Metrics view"), id="metrics-card")

    ctx = app.state_context(session_id="s1")
    root = app._build_root(app._pages["/dashboard/metrics"], ctx)
    assert root.id == "dash-shell"
    assert len(root.children) == 2
    assert root.children[0].id == "dash-hdr"
    assert root.children[1].id == "metrics-card"


def test_theme_rtl_direction():
    theme = gx.Theme(name="arabic", direction="rtl")
    css = theme.to_css()
    assert "direction: rtl;" in css

    app = gx.App("RTL App", theme=theme)

    @app.page("/")
    def home():
        return gx.text("مرحبا")

    ctx = app.state_context(session_id="s1")
    doc_html = app.renderer.render_document(
        "RTL Test",
        app._build_root(app._pages["/"], ctx),
        direction=theme.direction,
    )
    assert 'dir="rtl"' in doc_html


def test_distributed_redis_and_postgres_backends():
    # Production mode without Redis server must raise StateBackendUnavailableError (split-brain prevention)
    strict_backend = gx.RedisStateBackend("redis://127.0.0.1:6399/15", allow_fallback=False)
    with pytest.raises(gx.StateBackendUnavailableError):
        strict_backend.set("session", "u1", "k", "v")

    # Explicit degraded mode with allow_fallback=True
    redis_backend = gx.RedisStateBackend("redis://localhost:6379/15", allow_fallback=True)
    redis_backend.set("session", "user_123", "theme", "dark")
    assert redis_backend.get("session", "user_123", "theme") == "dark"
    all_keys = redis_backend.get_all("session", "user_123")
    assert all_keys["theme"] == "dark"
    redis_backend.delete("session", "user_123", "theme")
    assert redis_backend.get("session", "user_123", "theme") is None

    pg_backend = gx.PostgreSQLStateBackend()
    pg_backend.set("app", "global", "maintenance", False)
    assert pg_backend.get("app", "global", "maintenance") is False
    pg_backend.close()

    redis_jobs = gx.RedisJobBackend()
    fence_token = redis_jobs.acquire_lease("job-abc", ttl_seconds=10)
    assert fence_token is not None and fence_token >= 1
    assert redis_jobs.validate_fence("job-abc", fence_token) is True
    assert redis_jobs.validate_fence("job-abc", fence_token + 99) is False
    redis_jobs.release_lease("job-abc")


def test_cli_a11y_audit_and_static_export(tmp_path: Path):
    app_py = tmp_path / "app.py"
    app_py.write_text(
        """
import radui as gx

app = gx.App("Audited App")

@app.page("/")
def home():
    s = gx.state("q", "", scope="session")
    return gx.column(
        gx.heading("Welcome", level=1),
        gx.heading("Subtitle", level=2),
        gx.input("Search Query", bind=s),
    )
""",
        encoding="utf-8",
    )

    # Test audit --a11y
    audit_args = argparse.Namespace(target=str(app_py), a11y=True)
    res = cmd_audit(audit_args)
    assert res == 0

    # Test export --static
    dist_dir = tmp_path / "dist"
    export_args = argparse.Namespace(target=str(app_py), format="static", static=True, output=str(dist_dir))
    res_export = cmd_export(export_args)
    assert res_export == 0
    index_html = dist_dir / "index.html"
    assert index_html.exists()
    content = index_html.read_text(encoding="utf-8")
    assert "<!doctype html>" in content
    assert "Search Query" in content


def test_i18n_translation_and_formatters():
    gx.t("hello")  # Fallback to key
    translator = gx.Translator(default_locale="en")
    translator.load_catalog("es", {"welcome": "Bienvenido, {name}!"})
    translator.load_catalog("ar", {"welcome": "مرحبا بك يا {name}!"})

    assert translator.t("welcome", locale="es", name="Carlos") == "Bienvenido, Carlos!"
    assert translator.t("welcome", locale="ar", name="أحمد") == "مرحبا بك يا أحمد!"

    # Format numbers & currencies
    assert gx.format_number(1234567) == "1,234,567"
    assert gx.format_number(1234567, locale="de") == "1.234.567"
    assert gx.format_number(1234567, locale="fr") == "1 234 567"
    assert gx.format_currency(99.95, currency="USD") == "$99.95"
    assert gx.format_currency(1500, currency="EUR") == "€1,500"

    # Format dates
    dt_str = "2026-11-15T10:00:00"
    assert "2026" in gx.format_date(dt_str, format="short")


def test_plugin_manager_lifecycle():
    pm = gx.PluginManager()

    class CustomAnalyticsPlugin(gx.Plugin):
        name = "analytics_plugin"
        version = "2.0.0"

        def on_load(self, app):
            app._analytics_loaded = True

    plugin = CustomAnalyticsPlugin()
    pm.register(plugin)
    assert pm.get("analytics_plugin") is plugin

    app = gx.App("Plugin App")
    pm.apply_to_app(app)
    assert getattr(app, "_analytics_loaded", False) is True


def test_rate_limiter():
    limiter = gx.RateLimiter(requests_per_minute=2, burst=1)
    # 2 rpm + 1 burst = 3 allowed
    ok1, _ = limiter.check("client-ip-1")
    ok2, _ = limiter.check("client-ip-1")
    ok3, _ = limiter.check("client-ip-1")
    ok4, retry_after = limiter.check("client-ip-1")

    assert ok1 is True
    assert ok2 is True
    assert ok3 is True
    assert ok4 is False
    assert retry_after > 0

    # Different client key is unrestricted
    other_ok, _ = limiter.check("client-ip-2")
    assert other_ok is True


def test_ai_chat_repository_persistence():
    repo = gx.SQLiteChatRepository(":memory:")
    msg1 = repo.add_message("thread-101", "user", "Hello RADUI AI")
    msg2 = repo.add_message("thread-101", "assistant", "Hello! How can I assist you?", metadata={"model": "deepmind"})

    assert msg1.id.startswith("msg-")
    assert msg2.metadata["model"] == "deepmind"

    messages = repo.get_messages("thread-101")
    assert len(messages) == 2
    assert messages[0].content == "Hello RADUI AI"
    assert messages[1].content == "Hello! How can I assist you?"

    threads = repo.list_threads()
    assert "thread-101" in threads

    repo.delete_thread("thread-101")
    assert len(repo.get_messages("thread-101")) == 0
    repo.close()


def test_global_gx_notify():
    app = gx.App("Notify App")
    records = gx.notify("System update available", title="Notice", variant="warning")
    assert len(records) >= 1
    assert records[0].event == "gx:toast"
    assert records[0].data["message"] == "System update available"
    assert records[0].data["variant"] == "warning"


def test_documentation_and_registry_consistency():
    reg = gx.ComponentRegistry.builtins()
    assert len(reg._definitions) == 72
    readme = Path("README.md").read_text(encoding="utf-8")
    for comp_name in reg._definitions.keys():
        assert f"`ui.{comp_name}`" in readme or f"`gx.{comp_name}`" in readme, f"Component {comp_name} missing from README"


def test_cli_commands_documentation_consistency():
    import re
    cli_path = Path("radui/cli.py") if Path("radui/cli.py").exists() else Path("RADUI/cli.py")
    cli_text = cli_path.read_text(encoding="utf-8")
    cli_commands = re.findall(r'add_parser\(["\']([a-zA-Z0-9_-]+)["\']', cli_text)
    assert len(cli_commands) == 46
    readme = Path("README.md").read_text(encoding="utf-8")
    for cmd in cli_commands:
        assert f"`radui {cmd}" in readme or f"`RADUI {cmd}" in readme, f"CLI command {cmd} missing from README"


def test_plugin_dependency_validation():
    pm = gx.PluginManager()

    class PluginA(gx.Plugin):
        name = "plugin_a"
        dependencies = ["plugin_b"]

    pm.register(PluginA())
    missing = pm.validate_dependencies()
    assert len(missing) == 1
    assert "requires 'plugin_b'" in missing[0]

    class PluginB(gx.Plugin):
        name = "plugin_b"

    pm.register(PluginB())
    assert len(pm.validate_dependencies()) == 0

    unregistered = pm.unregister("plugin_a")
    assert unregistered.name == "plugin_a"
    assert pm.get("plugin_a") is None


def test_redis_job_fencing_tokens():
    redis_jobs = gx.RedisJobBackend()
    token = redis_jobs.acquire_lease("job-fenced-1", ttl_seconds=10)
    assert token is not None
    assert token >= 1
    assert redis_jobs.validate_fence("job-fenced-1", token) is True
    redis_jobs.release_lease("job-fenced-1")


@pytest.mark.anyio
async def test_aquery_async_fetching():
    call_count = 0

    async def fetch_async():
        nonlocal call_count
        call_count += 1
        return {"result": "async_ok", "count": call_count}

    gx.invalidate_query("test_async_k")
    r1 = await gx.aquery("test_async_k", fetch_async, stale_time=2.0)
    assert r1["result"] == "async_ok"
    assert call_count == 1

    # Second call hits cache
    r2 = await gx.aquery("test_async_k", fetch_async, stale_time=2.0)
    assert r2["count"] == 1
    assert call_count == 1


def test_localized_short_dates():
    dt_str = "2026-11-15T10:00:00"
    assert gx.format_date(dt_str, format="short") == "2026-11-15"
    assert gx.format_date(dt_str, format="short", locale="de") == "15.11.2026"
    assert gx.format_date(dt_str, format="short", locale="fr") == "15/11/2026"


def test_durable_idempotency_engine(tmp_path: Path):
    db_file = tmp_path / "idemp.db"

    # 1. InMemoryIdempotencyBackend
    mem = gx.InMemoryIdempotencyBackend()
    fp1 = gx.compute_payload_fingerprint("transfer.funds", {"amount": 100, "to": "Alice"})
    res1 = mem.begin("act-1", fp1)
    assert res1.is_new is True
    assert res1.completed is False
    mem.complete("act-1", {"status": "transferred", "tx_id": "tx-999"})

    # Same action submitted twice: returns completed cached response
    res1_dup = mem.begin("act-1", fp1)
    assert res1_dup.is_new is False
    assert res1_dup.completed is True
    assert res1_dup.response == {"status": "transferred", "tx_id": "tx-999"}

    # Same action ID with different payload: conflict
    fp2 = gx.compute_payload_fingerprint("transfer.funds", {"amount": 500, "to": "Bob"})
    res1_conflict = mem.begin("act-1", fp2)
    assert res1_conflict.conflict is True

    # 2. SQLiteIdempotencyBackend persistence and multi-instance sharing
    backend1 = gx.SQLiteIdempotencyBackend(str(db_file))
    r_act2 = backend1.begin("act-2", fp1)
    assert r_act2.is_new is True
    backend1.complete("act-2", {"result": "saved"})

    # Worker 2 connects to the same database file (server restart / multi-worker simulation)
    backend2 = gx.SQLiteIdempotencyBackend(str(db_file))
    r_act2_w2 = backend2.begin("act-2", fp1)
    assert r_act2_w2.is_new is False
    assert r_act2_w2.completed is True
    assert r_act2_w2.response == {"result": "saved"}

    # Atomic execution with business write
    with backend1.transaction() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, total INT);")
        r_order = backend1.begin("act-order-1", fp1)
        if not r_order.completed:
            conn.execute("INSERT INTO orders VALUES ('ord-1', 100);")
            backend1.complete("act-order-1", {"order_id": "ord-1"})

    # Check order was committed
    with backend1.transaction() as conn:
        row = conn.execute("SELECT total FROM orders WHERE id = 'ord-1'").fetchone()
        assert row[0] == 100

    # 3. RedisIdempotencyBackend in fail-closed mode
    redis_strict = gx.RedisIdempotencyBackend("redis://127.0.0.1:6399/15", allow_fallback=False)
    with pytest.raises(gx.IdempotencyBackendUnavailableError):
        redis_strict.begin("act-redis", fp1)

    # Redis degraded mode with explicit allow_fallback=True
    redis_fallback = gx.RedisIdempotencyBackend("redis://localhost:6379/15", allow_fallback=True)
    r_fb = redis_fallback.begin("act-fb", fp1)
    assert r_fb.is_new is True
    redis_fallback.complete("act-fb", {"ok": True})
    assert redis_fallback.get("act-fb").status == "COMPLETED"


@pytest.mark.anyio
async def test_distributed_event_backend_and_sse_replay(tmp_path: Path):
    db_file = tmp_path / "events.db"

    # SQLiteEventBackend persistence across instances
    backend1 = gx.SQLiteEventBackend(str(db_file))
    ev1 = backend1.append_sync("session-1", {"theme": "dark"}, event_type="state.patch")
    ev2 = backend1.append_sync("session-1", {"count": 1}, event_type="state.patch")
    assert ev1.sequence == 1
    assert ev2.sequence == 2
    assert ev1.session_id == "session-1"

    # Worker 2 reads events
    backend2 = gx.SQLiteEventBackend(str(db_file))
    replayed = await backend2.replay_after("session-1", sequence=0, limit=10)
    assert len(replayed) == 2
    assert replayed[0].sequence == 1
    assert replayed[1].sequence == 2

    # Replay after sequence 1
    replayed_after_1 = await backend2.replay_after("session-1", sequence=1, limit=10)
    assert len(replayed_after_1) == 1
    assert replayed_after_1[0].sequence == 2

    # EventBroker with SQLite backend
    broker = gx.EventBroker(backend=backend2)
    ev3 = broker.publish("session-1", "custom.event", {"hello": "world"})
    assert ev3.sequence == 3

    # Race-free replay stream: replay from sequence 1 delivers 2 and 3
    stream_iter = broker.stream("session-1", last_event_id=1, keepalive_seconds=0.1)
    msg1 = await stream_iter.__anext__()
    assert "id: 2" in msg1
    msg2 = await stream_iter.__anext__()
    assert "id: 3" in msg2


def test_app_idempotency_and_conflict_handling(tmp_path: Path):
    from starlette.testclient import TestClient

    db_file = tmp_path / "app_idemp.db"
    idemp_backend = gx.SQLiteIdempotencyBackend(str(db_file))
    app = gx.App("Idempotency Test App", idempotency_backend=idemp_backend)

    execution_count = 0
    s_item = gx.state("item", "", scope="session")

    @app.command("order.create")
    def create_order(ctx: gx.CommandContext):
        nonlocal execution_count
        execution_count += 1

    @app.page("/")
    def home():
        return gx.form(
            "order.create",
            gx.input("Item Name", bind=s_item),
            gx.button("Submit", variant="primary"),
            id="order-form",
        )

    client = TestClient(app.asgi())
    resp_init = client.get("/")
    assert resp_init.status_code == 200
    csrf_token = client.cookies.get("RADUI_session")

    # Extract CSRF token from page HTML
    import re
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', resp_init.text)
    token = m.group(1) if m else "test"

    action_id = "test-action-uuid-101"

    # First submission
    resp1 = client.post(
        "/_gx/commands/order.create",
        data={"_csrf": token, "_gx_action_id": action_id, "_gx_view_id": "/", "item": "Widget"},
    )
    assert resp1.status_code == 200, resp1.text
    assert resp1.json()["ok"] is True
    assert execution_count == 1

    # Second submission with exact same action ID and payload: returns cached response without re-executing
    resp2 = client.post(
        "/_gx/commands/order.create",
        data={"_csrf": token, "_gx_action_id": action_id, "_gx_view_id": "/", "item": "Widget"},
    )
    assert resp2.status_code == 200
    assert execution_count == 1  # Did NOT re-execute

    # Third submission with same action ID but DIFFERENT payload: returns 409 Conflict
    resp3 = client.post(
        "/_gx/commands/order.create",
        data={"_csrf": token, "_gx_action_id": action_id, "_gx_view_id": "/", "item": "DifferentWidget"},
    )
    assert resp3.status_code == 409
    assert resp3.json()["conflict"] is True
    assert execution_count == 1




