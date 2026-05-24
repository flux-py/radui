from __future__ import annotations

import json
import pytest
from starlette.requests import Request
from starlette.testclient import TestClient

import radui as gx


def test_otlp_span_formatting_and_exporter():
    collector = gx.TraceCollector(capacity=50)
    exporter = gx.OTLPExporter(service_name="TestApp")
    collector.set_exporter(exporter)

    # Record diverse traces
    collector.record("render", "/dashboard", session_id="sess-1", duration_ms=2.5)
    collector.record("command", "cart.add", session_id="sess-1", duration_ms=8.0, details={"item": "book"})
    collector.record("state", "cart.count", session_id="sess-1", details={"previous": 0, "value": 1})
    collector.record("error", "payment.charge", session_id="sess-1", duration_ms=12.0, details={"error": "declined"})

    otlp_payload = collector.export_otlp()
    assert "resourceSpans" in otlp_payload
    res_spans = otlp_payload["resourceSpans"]
    assert len(res_spans) == 1

    resource_attrs = {attr["key"]: attr["value"]["stringValue"] for attr in res_spans[0]["resource"]["attributes"]}
    assert resource_attrs["service.name"] == "TestApp"
    assert resource_attrs["telemetry.sdk.name"] == "radui"

    spans = res_spans[0]["scopeSpans"][0]["spans"]
    assert len(spans) == 4

    # Verify span names and kinds
    span_names = [s["name"] for s in spans]
    assert "gx.render./dashboard" in span_names
    assert "gx.command.cart.add" in span_names
    assert "gx.state.cart.count" in span_names
    assert "gx.error.payment.charge" in span_names

    # Check error span status
    error_span = next(s for s in spans if "payment.charge" in s["name"])
    assert error_span["status"]["code"] == 2
    assert "declined" in error_span["status"]["message"]


def test_visual_inspector_dag_svg_and_json_endpoint():
    app = gx.App("DAG App", debug=True)

    s_price = gx.state("price", 50.0, scope="session")
    s_qty = gx.state("qty", 2, scope="session")

    @gx.computed
    def s_total() -> float:
        return s_price.value * s_qty.value

    @app.command("checkout.submit")
    def checkout(ctx: gx.CommandContext):
        pass

    @app.page("/store")
    def store_view():
        return gx.column(
            gx.text(bind=s_total, id="total-label"),
            gx.form("checkout.submit", gx.button("Checkout", id="checkout-btn")),
        )

    with TestClient(app.asgi()) as client:
        # Load page to register dependencies
        res = client.get("/store")
        assert res.status_code == 200

        # Request SVG DAG
        svg_res = client.get("/_gx/inspect/dag")
        assert svg_res.status_code == 200
        assert svg_res.headers["content-type"].startswith("image/svg+xml")
        svg_text = svg_res.text
        assert "<svg" in svg_text
        assert "</svg>" in svg_text
        assert "price" in svg_text
        assert "total-label" in svg_text

        # Request JSON DAG
        json_res = client.get("/_gx/inspect/dag?format=json")
        assert json_res.status_code == 200
        data = json_res.json()
        assert data["ok"] is True
        node_labels = [n["label"] for n in data["nodes"]]
        assert "price" in node_labels or "qty" in node_labels
        assert "total-label" in node_labels

        # Verify Dashboard /_gx/inspect contains DAG preview
        dash_res = client.get("/_gx/inspect")
        assert dash_res.status_code == 200
        assert "Reactive Dependency Graph (SVG)" in dash_res.text
        assert "Raw SVG DAG" in dash_res.text


def test_multi_tenant_state_isolation():
    runtime = gx.StateRuntime("tenant-app")

    s_theme = gx.state("theme", "light", scope="app")
    s_draft = gx.state("draft", "empty", scope="session")

    ctx_tenant_a = runtime.context(session_id="s1", tenant_id="tenant-alpha")
    ctx_tenant_b = runtime.context(session_id="s1", tenant_id="tenant-beta")

    # App-scope state is isolated per tenant
    ctx_tenant_a.write(s_theme, "dark")
    assert ctx_tenant_a.read(s_theme) == "dark"
    assert ctx_tenant_b.read(s_theme) == "light"

    ctx_tenant_b.write(s_theme, "solarized")
    assert ctx_tenant_a.read(s_theme) == "dark"
    assert ctx_tenant_b.read(s_theme) == "solarized"

    # Session-scope state is isolated even when sharing identical session IDs
    ctx_tenant_a.write(s_draft, "draft-alpha")
    assert ctx_tenant_a.read(s_draft) == "draft-alpha"
    assert ctx_tenant_b.read(s_draft) == "empty"


def test_multi_tenant_query_cache_isolation():
    # Cache queries for two different tenants with the same key
    fetch_count_a = 0
    fetch_count_b = 0

    def fetch_a():
        nonlocal fetch_count_a
        fetch_count_a += 1
        return "data-for-tenant-a"

    def fetch_b():
        nonlocal fetch_count_b
        fetch_count_b += 1
        return "data-for-tenant-b"

    res_a1 = gx.query("org.profile", fetch_a, tenant_id="acme")
    res_b1 = gx.query("org.profile", fetch_b, tenant_id="globex")

    assert res_a1 == "data-for-tenant-a"
    assert res_b1 == "data-for-tenant-b"
    assert fetch_count_a == 1
    assert fetch_count_b == 1

    # Invalidate tenant acme only
    gx.invalidate_query("org.profile", tenant_id="acme")

    # Acme re-fetches, Globex uses cache
    res_a2 = gx.query("org.profile", fetch_a, tenant_id="acme")
    res_b2 = gx.query("org.profile", fetch_b, tenant_id="globex")

    assert res_a2 == "data-for-tenant-a"
    assert res_b2 == "data-for-tenant-b"
    assert fetch_count_a == 2
    assert fetch_count_b == 1  # Unchanged, did not re-fetch


def test_app_request_header_tenant_isolation():
    app = gx.App("MultiTenant App")
    s_brand = gx.state("brand.name", "Default Brand", scope="session")

    @app.page("/portal")
    def portal():
        current_brand = s_brand.value
        return gx.heading(f"Portal: {current_brand}", id="brand-header")

    with TestClient(app.asgi()) as client:
        # Tenant A visits
        res_a = client.get("/portal", headers={"X-Tenant-ID": "tenant-corp-a"})
        assert res_a.status_code == 200
        assert "Default Brand" in res_a.text

        # Tenant A state context writes new brand
        ctx_a = app.state_context(session_id=client.cookies.get("RADUI_session", "anon"), tenant_id="tenant-corp-a")
        ctx_a.write(s_brand, "Corp Alpha")

        # Tenant B visits
        res_b = client.get("/portal", headers={"X-Tenant-ID": "tenant-corp-b"})
        assert res_b.status_code == 200
        # Tenant B sees Default Brand, NOT Corp Alpha
        assert "Corp Alpha" not in res_b.text
        assert "Default Brand" in res_b.text
