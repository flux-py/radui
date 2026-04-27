from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest
from starlette.testclient import TestClient

import radui as gx


class FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, object]] = []
        self.current: dict[str, object] | None = None

    def handle_starttag(self, tag: str, attrs):
        data = dict(attrs)
        if tag == "form":
            self.current = {"action": data.get("action"), "command": data.get("data-gx-command"), "fields": {}}
            self.forms.append(self.current)
        elif tag == "input" and self.current is not None:
            name = data.get("name")
            if name:
                fields = self.current["fields"]
                assert isinstance(fields, dict)
                if data.get("type") == "checkbox":
                    if "checked" in data:
                        fields[name] = data.get("value", "on")
                else:
                    fields[name] = data.get("value", "")

    def handle_endtag(self, tag: str):
        if tag == "form":
            self.current = None


def get_form(html: str, command: str) -> tuple[str, dict[str, str]]:
    parser = FormParser()
    parser.feed(html)
    for form in parser.forms:
        if form["command"] == command:
            fields = form["fields"]
            assert isinstance(fields, dict)
            return str(form["action"]), dict(fields)
    raise AssertionError(f"form not found: {command}")


def make_app(*, user_id_resolver=None):
    app = gx.App(
        "Interactive Test",
        app_id="interactive-test",
        session_secret="test-secret-that-is-long-enough-for-starlette-123",
        user_id_resolver=user_id_resolver,
    )
    count = gx.state("counter.value", 0, scope="session")
    name = gx.state("profile.name", "Ada", scope="session")
    enabled = gx.state("profile.notifications", True, scope="session")

    @app.command("counter.increment")
    def increment(ctx: gx.CommandContext):
        count.value += 1

    @app.page("/")
    def home():
        return gx.column(
            gx.text("Static, never invalidated", id="static-label"),
            gx.text(bind=count, format="Count: {value}"),
            gx.form(
                "counter.increment",
                gx.input("Name", bind=name),
                gx.checkbox("Notifications", bind=enabled),
                gx.button("Increment"),
            ),
        )

    return app, count, name, enabled


def test_get_renders_interactive_form_with_csrf_action_and_view_tokens():
    app, *_ = make_app()
    response = TestClient(app.asgi()).get("/")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert 'name="_csrf"' in response.text
    assert 'name="_gx_action_id"' in response.text
    assert 'name="_gx_view_id" value="/"' in response.text
    assert 'data-gx-command="counter.increment"' in response.text
    assert 'name="gx-event-cursor"' in response.text


def test_command_updates_bound_state_and_only_invalidated_components():
    app, count, name, enabled = make_app()
    client = TestClient(app.asgi())
    page = client.get("/")
    action, fields = get_form(page.text, "counter.increment")
    fields["profile.name"] = "Grace"
    # Simulate the browser omitting an unchecked checkbox from form submission.
    fields.pop("profile.notifications", None)

    response = client.post(action, data=fields)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    patch_ids = {patch["id"] for patch in body["patches"]}
    assert patch_ids == {
        "gx-input-profile.name",
        "gx-checkbox-profile.notifications",
        "gx-text-counter.value",
    }
    assert all("static-label" not in patch["html"] for patch in body["patches"])

    session_id = client.cookies.get("RADUI_session")
    assert session_id
    refreshed = client.get("/")
    assert "Count: 1" in refreshed.text
    assert 'value="Grace"' in refreshed.text
    assert "checked" not in re.search(r'<input id="gx-checkbox-profile.notifications-control"[^>]*>', refreshed.text).group(0)


def test_duplicate_action_id_replays_response_without_reexecuting_command():
    app, count, *_ = make_app()
    client = TestClient(app.asgi())
    page = client.get("/")
    action, fields = get_form(page.text, "counter.increment")

    first = client.post(action, data=fields)
    second = client.post(action, data=fields)

    assert first.status_code == second.status_code == 200
    assert first.json()["ok"] is True
    assert second.json()["replayed"] is True
    assert second.json()["patches"] == []
    refreshed = client.get("/")
    assert "Count: 1" in refreshed.text


