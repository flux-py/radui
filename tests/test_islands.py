from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

import radui as gx
from radui.core.auth import User
from radui.core.islands import Island, island, sanitize_island_state, validate_island_config


def test_island_config_validation_and_invalid_combinations():
    assert validate_island_config("fetch", "eager") == ("fetch", "eager")
    assert validate_island_config("fetch", "visible") == ("fetch", "visible")
    assert validate_island_config("fetch", "interaction") == ("fetch", "interaction")
    assert validate_island_config("sse", "eager") == ("sse", "eager")
    assert validate_island_config("sse", "visible") == ("sse", "visible")
    assert validate_island_config("sse", "interaction") == ("sse", "interaction")
    assert validate_island_config("none", "eager") == ("none", "eager")

    with pytest.raises(ValueError, match="Invalid hydration strategy"):
        validate_island_config("websocket", "eager")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Invalid activation trigger"):
        validate_island_config("fetch", "hover")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="hydration='none'"):
        validate_island_config("none", "visible")

    with pytest.raises(ValueError, match="hydration='none'"):
        validate_island_config("none", "interaction")


def test_island_serialization_security_and_isolation():
    # Rejects unsupported non-JSON types
    with pytest.raises(TypeError, match="Unsupported non-JSON-serializable"):
        sanitize_island_state({"fn": lambda x: x})

    # Rejects secret / prototype-pollution keys
    for bad_key in ("password", "secret", "api_key", "csrf_token", "__proto__", "__class__"):
        with pytest.raises(ValueError, match="Forbidden or sensitive key"):
            sanitize_island_state({bad_key: "leak"})

    # Deep copy prevents shared mutable state between two islands
    shared = {"items": [1, 2]}
    i1 = island("a", gx.text("A"), id="isl-a", initial_state=shared)
    i2 = island("b", gx.text("B"), id="isl-b", initial_state=shared)
    shared["items"].append(3)
    assert i1.initial_state == {"items": [1, 2]}
    assert i2.initial_state == {"items": [1, 2]}

    # Untrusted dict deserialization cannot instantiate arbitrary Island nodes
    reg = gx.ComponentRegistry.builtins()
    assert len(reg._definitions) == 72
    with pytest.raises(gx.UnregisteredComponentError):
        reg.deserialize({"kind": "island", "name": "evil"})


def test_static_fetch_sse_and_trigger_rendering():
    app = gx.App("Islands App", session_secret="super-secret-key-at-least-32-chars-long!")
    s_secret = gx.state("server_only.secret_note", "do-not-leak")
    s_public = gx.state("public.count", 42)

    @app.island("static_banner", hydration="none", trigger="eager")
    def static_banner(title: str = "Static"):
        return gx.callout(title, variant="info")

    @app.island(
        "counter_widget",
        hydration="fetch",
        trigger="visible",
        allowed_state_keys=("public.count",),
    )
    def counter_widget(label: str = "Count"):
        return gx.card(
            gx.row(
                gx.text(f"{label}: {s_public.value}"),
                gx.badge("Live", variant="success"),
            )
        )

    @app.island("interactive_feed", hydration="sse", trigger="interaction")
    def interactive_feed():
        return gx.text("Click to activate SSE")

    @app.page("/")
    def home():
        # Ensure server-only secret state exists in session
        _ = s_secret.value
        _ = s_public.value
        return gx.column(
            static_banner(title="Pure SSR"),
            counter_widget(id="counter-1", label="Visits"),
            interactive_feed(id="feed-1"),
        )

    client = TestClient(app.asgi())
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    # Static island preserves SSR content and emits no serialized state
    assert 'data-gx-island="static_banner"' in html
    assert 'data-gx-hydration="none"' in html
    assert "Pure SSR" in html
    assert "do-not-leak" not in html

    # Visible fetch island preserves SSR content & allowlisted state only
    assert 'id="counter-1"' in html
    assert 'data-gx-hydration="fetch"' in html
    assert 'data-gx-trigger="visible"' in html
    assert "Visits: 42" in html

    # Interaction SSE island
    assert 'id="feed-1"' in html
    assert 'data-gx-hydration="sse"' in html
    assert 'data-gx-trigger="interaction"' in html

    # Client JS contains independent island lifecycle & no wrapper duplication
    js = client.get("/_gx/client.js").text
    assert "activateIsland" in js
    assert "IntersectionObserver" in js
    assert "pointerdown" in js


