import pytest
from starlette.requests import Request
from starlette.testclient import TestClient

import radui as gx
from radui.core.auth import RBACPolicy, User
from radui.renderers.html import HTMLRenderer


def test_user_rbac_evaluation():
    admin = User(id="u1", username="alice", roles=frozenset(["admin"]))
    editor = User(id="u2", username="bob", roles=frozenset(["editor"]), permissions=frozenset(["publish"]))
    viewer = User(id="u3", username="charlie", roles=frozenset(["viewer"]))

    assert admin.has_role("admin") is True
    assert admin.has_role("editor") is True  # Admin inherits all roles
    assert admin.has_permission("delete_everything") is True

    assert editor.has_role("editor") is True
    assert editor.has_role("admin") is False
    assert editor.has_permission("publish") is True
    assert editor.has_permission("delete_database") is False

    assert viewer.has_role("viewer") is True
    assert viewer.has_permission("publish") is False


def test_app_rbac_command_guards():
    app = gx.App("rbac-test")

    @app.page("/")
    def index():
        return gx.column(
            gx.form("public_action", gx.button("Public", id="btn-pub")),
            gx.form("protected_action", gx.button("Protected", id="btn-prot")),
            gx.form("admin_action", gx.button("Admin Only", id="btn-adm")),
        )

    @app.command("public_action")
    def public_cmd(ctx):
        pass

    @app.command("protected_action", require_auth=True)
    def protected_cmd(ctx):
        pass

    @app.command("admin_action", require_role="admin")
    def admin_cmd(ctx):
        pass

    client = TestClient(app.asgi())

    # Get page to extract forms
    res = client.get("/")
    assert res.status_code == 200

    from tests.test_interactivity import get_form

    # 1. Public action should succeed without auth
    action_pub, fields_pub = get_form(res.text, "public_action")
    resp1 = client.post(action_pub, data=fields_pub)
    assert resp1.status_code == 200
    assert resp1.json()["ok"] is True

    # 2. Protected action without user_id in session should return 401
    action_prot, fields_prot = get_form(res.text, "protected_action")
    resp2 = client.post(action_prot, data=fields_prot)
    assert resp2.status_code == 401
    assert "Authentication required" in resp2.json()["error"]


def test_optimistic_form_and_action_card():
    renderer = HTMLRenderer()

    f = gx.form(
        "save_settings",
        gx.button("Save"),
        optimistic=True,
        id="settings-form",
    )
    html_f = renderer.render_component(f, csrf_token="test-csrf")
    assert 'data-gx-optimistic="true"' in html_f

    btn = gx.button("Instant Action", command="do_instant", optimistic=True, id="instant-btn")
    html_b = renderer.render_component(btn, csrf_token="test-csrf")
    assert 'data-gx-optimistic="true"' in html_b


def test_generative_slot_attributes():
    renderer = HTMLRenderer()

    slot = gx.generative_slot(
        "ai_output",
        gx.text(value="Initial analysis"),
        streaming=True,
        scope="dashboard",
        id="slot-ai",
    )
    html = renderer.render_component(slot)
    assert 'data-gx-slot="ai_output"' in html
    assert "Initial analysis" in html
    assert 'id="slot-ai"' in html