def test_csrf_token_is_required():
    app, *_ = make_app()
    client = TestClient(app.asgi())
    page = client.get("/")
    action, fields = get_form(page.text, "counter.increment")
    fields.pop("_csrf")

    response = client.post(action, data=fields)

    assert response.status_code == 403
    assert response.json()["error"] == "Invalid CSRF token"


def test_cross_origin_command_is_rejected():
    app, *_ = make_app()
    client = TestClient(app.asgi())
    page = client.get("/")
    action, fields = get_form(page.text, "counter.increment")

    response = client.post(action, data=fields, headers={"Origin": "https://attacker.example"})

    assert response.status_code == 403
    assert response.json()["error"] == "Cross-origin request rejected"


def test_command_requires_urlencoded_form_content_type():
    app, *_ = make_app()
    client = TestClient(app.asgi())
    response = client.post("/_gx/commands/counter.increment", content="x=1", headers={"content-type": "text/plain"})
    assert response.status_code == 415


def test_state_isolation_between_two_browser_sessions():
    app, *_ = make_app()
    client_a = TestClient(app.asgi())
    client_b = TestClient(app.asgi())
    page_a = client_a.get("/")
    page_b = client_b.get("/")
    action_a, fields_a = get_form(page_a.text, "counter.increment")

    assert client_a.post(action_a, data=fields_a).status_code == 200
    assert "Count: 1" in client_a.get("/").text
    assert "Count: 0" in client_b.get("/").text


def test_user_scope_invalidation_is_published_to_other_view_in_same_session():
    class ObservedApp(gx.App):
        observed_sessions: list[str] = []

        def _session(self, request):
            session_id, csrf = super()._session(request)
            self.observed_sessions.append(session_id)
            return session_id, csrf

    app = ObservedApp(
        "User State",
        app_id="user-state",
        session_secret="test-secret-that-is-long-enough-for-starlette-123",
        user_id_resolver=lambda request: request.headers.get("x-test-user"),
    )
    preference = gx.state("preferences.theme", "light", scope="user")

    @app.command("theme.dark")
    def make_dark(ctx):
        preference.value = "dark"

    @app.page("/profile")
    def profile():
        return gx.text(bind=preference, format="Theme: {value}")

    @app.page("/settings")
    def settings():
        return gx.form("theme.dark", gx.button("Use dark theme"))

    profile_client = TestClient(app.asgi(), headers={"x-test-user": "alice"})
    settings_client = TestClient(app.asgi(), headers={"x-test-user": "alice"})
    profile_client.get("/profile")
    profile_session_id = app.observed_sessions[-1]
    page = settings_client.get("/settings")
    action, fields = get_form(page.text, "theme.dark")

    response = settings_client.post(action, data=fields)

    assert response.status_code == 200
    # The update from a separate browser session must be broadcast to the
    # session that previously rendered the same user's preference.
    records = app.events.history_snapshot(profile_session_id)
    assert any(
        record.event == "invalidate"
        and record.data.get("view_id") == "/profile"
        and record.data.get("component_ids") == ["gx-text-preferences.theme"]
        for record in records
    )
    refreshed = profile_client.get(
        "/_gx/refresh",
        params={"view_id": "/profile", "id": "gx-text-preferences.theme"},
    )
    assert refreshed.status_code == 200
    assert refreshed.headers["cache-control"] == "no-store"
    assert "Theme: dark" in refreshed.json()["patches"][0]["html"]


def test_static_application_ir_includes_commands_and_component_bindings():
    app, *_ = make_app()
    ir = app.to_ir().model_dump(mode="json")
    assert ir["version"] == "0.4"
    assert ir["commands"] == [{"id": "counter.increment"}]
    serialized = str(ir)
    assert "profile.name" in serialized
    assert "state_ref" not in serialized


def test_button_outside_form_is_rejected():
    app = gx.App("Invalid button", app_id="invalid-button")

    @app.page("/")
    def home():
        return gx.button("Do nothing")

    response = TestClient(app.asgi()).get("/")
    assert response.status_code == 500


def test_app_drop_session_clears_state_and_event_history():
    app, count, *_ = make_app()
    context = app.state_context(session_id="session-to-drop")
    context.write(count, 42)
    app.events.publish("session-to-drop", "invalidate", {"view_id": "/", "component_ids": ["x"]})

    app.drop_session("session-to-drop")

    new_context = app.state_context(session_id="new-session")
    assert new_context.read(count) == 0
    assert app.events.current_sequence("session-to-drop") == 0


