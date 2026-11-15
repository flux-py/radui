"""Overview and quickstart pages."""

from __future__ import annotations

import radui as ui
from docs_site.core import app, s_counter

def _render_why_radui_section() -> ui.Component:
    """Render the comprehensive, dynamic & interactive 'Why RADUI?' architectural centerpiece."""
    arch_nodes = [
        ui.diagram_node("n_ast", "Pure Python AST", description="Type-Safe Declarative Tree", x=40, y=40, width=180, height=64, status="success", icon="🐍"),
        ui.diagram_node("n_ssr", "High-Speed SSR Engine", description="< 3.1ms Initial Render", x=290, y=40, width=190, height=64, status="active", icon="⚡"),
        ui.diagram_node("n_dom", "Interactive Browser DOM", description="Zero npm / 9.6KB Micro-Runtime", x=550, y=40, width=220, height=64, status="normal", icon="🌐"),
        ui.diagram_node("n_dispatch", "Command Dispatch", description="Fencing Tokens & Deduplication", x=550, y=190, width=220, height=64, status="warning", icon="🛡️"),
        ui.diagram_node("n_dag", "Reactive DAG Runtime", description="5-Tier Scoped State & SWR", x=290, y=190, width=190, height=64, status="active", icon="🔄"),
    ]
    arch_edges = [
        ui.diagram_edge("n_ast", "n_ssr", label="1. Declarative AST", animated=True, color="var(--gx-primary)", directional=True),
        ui.diagram_edge("n_ssr", "n_dom", label="2. Semantic HTML (<3.1ms)", animated=True, color="var(--gx-primary)", directional=True),
        ui.diagram_edge("n_dom", "n_dispatch", label="3. User Action / Form / Event", animated=True, color="var(--gx-warning)", directional=True),
        ui.diagram_edge("n_dispatch", "n_dag", label="4. Fenced Command Dispatch", animated=True, color="var(--gx-warning)", directional=True),
        ui.diagram_edge("n_dag", "n_dom", label="5. Surgical SSE Sub-DOM Patch", animated=True, color="var(--gx-primary)", directional=True),
    ]

    return ui.column(
        # Section 1: Section Introduction
        ui.column(
            ui.row(
                ui.badge("ARCHITECTURAL ADVANTAGE", variant="primary"),
                ui.badge("SERVER-DRIVEN REACTIVITY", variant="success"),
                gap=8,
            ),
            ui.heading("Why RADUI?", level=2, id="why-radui-heading"),
            ui.text(
                "RADUI (Reactive Application Development User Interface) combines the unmatched developer velocity "
                "of classic Rapid Application Development (RAD) with a hyper-optimized Server-Driven Reactive Engine.",
                variant="lead",
            ),
            gap=12,
            id="why-radui",
            motion=ui.motion.slide_up(delay=0.05, duration=0.45),
        ),
        ui.spacer(size=14),

        # Section 2: Interactive Architecture Flow
        ui.card(
            ui.row(
                ui.heading("Interactive Architecture & Execution Lifecycle", level=3),
                ui.row(
                    ui.badge("● Initial SSR Path (< 3.1ms)", variant="success"),
                    ui.badge("● SSE Reactive Loop (0.168ms)", variant="warning"),
                    gap=8,
                ),
                justify="between",
                align="center",
            ),
            ui.text("Hover or click any node to trace data flow, latency budgets, and execution invariants through the lifecycle:"),
            ui.diagram(arch_nodes, arch_edges, height=310, id="why-radui-diagram"),
            ui.spacer(size=8),
            # Node Details Inspector Card
            ui.card(
                ui.row(
                    ui.row(
                        ui.badge("INITIAL BUILD", variant="primary", id="arch-node-phase"),
                        ui.heading("Pure Python AST (Type-Safe Declarative)", level=4, id="arch-node-title"),
                        gap=10,
                        align="center",
                    ),
                    ui.badge("0.012 ms AST build", variant="neutral", id="arch-node-latency"),
                    justify="between",
                    align="center",
                ),
                ui.text(
                    "Declarative component tree built with strongly typed Python classes. Automatically validates layout constraints, event triggers, and accessibility properties at definition time with zero compilers.",
                    id="arch-node-desc",
                ),
                id="arch-inspector-card",
                hover=ui.motion.hover(scale=1.01, translate_y=-1.0),
            ),
            title="Interactive Request-Response Lifecycle Flow",
            subtitle="Bidirectional visualization of initial HTML SSR and continuous SSE sub-DOM mutation streaming",
            hover=ui.motion.hover(scale=1.01, translate_y=-2.0),
        ),
        ui.spacer(size=16),

        # Section 3: Interactive Key Differentiators
        ui.accordion(
            ui.accordion_item(
                "Click to View Key Differentiators",
                ui.grid(
                    # Card 1: 100% Pure Python
                    ui.card(
                        ui.row(
                            ui.badge("01", variant="primary"),
                            ui.badge("TYPE-SAFE AST", variant="neutral"),
                            justify="between",
                        ),
                        ui.heading("100% Pure Python", level=3),
                        ui.text("Author layouts, reactivity graphs, async jobs, and tool calls in clean, type-safe Python. No JSX, no TypeScript, no context switching."),
                        ui.divider(),
                        ui.code_block(
                            "import radui as ui\n\n"
                            "@app.page('/dashboard')\n"
                            "def dashboard():\n"
                            "    return ui.card(\n"
                            "        ui.metric_card('RPS', '1,420'),\n"
                            "        ui.button('Scale', command='cluster.scale'),\n"
                            "    )",
                            language="python",
                            copyable=True,
                        ),
                        title="Pure Python AST",
                        hover=ui.motion.hover(scale=1.02, translate_y=-3.0),
                    ),

                    # Card 2: Zero JavaScript Build Pipeline
                    ui.card(
                        ui.row(
                            ui.badge("02", variant="primary"),
                            ui.badge("ZERO NPM / VITE", variant="neutral"),
                            justify="between",
                        ),
                        ui.heading("Zero JavaScript Build Pipeline", level=3),
                        ui.text("Eliminate Node.js, npm, Webpack, Vite, and hydration mismatches. The Python server renders and mutates views directly."),
                        ui.divider(),
                        ui.text("Zero package.json, zero dependency vulnerabilities, and zero client build steps. Ship modern web applications using standard pip/uv toolchains."),
                        title="Zero JS Toolchain",
                        hover=ui.motion.hover(scale=1.02, translate_y=-3.0),
                    ),

                    # Card 3: Surgical SSE Sub-DOM Morphing
                    ui.card(
                        ui.row(
                            ui.badge("03", variant="primary"),
                            ui.badge("SUB-DOM DIFF", variant="success"),
                            justify="between",
                        ),
                        ui.heading("Surgical SSE Sub-DOM Morphing", level=3),
                        ui.text("Initial requests receive server-side rendered HTML in under 3.1ms; user interactions stream targeted Server-Sent Event (SSE) patches that morph only mutated DOM elements."),
                        ui.divider(),
                        ui.row(
                            ui.metric_card("Initial SSR", "< 3.1 ms"),
                            ui.metric_card("Diff Morph", "0.168 ms"),
                            gap=10,
                            wrap=True,
                        ),
                        title="SSE Sub-DOM Morphing",
                        hover=ui.motion.hover(scale=1.02, translate_y=-3.0),
                    ),

                    # Card 4: Deterministic 5-Tier State Isolation
                    ui.card(
                        ui.row(
                            ui.badge("04", variant="primary"),
                            ui.badge("FAIL-CLOSED FENCING", variant="neutral"),
                            justify="between",
                        ),
                        ui.heading("Deterministic 5-Tier State Isolation", level=3),
                        ui.text("Clear separation between ephemeral, view, session, user, and app state with fail-closed tenant fencing."),
                        ui.divider(),
                        ui.text("Strict scoping boundaries prevent cross-tenant contamination in multi-tenant enterprise deployments: ephemeral (action args), view (outlet tree), session (encrypted cookie), user (cross-tab auth), and app (cluster signals)."),
                        title="5-Tier State Scoping",
                        hover=ui.motion.hover(scale=1.02, translate_y=-3.0),
                    ),

                    # Card 5: Native Streaming AI & MCP Protocol
                    ui.card(
                        ui.row(
                            ui.badge("05", variant="primary"),
                            ui.badge("AGENT & MCP READY", variant="primary"),
                            justify="between",
                        ),
                        ui.heading("Native Streaming AI & MCP Protocol", level=3),
                        ui.text("Out-of-the-box streaming generative UI, Model Context Protocol (MCP) tool integration, and human-in-the-loop approval cards."),
                        ui.divider(),
                        ui.chat_view(
                            ui.chat_message("Connected to Model Context Protocol server", role="assistant"),
                            ui.chat_message("Authorize batch partition rotation?", role="assistant"),
                        ),
                        title="AI & MCP Integration",
                        hover=ui.motion.hover(scale=1.02, translate_y=-3.0),
                    ),

                    # Card 6: Distributed Enterprise Hardening
                    ui.card(
                        ui.row(
                            ui.badge("06", variant="primary"),
                            ui.badge("ADR-001 LEASE FENCED", variant="neutral"),
                            justify="between",
                        ),
                        ui.heading("Distributed Enterprise Hardening", level=3),
                        ui.text("Monotonic fencing tokens, transactional outbox pattern, ACID WAL SQLite & Redis clustering, and OpenTelemetry OTLP tracing."),
                        ui.divider(),
                        ui.text("Monotonic fencing tokens eliminate split-brain write hazards under network partitions. Full OpenTelemetry tracing captures end-to-end spans across render, dispatch, and event delivery."),
                        title="Enterprise Hardening",
                        hover=ui.motion.hover(scale=1.02, translate_y=-3.0),
                    ),
                    columns={"sm": 1, "md": 2, "lg": 2, "xl": 3},
                    gap=16,
                    stagger_children=0.05,
                ),
                open=True,
            ),
        ),
        gap=16,
    )

