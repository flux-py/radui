from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

import radui as gx
from radui.core.ir import ApplicationIR, AppMetadata, RouteSpec
from radui.interactions import InteractionAction, InteractionBinding, act, on


def test_interaction_models_and_ir_serialization():
    card = gx.card(
        gx.text("0", id="cnt", bind_local={"text": "count"}),
        gx.button(
            "Add",
            id="add-btn",
            interactions=(
                on("click", act.increment("count", by=2), act.announce("Incremented")),
            ),
        ),
        id="counter-card",
        local_state={"count": 0, "open": False},
    )
    assert card.local_state == {"count": 0, "open": False}
    assert len(card.children) == 2

    ir = ApplicationIR(
        app=AppMetadata(id="m18-app", name="M18 App"),
        routes=(RouteSpec(id="home", path="/", title="Home", root=card),),
    )
    dumped = ir.model_dump_json()
    parsed = json.loads(dumped)
    assert parsed["routes"][0]["root"]["local_state"] == {"count": 0, "open": False}
    assert parsed["routes"][0]["root"]["children"][1]["interactions"][0]["event"] == "click"


def test_interaction_security_rejects_unsafe_attrs_and_payloads():
    # Unsafe event handler / scriptable attributes rejected
    for bad_attr in ("onclick", "onerror", "onload", "src", "href", "style", "innerHTML"):
        with pytest.raises(ValueError):
            act.set_attr(bad_attr, "evil")
        with pytest.raises(ValueError):
            act.remove_attr(bad_attr)

    # Allowlisted attributes succeed
    a1 = act.set_attr("aria-expanded", "true", target="panel-1")
    assert a1.key == "aria-expanded"
    a2 = act.set_attr("data-gx-state-mode", "compact")
    assert a2.key == "data-gx-state-mode"

    # Invalid CSS class / target / command / local_state rejected
    with pytest.raises(ValueError):
        act.add_class("bad class!")
    with pytest.raises(ValueError):
        act.show(target="1invalid-id")
    with pytest.raises(ValueError):
        gx.column(local_state={f"k{i}": i for i in range(33)})
    with pytest.raises(ValueError):
        gx.column(local_state={"nested": {"a": 1}})  # type: ignore[dict-item]
    with pytest.raises(ValueError):
        gx.text("hi", bind_local={"innerHTML": "x"})  # type: ignore[dict-item]


def test_html_renderer_emits_escaped_descriptors_and_aria_semantics():
    app = gx.App("M18Render")

    @app.page("/")
    def index():
        return gx.column(
            gx.tabs(
                gx.tab_item("One", gx.text("Tab 1")),
                gx.tab_item("Two", gx.text("Tab 2")),
                id="main-tabs",
            ),
            gx.modal("Confirm", gx.text("Modal Body"), trigger_label="Open Modal", id="m1"),
            gx.drawer("Menu", gx.text("Drawer Body"), trigger_label="Open Drawer", id="d1"),
            gx.tag("Beta", removable=True, id="t1"),
            gx.button(
                "XSS Check",
                id="xss-btn",
                interactions=(on("click", act.set_text('<script>alert(1)</script>', target="cnt")),),
            ),
            gx.text("0", id="cnt", bind_local={"text": "count"}),
            local_state={"count": 0},
        )

    with TestClient(app.asgi()) as client:
        res = client.get("/")
        assert res.status_code == 200
        html = res.text
        assert 'role="tablist"' in html
        assert 'role="tab"' in html
        assert 'aria-selected="true"' in html
        assert 'role="tabpanel"' in html
        assert 'role="dialog"' in html
        assert 'aria-modal="true"' in html
        assert 'aria-expanded="false"' in html
        assert 'data-gx-tag-remove="true"' in html
        assert 'gx-tag-remove" onclick=' not in html
        assert "<script>alert(1)</script>" not in html
        assert "data-gx-local-state=" in html
        assert "data-gx-interactions=" in html
        assert "data-gx-bind-local=" in html
