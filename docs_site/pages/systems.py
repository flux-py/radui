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
    elif meta["name"] == "slider":
        preview_widget = ui.slider("Interactive Value Slider", min=0, max=100, step=1, value=65)
    elif meta["name"] == "switch":
        preview_widget = ui.switch("Enable Real-Time Signals", checked=True)
    elif meta["name"] == "chat_view":
        preview_widget = ui.chat_view(
            ui.chat_message("Connected to Model Context Protocol server: postgres-analytics", role="assistant"),
            ui.chat_message("Can you execute the partition maintenance job?", role="user"),
            ui.chat_message("I have prepared the job payload. Authorize execution below:", role="assistant"),
        )
    elif meta["name"] == "action_card":
        preview_widget = ui.action_card(
            title="Authorize DB Partition Rotation?",
            description="Target: 'ALTER TABLE daily_logs ROTATE PARTITION 2026_11;'",
            approve_command="agent.approve_demo",
            reject_command="agent.reject_demo",
        )
    else:
        preview_widget = ui.card(
            ui.text(f"Live interactive preview for component: ui.{meta['name']}()"),
            ui.badge(f"Domain: {meta['domain']}", variant="primary"),
            ui.text(meta["description"]),
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

    # Build all 68 component chip buttons for instant discovery
    component_chips = [
        ui.button(
            c["name"],
            command=f"comp.select_{c['name']}",
            variant="primary" if active_name == c["name"] else "outline",
            id=f"comp-chip-{c['name']}",
        )
        for c in COMPONENTS
    ]

    return ui.column(
        ui.heading("Interactive Component Explorer (68 Built-in Primitives)", level=1),
        ui.text("Instant real-time discovery, interactive live previews, property inspection, and 3D flippable implementation code for all 68 RadUI primitives."),
        
        # Real-time search bar & Domain filter toolbar
        ui.card(
            ui.form(
                ui.row(
                    ui.input("Search 68 primitives (e.g. slider, chat, modal, grid, avatar, plot)...", id="comp-search-bar"),
                    ui.badge("Showing 68 of 68 primitives", variant="primary", id="comp-results-count"),
                    justify="between",
                    align="center",
                ),
                command="comp.test_trigger",
            ),
            ui.spacer(size=8),
            ui.row(
                ui.button("All (68)", command="comp.test_trigger", variant="primary", id="domain-filter-all"),
                ui.button("Layout (12)", command="comp.test_trigger", variant="outline", id="domain-filter-layout"),
                ui.button("Forms (11)", command="comp.test_trigger", variant="outline", id="domain-filter-forms"),
                ui.button("Action (5)", command="comp.test_trigger", variant="outline", id="domain-filter-action"),
                ui.button("Data (5)", command="comp.test_trigger", variant="outline", id="domain-filter-data"),
                ui.button("Feedback (7)", command="comp.test_trigger", variant="outline", id="domain-filter-feedback"),
                ui.button("Navigation (5)", command="comp.test_trigger", variant="outline", id="domain-filter-nav"),
                ui.button("Indicators (8)", command="comp.test_trigger", variant="outline", id="domain-filter-indicators"),
                ui.button("AI & Agent (8)", command="comp.test_trigger", variant="outline", id="domain-filter-ai"),
                ui.button("Diagrams (2)", command="comp.test_trigger", variant="outline", id="domain-filter-diagrams"),
                ui.button("Typography (5)", command="comp.test_trigger", variant="outline", id="domain-filter-typography"),
                gap=6,
                wrap=True,
                id="comp-domain-pills",
            ),
            title="Instant Component Discovery & Search",
            hover=ui.motion.hover(scale=1.01, translate_y=-1.0),
        ),
        ui.spacer(size=8),

        ui.grid(
            # Left Column: Component Catalog Grid (all 68 primitives)
            ui.card(
                ui.row(
                    ui.heading("Primitive Catalog", level=4),
                    ui.text(f"Selected: ui.{meta['name']}", variant="code", id="component-selection"),
                    justify="between",
                    align="center",
                ),
                ui.spacer(size=8),
                ui.row(
                    *component_chips,
                    gap=6,
                    wrap=True,
                    id="component-chips-grid",
                ),
                ui.spacer(size=12),
                ui.text(meta["description"], id="component-description-text"),
                title="Primitive Catalog (68 Total)",
                hover=ui.motion.hover(scale=1.01, translate_y=-1.0),
            ),
            # Right Column: Property Inspector
            ui.card(
                ui.form(
                    ui.heading("Property Inspector", level=4),
                    ui.input("Label / Text Content", bind=s_prop_label),
                    ui.select(
                        "Style Variant",
                        bind=s_prop_variant,
                        options=[("primary", "primary"), ("secondary", "secondary"), ("success", "success"), ("warning", "warning"), ("danger", "danger"), ("neutral", "neutral"), ("outline", "outline")],
                    ),
                    ui.switch("Disabled State", bind=s_prop_disabled),
                    ui.button("Apply Parameters", variant="secondary"),
                    command="comp.apply_props",
                ),
                title="Live Property Controls",
                hover=ui.motion.hover(scale=1.01, translate_y=-1.0),
            ),
            columns=2,
            gap=16,
        ),
        ui.spacer(size=12),
        
        # Live Rendered Sandbox Preview with 3D Flip capability
        ui.card(
            ui.row(
                ui.heading(f"Live Preview: ui.{active_name}", level=3, id="comp-preview-heading"),
                ui.button("⟳ Flip for RadUI Code", variant="outline", command="comp.test_trigger", id="comp-flip-toggle-btn"),
                justify="between",
                align="center",
            ),
            ui.spacer(size=10),
            preview_widget,
            id="component-preview",
            flippable=True,
            title="Live Rendered Component Preview (Click to Flip 3D)",
            subtitle="Click card or flip button to rotate 180° in 3D and reveal implementation code",
            hover=ui.motion.hover(scale=1.015, translate_y=-2.0),
        ),
        ui.spacer(size=12),
        
        # Synchronized Python Implementation Code
        ui.heading("Synchronized Python Implementation", level=3),
        ui.code_block(gen_code, language="python", copyable=True, id="comp-code-block"),
        ui.heading("Complete component reference (68 Primitives)", level=2),
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
