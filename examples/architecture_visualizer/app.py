"""RADUI Architecture & Complex Component Visualizer.

Demonstrates interactive architecture diagrams, flowcharts, code blocks,
tree views, data grids, and reactive state updates.
"""

from __future__ import annotations

from radui import (
    App,
    badge,
    card,
    code_block,
    column,
    data_grid,
    diagram,
    diagram_edge,
    diagram_node,
    divider,
    grid,
    heading,
    metric_card,
    motion,
    row,
    spacer,
    state,
    text,
    tree_node,
    tree_view,
)

app = App(title="RADUI Architecture & Component Studio")

STAGE_DETAILS = {
    "step1": {
        "title": "1. User interacts",
        "description": "User clicks a button, submits a form, types into an input, or triggers navigation.",
        "code": "# Client-side dispatch\nfetch('/_gx/commands/counter.inc', {\n    method: 'POST',\n    body: new URLSearchParams({ _csrf: token, delta: '1' })\n});",
    },
    "step2": {
        "title": "2. Command dispatcher",
        "description": "Validates cryptographic CSRF tokens, authorizes requests, checks rate limits, and deduplicates actions via idempotent action IDs.",
        "code": "@app.command('counter.inc')\ndef handle_increment(ctx: CommandContext):\n    # Automatic validation & CSRF check completed\n    ctx.state['count'] = ctx.state.get('count', 0) + 1",
    },
    "step3": {
        "title": "3. Application runtime",
        "description": "Resolves session-isolated state references and determines whether to mutate state or submit a long-running background job.",
        "code": "# State update vs Job submission decision\nif is_background_job:\n    job_handle = ctx.jobs.submit('train_model', dataset=ds)\nelse:\n    ctx.state['status'] = 'ready'",
    },
    "step3_state": {
        "title": "State update",
        "description": "Applies transactional reactive state changes, recalculates derived values, and marks dependent component IDs as invalidated.",
        "code": "change = StateChange(\n    key='count',\n    scope='session',\n    previous=0,\n    value=1,\n    revision=1\n)",
    },
    "step3_job": {
        "title": "Job submission",
        "description": "Queues execution to an external or local thread/process executor with cooperative cancellation and progress reporting.",
        "code": "@app.job('data.process')\ndef process_data(ctx: JobContext):\n    for i in range(100):\n        ctx.report_progress(i, f'Processing step {i}')\n    return {'status': 'done'}",
    },
    "step4": {
        "title": "4. Event journal",
        "description": "Appends an immutable, monotonic revision record to the SSE EventBroker. Broadcasts targeted invalidation events to connected clients.",
        "code": "event = EventRecord(\n    cursor=42,\n    event_type='invalidate',\n    data={'view_id': '/', 'component_ids': ['counter-display']}\n)\nbroker.publish(event)",
    },
    "step5": {
        "title": "5. Renderer and browser",
        "description": "HTML renderer builds virtual DOM fragments for only the invalidated components. Browser applies micro-patches without full page reload.",
        "code": "<!-- Browser DOM micro-patch -->\nconst target = document.querySelector('[data-gx-id=\"counter-display\"]');\ntarget.outerHTML = patch.html;",
    },
}


