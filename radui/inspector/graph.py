from __future__ import annotations

import html
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from radui.state.dependencies import DependencyTracker


def extract_dag_structure(tracker: DependencyTracker) -> dict[str, Any]:
    """Extract raw nodes and edges from DependencyTracker."""
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[tuple[str, str]] = []

    with tracker._lock:
        # State references and direct component dependencies
        for state_key, contexts in tracker._by_state.items():
            if isinstance(state_key, tuple) and len(state_key) == 3:
                scope, owner, key = state_key
            else:
                scope, owner, key = "session", "default", str(state_key)

            node_id = f"state:{key}"
            if node_id not in nodes:
                nodes[node_id] = {
                    "id": node_id,
                    "label": key,
                    "sublabel": f"scope: {scope}",
                    "type": "state",
                    "scope": scope,
                }
            for ctx, comp_ids in contexts.items():
                for comp_id in comp_ids:
                    comp_node_id = f"comp:{comp_id}"
                    if comp_node_id not in nodes:
                        nodes[comp_node_id] = {
                            "id": comp_node_id,
                            "label": comp_id,
                            "sublabel": "component",
                            "type": "component",
                        }
                    edges.append((node_id, comp_node_id))

        # Computed states and dependencies
        state_by_comp = getattr(tracker, "_state_by_computed", {})
        for computed_key, upstream_set in state_by_comp.items():
            if isinstance(computed_key, tuple) and len(computed_key) == 3:
                comp_scope, comp_owner, comp_name = computed_key
            else:
                comp_scope, comp_owner, comp_name = "session", "default", str(computed_key)

            comp_id = f"computed:{comp_name}"
            if comp_id not in nodes:
                nodes[comp_id] = {
                    "id": comp_id,
                    "label": comp_name,
                    "sublabel": "computed",
                    "type": "computed",
                }
            for u_key in upstream_set:
                if isinstance(u_key, tuple) and len(u_key) == 3:
                    u_scope, u_owner, u_name = u_key
                else:
                    u_scope, u_owner, u_name = "session", "default", str(u_key)

                u_id = f"state:{u_name}"
                if u_id not in nodes:
                    nodes[u_id] = {
                        "id": u_id,
                        "label": u_name,
                        "sublabel": f"scope: {u_scope}",
                        "type": "state",
                        "scope": u_scope,
                    }
                edges.append((u_id, comp_id))

    return {
        "nodes": list(nodes.values()),
        "edges": [{"source": src, "target": tgt} for src, tgt in sorted(set(edges))],
    }


def generate_dag_svg(tracker: DependencyTracker) -> str:
    """Generate a clean dark-mode SVG visualization of the reactive dependency DAG."""
    data = extract_dag_structure(tracker)
    nodes = data["nodes"]
    edges = data["edges"]

    # Partition nodes by category
    state_nodes = [n for n in nodes if n["type"] == "state"]
    computed_nodes = [n for n in nodes if n["type"] == "computed"]
    comp_nodes = [n for n in nodes if n["type"] == "component"]

    has_computed = len(computed_nodes) > 0
    col_x = {
        "state": 80,
        "computed": 400 if has_computed else 80,
        "component": 720 if has_computed else 480,
    }

    width = 960 if has_computed else 720
    max_rows = max(len(state_nodes), len(computed_nodes), len(comp_nodes), 1)
    height = max(420, max_rows * 80 + 100)

    # Position each node
    node_positions: dict[str, tuple[int, int]] = {}
    box_w, box_h = 180, 50

    def layout_col(col_nodes: list[dict[str, Any]], x: int):
        spacing = (height - 80) / max(len(col_nodes) + 1, 2)
        for idx, n in enumerate(col_nodes, 1):
            y = int(40 + idx * spacing - box_h / 2)
            node_positions[n["id"]] = (x, y)

    layout_col(state_nodes, col_x["state"])
    if has_computed:
        layout_col(computed_nodes, col_x["computed"])
    layout_col(comp_nodes, col_x["component"])

    # Build SVG paths and shapes
    svg_elements = []

    # Defs: arrow marker
    svg_elements.append("""<defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 1 L 10 5 L 0 9 z" fill="#64748b" />
      </marker>
    </defs>""")

    # Background
    svg_elements.append(f'<rect width="{width}" height="{height}" fill="#0b0f19" rx="12" />')

    # Draw Edges
    for edge in edges:
        src_id, tgt_id = edge["source"], edge["target"]
        if src_id in node_positions and tgt_id in node_positions:
            x1, y1 = node_positions[src_id]
            x2, y2 = node_positions[tgt_id]
            start_x = x1 + box_w
            start_y = y1 + box_h // 2
            end_x = x2
            end_y = y2 + box_h // 2
            mid_x = (start_x + end_x) // 2
            d = f"M {start_x} {start_y} C {mid_x} {start_y}, {mid_x} {end_y}, {end_x} {end_y}"
            svg_elements.append(
                f'<path d="{d}" fill="none" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)" />'
            )

    # Draw Nodes
    colors = {
        "state": ("#0f172a", "#38bdf8", "#7dd3fc"),
        "computed": ("#2e1065", "#c084fc", "#e9d5ff"),
        "component": ("#064e3b", "#34d399", "#a7f3d0"),
    }

    for n in nodes:
        nid = n["id"]
        if nid not in node_positions:
            continue
        x, y = node_positions[nid]
        bg, border, text_color = colors.get(n["type"], ("#1e293b", "#94a3b8", "#f1f5f9"))
        lbl = html.escape(n["label"][:20])
        sub = html.escape(n["sublabel"][:22])

        node_svg = f"""<g transform="translate({x},{y})">
          <rect width="{box_w}" height="{box_h}" rx="8" fill="{bg}" stroke="{border}" stroke-width="1.5" />
          <text x="14" y="22" font-family="-apple-system, system-ui, sans-serif" font-size="13" font-weight="600" fill="{text_color}">{lbl}</text>
          <text x="14" y="38" font-family="-apple-system, system-ui, sans-serif" font-size="10" fill="#94a3b8">{sub}</text>
        </g>"""
        svg_elements.append(node_svg)

    elements_str = "\n".join(svg_elements)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="auto">
{elements_str}
</svg>"""
