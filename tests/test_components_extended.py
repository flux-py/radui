from __future__ import annotations

import radui as gx


def test_layout_components_rendering():
    registry = gx.ComponentRegistry.builtins()

    badge = gx.badge("Beta", variant="warning", id="b1")
    html = registry.render(badge)
    assert "gx-badge-warning" in html
    assert "Beta" in html

    callout = gx.callout("System notice", variant="danger", id="c1")
    html = registry.render(callout)
    assert "gx-callout-danger" in html
    assert "System notice" in html

    spacer = gx.spacer(24)
    html = registry.render(spacer)
    assert "height:24px" in html

    grid = gx.grid(gx.text("Left"), gx.text("Right"), columns=2, gap=16, id="g1")
    html = registry.render(grid)
    assert "gx-grid" in html
    assert "grid-template-columns:repeat(2, minmax(0, 1fr))" in html
    assert "gap:16px" in html

    tabs = gx.tabs(
        [
            gx.tab_item("Tab 1", gx.text("Content 1"), id="t1"),
            gx.tab_item("Tab 2", gx.text("Content 2"), id="t2"),
        ],
        id="tabs1",
    )
    html = registry.render(tabs)
    assert "gx-tabs" in html
    assert "Tab 1" in html
    assert "Tab 2" in html
    assert "Content 1" in html

    modal = gx.modal("Confirm Action", gx.text("Are you sure?"), id="mod1")
    html = registry.render(modal)
    assert "gx-modal" in html
    assert "Confirm Action" in html
    assert "Are you sure?" in html


def test_input_components_rendering():
    registry = gx.ComponentRegistry.builtins()

    ta = gx.textarea("Biography", id="bio", placeholder="Enter bio...", rows=4)
    html = registry.render(ta)
    assert "<textarea" in html
    assert "Biography" in html

    sel = gx.select("Select Role", options=["Admin", "User", "Guest"], id="role")
    html = registry.render(sel)
    assert "<select" in html
    assert "<option" in html
    assert "Admin" in html

    sw = gx.switch("Dark Mode", id="dark_mode", default=True)
    html = registry.render(sw)
    assert "gx-switch" in html
    assert "checked" in html

    rg = gx.radio_group("Shirt Size", options=["S", "M", "L"], id="size", default="M")
    html = registry.render(rg)
    assert "gx-radio-group" in html
    assert 'type="radio"' in html
    assert "Shirt Size" in html


def test_analytics_components_rendering():
    registry = gx.ComponentRegistry.builtins()

    mc = gx.metric_card("MRR", "$124,500", delta="+12.4%", delta_type="positive", icon="trending-up", id="mc1")
    html = registry.render(mc)
    assert "gx-metric" in html
    assert "$124,500" in html
    assert "+12.4%" in html
    assert "trending-up" in html

    tbl = gx.table(
        headers=["Name", "Role", "Status"],
        rows=[
            ["Alice", "Admin", "Active"],
            ["Bob", "User", "Offline"],
        ],
        id="t1",
    )
    html = registry.render(tbl)
    assert "<table" in html
    assert "Alice" in html
    assert "Offline" in html

    plot_bar = gx.plot(
        type="bar",
        data=[{"x": "A", "y": 10}, {"x": "B", "y": 25}],
        title="Sample Bar",
        id="p1",
    )
    html = registry.render(plot_bar)
    assert "<svg" in html
    assert "Sample Bar" in html
    assert "rect" in html

    plot_line = gx.plot(
        type="line",
        data=[{"x": 1, "y": 10}, {"x": 2, "y": 30}],
        title="Sample Line",
        id="p2",
    )
    html = registry.render(plot_line)
    assert "<svg" in html
    assert "Sample Line" in html
    assert "polyline" in html


def test_ai_agent_components_rendering():
    registry = gx.ComponentRegistry.builtins()

    msg = gx.chat_message("Hello human!", role="assistant", timestamp="12:00")
    html = registry.render(msg)
    assert "gx-chat-assistant" in html
    assert "Hello human!" in html

    chat = gx.chat_view([msg], id="cv1")
    html = registry.render(chat)
    assert "gx-chat-box" in html

    ci = gx.chat_input(placeholder="Type here...", label="Ask")
    html = registry.render(ci, csrf_token="test_token")
    assert 'name="message"' in html
    assert "Ask" in html

    st = gx.streaming_text("Generating response...", is_streaming=True, id="st1")
    html = registry.render(st)
    assert "gx-stream-cursor" in html

    ac = gx.action_card(
        title="Database Migration",
        description="Run migration 004?",
        approve_command="db.approve",
        reject_command="db.reject",
        metadata={"tables": "users, sessions"},
        id="ac1",
    )
    html = registry.render(ac, csrf_token="test_token")
    assert "gx-action-card" in html
    assert "Database Migration" in html
    assert 'data-gx-command="db.approve"' in html

    timeline = gx.step_timeline(
        [
            {"title": "Step 1", "status": "completed", "details": "Done"},
            {"title": "Step 2", "status": "in_progress", "details": "Working"},
        ],
        id="stl1",
    )
    html = registry.render(timeline)
    assert "gx-timeline" in html
    assert "Step 1" in html
    assert "Working" in html

    dc = gx.dynamic_card({"block_type": "dynamic.block"}, title="Dynamic Widget", id="dc1")
    html = registry.render(dc)
    assert "Dynamic Widget" in html
    assert "dynamic.block" in html