def test_island_fetch_hydration_endpoint_and_error_isolation():
    app = gx.App("Hydrate App", session_secret="super-secret-key-at-least-32-chars-long!")
    s_count = gx.state("counter.val", 7)
    s_internal = gx.state("internal.token", "top-secret")

    @app.island("metric", hydration="fetch", trigger="eager", allowed_state_keys=("counter.val",))
    def metric_island(label: str = "Metric"):
        _ = s_internal.value
        return gx.card(gx.text(f"{label}={s_count.value}"))

    fail_hydrate = [False]

    @app.island("broken", hydration="fetch", trigger="eager")
    def broken_island():
        if fail_hydrate[0]:
            raise RuntimeError("sensitive internal traceback detail")
        return gx.text("Initial SSR")

    @app.page("/")
    def index():
        return gx.column(
            metric_island(id="m1", label="CPU"),
            broken_island(id="b1", fallback=gx.text("Fallback")),
        )

    client = TestClient(app.asgi())
    assert client.get("/").status_code == 200
    fail_hydrate[0] = True

    # Valid fetch hydration returns inner HTML (no outer <div class="gx-island"> duplication) and allowlisted state
    r_ok = client.get(
        "/_gx/islands/m1",
        params={"name": "metric", "view_id": "/", "props": json.dumps({"label": "GPU"})},
    )
    assert r_ok.status_code == 200
    data = r_ok.json()
    assert data["ok"] is True
    assert data["island_id"] == "m1"
    assert "GPU=7" in data["html"]
    assert 'class="gx-island"' not in data["html"]
    assert data["state"] == {"counter.val": 7}
    assert "top-secret" not in r_ok.text

    # Failed island returns generic 500 without leaking exception detail; healthy island unaffected
    r_err = client.get("/_gx/islands/b1", params={"name": "broken", "view_id": "/"})
    assert r_err.status_code == 500
    assert "sensitive internal traceback detail" not in r_err.text
    assert client.get("/_gx/islands/m1", params={"name": "metric", "view_id": "/"}).status_code == 200


def test_island_endpoint_security_boundaries():
    current_user: list[User | None] = [None]
    app = gx.App(
        "Secure Islands",
        session_secret="super-secret-key-at-least-32-chars-long!",
        user_resolver=lambda _req: current_user[0],
    )

    @app.island("admin_panel", hydration="fetch", trigger="eager", require_role="admin")
    def admin_panel():
        return gx.text("Admin Only")

    @app.page("/")
    def index():
        return gx.text("Public")

    # Duplicate island registration fails clearly
    with pytest.raises(ValueError, match="island already registered"):
        @app.island("admin_panel")
        def dup():
            return gx.text("Dup")

    client = TestClient(app.asgi())

    # 1. Missing session -> 401
    assert client.get("/_gx/islands/a1", params={"name": "admin_panel"}).status_code == 401

    # Mint session
    assert client.get("/").status_code == 200

    # 2. Invalid island ID -> 400
    assert client.get("/_gx/islands/bad$id!", params={"name": "admin_panel"}).status_code == 400

    # 3. Unknown island name -> 404
    assert client.get("/_gx/islands/a1", params={"name": "nonexistent"}).status_code == 404

    # 4. Cross-origin / untrusted Origin -> 403
    assert client.get(
        "/_gx/islands/a1",
        params={"name": "admin_panel"},
        headers={"Origin": "https://evil.example.com"},
    ).status_code == 403

    # 5. Ordinary user -> 403; Admin user -> 200
    current_user[0] = User(id="u1", username="alice", roles=("viewer",))
    assert client.get("/_gx/islands/a1", params={"name": "admin_panel"}).status_code == 403

    current_user[0] = User(id="u2", username="root", roles=("admin",))
    assert client.get("/_gx/islands/a1", params={"name": "admin_panel"}).status_code == 200

    # 6. Forbidden props key -> 400
    assert client.get(
        "/_gx/islands/a1",
        params={"name": "admin_panel", "props": json.dumps({"__class__": "X"})},
    ).status_code == 400

    # 7. Unexpected prop not in handler signature -> 400
    assert client.get(
        "/_gx/islands/a1",
        params={"name": "admin_panel", "props": json.dumps({"unexpected_override": 123})},
    ).status_code == 400

    # 8. Non-finite float rejected
    with pytest.raises(ValueError, match="Non-finite float"):
        sanitize_island_state({"bad": float("nan")})

    # 9. Script/HTML injection in state attribute is escaped
    xss_island = island("xss_test", gx.text("<script>alert(1)</script>"), initial_state={"payload": "</script><img onerror=alert(1)>"})
    rendered = gx.ComponentRegistry.builtins().render(xss_island)
    assert "<script>alert(1)</script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "</script>" not in rendered
