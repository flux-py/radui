"""Component, state, transport, and architecture guides."""

from __future__ import annotations

import radui as ui
from docs_site.core import app, s_active_comp, s_prop_label, s_prop_variant, s_prop_disabled, s_price, s_tax, s_calc_total
from docs_site.data import COMPONENTS

@app.page("/architecture")
def architecture_page():
    nodes = [
        ui.diagram_node("n_browser", "Browser DOM (Client)", x=50, y=100),
        ui.diagram_node("n_asgi", "ASGI 3.0 Handler", x=260, y=100),
        ui.diagram_node("n_state", "5-Tier Reactive DAG", x=480, y=50),
        ui.diagram_node("n_diff", "Sub-DOM Diff Engine", x=480, y=160),
        ui.diagram_node("n_sse", "SSE Event Broker", x=700, y=100),
    ]
    edges = [
        ui.diagram_edge("n_browser", "n_asgi", label="1. POST /command"),
        ui.diagram_edge("n_asgi", "n_state", label="2. ctx.write()"),
        ui.diagram_edge("n_state", "n_diff", label="3. Dirty Node Diff"),
        ui.diagram_edge("n_diff", "n_sse", label="4. Patch Payload"),
        ui.diagram_edge("n_sse", "n_browser", label="5. SSE Stream Morph"),
    ]

    return ui.column(
        ui.heading("RADUI System Architecture & Execution Lifecycle", level=1),
        ui.text("An interactive vector diagram illustrating the end-to-end request-response and reactive event streaming pipeline:"),
        ui.card(
            ui.diagram(nodes, edges, height=280),
            title="Interactive Execution Pipeline",
            subtitle="Click or inspect nodes to understand lifecycle invariants",
            hover=ui.motion.hover(scale=1.015, translate_y=-3.0),
        ),
        ui.spacer(size=12),
        ui.heading("Core Architectural Invariants", level=2),
        ui.accordion(
            ui.accordion_item(
                "Server-Side Rendering + Surgical Sub-DOM Diffing",
                ui.text("Initial requests render complete HTML in 3.037 ms. Subsequent interactions emit compact SSE patches diffed in 0.168 ms that morph only mutated DOM elements."),
                open=True,
            ),
            ui.accordion_item(
                "Deterministic 5-Tier Scoping",
                ui.text("State is partitioned across ephemeral, view, session, user, and app scopes with fail-closed tenant fencing to prevent cross-tenant data leaks."),
                open=True,
            ),
            ui.accordion_item(
                "Monotonic Lease Fencing (ADR-001)",
                ui.text("Every distributed background job and state lease carries an incremented fencing token, guaranteeing split-brain prevention under network partitions."),
                open=True,
            ),
        ),
        gap=16,
        stagger_children=0.05,
    )

@app.page("/components")
def components_page():
    active_name = s_active_comp.value
    meta = next((c for c in COMPONENTS if c["name"] == active_name), COMPONENTS[0])

    # Dynamic live preview of the selected component
    preview_widget: ui.Component
    if meta["name"] == "button":
        preview_widget = ui.button(
            s_prop_label.value,
            command="comp.test_trigger",
            variant=s_prop_variant.value,
            disabled=s_prop_disabled.value,
            tap=ui.motion.tap(scale=0.96),
        )
    elif meta["name"] == "badge":
        preview_widget = ui.badge(s_prop_label.value, variant=s_prop_variant.value)
    elif meta["name"] == "callout":
        preview_widget = ui.callout(s_prop_label.value, title="Inspection Callout", variant=s_prop_variant.value)
    elif meta["name"] == "metric_card":
        preview_widget = ui.metric_card("Real-Time KPI", s_prop_label.value, delta="+12% vs target")
    elif meta["name"] == "progress_bar":
        preview_widget = ui.progress_bar(value=75.0, variant=s_prop_variant.value)
    else:
        preview_widget = ui.card(
            ui.text(f"Live preview for component: ui.{meta['name']}"),
            title=f"Component: {meta['name']}",
            subtitle=meta["domain"],
        )

    # The catalog example is the canonical, copyable usage for this component.
    gen_code = meta.get("example") or f"import radui as ui\n\nwidget = ui.{meta['name']}()"
    component_rows = []
    for component in COMPONENTS:
        params = "; ".join(
            f"{param['name']} ({param['type']}): {param['description']}"
            for param in component.get("params", [])
        ) or "No configurable parameters listed"
        component_rows.append((
            f"ui.{component['name']}",
            component["domain"],
            component["description"],
            params,
            component.get("example", "See the API signature"),
        ))

    return ui.column(
        ui.heading("Interactive Component Explorer (68 Built-in Primitives)", level=1),
        ui.text("Try five live previews, then search the complete reference for every component, its parameters, and a Python example."),
        ui.grid(
            # Left Column: Component Catalog Selector
            ui.card(
                ui.heading("Component Catalog", level=4),
                ui.row(
                    ui.button("Button", command="comp.select_button", variant="primary" if active_name == "button" else "outline"),
                    ui.button("Badge", command="comp.select_badge", variant="primary" if active_name == "badge" else "outline"),
                    ui.button("Callout", command="comp.select_callout", variant="primary" if active_name == "callout" else "outline"),
                    ui.button("Metric Card", command="comp.select_metric", variant="primary" if active_name == "metric_card" else "outline"),
                    ui.button("Progress Bar", command="comp.select_progress", variant="primary" if active_name == "progress_bar" else "outline"),
                    gap=8,
                    wrap=True,
                ),
                ui.spacer(size=12),
                ui.text(f"Selected: ui.{meta['name']}", variant="code", id="component-selection"),
                ui.text(meta["description"]),
                title="Catalog Index (68 Total)",
                hover=ui.motion.hover(scale=1.015, translate_y=-2.0),
            ),
            # Right Column: Property Inspector
            ui.card(
                ui.form(
                    ui.heading("Property Inspector", level=4),
                    ui.input("Label / Text Content", bind=s_prop_label),
                    ui.select(
                        "Style Variant",
                        bind=s_prop_variant,
                        options=[("primary", "primary"), ("secondary", "secondary"), ("success", "success"), ("warning", "warning"), ("danger", "danger")],
                    ),
                    ui.switch("Disabled State", bind=s_prop_disabled),
                    ui.button("Apply Parameters", variant="secondary"),
                    command="comp.apply_props",
                ),
                title="Live Property Controls",
                hover=ui.motion.hover(scale=1.015, translate_y=-2.0),
            ),
            columns=2,
            gap=16,
        ),
        ui.spacer(size=12),
        # Live Rendered Sandbox Preview
        ui.card(
            preview_widget,
            id="component-preview",
            title="Live Rendered Component Preview",
            subtitle="Mutations update through server-side surgical SSE sub-DOM morphing",
            hover=ui.motion.hover(scale=1.015, translate_y=-2.0),
        ),
        ui.spacer(size=12),
        # Synchronized Python Implementation Code
        ui.heading("Synchronized Python Implementation", level=3),
        ui.code_block(gen_code, language="python", copyable=True),
        ui.heading("Complete component reference", level=2),
        ui.data_grid(
            headers=["Component", "Category", "Description", "Parameters", "Example"],
            rows=component_rows,
            searchable=True,
            sortable=True,
            page_size=8,
            empty_message="No components match that search.",
        ),
        gap=16,
        stagger_children=0.05,
    )