@app.page("/")
def home_page():
    return ui.column(
        ui.column(
            ui.badge("Python-first | Server-rendered | Reactive", variant="success"),
            ui.heading("Build responsive apps with Python.", level=1),
            ui.text(
                "RADUI is a component library and reactive runtime for building interactive web apps in Python. Define your interface as a typed component tree; RADUI renders it on the server and streams updates as state changes.",
                variant="lead",
            ),
            ui.row(
                ui.link("Start building >", "getting-started.html"),
                ui.link("Browse components", "components.html"),
                ui.link("Why RADUI? ↓", "#why-radui"),
                gap=20,
            ),
            gap=15,
            motion=ui.motion.slide_up(delay=0.04, duration=0.45),
        ),
        ui.spacer(size=24),
        ui.grid(
            ui.card(
                ui.row(
                    ui.badge("LIVE EXAMPLE", variant="success"),
                    ui.badge("session state", variant="neutral"),
                    gap=8,
                ),
                ui.heading("A small state change. A live page update.", level=3),
                ui.text("Change the counter. The command runs on the server, updates session state, and sends the resulting UI patch to this page."),
                ui.metric_card("Counter", s_counter, delta="Bound to a server state signal"),
                ui.row(
                    ui.form(ui.button("Decrease", variant="secondary"), command="demo.dec"),
                    ui.form(ui.button("Increase", variant="primary"), command="demo.inc"),
                    gap=10,
                ),
                gap=14,
                motion=ui.motion.fade_in(delay=0.12),
                flippable=True,
                code='count = ui.state("count", default=0, scope="session")\n\nui.metric_card("Counter", count)\nctx.write(count, ctx.read(count) + 1)',
                id="demo-counter-card",
            ),
            ui.card(
                ui.badge("THE RADUI MODEL", variant="primary"),
                ui.heading("One Python tree. A responsive interface.", level=3),
                ui.text("Compose layouts, forms, data displays, feedback, and AI workflows from the same native component system."),
                ui.divider(),
                ui.row(ui.badge("Typed components", variant="neutral"), ui.badge("Server rendered", variant="neutral"), gap=8),
                ui.row(ui.badge("Reactive state", variant="neutral"), ui.badge("SSE updates", variant="neutral"), gap=8),
                ui.spacer(size=8),
                ui.callout("No JavaScript build pipeline is required. Add client code only when your application needs it.", title="A focused Python workflow", variant="info"),
                gap=12,
                motion=ui.motion.slide_up(delay=0.2, duration=0.45),
            ),
            columns={"sm": 1, "md": 2, "lg": 2},
            gap=18,
            stagger_children=0.08,
        ),
        ui.spacer(size=32),
        
        # Centerpiece "Why RADUI?" Section
        _render_why_radui_section(),
        ui.spacer(size=32),

        ui.heading("A clear path from first view to production", level=2),
        ui.grid(
            ui.card(ui.badge("01", variant="primary"), ui.heading("Get started", level=3), ui.text("Install RADUI, create an app, and run the development server."), ui.link("Follow the quickstart >", "getting-started.html"), gap=10),
            ui.card(ui.badge("02", variant="primary"), ui.heading("Compose your UI", level=3), ui.text("Explore the component catalog and see how layouts, inputs, and feedback fit together."), ui.link("Explore components >", "components.html"), gap=10),
            ui.card(ui.badge("03", variant="primary"), ui.heading("Understand reactivity", level=3), ui.text("Learn state scopes, command handling, and the server-to-browser update flow."), ui.link("Read the core concepts >", "state.html"), gap=10),
            columns={"sm": 1, "md": 3, "lg": 3},
            gap=14,
            stagger_children=0.06,
        ),
        gap=16,
    )