def test_number_input_parses_scalar_string_to_declared_integer_type():
    app = gx.App(
        "Number Field",
        app_id="number-field",
        session_secret="test-secret-that-is-long-enough-for-starlette-123",
    )
    age = gx.state("profile.age", 20, scope="session")

    @app.command("profile.save")
    def save(ctx):
        assert isinstance(age.value, int)

    @app.page("/")
    def home():
        return gx.form(
            "profile.save",
            gx.input("Age", bind=age, input_type="number"),
            gx.button("Save"),
        )

    client = TestClient(app.asgi())
    page = client.get("/")
    action, fields = get_form(page.text, "profile.save")
    fields["profile.age"] = "42"
    response = client.post(action, data=fields)

    assert response.status_code == 200
    assert 'value="42"' in client.get("/").text


def test_invalid_number_form_value_is_rejected_without_mutating_state():
    app = gx.App(
        "Number Validation",
        app_id="number-validation",
        session_secret="test-secret-that-is-long-enough-for-starlette-123",
    )
    age = gx.state("profile.age", 20, scope="session")

    @app.command("profile.save")
    def save(ctx):
        pass

    @app.page("/")
    def home():
        return gx.form(
            "profile.save",
            gx.input("Age", bind=age, input_type="number"),
            gx.button("Save"),
        )

    client = TestClient(app.asgi())
    page = client.get("/")
    action, fields = get_form(page.text, "profile.save")
    fields["profile.age"] = "not-a-number"
    response = client.post(action, data=fields)

    assert response.status_code == 400
    assert 'value="20"' in client.get("/").text


def test_async_command_handler_updates_bound_state():
    app = gx.App(
        "Async Command",
        app_id="async-command",
        session_secret="test-secret-that-is-long-enough-for-starlette-123",
    )
    status = gx.state("job.status", "idle", scope="session")

    @app.command("job.start")
    async def start(ctx):
        status.value = "complete"

    @app.page("/")
    def home():
        return gx.column(
            gx.text(bind=status, format="Status: {value}"),
            gx.form("job.start", gx.button("Start")),
        )

    client = TestClient(app.asgi())
    page = client.get("/")
    action, fields = get_form(page.text, "job.start")
    response = client.post(action, data=fields)

    assert response.status_code == 200
    assert any("Status: complete" in patch["html"] for patch in response.json()["patches"])


def test_input_and_checkbox_cannot_be_used_outside_a_form():
    app = gx.App("Loose Input", app_id="loose-input")
    value = gx.state("field.value", "x")

    @app.page("/")
    def home():
        return gx.input("Field", bind=value)

    assert TestClient(app.asgi()).get("/").status_code == 500


def test_page_responses_include_restrictive_baseline_security_headers():
    app, *_ = make_app()
    response = TestClient(app.asgi()).get("/")
    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "same-origin"


def test_oversized_form_submission_is_rejected():
    app, *_ = make_app()
    client = TestClient(app.asgi())
    page = client.get("/")
    action, fields = get_form(page.text, "counter.increment")
    fields["profile.name"] = "x" * (70 * 1024)

    response = client.post(action, data=fields)

    assert response.status_code == 413


def test_invalid_component_id_is_rejected():
    with pytest.raises(ValueError, match="component id"):
        gx.text("bad id", id="bad id")


def test_ir_export_does_not_leave_fake_session_dependencies_behind():
    app, count, *_ = make_app()
    app.to_ir()
    context = app.state_context(session_id="real-session", user_id="u1", view_id="/")
    with context.track_component("counter"):
        context.read(count)
    change = context.write(count, 5)
    assert change.invalidations[0].context.session_id == "real-session"