@app.page("/state")
def state_page():
    return ui.column(
        ui.heading("5-Tier Reactive State & Computed Signals", level=1),
        ui.text("RADUI eliminates state synchronization bugs through deterministic scoping and automated reactive DAG dependency tracking."),
        # Computed State Live Calculator
        ui.card(
            ui.heading("Computed State Signal Calculator", level=3),
            ui.text("Adjust the price or tax rate. The derived total re-calculates automatically with zero manual listeners:"),
            ui.form(
                ui.row(
                    ui.input("Base Price ($)", bind=s_price, input_type="number"),
                    ui.input("Tax Rate (0.20 = 20%)", bind=s_tax, input_type="number"),
                    gap=16,
                ),
                ui.button("Recalculate", variant="secondary"),
                command="calc.update",
            ),
            ui.spacer(size=12),
            ui.row(
                ui.metric_card("Base Price", f"${s_price.value:.2f}", id="calc-base-price", hover=ui.motion.hover(scale=1.03, translate_y=-4.0)),
                ui.metric_card("Tax Rate", f"{s_tax.value * 100:.0f}%", id="calc-tax-rate", hover=ui.motion.hover(scale=1.03, translate_y=-4.0)),
                ui.metric_card("Computed Total", f"${s_calc_total.value:.2f}", delta="Automated DAG derivation", id="calc-total", hover=ui.motion.hover(scale=1.03, translate_y=-4.0)),
                gap=16,
            ),
            title="Live Computed Signal Sandbox",
            hover=ui.motion.hover(scale=1.015, translate_y=-2.0),
        ),
        ui.spacer(size=16),
        ui.heading("The 5 Deterministic Scopes", level=2),
        ui.table(
            headers=["Scope", "Lifetime", "Storage Backend", "Isolation Boundary"],
            rows=[
                ["ephemeral", "Single HTTP request / command", "In-memory stack", "Isolated to current handler"],
                ["view", "Active browser tab / DOM view", "Server process memory", "Survives SSE patches; reset on route leave"],
                ["session", "Signed cookie (_gx_sid) duration", "StateBackend (Redis/Postgres/SQLite)", "Shared across browser tabs in session"],
                ["user", "Authenticated account lifetime", "Persistent Cluster Store", "Shared across user's devices & sessions"],
                ["app", "Application lifetime", "Cluster Singleton Store", "Global across all workers and nodes"],
            ],
        ),
        gap=16,
        stagger_children=0.05,
    )

@app.page("/transport")
def transport_page():
    return ui.column(
        ui.heading("Real-Time Server-Sent Events (SSE) Infrastructure", level=1),
        ui.text("RADUI delivers sub-millisecond incremental state diffs over persistent HTTP Server-Sent Events streams."),
        ui.callout(
            "Reconnecting clients pass '?since=<seq>'. The event broker replays missed events from durable storage in monotonic sequence order before transitioning into live streaming.",
            title="High-Watermark Replay (ADR-003)",
            variant="success",
        ),
        ui.grid(
            ui.metric_card("Wire Dispatch Latency", "0.007 ms", delta="Sub-millisecond delivery", hover=ui.motion.hover(scale=1.03, translate_y=-4.0)),
            ui.metric_card("Client Footprint", "9.6 KB", delta="Gzip uncompressed 37.6KB", hover=ui.motion.hover(scale=1.03, translate_y=-4.0)),
            ui.metric_card("Replay Guarantees", "Monotonic", delta="Zero duplicate execution", hover=ui.motion.hover(scale=1.03, translate_y=-4.0)),
            columns=3,
            gap=12,
        ),
        ui.heading("SSE Stream Encoding Format", level=3),
        ui.code_block(
            'event: state.patch\n'
            'id: 104\n'
            'data: {"view_id": "/dashboard", "sequence": 104, "patches": [{"id": "kpi_counter", "html": "<span>43</span>"}]}\n\n',
            language="json",
            copyable=True,
        ),
        gap=16,
        stagger_children=0.05,
    )
