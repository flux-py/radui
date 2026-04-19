from __future__ import annotations

import pytest
from starlette.testclient import TestClient

import radui as gx
from radui.components.nodes import Link
from radui.core.registry import ComponentRegistry


def test_component_tree_serializes_to_application_ir():
    app = gx.App("Test App", app_id="test-app")

    @app.page("/")
    def home():
        return gx.column(
            gx.heading("Hello", level=1, id="hero"),
            gx.text("World", id="body"),
        )

    ir = app.to_ir()
    assert ir.format == "radui.application"
    assert ir.version == "0.4"
    assert ir.routes[0].path == "/"
    assert ir.routes[0].root.kind == "column"
    assert ir.model_dump(mode="json")["routes"][0]["root"]["children"][0]["value"] == "Hello"


def test_html_renderer_escapes_text_and_title():
    app = gx.App("<script>alert(1)</script>")

    @app.page("/")
    def home():
        return gx.column(gx.heading("<img src=x onerror=alert(1)>", level=1))

    response = TestClient(app.asgi()).get("/")
    assert response.status_code == 200
    assert "&lt;script&gt;" in response.text
    assert "&lt;img src=x onerror=alert(1)&gt;" in response.text
    assert "<img src=x onerror=alert(1)>" not in response.text


def test_dangerous_link_schemes_rejected():
    with pytest.raises(ValueError):
        Link(label="click", href="javascript:alert(1)")
    with pytest.raises(ValueError):
        Link(label="click", href="data:text/html,evil")
    with pytest.raises(ValueError):
        Link(label="click", href="//evil.example/path")
    with pytest.raises(ValueError):
        Link(label="click", href="https://\nexample.com")
    with pytest.raises(ValueError):
        Link(label="click", href="https:relative-path")


def test_relative_and_https_links_are_allowed():
    assert Link(label="home", href="/docs").href == "/docs"
    assert Link(label="site", href="https://example.com").href == "https://example.com"


def test_duplicate_component_ids_rejected():
    app = gx.App("Test")

    @app.page("/")
    def home():
        return gx.column(
            gx.text("one", id="same"),
            gx.text("two", id="same"),
        )

    response = TestClient(app.asgi()).get("/")
    assert response.status_code == 500


def test_duplicate_routes_rejected():
    app = gx.App("Test")

    @app.page("/")
    def first():
        return gx.text("one")

    with pytest.raises(ValueError, match="already registered"):
        @app.page("/")
        def second():
            return gx.text("two")


def test_invalid_page_path_rejected():
    app = gx.App("Test")
    with pytest.raises(ValueError):
        @app.page("//evil")
        def home():
            return gx.text("x")


def test_unregistered_component_kind_rejected():
    registry = ComponentRegistry.builtins()
    with pytest.raises(ValueError, match="unregistered component"):
        registry.get("raw_html")


def test_not_found_is_standard_404():
    app = gx.App("Test")
    response = TestClient(app.asgi()).get("/missing")
    assert response.status_code == 404


def test_health_endpoint_healthy_and_draining():
    app = gx.App("Health Test App")

    with TestClient(app.asgi()) as client:
        # Standard healthy check -> 200 OK
        res = client.get("/_gx/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["version"] == "1.0.0"
        assert "worker_id" in data

        # When server begins draining / shutting down -> 503 Draining
        app._shutting_down = True
        res_drain = client.get("/_gx/health")
        assert res_drain.status_code == 503
        data_drain = res_drain.json()
        assert data_drain["status"] == "draining"
