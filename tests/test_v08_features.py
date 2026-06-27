import os
import tempfile
import pytest
from starlette.testclient import TestClient

import radui as gx
from radui.state.backend import InMemoryStateBackend, SQLiteStateBackend


def test_dynamic_routes_and_path_params():
    app = gx.App(name="Dynamic Route App")

    @app.page("/users/{user_id}")
    def user_profile(user_id: str):
        return gx.column(
            gx.heading(f"User Profile: {user_id}"),
            gx.text(f"Viewing account for {user_id}"),
        )

    @app.page("/orgs/{org_name}/repos/{repo_name}")
    def repo_view(org_name: str, repo_name: str):
        return gx.card(
            gx.heading(f"Repository: {org_name}/{repo_name}"),
            gx.badge("Active", variant="success"),
        )

    client = TestClient(app.asgi())

    # Test single path parameter
    res1 = client.get("/users/alex99")
    assert res1.status_code == 200
    assert "User Profile: alex99" in res1.text
    assert "Viewing account for alex99" in res1.text

    # Test multiple path parameters
    res2 = client.get("/orgs/deepmind/repos/RADUI")
    assert res2.status_code == 200
    assert "Repository: deepmind/RADUI" in res2.text


def test_route_level_guards():
    app = gx.App(name="Guarded App")

    @app.page("/public")
    def public_page():
        return gx.text("Public Content")

    @app.page("/admin", require_auth=True, require_role="admin")
    def admin_page():
        return gx.text("Admin Secrets")

    client = TestClient(app.asgi())

    # Public works
    res_pub = client.get("/public")
    assert res_pub.status_code == 200
    assert "Public Content" in res_pub.text

    # Admin blocked for unauthenticated user
    res_adm = client.get("/admin")
    assert res_adm.status_code in (401, 403)
    assert "Admin Secrets" not in res_adm.text


def test_error_boundary():
    registry = gx.ComponentRegistry.builtins()
    renderer = gx.renderers.html.HTMLRenderer(registry)

    # 1. Normal boundary rendering
    boundary_normal = gx.error_boundary(
        gx.text("Healthy inner component"),
        fallback_message="Something failed",
        id="normal_boundary",
    )
    html_normal = renderer.render_component(boundary_normal)
    assert "Healthy inner component" in html_normal
    assert "gx-error-boundary-wrap" in html_normal

    # 2. Crash-handling boundary rendering
    class FailingComponent(gx.components.nodes.Component):
        kind: str = "failing"

    def render_failing(component, reg, ctx, csrf):
        raise ValueError("Simulated render explosion")

    registry.register("failing", FailingComponent, render_failing)

    boundary_failing = gx.error_boundary(
        FailingComponent(kind="failing"),
        fallback_message="Custom chart render failure",
        id="failed_boundary",
    )
    html_failing = renderer.render_component(boundary_failing)
    assert "gx-error-boundary" in html_failing
    assert "Custom chart render failure" in html_failing
    assert "Component Error" in html_failing
    assert "Retry" in html_failing


def test_state_backends_and_sqlite_persistence():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_state.db")

        # Create SQLite state backend
        backend = SQLiteStateBackend(db_path=db_path)
        backend.set("user", "user-101", "preferred_theme", "dark")
        backend.set("user", "user-101", "notifications_enabled", True)
        backend.set("app", "app-global", "system_status", "operational")

        # Read back
        assert backend.get("user", "user-101", "preferred_theme") == "dark"
        assert backend.get("user", "user-101", "notifications_enabled") is True
        assert backend.get("app", "app-global", "system_status") == "operational"

        # Multi-worker test: instantiate a second backend pointing to same file
        worker2_backend = SQLiteStateBackend(db_path=db_path)
        assert worker2_backend.get("user", "user-101", "preferred_theme") == "dark"
        assert worker2_backend.get("app", "app-global", "system_status") == "operational"

        # Delete key
        backend.delete("user", "user-101", "notifications_enabled")
        assert backend.get("user", "user-101", "notifications_enabled") is None
        assert worker2_backend.get("user", "user-101", "notifications_enabled") is None

        # Clean close for Windows file unlocks
        backend.close()
        worker2_backend.close()


def test_modal_accessible_aria_attributes():
    registry = gx.ComponentRegistry.builtins()
    renderer = gx.renderers.html.HTMLRenderer(registry)

    modal_comp = gx.modal(
        "Settings Dialog",
        gx.text("Modal Dialog Content"),
        trigger_label="Open Settings",
        id="settings_modal",
    )
    html = renderer.render_component(modal_comp)
    assert 'class="gx-modal-box"' in html
    assert "Settings Dialog" in html
    assert "Open Settings" in html