@app.page("/")
def index():
    selected_node_id = state("selected_node", default="step1")
    curr_id = getattr(selected_node_id, "default", "step1")
    # Retrieve detail for selected node
    details = STAGE_DETAILS.get(curr_id, STAGE_DETAILS["step1"])

    # Define architecture flowchart nodes matching the 5-stage lifecycle architecture
    nodes = [
        diagram_node(
            "step1",
            "1. User interacts",
            x=320,
            y=30,
            width=240,
            height=64,
            kind="rounded",
            status="active" if curr_id == "step1" else "normal",
            description="Button, form, input or navigation",
            icon="user",
        ),
        diagram_node(
            "step2",
            "2. Command dispatcher",
            x=320,
            y=140,
            width=240,
            height=64,
            kind="rounded",
            status="active" if curr_id == "step2" else "normal",
            description="Validate, authorize, deduplicate",
            icon="shield",
        ),
        diagram_node(
            "step3",
            "3. Application runtime",
            x=320,
            y=250,
            width=240,
            height=64,
            kind="rounded",
            status="active" if curr_id == "step3" else "normal",
            description="Resolve session & state references",
            icon="gear",
        ),
        diagram_node(
            "step3_state",
            "State update",
            x=180,
            y=360,
            width=220,
            height=64,
            kind="rounded",
            status="active" if curr_id == "step3_state" else "success",
            description="Derived values & invalidations",
            icon="latency",
        ),
        diagram_node(
            "step3_job",
            "Job submission",
            x=480,
            y=360,
            width=220,
            height=64,
            kind="rounded",
            status="active" if curr_id == "step3_job" else "warning",
            description="External or local executor",
            icon="timer",
        ),
        diagram_node(
            "step4",
            "4. Event journal",
            x=320,
            y=470,
            width=240,
            height=64,
            kind="rounded",
            status="active" if curr_id == "step4" else "normal",
            description="Ordered events, revisions, traces",
            icon="journal",
        ),
        diagram_node(
            "step5",
            "5. Renderer and browser",
            x=320,
            y=580,
            width=240,
            height=64,
            kind="rounded",
            status="active" if curr_id == "step5" else "normal",
            description="HTML fragments & micro-patches",
            icon="browser",
        ),
    ]

    # Flowchart connectors
    edges = [
        diagram_edge("step1", "step2", directional=True, animated=True),
        diagram_edge("step2", "step3", directional=True, animated=True),
        diagram_edge("step3", "step3_state", directional=True, style="solid"),
        diagram_edge("step3", "step3_job", directional=True, style="solid"),
        diagram_edge("step3_state", "step4", directional=True, style="solid"),
        diagram_edge("step3_job", "step4", directional=True, style="solid"),
        diagram_edge("step4", "step5", directional=True, animated=True),
    ]

    arch_diagram = diagram(
        nodes,
        edges,
        height=680,
        on_node_click="stage.select",
        selected_id=curr_id,
        id="arch-flowchart",
    )

    # Component AST / Tree view
    tree = tree_view(
        [
            tree_node(
                "root",
                "RADUI Application",
                icon="build",
                expanded=True,
                children=[
                    tree_node(
                        "core",
                        "radui.core",
                        icon="package",
                        expanded=True,
                        children=[
                            tree_node("app", "app.py (App & Dispatcher)", icon="python"),
                            tree_node("ir", "ir.py (Application IR)", icon="doc"),
                            tree_node("reg", "registry.py (Component Registry)", icon="book"),
                        ],
                    ),
                    tree_node(
                        "comp",
                        "radui.components",
                        icon="component",
                        expanded=True,
                        children=[
                            tree_node("diag", "Diagram & Flowchart Engine", icon="chart"),
                            tree_node("code", "CodeBlock & Syntax", icon="terminal"),
                            tree_node("tree", "TreeView & Collapsible AST", icon="tree"),
                            tree_node("grid", "DataGrid (Search & Sort)", icon="table"),
                        ],
                    ),
                    tree_node(
                        "state",
                        "radui.state",
                        icon="latency",
                        children=[
                            tree_node("rt", "runtime.py (Session Store)", icon="lock"),
                            tree_node("ref", "refs.py (Reactive StateRef)", icon="link"),
                        ],
                    ),
                ],
            )
        ],
        on_select_command="tree.select",
        id="app-tree",
    )

    # Telemetry data grid
    telemetry_grid = data_grid(
        headers=["Event ID", "Timestamp", "Lifecycle Stage", "Type", "Status", "Duration (ms)"],
        rows=[
            ["EVT-1001", "12:00:01", "1. User interacts", "HTTP POST", "Received", 1.2],
            ["EVT-1002", "12:00:01", "2. Command dispatcher", "CSRF Verify", "Passed", 0.4],
            ["EVT-1003", "12:00:02", "3. Application runtime", "State Mutation", "Applied", 0.8],
            ["EVT-1004", "12:00:02", "4. Event journal", "SSE Invalidate", "Published", 0.3],
            ["EVT-1005", "12:00:03", "5. Renderer and browser", "DOM Patch", "Rendered", 2.1],
            ["EVT-1006", "12:00:05", "3. Application runtime", "Job Queue", "Submitted", 1.5],
            ["EVT-1007", "12:00:06", "Job submission", "Background Worker", "Running", 45.0],
            ["EVT-1008", "12:00:08", "Job submission", "Background Worker", "Completed", 120.4],
        ],
        searchable=True,
        sortable=True,
        page_size=4,
        id="telemetry-grid",
    )

    return column(
        row(
            heading("RADUI Architecture & Component Studio", level=1),
            badge("Motion & Visual Engine 0.6", variant="primary"),
            justify="space-between",
        ),
        text(
            "A full interactive demonstration of RADUI architecture diagrams, responsive flowcharts, "
            "native event-driven animations, hardware-accelerated micro-interactions, code blocks, and data grids."
        ),
        spacer(16),
        grid(
            metric_card(
                "Active Pipeline Nodes",
                "7",
                delta="100% operational",
                delta_type="positive",
                animate_number=True,
                hover=motion.hover(scale=1.03),
                tap=motion.tap(),
                id="metric-nodes",
            ),
            metric_card(
                "Motion Compositor",
                "120 FPS",
                delta="GPU Accelerated",
                delta_type="positive",
                hover=motion.hover(scale=1.03),
                tap=motion.tap(),
                id="metric-fps",
            ),
            metric_card(
                "DOM Micro-patch Latency",
                "1.2 ms",
                delta="Direct WAAPI FLIP",
                delta_type="positive",
                hover=motion.hover(scale=1.03),
                tap=motion.tap(),
                id="metric-latency",
            ),
            columns=3,
            stagger_children=0.05,
            id="kpi-grid",
        ),
        spacer(20),
        row(
            card(
                heading("5-Stage Architecture Flowchart", level=3),
                text("Click on any lifecycle stage to inspect its operational mechanism:"),
                spacer(10),
                arch_diagram,
                motion=motion.slide_up(distance=16),
                hover=motion.hover(scale=1.01),
                style="flex: 2; min-width: 540px;",
            ),
            column(
                card(
                    heading(details["title"], level=3),
                    badge("Selected Stage", variant="info"),
                    spacer(8),
                    text(details["description"]),
                    spacer(12),
                    heading("Implementation Snippet", level=4),
                    code_block(
                        details["code"],
                        language="python",
                        title=f"{curr_id}.py",
                        show_line_numbers=True,
                        copyable=True,
                    ),
                    motion=motion.fade_in(),
                ),
                card(
                    heading("Module Hierarchy", level=3),
                    text("Framework AST and Component Tree:"),
                    spacer(8),
                    tree,
                    motion=motion.slide_up(distance=12),
                ),
                style="flex: 1; min-width: 320px; gap: 16px;",
            ),
            style="align-items: flex-start; gap: 24px;",
        ),
        spacer(24),
        card(
            heading("Runtime Telemetry & Event Journal", level=3),
            text("Real-time searchable and sortable event log dispatched across system lifecycle:"),
            spacer(12),
            telemetry_grid,
        ),
        spacer(32),
    )


@app.command("stage.select")
def select_stage(ctx):
    node_id = ctx.params.get("node_id", "step1")
    ctx.state["selected_node"] = node_id


@app.command("tree.select")
def select_tree(ctx):
    node_id = ctx.params.get("node_id", "")
    if node_id in STAGE_DETAILS:
        ctx.state["selected_node"] = node_id


if __name__ == "__main__":
    app.run(port=3000)
