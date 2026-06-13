from __future__ import annotations

import radui as gx
from starlette.testclient import TestClient


def test_trace_collector_basic():
    collector = gx.TraceCollector(capacity=50)
    rec1 = collector.record("render", "/home", session_id="sess-1", duration_ms=4.2)
    assert rec1.id.startswith("trc-")
    assert rec1.category == "render"
    assert rec1.duration_ms == 4.2

    rec2 = collector.record("state", "counter.val", session_id="sess-1", details={"previous": 0, "value": 1})
    assert rec2.category == "state"

    rec3 = collector.record("command", "counter.inc", session_id="sess-2", duration_ms=1.1)

    all_records = collector.get_records()
    assert len(all_records) == 3

    render_records = collector.get_records(category="render")
    assert len(render_records) == 1
    assert render_records[0].name == "/home"

    sess1_records = collector.get_records(session_id="sess-1")
    assert len(sess1_records) == 2

    stats = collector.stats()
    assert stats["total_records"] == 3
    assert stats["by_category"]["render"] == 1
    assert stats["by_category"]["state"] == 1
    assert stats["by_category"]["command"] == 1

    collector.clear()
    assert len(collector.get_records()) == 0


def test_app_inspector_endpoints():
    app = gx.App("Inspector App", app_id="insp-app", debug=True)

    @app.page("/")
    def home():
        return gx.column(
            gx.heading("Test Inspector", level=1),
            gx.text("Body"),
        )

    with TestClient(app.asgi()) as client:
        # Load page to generate render trace
        page = client.get("/")
        assert page.status_code == 200
        # In debug mode, the inspector badge and drawer are rendered in the HTML
        assert 'id="gx-inspect-badge"' in page.text
        assert 'id="gx-inspect-drawer"' in page.text

        # Test /_gx/inspect dashboard
        inspect_page = client.get("/_gx/inspect")
        assert inspect_page.status_code == 200
        assert "RADUI Runtime Inspector" in inspect_page.text
        assert "insp-app" in inspect_page.text

        # Test /_gx/inspect/traces
        traces_res = client.get("/_gx/inspect/traces")
        assert traces_res.status_code == 200
        data = traces_res.json()
        assert data["ok"] is True
        assert len(data["records"]) >= 1
        assert any(r["category"] == "render" and r["name"] == "/" for r in data["records"])

        # Test /_gx/inspect/stats
        stats_res = client.get("/_gx/inspect/stats")
        assert stats_res.status_code == 200
        stats_data = stats_res.json()
        assert stats_data["ok"] is True
        assert stats_data["stats"]["total_records"] >= 1