def test_unmounted_component_dependencies_are_removed_after_conditional_render():
    class ObservedApp(gx.App):
        observed_sessions: list[str] = []

        def _session(self, request):
            session_id, csrf = super()._session(request)
            self.observed_sessions.append(session_id)
            return session_id, csrf

    app = ObservedApp(
        "Conditional UI",
        app_id="conditional-ui",
        session_secret="test-secret-that-is-long-enough-for-starlette-123",
    )
    visible = gx.state("ui.visible", True, scope="session")
    detail = gx.state("ui.detail", "secret", scope="session")

    @app.command("ui.hide")
    def hide(ctx):
        visible.value = False

    @app.page("/")
    def home():
        if visible.value:
            return gx.column(
                gx.text(bind=detail, id="conditional-detail"),
                gx.form("ui.hide", gx.button("Hide")),
            )
        return gx.text("Hidden", id="hidden-label")

    client = TestClient(app.asgi())
    page = client.get("/")
    session_id = app.observed_sessions[-1]
    context = app.state_context(session_id=session_id, view_id="/")
    assert app.state_runtime.dependencies.dependents(detail._state_key(context))

    action, fields = get_form(page.text, "ui.hide")
    response = client.post(action, data=fields)

    assert response.status_code == 200
    assert response.json()["patches"][0]["id"] == "gx-root"
    assert app.state_runtime.dependencies.dependents(detail._state_key(context)) == {}


def test_duplicate_action_while_first_request_is_running_returns_conflict():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    entered = Event()
    release = Event()
    calls = []
    app = gx.App(
        "Concurrent Action",
        app_id="concurrent-action",
        session_secret="test-secret-that-is-long-enough-for-starlette-123",
    )
    count = gx.state("counter.value", 0, scope="session")

    @app.command("counter.increment")
    def increment(ctx):
        calls.append("called")
        entered.set()
        if not release.wait(timeout=3):
            raise TimeoutError("test did not release first command")
        count.value += 1

    @app.page("/")
    def home():
        return gx.column(
            gx.text(bind=count, format="Count: {value}"),
            gx.form("counter.increment", gx.button("Increment")),
        )

    with TestClient(app.asgi()) as first_client, TestClient(app.asgi()) as second_client:
        page = first_client.get("/")
        action, fields = get_form(page.text, "counter.increment")
        second_client.cookies.update(first_client.cookies)

        with ThreadPoolExecutor(max_workers=1) as pool:
            first_future = pool.submit(first_client.post, action, data=dict(fields))
            assert entered.wait(timeout=2)
            second_response = second_client.post(action, data=dict(fields))
            release.set()
            first_response = first_future.result(timeout=4)

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert "already processing" in second_response.json()["error"]
    assert calls == ["called"]


def test_unexpected_form_fields_are_rejected():
    app, *_ = make_app()
    client = TestClient(app.asgi())
    page = client.get("/")
    action, fields = get_form(page.text, "counter.increment")
    fields["admin"] = "true"

    response = client.post(action, data=fields)

    assert response.status_code == 400
    assert response.json()["error"] == "Unexpected form fields"


def test_malformed_percent_encoding_is_rejected():
    app, *_ = make_app()
    client = TestClient(app.asgi())
    page = client.get("/")
    action, fields = get_form(page.text, "counter.increment")
    from urllib.parse import urlencode

    fields["profile.name"] = "%zz"
    raw = urlencode(fields).replace("%25zz", "%zz")
    response = client.post(
        action,
        content=raw,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "Malformed form encoding"


def test_command_response_is_not_cacheable():
    app, *_ = make_app()
    client = TestClient(app.asgi())
    page = client.get("/")
    action, fields = get_form(page.text, "counter.increment")
    response = client.post(action, data=fields)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_chunked_request_without_content_length_is_still_size_limited():
    from urllib.parse import urlencode

    app = gx.App(
        "Chunked Body",
        app_id="chunked-body",
        session_secret="test-secret-that-is-long-enough-for-starlette-123",
        max_form_bytes=1024,
    )
    value = gx.state("field.value", "", scope="session")

    @app.command("field.save")
    def save(ctx):
        pass

    @app.page("/")
    def home():
        return gx.form("field.save", gx.input("Value", bind=value), gx.button("Save"))

    client = TestClient(app.asgi())
    page = client.get("/")
    action, fields = get_form(page.text, "field.save")
    fields["field.value"] = "x" * 1800
    body = urlencode(fields).encode("utf-8")
    chunks = (body[index:index + 400] for index in range(0, len(body), 400))

    response = client.post(
        action,
        content=chunks,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.request.headers.get("content-length") is None
    assert response.request.headers.get("transfer-encoding") == "chunked"
    assert response.status_code == 413
