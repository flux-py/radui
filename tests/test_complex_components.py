"""Tests for complex enterprise components: Diagram, CodeBlock, TreeView, DataGrid, GenerativeSlot, and CLI."""

from __future__ import annotations

import pytest
from radui.components import (
    CodeBlock,
    DataGrid,
    Diagram,
    DiagramEdge,
    DiagramNode,
    GenerativeSlot,
    TreeNode,
    TreeView,
    code_block,
    data_grid,
    diagram,
    diagram_edge,
    diagram_node,
    generative_slot,
    text,
    tree_node,
    tree_view,
)
from radui.core.registry import ComponentRegistry
from radui.cli import (
    cmd_info,
    cmd_routes,
    cmd_check,
    cmd_components,
    cmd_doctor,
    cmd_assets,
    cmd_tree,
    cmd_validate,
    cmd_security,
    cmd_protocols,
    cmd_version,
    DEFAULT_PORT,
    _load_app,
)
import argparse


def test_diagram_node_and_edge_creation():
    node1 = diagram_node("n1", "User", x=100, y=50, kind="rounded", status="active", icon="user")
    node2 = diagram_node("n2", "Server", x=100, y=200, kind="database", status="normal", icon="database")
    edge = diagram_edge("n1", "n2", label="HTTP POST", style="dashed", directional=True, animated=True)

    diag = diagram([node1, node2], [edge], height=500, on_node_click="node.inspect", selected_id="n1")

    assert len(diag.nodes) == 2
    assert len(diag.edges) == 1
    assert diag.nodes[0].id == "n1"
    assert diag.edges[0].label == "HTTP POST"
    assert diag.selected_id == "n1"


def test_diagram_rendering():
    registry = ComponentRegistry.builtins()
    node1 = diagram_node("step1", "1. User interacts", x=200, y=50, width=200, height=60, status="active")
    node2 = diagram_node("step2", "2. Command dispatcher", x=200, y=170, width=200, height=60, status="normal")
    edge = diagram_edge("step1", "step2", label="dispatches", animated=True)

    diag = diagram([node1, node2], [edge], on_node_click="select_step", id="diag-1")
    html = registry.render(diag, csrf_token="test-token")

    assert 'class="gx-diagram-container"' in html
    assert 'id="diag-1"' in html
    assert '<svg class="gx-diagram-svg"' in html
    assert '<path' in html
    assert 'gx-diagram-edge-animated' in html
    assert 'marker-end="url(#gx-arrow)"' in html
    assert '1. User interacts' in html
    assert '2. Command dispatcher' in html
    assert 'data-gx-action-trigger="select_step"' in html
    assert 'data-csrf="test-token"' in html


def test_diagram_vertical_auto_layout():
    registry = ComponentRegistry.builtins()
    nodes = [
        diagram_node("a", "Node A"),
        diagram_node("b", "Node B"),
    ]
    diag = diagram(nodes, layout="vertical")
    html = registry.render(diag)

    # In vertical layout, y coordinates are automatically calculated and spaced
    assert "Node A" in html
    assert "Node B" in html
    assert '<svg class="gx-diagram-svg"' in html


def test_code_block_rendering():
    registry = ComponentRegistry.builtins()
    cb = code_block(
        code="def hello():\n    return 'world'",
        language="python",
        title="hello.py",
        show_line_numbers=True,
        copyable=True,
        id="code-1",
    )
    html = registry.render(cb)

    assert 'class="gx-code-container"' in html
    assert 'id="code-1"' in html
    assert "hello.py" in html
    assert "data-gx-copy=" in html
    assert "def hello():" in html
    assert "return &#x27;world&#x27;" in html or "return 'world'" in html
    # Line number 1 and 2 present
    assert '>1</span>' in html
    assert '>2</span>' in html


def test_tree_view_rendering():
    registry = ComponentRegistry.builtins()
    child1 = tree_node("f1", "main.py", icon="file")
    child2 = tree_node("f2", "config.json", icon="settings")
    root = tree_node("dir1", "src", icon="folder", expanded=True, children=[child1, child2])

    tv = tree_view([root], on_select_command="file.open", id="tree-1")
    html = registry.render(tv, csrf_token="csrf-123")

    assert 'class="gx-tree-container"' in html
    assert 'id="tree-1"' in html
    assert "src" in html
    assert "main.py" in html
    assert "config.json" in html
    assert "gx-tree-caret expanded" in html
    assert "gx-tree-nested open" in html
    assert 'data-gx-action-trigger="file.open"' in html


