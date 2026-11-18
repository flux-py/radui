"""Automated Test Suite for RADUI-Native Documentation Application (docs_site).

Validates all 11 documentation routes, layout hierarchy, command dispatch,
interactive component explorer, computed state derivation, and event tracing.
"""

from __future__ import annotations

import re
import pytest
from starlette.testclient import TestClient

from docs_site.app import app, s_price, s_tax, s_calc_total
from docs_site.data import COMPONENTS, CLI_COMMANDS, ADRS


@pytest.fixture
def client():
    """Provides a Starlette TestClient configured with the docs_site ASGI handler."""
    return TestClient(app.asgi())


def test_docs_site_metadata_integrity():
    """Verify data catalog contains all 72 components, 46 CLI commands, and 18 ADRs."""
    assert len(COMPONENTS) == 72
    assert len(CLI_COMMANDS) == 46
    assert len(ADRS) == 18


def test_docs_site_all_routes_render_200(client):
    """Verify all 24 documentation routes render with HTTP 200 OK."""
    routes = [
        "/",
        "/getting-started",
        "/api-reference",
        "/architecture",
        "/components",
        "/components-layout",
        "/components-forms",
        "/components-data",
        "/components-feedback",
        "/components-ai",
        "/cli",
        "/cli-workflows",
        "/state",
        "/transport",
        "/jobs",
        "/ai",
        "/adrs",
        "/interactions",
        "/navigation",
        "/resumability",
        "/compiler",
        "/web-components",
        "/streaming-ssr",
        "/integrations",
    ]

    for route in routes:
        response = client.get(route)
        assert response.status_code == 200, f"Route {route} failed with status {response.status_code}"
        assert "radui" in response.text.lower()
        assert "Start here" in response.text or "Core concepts" in response.text  # Layout sidebar check
        assert "docs" in response.text.lower()  # Header pill


def test_docs_site_home_hero_rendering(client):
    """Verify home page contains hero headline and live counter."""
    res = client.get("/")
    assert res.status_code == 200
    assert "Build responsive apps with Python" in res.text
    assert "Counter" in res.text


def test_docs_site_component_explorer_page(client):
    """Verify component explorer renders catalog index and property inspector."""
    res = client.get("/components")
    assert res.status_code == 200
    assert "Interactive Component Explorer (72 Built-in Primitives)" in res.text
    assert "Property Inspector" in res.text
    assert "Synchronized Python Implementation" in res.text


def test_docs_site_computed_state_signal():
    """Verify computed total reacts to price and tax mutations."""
    ctx = app.state_context(session_id="test-session-calc")
    with ctx.activate():
        ctx.write(s_price, 200.0)
        ctx.write(s_tax, 0.10)
        assert round(s_calc_total.value, 2) == 220.0

        ctx.write(s_price, 50.0)
        ctx.write(s_tax, 0.20)
        assert round(s_calc_total.value, 2) == 60.0


def test_docs_site_command_dispatch(client):
    """Verify command dispatch for interactive counter and event tracing."""
    init_res = client.get("/")
    assert init_res.status_code == 200
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', init_res.text)
    assert m is not None, "CSRF token must be present in rendered form"
    csrf_token = m.group(1)

    payload = {
        "_csrf": csrf_token,
        "_gx_action_id": "act-00000001",
        "_gx_view_id": "/",
    }
    cmd_res = client.post("/_gx/commands/demo.inc", data=payload)
    assert cmd_res.status_code == 200
    assert cmd_res.json()["ok"] is True


def test_docs_site_health_probe(client):
    """Verify production operational health check endpoint."""
    res = client.get("/_gx/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["version"] == "1.0.0"
