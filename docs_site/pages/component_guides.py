"""Dedicated deep-dive component guides with practical implementation examples,
code blocks, and corresponding live rendered outputs.
"""

from __future__ import annotations

import radui as ui
from docs_site.core import app

# =========================================================================
# 1. LAYOUT & GRID PRIMITIVES
# =========================================================================

@app.page("/components-layout")
def components_layout_page():
    return ui.column(
        ui.badge("Layout System", variant="primary"),
        ui.heading("Layout & Grid Architecture", level=1),
        ui.text(
            "RADUI provides a deterministic, zero-CSS layout system built on typed flexbox and CSS Grid primitives. "
            "Compose responsive, adaptive interfaces in pure Python without writing media queries or boilerplate CSS.",
            variant="lead",
        ),
        ui.spacer(size=16),

        # Section 1: Container & Shell
        ui.card(
            ui.heading("1. Container & Max-Width Shells", level=3),
            ui.text("`ui.container` provides a centered viewport boundary with responsive margins and max-width constraints:"),
            ui.grid(
                ui.code_block(
                    "import radui as ui\n\n"
                    "# Centered container with 1200px max width\n"
                    "shell = ui.container(\n"
                    "    ui.heading('Dashboard Overview'),\n"
                    "    ui.text('Responsive container content'),\n"
                    "    max_width='1200px',\n"
                    "    centered=True,\n"
                    ")",
                    language="python",
                    copyable=True,
                ),
                ui.card(
                    ui.badge("LIVE RENDERED PREVIEW", variant="success"),
                    ui.heading("Dashboard Overview", level=4),
                    ui.text("Responsive container content centered across desktop and mobile viewports."),
                    ui.divider(),
                    ui.text("Container boundary: max-width 1200px | margin: 0 auto", variant="caption"),
                ),
                columns={"sm": 1, "md": 2, "lg": 2},
                gap=16,
            ),
        ),
        ui.spacer(size=16),

        # Section 2: Flexbox Rows & Columns
        ui.card(
            ui.heading("2. Flex Rows, Columns & Spacing", level=3),
            ui.text("`ui.row` and `ui.column` distribute elements along horizontal or vertical axes with typed alignment and gap tokens:"),
            ui.grid(
                ui.code_block(
                    "import radui as ui\n\n"
                    "# Flex row with space-between distribution\n"
                    "header = ui.row(\n"
                    "    ui.row(\n"
                    "        ui.badge('ACTIVE', variant='success'),\n"
                    "        ui.text('Cluster-01'),\n"
                    "        gap=8,\n"
                    "    ),\n"
                    "    ui.button('Inspect', variant='outline'),\n"
                    "    justify='between',\n"
                    "    align='center',\n"
                    ")",
                    language="python",
                    copyable=True,
                ),
                ui.card(
                    ui.badge("LIVE RENDERED PREVIEW", variant="success"),
                    ui.row(
                        ui.row(
                            ui.badge("ACTIVE", variant="success"),
                            ui.text("Cluster-01"),
                            gap=8,
                            align="center",
                        ),
                        ui.button("Inspect", variant="outline", command="comp.test_trigger"),
                        justify="between",
                        align="center",
                    ),
                    ui.divider(),
                    ui.column(
                        ui.text("Vertical column stack: item 1", variant="caption"),
                        ui.text("Vertical column stack: item 2", variant="caption"),
                        gap=4,
                    ),
                ),
                columns={"sm": 1, "md": 2, "lg": 2},
                gap=16,
            ),
        ),
        ui.spacer(size=16),

        # Section 3: Responsive Multi-Column Grids
        ui.card(
            ui.heading("3. Responsive Multi-Column Grids", level=3),
            ui.text("`ui.grid` defines dynamic responsive columns with breakpoint-specific column counts (`sm`, `md`, `lg`):"),
            ui.grid(
                ui.code_block(
                    "import radui as ui\n\n"
                    "# 1 col on mobile, 2 on tablet, 3 on desktop\n"
                    "kpi_grid = ui.grid(\n"
                    "    ui.metric_card('Throughput', '4.2k req/s'),\n"
                    "    ui.metric_card('Latency', '0.039 ms'),\n"
                    "    ui.metric_card('Error Rate', '0.00%'),\n"
                    "    columns={'sm': 1, 'md': 2, 'lg': 3},\n"
                    "    gap=14,\n"
                    ")",
                    language="python",
                    copyable=True,
                ),
                ui.card(
                    ui.badge("LIVE RENDERED PREVIEW", variant="success"),
                    ui.grid(
                        ui.metric_card("Throughput", "4.2k req/s"),
                        ui.metric_card("Latency", "0.039 ms"),
                        ui.metric_card("Error Rate", "0.00%"),
                        columns={"sm": 1, "md": 3, "lg": 3},
                        gap=10,
                    ),
                ),
                columns={"sm": 1, "md": 2, "lg": 2},
                gap=16,
            ),
        ),
        gap=16,
    )


