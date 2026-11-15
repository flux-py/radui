"""Overview and quickstart pages."""

from __future__ import annotations

import radui as ui
from docs_site.core import app, s_counter

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
                ui.code_block(
                    'count = ui.state("count", default=0, scope="session")\n\n'
                    'ui.metric_card("Counter", count)\n'
                    'ctx.write(count, ctx.read(count) + 1)',
                    language="python",
                    copyable=True,
                ),
                gap=14,
                motion=ui.motion.fade_in(delay=0.12),
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