def test_data_grid_rendering():
    registry = ComponentRegistry.builtins()
    headers = ["ID", "Name", "Role", "Active"]
    rows = [
        [1, "Alice", "Admin", True],
        [2, "Bob", "Developer", True],
        [3, "Charlie", "Designer", False],
    ]
    grid = data_grid(headers, rows, searchable=True, sortable=True, page_size=2, id="grid-1")
    html = registry.render(grid)

    assert 'class="gx-grid-card"' in html
    assert 'id="grid-1"' in html
    assert 'data-gx-grid' in html
    assert 'data-gx-page-size="2"' in html
    assert 'data-gx-grid-search' in html
    assert 'data-gx-sort-col="0"' in html
    assert "Alice" in html
    assert "Developer" in html
    assert "Designer" in html
    assert "Page 1 of 2" in html


def test_generative_slot_rendering():
    registry = ComponentRegistry.builtins()
    slot = generative_slot("preview", text("Dynamic generated message"), id="slot-1")
    html = registry.render(slot)

    assert 'class="gx-generative-slot"' in html
    assert 'id="slot-1"' in html
    assert 'data-gx-slot="preview"' in html
    assert "Dynamic generated message" in html


def test_cli_info(capsys):
    parser = argparse.Namespace()
    ret = cmd_info(parser)
    assert ret == 0
    captured = capsys.readouterr()
    assert "RADUI UI Framework" in captured.out
    from radui.core.registry import ComponentRegistry
    reg = ComponentRegistry.builtins()
    assert f"{len(reg._definitions)} registered built-in components" in captured.out


def test_architecture_visualizer_integration():
    from starlette.testclient import TestClient
    from examples.architecture_visualizer.app import app
    import re

    client = TestClient(app.asgi())
    res = client.get("/")
    assert res.status_code == 200
    assert "gx-diagram-container" in res.text
    assert "gx-code-container" in res.text
    assert "gx-tree-container" in res.text
    assert "gx-grid-card" in res.text

    # Extract CSRF token
    csrf_match = re.search(r'data-csrf="([^"]+)"', res.text)
    assert csrf_match is not None
    csrf = csrf_match.group(1)

    # Dispatch stage.select command
    cmd_res = client.post(
        "/_gx/commands/stage.select",
        data={"_csrf": csrf, "_gx_action_id": "act-12345678", "_gx_view_id": "/", "node_id": "step3_state"},
    )
    assert cmd_res.status_code == 200
    payload = cmd_res.json()
    assert payload.get("ok") is True


def test_cli_default_port():
    assert DEFAULT_PORT == 3000


def test_cli_routes(capsys):
    args = argparse.Namespace(target="examples/architecture_visualizer/app.py")
    ret = cmd_routes(args)
    assert ret == 0
    captured = capsys.readouterr()
    assert "stage.select" in captured.out
    assert "tree.select" in captured.out


def test_cli_check(capsys):
    args = argparse.Namespace(target="examples/architecture_visualizer/app.py")
    ret = cmd_check(args)
    assert ret == 0
    captured = capsys.readouterr()
    assert "Validating RADUI application" in captured.out


def test_cli_components(capsys):
    args = argparse.Namespace()
    ret = cmd_components(args)
    assert ret == 0
    captured = capsys.readouterr()
    assert "Architecture & Flowcharts" in captured.out
    assert "Developer & Enterprise Suite" in captured.out
    assert "diagram" in captured.out
    assert "data_grid" in captured.out


def test_cli_doctor(capsys):
    args = argparse.Namespace()
    ret = cmd_doctor(args)
    assert ret == 0
    captured = capsys.readouterr()
    assert "RADUI Doctor" in captured.out
    assert "Python Version" in captured.out


def test_cli_assets(capsys):
    args = argparse.Namespace()
    ret = cmd_assets(args)
    assert ret == 0
    captured = capsys.readouterr()
    assert "BASE_CSS" in captured.out
    assert "CLIENT_JS" in captured.out


def test_cli_tree(capsys):
    args = argparse.Namespace(target="examples/architecture_visualizer/app.py")
    ret = cmd_tree(args)
    assert ret == 0
    captured = capsys.readouterr()
    assert "Application Structure" in captured.out


def test_cli_validate(capsys):
    args = argparse.Namespace(target="examples/architecture_visualizer/app.py")
    ret = cmd_validate(args)
    assert ret == 0
    captured = capsys.readouterr()
    assert "Application IR validation passed" in captured.out


def test_cli_security(capsys):
    args = argparse.Namespace(target="examples/architecture_visualizer/app.py")
    ret = cmd_security(args)
    assert ret == 0
    captured = capsys.readouterr()
    assert "CSRF Protection: Active" in captured.out


def test_cli_protocols(capsys):
    args = argparse.Namespace()
    ret = cmd_protocols(args)
    assert ret == 0
    captured = capsys.readouterr()
    assert "A2UI 1.0" in captured.out
    assert "AG-UI" in captured.out


def test_cli_version(capsys):
    args = argparse.Namespace()
    ret = cmd_version(args)
    assert ret == 0
    captured = capsys.readouterr()
    assert "RADUI-ui" in captured.out



