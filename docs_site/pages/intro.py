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
                    columns={"sm": 1, "md": 2, "lg": 2, "xl": 2},
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
            ui.text(
                "Hardware-accelerated CSS animations, micro-interactions, analytical spring physics, and motion presets:"
            ),
            ui.code_block(
                "# 1. Analytical Spring Physics\n"
                "spring_cfg = ui.motion.spring(stiffness=120, damping=14, mass=1.0)\n\n"
                "# 2. Micro-interactions\n"
                "hover_fx = ui.motion.hover(scale=1.02, translate_y=-3.0)\n"
                "tap_fx = ui.motion.tap(scale=0.96)\n\n"
                "# 3. Motion Presets\n"
                "fade = ui.motion.fade_in(duration=0.3)\n"
                "slide = ui.motion.slide_up(distance=16, use_spring=True)\n"
                "slide_down = ui.motion.slide_down(distance=16)\n"
                "scale = ui.motion.scale_up(initial_scale=0.92)\n"
                "pop_fx = ui.motion.pop(duration=0.35)\n"
                "pulse_fx = ui.motion.pulse()\n"
                "stagger_delay = ui.motion.stagger(index=2, base=0.04)\n\n"
                "btn = ui.button('Launch', hover=hover_fx, tap=tap_fx, motion=slide)",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("4. Automated Pydantic Model Forms (`ui.form_from_model`)", level=3),
            ui.text("Automatically generate complete, typed, reactive RADUI Forms from Pydantic schemas or dataclasses:"),
            ui.code_block(
                "from pydantic import BaseModel\n"
                "from enum import Enum\n"
                "import radui as ui\n\n"
                "class Environment(str, Enum):\n"
                "    DEV = 'Development'\n"
                "    STAGING = 'Staging'\n"
                "    PROD = 'Production'\n\n"
                "class DeploymentSchema(BaseModel):\n"
                "    service_name: str\n"
                "    replicas: int = 3\n"
                "    env: Environment = Environment.DEV\n"
                "    enable_autoscaling: bool = True\n"
                "    release_notes: str = ''\n\n"
                "# Generates inputs, number fields, select dropdown, checkbox, textarea, and submit button\n"
                "deploy_form = ui.form_from_model(\n"
                "    DeploymentSchema,\n"
                "    command='deploy.service',\n"
                "    submit_label='Deploy Service',\n"
                "    optimistic=True,\n"
                ")",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("5. State Batches, Transactions & Middleware", level=3),
            ui.text("Group multiple mutations or enforce atomic rollbacks inside command handlers:"),
            ui.code_block(
                "@app.command('batch.update')\n"
                "def on_batch_update(ctx: ui.CommandContext):\n"
                "    # 1. Batch writes into a single DOM invalidation pass\n"
                "    with ctx.batch():\n"
                "        ctx.write(s_kpi_a, 100)\n"
                "        ctx.write(s_kpi_b, 200)\n"
                "        ctx.write(s_kpi_c, 300)\n\n"
                "    # 2. Atomic transaction with automatic rollback on error\n"
                "    with ctx.transaction():\n"
                "        ctx.write(s_balance, ctx.read(s_balance) - 50)\n"
                "        ctx.write(s_transferred, True)\n\n"
                "# 3. Pluggable state interceptor middleware\n"
                "class AuditMiddleware(ui.state.StateMiddleware):\n"
                "    def after_write(self, ref, context, change):\n"
                "        print(f'State mutated: {change.key} -> {change.value}')\n\n"
                "app.add_state_middleware(AuditMiddleware())",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("6. Internationalization & Currency Formatting (`ui.i18n`)", level=3),
            ui.text("Multi-language translation catalogs and locale-aware number/currency/date formatters:"),
            ui.code_block(
                "from radui import i18n\n\n"
                "# 1. Load localized messages\n"
                "translator = i18n.Translator(default_locale='en')\n"
                "translator.load_catalog('es', {'welcome': '¡Bienvenido, {name}!'})\n\n"
                "# 2. Interpolate message\n"
                "msg = translator.t('welcome', locale='es', name='Elena')\n\n"
                "# 3. Format numbers and currencies\n"
                "price_str = i18n.format_currency(1420.50, currency='EUR', locale='de')  # -> '1.420,50 €'\n"
                "count_str = i18n.format_number(982341.2, decimals=1, locale='fr')",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("7. OpenTelemetry Tracing & SVG DAG Visualizer (`ui.inspector`)", level=3),
            ui.text("Distributed tracing exports and reactive dependency graph visualization:"),
            ui.code_block(
                "from radui.inspector import OTLPExporter, generate_dag_svg\n\n"
                "# 1. Export spans to OTLP collector over gRPC/HTTP\n"
                "exporter = OTLPExporter(endpoint='http://localhost:4318/v1/traces')\n\n"
                "# 2. Generate pure SVG diagram of the active reactive DAG\n"
                "svg_code = generate_dag_svg(app.state_runtime)",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("8. Distributed State Backends & Failover (`ui.*StateBackend`)", level=3),
            ui.text(
                "Pluggable enterprise storage engines for session and view state. Supports local in-memory, "
                "embedded SQLite WAL mode, distributed Redis, and ACID PostgreSQL."
            ),
            ui.code_block(
                "from radui import (\n"
                "    App,\n"
                "    InMemoryStateBackend,\n"
                "    SQLiteStateBackend,\n"
                "    RedisStateBackend,\n"
                "    PostgreSQLStateBackend,\n"
                "    StateBackendUnavailableError,\n"
                ")\n\n"
                "# 1. Clustered Redis storage with connection pooling\n"
                "redis_backend = RedisStateBackend(redis_url='redis://cluster-auth:6379/0', ttl_seconds=86400)\n\n"
                "# 2. Embedded SQLite WAL storage for zero-dependency edge deployments\n"
                "sqlite_backend = SQLiteStateBackend(db_path='/data/radui_state.db')\n\n"
                "# 3. ACID PostgreSQL state with tenant row isolation\n"
                "pg_backend = PostgreSQLStateBackend(dsn='postgresql://app:secret@db:5432/radui')\n\n"
                "# Bind backend to App lifecycle\n"
                "app = App(state_backend=redis_backend)\n\n"
                "# Fault handling: catch transient network partition errors\n"
                "try:\n"
                "    await redis_backend.ping()\n"
                "except StateBackendUnavailableError as err:\n"
                "    logger.critical(f'State store unreachable: {err}')",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("9. Event Streaming Backends & Event Broker (`ui.*EventBackend`)", level=3),
            ui.text(
                "High-throughput pub/sub event distribution protocols for multi-node web server clusters. "
                "Enables sub-millisecond SSE broadcasting across instances."
            ),
            ui.code_block(
                "from radui import (\n"
                "    EventBackend,\n"
                "    EventRecord,\n"
                "    InMemoryEventBackend,\n"
                "    SQLiteEventBackend,\n"
                "    RedisEventBackend,\n"
                "    PostgreSQLEventBackend,\n"
                ")\n\n"
                "# 1. Initialize distributed Redis Streams event broker\n"
                "broker: EventBackend = RedisEventBackend(redis_url='redis://localhost:6379/1')\n\n"
                "# 2. Publish structured event record\n"
                "event = EventRecord(\n"
                "    topic='cluster.alerts',\n"
                "    event_type='node_scaled',\n"
                "    payload={'node_id': 'srv-east-4', 'cores': 64},\n"
                "    sequence=10492,\n"
                ")\n"
                "await broker.publish(event)\n\n"
                "# 3. Subscribe with non-blocking async generator\n"
                "async for record in broker.subscribe('cluster.*'):\n"
                "    print(f'[{record.topic}] {record.event_type}: {record.payload}')",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("10. Idempotency Engine & Deduplication (`ui.*IdempotencyBackend`)", level=3),
            ui.text(
                "Cryptographic request fingerprinting and deduplication backends preventing double-submits, "
                "network replay attacks, and duplicate payment or command mutations."
            ),
            ui.code_block(
                "from radui import (\n"
                "    IdempotencyBackend,\n"
                "    IdempotencyRecord,\n"
                "    IdempotencyResult,\n"
                "    IdempotencyError,\n"
                "    IdempotencyConflictError,\n"
                "    IdempotencyBackendUnavailableError,\n"
                "    InMemoryIdempotencyBackend,\n"
                "    SQLiteIdempotencyBackend,\n"
                "    RedisIdempotencyBackend,\n"
                "    PostgreSQLIdempotencyBackend,\n"
                "    compute_payload_fingerprint,\n"
                ")\n\n"
                "# 1. Hash command payload into deterministic SHA-256 fingerprint\n"
                "fp = compute_payload_fingerprint({'cmd': 'transfer', 'amount': 1500, 'to': 'acc_928'})\n\n"
                "# 2. Query idempotency store with lease fencing\n"
                "idempotency = RedisIdempotencyBackend('redis://localhost:6379/2')\n"
                "status: IdempotencyResult = await idempotency.acquire_or_get(key=fp, ttl_seconds=300)\n\n"
                "if status.is_cached:\n"
                "    return status.cached_response\n"
                "elif status.is_in_progress:\n"
                "    raise IdempotencyConflictError('Mutation currently executing in concurrent worker')",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("11. Distributed Jobs, Lease Fencing & Transactional Outbox", level=3),
            ui.text(
                "Durable asynchronous background queues, monotonic lease fencing tokens, and transactional "
                "outbox patterns ensuring atomic state commits and reliable event delivery."
            ),
            ui.code_block(
                "from radui import (\n"
                "    JobBackend,\n"
                "    LocalJobBackend,\n"
                "    SQLiteJobBackend,\n"
                "    RedisJobBackend,\n"
                "    JobDefinition,\n"
                "    JobContext,\n"
                "    JobSnapshot,\n"
                "    JobStatus,\n"
                "    JobSpec,\n"
                "    JobError,\n"
                "    JobCancelledError,\n"
                "    JobCapacityError,\n"
                "    JobNotFoundError,\n"
                "    StaleLeaseError,\n"
                "    TransactionalOutbox,\n"
                "    OutboxRecord,\n"
                "    OutboxStatus,\n"
                "    StaleOutboxLeaseError,\n"
                ")\n\n"
                "# 1. Define resilient background job with progress reporting\n"
                "async def sync_remote_telemetry(ctx: JobContext):\n"
                "    for idx in range(1, 101):\n"
                "        if ctx.is_cancelled():\n"
                "            raise JobCancelledError('Job aborted by operator')\n"
                "        await ctx.update_progress(percent=idx, status_message=f'Processing shard {idx}/100')\n"
                "    return {'status': 'synced', 'count': 100}\n\n"
                "# 2. Register job on Redis backend\n"
                "job_engine = RedisJobBackend('redis://localhost:6379/3')\n"
                "job_def = JobDefinition(func=sync_remote_telemetry, retries=3, timeout_seconds=120)\n"
                "job_id = await job_engine.enqueue(job_def)\n\n"
                "# 3. Atomic Transactional Outbox write\n"
                "outbox = TransactionalOutbox(sqlite_backend)\n"
                "outbox.record_event(OutboxRecord(topic='billing', payload={'invoice_id': 'inv_102'}))",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("12. Reactivity Graph Internals & Scopes", level=3),
            ui.text(
                "Internal architecture of RADUI's 5-tier reactivity runtime: DAG cycle detection, "
                "atomic batch contexts, transaction snapshot rollback, and scoped state references."
            ),
            ui.code_block(
                "from radui import (\n"
                "    StateRuntime,\n"
                "    StateScope,\n"
                "    StateContext,\n"
                "    StateChange,\n"
                "    BatchContext,\n"
                "    TransactionContext,\n"
                "    ComputedRef,\n"
                "    CyclicDependencyError,\n"
                ")\n\n"
                "# 1. Scopes enum isolation\n"
                "scope_app = StateScope.APP        # Cluster-wide shared signals\n"
                "scope_sess = StateScope.SESSION   # Cross-tab user session\n"
                "scope_view = StateScope.VIEW      # Isolated browser tab\n\n"
                "# 2. Graph runtime inspection\n"
                "runtime = StateRuntime()\n"
                "try:\n"
                "    runtime.register_computed('node_a', depends_on=['node_b'])\n"
                "    runtime.register_computed('node_b', depends_on=['node_a'])  # Circular!\n"
                "except CyclicDependencyError as err:\n"
                "    print(f'Dependency cycle prevented: {err}')",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("13. SWR Query Cache Internals (`QueryCache` & `QueryEntry`)", level=3),
            ui.text(
                "Fine-grained control over the Stale-While-Revalidate caching engine, cache entry introspection, "
                "TTL expiration, and background revalidation promises."
            ),
            ui.code_block(
                "from radui import QueryCache, QueryEntry\n\n"
                "# 1. Inspect query cache instance\n"
                "cache = QueryCache(max_entries=2000, default_ttl=300)\n\n"
                "# 2. Direct entry lookup\n"
                "entry: QueryEntry | None = cache.get_entry('fetch_cluster_stats:us-east')\n"
                "if entry and entry.is_stale:\n"
                "    print(f'Cached value: {entry.value} (revalidating in background...)')\n\n"
                "# 3. Programmatic eviction\n"
                "cache.evict_matching('fetch_cluster_stats:*')",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("14. AI Protocol, MCP Tool Registry & AGUI Streaming", level=3),
            ui.text(
                "Full support for Model Context Protocol (MCP) tool exposure, Agentic UI (AGUI) streaming "
                "protocols, fence parsing, and SQLite-backed agent chat repositories."
            ),
            ui.code_block(
                "from radui import (\n"
                "    AGUIEvent,\n"
                "    AGUIEventJournal,\n"
                "    AGUIEventType,\n"
                "    ChatMessageRecord,\n"
                "    MCPToolDescriptor,\n"
                "    MCPToolRegistry,\n"
                "    SQLiteChatRepository,\n"
                "    StreamingFenceParser,\n"
                "    TokenStream,\n"
                "    a2ui_to_component,\n"
                ")\n\n"
                "# 1. Register callable tool with MCP JSON schema\n"
                "mcp_registry = MCPToolRegistry()\n"
                "mcp_registry.register(\n"
                "    MCPToolDescriptor(\n"
                "        name='restart_service',\n"
                "        description='Gracefully restarts a cluster service',\n"
                "        parameters={'type': 'object', 'properties': {'service': {'type': 'string'}}},\n"
                "        handler=lambda args: 'Restarted ' + args.get('service', 'service'),\n"
                "    )\n"
                ")\n\n"
                "# 2. Stream tokens and parse generative markdown UI fences\n"
                "parser = StreamingFenceParser()\n"
                "async for token in TokenStream(llm_client.stream_tokens()):\n"
                "    component_update = parser.feed_token(token)\n"
                "    if component_update:\n"
                "        ui.notify('Generated interactive UI widget on the fly!')",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("15. Observability, Tracing & Benchmark Engine", level=3),
            ui.text(
                "Built-in diagnostic tooling for measuring render latency, recording microsecond trace spans, "
                "and extracting DAG dependency matrices."
            ),
            ui.code_block(
                "from radui import (\n"
                "    BenchmarkSuite,\n"
                "    BenchmarkResult,\n"
                "    TraceCategory,\n"
                "    TraceCollector,\n"
                "    TraceRecord,\n"
                "    extract_dag_structure,\n"
                ")\n\n"
                "# 1. Execute rendering benchmark suite\n"
                "bench = BenchmarkSuite(app)\n"
                "results: BenchmarkResult = bench.run_iterations(n=1000)\n"
                "print(f'Mean render latency: {results.mean_ms:.2f}ms | p99: {results.p99_ms:.2f}ms')\n\n"
                "# 2. Inspect active trace collector spans\n"
                "collector = TraceCollector()\n"
                "spans = collector.get_spans(category=TraceCategory.STATE_IO)\n\n"
                "# 3. Extract DAG structure for telemetry visualization\n"
                "dag_graph = extract_dag_structure(app.state_runtime)",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("16. Plugin Architecture (`ui.Plugin` & `PluginManager`)", level=3),
            ui.text(
                "Extensible modular architecture for packaging third-party components, state middleware, "
                "command handlers, and static assets into reusable RADUI plugins with entry-point auto-discovery:"
            ),
            ui.code_block(
                "from radui import Plugin, PluginManager\n\n"
                "class AnalyticsPlugin(Plugin):\n"
                "    name = 'analytics'\n"
                "    version = '1.0.0'\n\n"
                "    def on_load(self, app):\n"
                "        # Initialize plugin lifecycle\n"
                "        app.add_middleware(self.track_request)\n\n"
                "    def on_unload(self, app):\n"
                "        # Teardown database pools and collectors\n"
                "        pass\n\n"
                "    def register_components(self, registry):\n"
                "        # Expose custom AST nodes\n"
                "        pass\n\n"
                "# Register and initialize plugin with manager\n"
                "manager = PluginManager(app)\n"
                "manager.load(AnalyticsPlugin())",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("17. Application IR & Schema Registry", level=3),
            ui.text(
                "Access low-level application intermediate representation (IR), component catalogs, command schemas, "
                "and library release metadata."
            ),
            ui.code_block(
                "from radui import (\n"
                "    ApplicationIR,\n"
                "    ComponentRegistry,\n"
                "    CommandSpec,\n"
                "    DuplicateComponentRegistrationError,\n"
                "    UnregisteredComponentError,\n"
                "    __version__,\n"
                ")\n\n"
                "print(f'Running RADUI version: {__version__}')\n\n"
                "# 1. Inspect complete Application Intermediate Representation\n"
                "ir: ApplicationIR = app.export_ir()\n"
                "print(f'Total pages registered: {len(ir.pages)}')\n"
                "print(f'Total server commands: {len(ir.commands)}')\n\n"
                "# 2. Component registry introspection\n"
                "registry = ComponentRegistry.get_global_registry()\n"
                "is_registered = registry.has('data_grid')  # -> True",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("18. Date Formatting & Locale Management", level=3),
            ui.text(
                "Direct helper functions for reading and configuring active execution locales and formatting "
                "localized date and timestamp strings."
            ),
            ui.code_block(
                "from radui import set_locale, get_locale, format_date\n"
                "from datetime import datetime\n\n"
                "# 1. Configure and query context locale\n"
                "set_locale('fr_FR')\n"
                "curr_locale = get_locale()  # -> 'fr_FR'\n\n"
                "# 2. Localized date rendering\n"
                "now = datetime(2026, 11, 15, 14, 30)\n"
                "formatted = format_date(now, format_style='full', locale='fr_FR')\n"
                "print(formatted)  # -> 'dimanche 15 novembre 2026'",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("19. Complete AST Node Class Hierarchy (42 Primitive Classes)", level=3),
            ui.text(
                "Direct instantiation of PascalCase AST Node classes for metaprogramming, dynamic component "
                "factories, tree visitors, and strongly-typed compiler transforms:"
            ),
            ui.code_block(
                "# Available node classes in radui:\n"
                "from radui import (\n"
                "    AccordionItem, ActionCard, AvatarGroup, BreadcrumbItem,\n"
                "    CanvasStream, ChatInput, ChatMessage, ChatView, CodeBlock, DatePicker,\n"
                "    DiagramEdge, DiagramNode, DropdownMenu, DropdownMenuItem,\n"
                "    DynamicCard, EmptyState, ErrorBoundary, FileUpload,\n"
                "    GenerativeSlot, JobPanel, Kbd, MetricCard, Plot, PresenceBar,\n"
                "    ProgressBar, ProgressCircle, RadioGroup, Skeleton, Spacer,\n"
                "    SplitPanel, Stack, StepTimeline, StreamingText, TabItem,\n"
                "    Tabs, ThemeToggle, TimePicker, Toast, ToastContainer,\n"
                "    TreeNode, TreeView, VirtualList\n"
                ")\n\n"
                "# Example: Direct AST class instantiation for recursive tree construction\n"
                "root_panel = SplitPanel(\n"
                "    left=TreeView(\n"
                "        nodes=[\n"
                "            TreeNode(label='src', children=[TreeNode(label='app.py')]),\n"
                "            TreeNode(label='tests', children=[TreeNode(label='test_harness.py')]),\n"
                "        ]\n"
                "    ),\n"
                "    right=VirtualList(\n"
                "        items=[f'Log record #{i}' for i in range(10000)],\n"
                "        item_height=36,\n"
                "    ),\n"
                "    orientation='horizontal',\n"
                ")",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("20. In-Browser Live DevTools & Time-Travel Debugger (`ui.DevTools`)", level=3),
            ui.text(
                "Zero-config floating developer HUD (`DevToolsConfig`, `TimeTravelDebugger`, `StateSnapshot`) providing live reactive DAG inspection, "
                "wall-clock microsecond latency watermarks, surgical SSE morph glow animations, and reverse-diff time-travel state rollbacks:"
            ),
            ui.code_block(
                "from radui import DevTools, DevToolsConfig, TimeTravelDebugger, StateSnapshot\n"
                "import radui as ui\n\n"
                "# 1. Activate DevTools during development\n"
                "app = ui.App(\n"
                "    title='Enterprise Analytics',\n"
                "    devtools=DevToolsConfig(\n"
                "        enabled=True,\n"
                "        time_travel=True,\n"
                "        highlight_morphs=True,\n"
                "        max_journal_entries=50,\n"
                "        dock_position='bottom-right',\n"
                "    )\n"
                ")\n\n"
                "# 2. Programmatic time-travel rollback inside command handlers\n"
                "@app.command('debug.rollback')\n"
                "def rollback_action(ctx: ui.CommandContext):\n"
                "    # Steps back 1 transaction in state history and restores state values\n"
                "    restored_keys = ctx.devtools.rollback_steps(steps=1)\n"
                "    ui.notify(f'Rolled back mutations: {restored_keys}', variant='warning')",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("21. Collaborative Multi-User State & Live Presence (`ui.presence_bar`)", level=3),
            ui.text(
                "Built-in multi-user presence strip, collaborative occupant tracking (`PresenceManager`, `PresenceUser`), and cooperative field locking "
                "to prevent simultaneous write conflicts across multiple connected browser sessions:"
            ),
            ui.code_block(
                "import radui as ui\n"
                "from radui import PresenceManager, PresenceUser, get_global_presence_manager\n\n"
                "# 1. Place a real-time presence bar in any document or room\n"
                "@app.page('/doc/{doc_id}')\n"
                "def document_editor(doc_id: str):\n"
                "    return ui.column(\n"
                "        ui.row(\n"
                "            ui.heading(f'Collaborative Document #{doc_id}', level=2),\n"
                "            ui.presence_bar(room=f'doc:{doc_id}', max_avatars=5, show_status=True),\n"
                "            justify='between',\n"
                "            align='center',\n"
                "        ),\n"
                "        ui.textarea('Shared Notes', placeholder='Type with live presence...'),\n"
                "    )\n\n"
                "# 2. Programmatic cooperative field locking\n"
                "pm: PresenceManager = get_global_presence_manager()\n"
                "locked = pm.lock_field(room='doc:101', field_id='notes_input', user_id='usr_elena', timeout_seconds=15.0)\n"
                "if not locked:\n"
                "    raise ValueError('Input field currently locked by another collaborator')",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("22. High-Frequency Telemetry Canvas (`ui.canvas_stream`)", level=3),
            ui.text(
                "Hardware-accelerated 60 FPS HTML5 / WebGL canvas rendering streaming time-series data at up to 100,000 points/sec "
                "with Largest-Triangle-Three-Buckets (LTTB) downsampling, bypassing DOM thrashing completely:"
            ),
            ui.code_block(
                "import radui as ui\n\n"
                "@app.page('/telemetry')\n"
                "def telemetry_dashboard():\n"
                "    return ui.column(\n"
                "        ui.heading('High-Frequency Sensor Waveform (100k pts/sec)'),\n"
                "        ui.canvas_stream(\n"
                "            stream_topic='sensor.vibration',\n"
                "            width='100%',\n"
                "            height=380,\n"
                "            mode='waveform',      # 'line', 'scatter', 'waveform', 'bar'\n"
                "            buffer_size=50000,\n"
                "            downsample='lttb',    # LTTB decimation keeps visual peaks intact\n"
                "            color='var(--gx-primary)',\n"
                "            grid=True,\n"
                "        ),\n"
                "    )",
                language="python",
                copyable=True,
            ),
        ),
        ui.spacer(size=14),
        ui.card(
            ui.heading("23. WebAssembly & Pyodide Serverless Offline Engine (`radui export --wasm`)", level=3),
            ui.text(
                "Bundle complete pure-Python RADUI applications into standalone WebAssembly distributions running 100% inside the browser "
                "via Pyodide and WebWorkers with offline PWA CacheStorage and zero backend servers:"
            ),
            ui.code_block(
                "# 1. Compile application via CLI\n"
                "$ radui export app.py --wasm --output ./dist_wasm\n\n"
                "# 2. Or programmatically via Python API\n"
                "from radui import WasmExportEngine, export_wasm_bundle\n\n"
                "out_dir = export_wasm_bundle(app_path='app.py', output_dir='dist_wasm')\n"
                "# Emits index.html, wasm-worker.js, and service-worker.js ready to deploy on GitHub Pages",
                language="python",
                copyable=True,
            ),
        ),
        gap=16,
    )