@app.page("/getting-started")
def getting_started_page():
    return ui.column(
        ui.heading("Getting Started with RADUI", level=1),
        ui.text("Install RADUI and construct your first reactive application in under 60 seconds."),
        ui.callout(
            "RADUI requires Python 3.11+. No Node.js, npm, Webpack, or Vite build steps required.",
            title="Zero JavaScript Toolchain Required",
            variant="info",
        ),
        ui.spacer(size=12),
        ui.heading("1. Installation", level=2),
        ui.code_block(
            "# Direct install from GitHub (Available immediately):\n"
            "pip install \"git+https://github.com/flux-py/radui.git\"\n\n"
            "# Enterprise production bundle from GitHub:\n"
            "pip install \"radui[all] @ git+https://github.com/flux-py/radui.git\"\n\n"
            "# Or install from PyPI (once published):\n"
            "pip install radui\n"
            "pip install \"radui[all]\"",
            language="bash",
            copyable=True,
        ),
        ui.heading("2. Create Your First App (app.py)", level=2),
        ui.code_block(
            'import radui as ui\n\n'
            'app = ui.App(title="Quickstart Portal")\n'
            's_msg = ui.state("msg", "Welcome to RADUI!", scope="session")\n\n'
            '@app.page("/")\n'
            'def index():\n'
            '    return ui.container(\n'
            '        ui.heading("My First Reactive Application"),\n'
            '        ui.card(\n'
            '            ui.text(s_msg.value),\n'
            '            ui.button("Say Hello", command="hello.click", variant="primary"),\n'
            '        )\n'
            '    )\n\n'
            '@app.command("hello.click")\n'
            'def on_hello(ctx: ui.CommandContext):\n'
            '    ctx.write(s_msg, "Hello from RADUI reactive runtime!")\n'
            '    ui.notify("Updated greeting over SSE!", variant="success")\n\n'
            'if __name__ == "__main__":\n'
            '    app.run(port=3000)',
            language="python",
            copyable=True,
        ),
        ui.heading("3. Run the Development Server", level=2),
        ui.code_block("radui dev app.py --port 3000 --open", language="bash", copyable=True),
        gap=16,
        stagger_children=0.05,
    )