# =========================================================================
# 2. FORMS & INPUTS
# =========================================================================

@app.page("/components-forms")
def components_forms_page():
    return ui.column(
        ui.badge("Form System", variant="primary"),
        ui.heading("Forms, Inputs & Reactive Controls", level=1),
        ui.text(
            "Build type-safe, accessible form interfaces with two-way reactive state binding, client-side validation, "
            "and CSRF-protected server command dispatching.",
            variant="lead",
        ),
        ui.spacer(size=16),

        # Section 1: Buttons & Variants
        ui.card(
            ui.heading("1. Buttons & Variants", level=3),
            ui.text("`ui.button` supports primary, outline, secondary, success, warning, and danger variants:"),
            ui.grid(
                ui.code_block(
                    "import radui as ui\n\n"
                    "ui.row(\n"
                    "    ui.button('Primary Action', variant='primary'),\n"
                    "    ui.button('Outline', variant='outline'),\n"
                    "    ui.button('Secondary', variant='secondary'),\n"
                    "    ui.button('Danger', variant='danger'),\n"
                    "    gap=10,\n"
                    ")",
                    language="python",
                    copyable=True,
                ),
                ui.card(
                    ui.badge("LIVE RENDERED PREVIEW", variant="success"),
                    ui.row(
                        ui.button("Primary Action", variant="primary", command="comp.test_trigger"),
                        ui.button("Outline", variant="outline", command="comp.test_trigger"),
                        ui.button("Secondary", variant="secondary", command="comp.test_trigger"),
                        ui.button("Danger", variant="danger", command="comp.test_trigger"),
                        gap=8,
                        wrap=True,
                    ),
                ),
                columns={"sm": 1, "md": 2, "lg": 2},
                gap=16,
            ),
        ),
        ui.spacer(size=16),

        # Section 2: Text Inputs, Selects & Switches
        ui.card(
            ui.heading("2. Inputs, Selects, Switches & Textareas", level=3),
            ui.text("Form elements automatically synchronize with reactive session signals (`ui.state`):"),
            ui.grid(
                ui.code_block(
                    "import radui as ui\n\n"
                    "s_email = ui.state('email', default='', scope='session')\n"
                    "s_role = ui.state('role', default='engineer', scope='session')\n"
                    "s_alerts = ui.state('alerts', default=True, scope='session')\n\n"
                    "form = ui.form(\n"
                    "    ui.input('Work Email', bind=s_email, placeholder='user@domain.com'),\n"
                    "    ui.select('Role', bind=s_role, options=[('eng', 'Engineer'), ('lead', 'Tech Lead')]),\n"
                    "    ui.switch('Email Notifications', bind=s_alerts),\n"
                    "    ui.button('Save Profile', variant='primary'),\n"
                    "    command='user.save',\n"
                    ")",
                    language="python",
                    copyable=True,
                ),
                ui.card(
                    ui.badge("LIVE RENDERED PREVIEW", variant="success"),
                    ui.form(
                        ui.input("Work Email", placeholder="user@domain.com"),
                        ui.select("Role", options=[("eng", "Engineer"), ("lead", "Tech Lead"), ("arch", "Architect")]),
                        ui.switch("Email Notifications"),
                        ui.button("Save Profile", variant="primary"),
                        command="comp.test_trigger",
                    ),
                ),
                columns={"sm": 1, "md": 2, "lg": 2},
                gap=16,
            ),
        ),
        gap=16,
    )


# =========================================================================
# 3. DATA DISPLAY & DATA GRIDS
# =========================================================================

