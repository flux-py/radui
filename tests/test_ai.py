from __future__ import annotations

import radui as gx


def test_token_stream():
    stream = gx.TokenStream()
    stream.push("Hello")
    stream.push(" ")
    stream.push("world!")
    assert stream.text == "Hello world!"
    assert list(stream) == ["Hello", " ", "world!"]


def test_streaming_fence_parser():
    parser = gx.StreamingFenceParser()

    delta1, comps1 = parser.feed("Here is an answer:\n```RADUI\n")
    assert comps1 == []

    chunk = '{"type": "metric", "props": {"title": "Active", "value": "42"}}\n```\nDone!'
    delta2, comps2 = parser.feed(chunk)
    assert len(comps2) == 1
    assert comps2[0]["type"] == "metric"
    assert comps2[0]["props"]["value"] == "42"


def test_a2ui_mapper():
    text_spec = {"type": "text", "props": {"text": "A2UI content"}, "id": "t1"}
    c_text = gx.a2ui_to_component(text_spec)
    assert isinstance(c_text, gx.Text)
    assert c_text.value == "A2UI content"

    metric_spec = {
        "type": "metric",
        "props": {"title": "Users", "value": "1000", "delta": "+10%", "delta_type": "positive"},
        "id": "m1",
    }
    c_metric = gx.a2ui_to_component(metric_spec)
    assert isinstance(c_metric, gx.MetricCard)
    assert c_metric.title == "Users"
    assert c_metric.change == "+10%"

    card_spec = {
        "type": "card",
        "children": [text_spec],
        "id": "c1",
    }
    c_card = gx.a2ui_to_component(card_spec)
    assert isinstance(c_card, gx.Card)
    assert len(c_card.children) == 1


def test_ag_ui_journal():
    journal = gx.AGUIEventJournal(run_id="run-123")
    journal.emit("tool_call", step_id="s1", payload={"tool": "search_docs", "arguments": {"q": "radui"}})
    journal.emit("tool_result", step_id="s1", payload={"tool": "search_docs", "result": "Found 3 articles"})
    journal.emit("approval_request", step_id="s2", payload={"action": "reboot_server"})
    journal.emit("step_end", step_id="s2", payload={"description": "Execution verified"})

    steps = journal.to_steps_timeline()
    assert len(steps) == 4
    assert "Tool Call: search_docs" in steps[0][0]
    assert steps[0][1] == "running"
    assert steps[1][1] == "completed"
    assert "Human Approval: reboot_server" in steps[2][0]
    assert steps[2][1] == "pending"


def test_mcp_tool_registry():
    registry = gx.MCPToolRegistry()

    def dummy_query(q: str):
        return f"result: {q}"

    tool = gx.MCPToolDescriptor(
        name="query_knowledge_base",
        description="Search vector database",
        parameters_schema={"type": "object", "required": ["q"]},
        handler=dummy_query,
        requires_approval=False,
    )
    registry.register(tool)

    retrieved = registry.get("query_knowledge_base")
    assert retrieved is not None
    assert retrieved.name == "query_knowledge_base"
    assert retrieved.validate_arguments({"q": "test"}) is True
    assert retrieved.validate_arguments({}) is False

    tools = registry.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "query_knowledge_base"