@app.page("/api-reference")
def api_reference_page():
    return ui.column(
        ui.badge("Core SDK", variant="primary"),
        ui.heading("Python API & SDK Reference", level=1),
        ui.text(
            "Complete reference for the top-level RADUI Python programming interface, decorators, context managers, and reactive primitives.",
            variant="lead",
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("1. App Initialization & Lifecycle (`ui.App`)", level=3),
            ui.text("The central registry managing routes, layouts, state backends, theme configuration, and ASGI 3.0 protocol routing:"),
            ui.code_block(
                "app = ui.App(\n"
                "    title='Enterprise Portal',\n"
                "    theme=ui.Theme(name='dark', mode='dark'),\n"
                "    command_palette=True,\n"
                "    debug=False,\n"
                ")\n\n"
                "# Decorator for route registration\n"
                "@app.page('/analytics', title='Analytics')\n"
                "def analytics_page():\n"
                "    return ui.heading('Analytics')\n\n"
                "# Layout wrapper decorator\n"
                "@app.layout('/')\n"
                "def root_layout(outlet: ui.Component):\n"
                "    return ui.container(outlet)\n\n"
                "# Server command handler decorator\n"
                "@app.command('data.refresh')\n"
                "def on_refresh(ctx: ui.CommandContext):\n"
                "    ui.notify('Refreshed!', variant='success')",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("2. Reactive Signals (`ui.state` & `@ui.computed`)", level=3),
            ui.text("Deterministic state declarations with automatic reactive dependency graph resolution:"),
            ui.code_block(
                "# 1. Declare state with deterministic scope ('session', 'view', 'app')\n"
                "s_price = ui.state('cart.price', default=99.0, scope='session')\n"
                "s_qty = ui.state('cart.qty', default=2, scope='session')\n\n"
                "# 2. Derived computed signal with automated DAG dependency tracking\n"
                "@ui.computed\n"
                "def s_subtotal() -> float:\n"
                "    return round(s_price.value * s_qty.value, 2)\n\n"
                "# 3. Mutation inside command handler\n"
                "@app.command('cart.add')\n"
                "def on_add(ctx: ui.CommandContext):\n"
                "    ctx.write(s_qty, ctx.read(s_qty) + 1)",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("3. Motion & Animation Tokens (`ui.motion`)", level=3),
            ui.text("Hardware-accelerated CSS animations and spring physics:"),
            ui.code_block(
                "# Hover elevation and scale\n"
                "hover_fx = ui.motion.hover(scale=1.02, translate_y=-3.0)\n\n"
                "# Active press/tap scale down\n"
                "tap_fx = ui.motion.tap(scale=0.96)\n\n"
                "# Entrance slide animation\n"
                "enter_fx = ui.motion.slide_up(delay=0.1, duration=0.4)\n\n"
                "btn = ui.button('Launch', hover=hover_fx, tap=tap_fx, motion=enter_fx)",
                language="python",
                copyable=True,
            ),
        ),
        gap=16,
    )
