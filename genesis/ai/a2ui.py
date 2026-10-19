from __future__ import annotations

from typing import Any
import radui.components.nodes as nodes


def a2ui_to_component(spec: dict[str, Any]) -> nodes.Component:
    """
    Maps an A2UI 1.0 component specification into a native RADUI Component node.
    Enforces safe property mapping and type safety.
    """
    comp_type = spec.get("type", "").lower()
    cid = spec.get("id")
    props = spec.get("props", {})

    if comp_type == "text":
        return nodes.text(str(props.get("text", "")), id=cid)

    if comp_type == "heading":
        return nodes.heading(
            str(props.get("text", "")),
            level=int(props.get("level", 1)),
            id=cid,
        )

    if comp_type in {"column", "vertical_layout"}:
        children = [a2ui_to_component(c) for c in spec.get("children", []) if isinstance(c, dict)]
        return nodes.column(*children, gap=int(props.get("gap", 16)), id=cid)

    if comp_type in {"row", "horizontal_layout"}:
        children = [a2ui_to_component(c) for c in spec.get("children", []) if isinstance(c, dict)]
        return nodes.row(*children, gap=int(props.get("gap", 12)), id=cid)

    if comp_type == "card":
        children = [a2ui_to_component(c) for c in spec.get("children", []) if isinstance(c, dict)]
        return nodes.card(*children, id=cid)

    if comp_type == "badge":
        return nodes.badge(
            str(props.get("label", "")),
            variant=props.get("variant", "neutral"),
            id=cid,
        )

    if comp_type == "callout":
        return nodes.callout(
            str(props.get("message", "")),
            title=str(props.get("title", "")),
            variant=props.get("variant", "info"),
            id=cid,
        )

    if comp_type in {"metric", "stat"}:
        delta_val = props.get("delta") or props.get("change")
        trend_val = props.get("delta_type") or props.get("trend", "neutral")
        return nodes.metric_card(
            title=str(props.get("title", "")),
            value=str(props.get("value", "")),
            delta=str(delta_val) if delta_val is not None else None,
            delta_type=trend_val,
            subtitle=str(props.get("subtitle", "")),
            id=cid,
        )

    if comp_type == "button":
        return nodes.button(str(props.get("label", "Click")), id=cid)

    if comp_type == "table":
        headers = props.get("headers") or props.get("columns") or []
        return nodes.table(
            headers=headers,
            rows=props.get("rows", []),
            id=cid,
        )

    # Fallback for dynamic/unmapped components: wrap in DynamicCard
    return nodes.dynamic_card(
        title=str(props.get("title", comp_type)),
        block_type=comp_type,
        payload=spec,
        id=cid,
    )