@app.page("/components-data")
def components_data_page():
    sample_users = [
        ["USR-101", "Ada Lovelace", "Founder", "Production", "0.012 ms"],
        ["USR-102", "Alan Turing", "Cryptographer", "Staging", "0.045 ms"],
        ["USR-103", "Grace Hopper", "Compiler Lead", "Production", "0.018 ms"],
        ["USR-104", "Claude Shannon", "Information Theory", "Research", "0.022 ms"],
        ["USR-105", "John von Neumann", "System Architect", "Production", "0.031 ms"],
    ]

    return ui.column(
        ui.badge("Data Display", variant="primary"),
        ui.heading("Data Grids, Tables & Metric Cards", level=1),
        ui.text(
            "Present complex enterprise datasets with client-side instant search, multi-column sorting, "
            "paginated data grids, and live metric cards.",
            variant="lead",
        ),
        ui.spacer(size=16),

        # Section 1: Interactive DataGrid
        ui.card(
            ui.heading("1. Interactive DataGrid (Search, Sort & Paginate)", level=3),
            ui.text("`ui.data_grid` enables real-time client-side search filtering and column sorting with zero extra dependencies:"),
            ui.data_grid(
                headers=["Operator ID", "Engineer", "Role", "Environment", "AST Latency"],
                rows=sample_users,
                searchable=True,
                sortable=True,
                page_size=3,
                empty_message="No matching operators found.",
            ),
            ui.code_block(
                "import radui as ui\n\n"
                "ui.data_grid(\n"
                "    headers=['Operator ID', 'Engineer', 'Role', 'Environment', 'AST Latency'],\n"
                "    rows=operator_records,\n"
                "    searchable=True,\n"
                "    sortable=True,\n"
                "    page_size=10,\n"
                ")",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=16),

        # Section 2: Metric Cards & Avatars
        ui.card(
            ui.heading("2. KPI Metric Cards & Badges", level=3),
            ui.text("Visualize high-level metrics with trend indicators, subtitles, and reactive number updates:"),
            ui.grid(
                ui.metric_card("Total Cluster Revenue", "$124,590", delta="+18.4% vs last mo", trend="up"),
                ui.metric_card("P99 Request Latency", "1.24 ms", delta="-0.31 ms improvement", trend="up"),
                ui.metric_card("Active Agent Sessions", "84", delta="12 idle workers", trend="neutral"),
                columns={"sm": 1, "md": 3, "lg": 3},
                gap=14,
            ),
        ),
        gap=16,
    )


# =========================================================================
# 4. FEEDBACK & OVERLAYS
# =========================================================================

@app.page("/components-feedback")
def components_feedback_page():
    return ui.column(
        ui.badge("Feedback & Overlays", variant="primary"),
        ui.heading("Callouts, Alerts, Progress & Feedback", level=1),
        ui.text(
            "Deliver instant user feedback with callout boxes, status badges, linear progress indicators, "
            "and notification banners.",
            variant="lead",
        ),
        ui.spacer(size=16),

        # Section 1: Callouts
        ui.card(
            ui.heading("1. Contextual Callout Banners", level=3),
            ui.text("`ui.callout` communicates system information, warnings, success milestones, and errors:"),
            ui.grid(
                ui.callout("Production cluster is running healthy across 8 regions with 99.999% uptime.", title="System Operational", variant="success"),
                ui.callout("Zero JavaScript toolchain required. Python executes server-side and streams diffs.", title="Zero Build Steps", variant="info"),
                ui.callout("Scheduled database maintenance in 14 minutes. Long-running transactions will pause.", title="Notice", variant="warning"),
                ui.callout("Memory pressure threshold exceeded on worker pool 3. Autoscaling triggered.", title="Alert", variant="danger"),
                columns={"sm": 1, "md": 2, "lg": 2},
                gap=14,
            ),
            ui.code_block(
                "import radui as ui\n\n"
                "ui.callout('Production cluster is running healthy.', title='System Operational', variant='success')\n"
                "ui.callout('Memory pressure threshold exceeded.', title='Alert', variant='danger')",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=16),

        # Section 2: Progress Bars
        ui.card(
            ui.heading("2. Progress Indicators & Status Badges", level=3),
            ui.text("Render determinate progress bars with typed variant accents:"),
            ui.column(
                ui.row(ui.text("Deployment Progress (Primary)"), ui.badge("75%", variant="primary"), justify="between"),
                ui.progress_bar(value=75.0, variant="primary"),
                ui.spacer(size=8),
                ui.row(ui.text("Cache Eviction (Success)"), ui.badge("100%", variant="success"), justify="between"),
                ui.progress_bar(value=100.0, variant="success"),
                gap=6,
            ),
        ),
        gap=16,
    )


# =========================================================================
# 5. AI AGENTS, STREAMING & DIAGRAMS
# =========================================================================

@app.page("/components-ai")
def components_ai_page():
    nodes = [
        ui.diagram_node("n_prompt", "User Request", x=40, y=80),
        ui.diagram_node("n_agent", "Autonomous Agent", x=240, y=80),
        ui.diagram_node("n_mcp", "MCP Protocol Server", x=460, y=40),
        ui.diagram_node("n_approval", "Human-in-the-Loop", x=460, y=140),
        ui.diagram_node("n_exec", "Cluster Execution", x=680, y=80),
    ]
    edges = [
        ui.diagram_edge("n_prompt", "n_agent", label="Prompt"),
        ui.diagram_edge("n_agent", "n_mcp", label="List Tools"),
        ui.diagram_edge("n_agent", "n_approval", label="Request Action"),
        ui.diagram_edge("n_mcp", "n_exec", label="Tool Schema"),
        ui.diagram_edge("n_approval", "n_exec", label="Authorized"),
    ]

    return ui.column(
        ui.badge("AI & Streaming", variant="primary"),
        ui.heading("Autonomous AI Agents, Chat & Diagrams", level=1),
        ui.text(
            "Build autonomous agent workbenches with streaming chat views, Model Context Protocol (MCP) integrations, "
            "human-in-the-loop authorization cards, and interactive execution flow diagrams.",
            variant="lead",
        ),
        ui.spacer(size=16),

        # Section 1: Execution Pipeline Diagram
        ui.card(
            ui.heading("1. Interactive Execution Pipeline Diagram", level=3),
            ui.text("`ui.diagram` generates vector SVG graphs with drag-ready nodes and labeled directed edges:"),
            ui.diagram(nodes, edges, height=260),
            ui.code_block(
                "import radui as ui\n\n"
                "nodes = [\n"
                "    ui.diagram_node('n_agent', 'Autonomous Agent', x=240, y=80),\n"
                "    ui.diagram_node('n_exec', 'Cluster Execution', x=680, y=80),\n"
                "]\n"
                "edges = [ui.diagram_edge('n_agent', 'n_exec', label='Execute Tool')]\n"
                "ui.diagram(nodes, edges, height=260)",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=16),

        # Section 2: Agent Conversation & Human Approval
        ui.grid(
            ui.card(
                ui.heading("2. Agent Conversation Stream", level=3),
                ui.chat_view(
                    ui.chat_message("Connected to Model Context Protocol server: postgres-analytics", role="assistant"),
                    ui.chat_message("Can you execute the partition maintenance job?", role="user"),
                    ui.chat_message("I have prepared the job payload. Authorize execution below:", role="assistant"),
                ),
                flippable=True,
                code=(
                    'import radui as ui\n\n'
                    'chat = ui.chat_view(\n'
                    '    ui.chat_message("Connected to Model Context Protocol server: postgres-analytics", role="assistant"),\n'
                    '    ui.chat_message("Can you execute the partition maintenance job?", role="user"),\n'
                    '    ui.chat_message("I have prepared the job payload. Authorize execution below:", role="assistant"),\n'
                    ')'
                ),
                id="showcase-chat-view",
            ),
            ui.card(
                ui.heading("3. Human-in-the-Loop Action Card", level=3),
                ui.text("Privileged action gate for autonomous AI agent tool execution:"),
                ui.action_card(
                    title="Authorize DB Partition Rotation?",
                    description="Target: 'ALTER TABLE daily_logs ROTATE PARTITION 2026_11;'",
                    approve_command="agent.approve_demo",
                    reject_command="agent.reject_demo",
                ),
                flippable=True,
                code=(
                    'import radui as ui\n\n'
                    'action = ui.action_card(\n'
                    '    title="Authorize DB Partition Rotation?",\n'
                    '    description="Target: \'ALTER TABLE daily_logs ROTATE PARTITION 2026_11;\'",\n'
                    '    approve_command="agent.approve_demo",\n'
                    '    reject_command="agent.reject_demo",\n'
                    ')'
                ),
                id="showcase-action-card",
            ),
            columns={"sm": 1, "md": 2, "lg": 2},
            gap=16,
        ),
        gap=16,
    )
