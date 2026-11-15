"""RADUI documentation app and interactive examples, built from RADUI components."""

from __future__ import annotations

import radui as ui
from docs_site.data import COMPONENTS, CLI_COMMANDS, ADRS

# =========================================================================
# DOCUMENTATION DESIGN SYSTEM
# =========================================================================

CUSTOM_CSS = """
:root, [data-theme], html, body {
  --gx-font: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
  --gx-font-mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace !important;
  --gx-bg: #f5f4ef !important;
  --gx-surface: #ffffff !important;
  --gx-surface-alt: #f0efe9 !important;
  --gx-text: #19221e !important;
  --gx-text-muted: #69736c !important;
  --gx-border: #e5e4dc !important;
  --gx-border-strong: #d4d5ca !important;
  --gx-primary: #206b52 !important;
  --gx-primary-hover: #174d3b !important;
  --gx-primary-subtle: #e7f1eb !important;
  color-scheme: light !important;
}
html { scroll-behavior: smooth; scroll-padding-top: 84px; }
body {
  background: #f5f4ef !important;
  background-image: radial-gradient(ellipse at 50% -25%, rgba(184, 207, 185, .42), transparent 62%),
    linear-gradient(90deg, rgba(32,107,82,.025) 1px, transparent 1px),
    linear-gradient(rgba(32,107,82,.025) 1px, transparent 1px) !important;
  background-size: auto, 52px 52px, 52px 52px !important;
  color: #19221e !important;
  font-family: var(--gx-font) !important;
  line-height: 1.65;
  -webkit-font-smoothing: antialiased;
}
#docs-shell { max-width: 1320px !important; padding: 0 36px !important; }
.gx-shell:has(#docs-shell) { width: min(1400px, calc(100% - 36px)) !important; max-width: none !important; margin: 24px auto 64px !important; }
#docs-header {
  position: sticky; top: 0; z-index: 30; padding: 18px 0 14px;
  background: rgba(245,244,239,.9); backdrop-filter: blur(18px);
  border-bottom: 1px solid rgba(212,213,202,.72); margin-bottom: 28px;
}
#docs-header .gx-heading { margin: 0; font-size: 1.2rem !important; letter-spacing: -.055em !important; color: #19221e !important; }
#docs-header .gx-link { padding: 7px 10px; border-radius: 8px; color: #536158 !important; font-size: .88rem; text-decoration: none; transition: color .18s ease, background .18s ease; }
#docs-header .gx-link:hover { color: #174d3b !important; background: #e7f1eb; text-decoration: none; }
#docs-layout { align-items: start; grid-template-columns: 224px minmax(0,1fr) !important; gap: 62px !important; }
#docs-sidebar { position: sticky; top: 102px; padding: 4px 0 20px; max-height: calc(100vh - 116px); overflow: auto; }
#docs-sidebar .gx-heading { color: #879087 !important; font-size: .7rem !important; font-weight: 700 !important; letter-spacing: .12em !important; text-transform: uppercase; margin: 16px 0 6px; }
#docs-sidebar .gx-accordion { border: 0 !important; gap: 15px; overflow: visible !important; background: transparent !important; }
#docs-sidebar .gx-accordion-item { border: 0 !important; background: transparent !important; }
#docs-sidebar .gx-accordion-header { padding: 2px 0 7px !important; background: transparent !important; color: #26332b !important; font-size: .82rem !important; font-weight: 700 !important; }
#docs-sidebar .gx-accordion-content { border: 0 !important; padding: 0 !important; background: transparent !important; }
#docs-sidebar .gx-column { gap: 2px !important; }
#docs-sidebar .gx-link { color: #69736c !important; padding: 5px 9px !important; border-radius: 6px; font-size: .84rem !important; font-weight: 450 !important; text-decoration: none; transition: color .18s ease, background .18s ease, transform .18s ease; }
#docs-sidebar .gx-link:hover { color: #174d3b !important; background: #e7f1eb; padding-left: 13px !important; text-shadow: none !important; }
#docs-sidebar > .gx-card { margin-top: 22px; padding: 14px !important; background: rgba(255,255,255,.62) !important; box-shadow: none !important; border-radius: 12px !important; }
#docs-sidebar > .gx-card .gx-text { font-size: .8rem; }
#docs-content { min-width: 0; padding: 3px 0 54px; animation: docs-enter .55s cubic-bezier(.2,.75,.25,1) both; }
@keyframes docs-enter { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes docs-reveal { from { opacity: .55; transform: translateY(14px); } to { opacity: 1; transform: translateY(0); } }
@supports (animation-timeline: view()) {
  #docs-content .gx-grid .gx-card {
    animation: docs-reveal .65s ease both;
    animation-timeline: view();
    animation-range: entry 0% cover 18%;
  }
}
.gx-heading { color: #19221e !important; letter-spacing: -.04em !important; line-height: 1.16 !important; }
#docs-content > .gx-column > .gx-heading:first-child { font-size: clamp(2.1rem, 4vw, 3.35rem) !important; max-width: 850px; margin: 0; }
#docs-content .gx-column:first-child > .gx-heading { font-size: clamp(2.35rem, 4.5vw, 3.8rem) !important; max-width: 780px; }
.gx-text { color: #536158 !important; line-height: 1.72 !important; }
.gx-text[class*="lead"] { max-width: 690px; color: #536158 !important; font-size: 1.12rem !important; }
.gx-card {
  display: flex !important; flex-direction: column !important; gap: 14px !important;
  background: rgba(255,255,255,.88) !important; border: 1px solid #e5e4dc !important;
  border-radius: 16px !important; padding: 22px !important; box-shadow: 0 6px 22px rgba(36,48,39,.035) !important;
  transition: transform .24s cubic-bezier(.2,.75,.25,1), box-shadow .24s ease, border-color .24s ease !important;
}
.gx-card:hover { transform: translateY(-3px); border-color: #c4d7c9 !important; box-shadow: 0 14px 34px rgba(36,48,39,.08) !important; }
.gx-metric { background: #f8f8f4 !important; border: 1px solid #e8e9e2 !important; border-radius: 12px !important; padding: 17px !important; transition: transform .2s ease, border-color .2s ease !important; }
.gx-metric:hover { transform: translateY(-2px); border-color: #b9d1c1 !important; }
.gx-metric-value { color: #206b52 !important; font-family: var(--gx-font-mono) !important; font-size: 1.8rem !important; font-weight: 700 !important; }
.gx-badge { border-radius: 999px !important; padding: 4px 10px !important; font-size: .72rem !important; letter-spacing: .02em; }
.gx-badge-primary { color: #206b52 !important; background: #e7f1eb !important; border: 1px solid #d0e4d6 !important; }
.gx-badge-success { color: #276a4a !important; background: #e8f3e8 !important; border: 1px solid #d0e5d1 !important; }
.gx-badge-neutral { color: #606a62 !important; background: #f0efe9 !important; border: 1px solid #e1e0d8 !important; }
.gx-btn, .gx-button { border-radius: 9px !important; transition: transform .18s ease, box-shadow .18s ease, background .18s ease !important; }
.gx-btn:hover, .gx-button:hover { transform: translateY(-1px); }
.gx-button-primary, .gx-btn-primary { background: #206b52 !important; box-shadow: 0 4px 12px rgba(32,107,82,.15) !important; }
.gx-button-primary:hover, .gx-btn-primary:hover { background: #174d3b !important; box-shadow: 0 7px 18px rgba(32,107,82,.23) !important; }
.gx-link { color: #206b52 !important; text-decoration-color: rgba(32,107,82,.25); text-underline-offset: 3px; transition: color .18s ease; }
.gx-link:hover { color: #174d3b !important; }
.gx-code-block { background: #1e2823 !important; color: #e6eee8 !important; border: 1px solid #303e35 !important; border-radius: 13px !important; box-shadow: 0 12px 30px rgba(25,34,30,.1) !important; font-size: .86rem !important; }
.gx-callout { border-left: 3px solid #4b9674 !important; border-radius: 8px 12px 12px 8px !important; background: #edf4ed !important; }
.gx-accordion { border-color: #e5e4dc !important; border-radius: 12px !important; background: rgba(255,255,255,.65) !important; }
.gx-accordion-item { border-color: #e5e4dc !important; }
.gx-accordion-header { background: #fff !important; transition: background .18s ease, color .18s ease; }
.gx-accordion-header:hover { background: #f6f8f4 !important; color: #206b52 !important; }
.gx-accordion-content { background: #fff !important; border-color: #e5e4dc !important; }
.gx-input, .gx-select, .gx-textarea { border-radius: 9px !important; border-color: #d9dcd4 !important; background: #fff !important; }
.gx-input:focus, .gx-select:focus, .gx-textarea:focus { border-color: #579477 !important; box-shadow: 0 0 0 3px rgba(32,107,82,.12) !important; outline: none !important; }
.gx-tabs-header { border-color: #e5e4dc !important; }
.gx-tab-btn { transition: color .18s ease, border-color .18s ease, background .18s ease; }
.gx-tab-btn:hover { color: #206b52 !important; }
:focus-visible { outline: 3px solid rgba(32,107,82,.55) !important; outline-offset: 3px; }
::selection { background: #cfe3d4; color: #19221e; }
@media (max-width: 960px) {
  #docs-shell { padding: 0 22px !important; }
  #docs-layout { grid-template-columns: 1fr !important; gap: 20px !important; }
  #docs-sidebar { position: relative; top: auto; max-height: none; padding-bottom: 0; }
  #docs-sidebar > .gx-card { display: none; }
}
@media (max-width: 640px) {
  #docs-shell { padding: 0 16px !important; }
  #docs-header { position: relative; margin-bottom: 20px; }
  #docs-header > .gx-row { align-items: flex-start !important; flex-direction: column; gap: 10px !important; }
  #docs-header > .gx-row:last-child { flex-direction: row; flex-wrap: wrap; }
  #docs-content > .gx-column > .gx-heading:first-child { font-size: 2.15rem !important; }
  .gx-card { padding: 17px !important; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; }
}
"""

# =========================================================================
# APPLICATION INITIALIZATION & CONFIGURATION
# =========================================================================

app = ui.App(
    title="RADUI Documentation",
    theme=ui.Theme(
        name="radui-docs",
        mode="light",
        direction="ltr",
        primary="#206b52",
        primary_hover="#174d3b",
        bg="#f5f4ef",
        surface="#ffffff",
        surface_alt="#f0efe9",
        text="#19221e",
        text_muted="#69736c",
        border="#e5e4dc",
        border_strong="#d4d5ca",
        custom_css=CUSTOM_CSS,
    ),
)

# =========================================================================
# REACTIVE STATE DEFINITIONS (Session Scoped)
# =========================================================================

s_active_comp = ui.state("docs.active_comp", default="button", scope="session")
# Interactive Counter Demonstration State
s_counter = ui.state("demo.counter", default=42, scope="session")

# Interactive Property Inspector State for Component Explorer
s_prop_label = ui.state("prop.label", default="Launch Cluster", scope="session")
s_prop_variant = ui.state("prop.variant", default="primary", scope="session")
s_prop_disabled = ui.state("prop.disabled", default=False, scope="session")

# Reactive Calculator State (Computed Signals Demo)
s_price = ui.state("calc.price", default=100.0, scope="session")
s_tax = ui.state("calc.tax", default=0.20, scope="session")

# Live Background Job Simulation State
s_job_status = ui.state("job.status", default="IDLE", scope="session")
s_job_progress = ui.state("job.progress", default=0.0, scope="session")

# =========================================================================
# COMPUTED REACTIVE SIGNALS
# =========================================================================

@ui.computed
def s_calc_total() -> float:
    """Dynamically calculates total with tax using reactive dependency tracking."""
    return round(s_price.value * (1.0 + s_tax.value), 2)


# =========================================================================
# PERSISTENT DOCUMENTATION SHELL LAYOUT (@app.layout("/"))
# =========================================================================

def _render_sidebar() -> ui.Component:
    """A compact, task-oriented guide navigation built from native disclosure components."""
    return ui.column(
        ui.accordion(
            ui.accordion_item(
                "Start here",
                ui.column(
                    ui.link("Overview", "index.html"),
                    ui.link("Install & quickstart", "getting-started.html"),
                    ui.link("Components", "components.html"),
                    gap=4,
                ),
                open=True,
            ),
            ui.accordion_item(
                "Core concepts",
                ui.column(
                    ui.link("State & reactivity", "state.html"),
                    ui.link("Architecture", "architecture.html"),
                    ui.link("Events & streaming", "transport.html"),
                    ui.link("Background jobs", "jobs.html"),
                    gap=4,
                ),
                open=True,
            ),
            ui.accordion_item(
                "Advanced guides",
                ui.column(
                    ui.link("AI & approvals", "ai.html"),
                    ui.link("CLI reference", "cli.html"),
                    ui.link("Architecture decisions", "adrs.html"),
                    gap=4,
                ),
                open=False,
            ),
        ),
        ui.card(
            ui.badge("Open source | Apache 2.0", variant="neutral"),
            ui.text("A reactive UI toolkit for Python developers.", variant="muted"),
        ),
        id="docs-sidebar",
        gap=10,
    )


def _render_header() -> ui.Component:
    """A quiet, responsive global navigation bar."""
    return ui.row(
        ui.row(
            ui.heading("radui", level=3),
            ui.badge("docs", variant="primary"),
            gap=10,
            align="center",
        ),
        ui.row(
            ui.link("Quickstart", "getting-started.html"),
            ui.link("Components", "components.html"),
            ui.link("GitHub >", "https://github.com/flux-py/radui", external=True),
            gap=10,
            align="center",
        ),
        id="docs-header",
        justify="between",
        align="center",
    )


@app.layout("/")
def docs_layout(outlet: ui.Component) -> ui.Component:
    """Persistent, responsive documentation frame."""
    return ui.container(
        _render_header(),
        ui.grid(
            _render_sidebar(),
            ui.column(outlet, id="docs-content", gap=0),
            columns={"sm": 1, "md": 1, "lg": 2},
            gap=32,
            id="docs-layout",
        ),
        ui.divider(),
        ui.row(
            ui.text("RADUI ? Python-first reactive UI", variant="caption"),
            ui.row(
                ui.link("GitHub", "https://github.com/flux-py/radui", external=True),
                ui.link("Decisions", "adrs.html"),
                gap=14,
            ),
            justify="between",
            align="center",
        ),
        max_width="1320px",
        centered=True,
        id="docs-shell",
    )


# =========================================================================
# PAGE 1: HOME & HERO SHOWCASE ("/")
# =========================================================================

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


# =========================================================================
# PAGE 2: GETTING STARTED ("/getting-started")
# =========================================================================

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


# =========================================================================
# PAGE 3: SYSTEM ARCHITECTURE ("/architecture")
# =========================================================================

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


# =========================================================================
# PAGE 4: INTERACTIVE COMPONENT EXPLORER ("/components")
# =========================================================================

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

    # Generated Python AST code snippet
    gen_code = f"import radui as ui\n\n# Declarative component usage\nwidget = ui.{meta['name']}("
    if meta["params"]:
        gen_code += f'\n    label="{s_prop_label.value}",\n    variant="{s_prop_variant.value}",\n    disabled={s_prop_disabled.value},\n'
    gen_code += ")"

    return ui.column(
        ui.heading("Interactive Component Explorer (68 Built-in Primitives)", level=1),
        ui.text("Select any component from the catalog, manipulate its properties in real time, and inspect the rendered result:"),
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
                ui.text(f"Selected: ui.{meta['name']}", variant="code"),
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
            title="Live Rendered Component Preview",
            subtitle="Mutations update through server-side surgical SSE sub-DOM morphing",
            hover=ui.motion.hover(scale=1.015, translate_y=-2.0),
        ),
        ui.spacer(size=12),
        # Synchronized Python Implementation Code
        ui.heading("Synchronized Python Implementation", level=3),
        ui.code_block(gen_code, language="python", copyable=True),
        gap=16,
        stagger_children=0.05,
    )


# =========================================================================
# PAGE 5: REACTIVE STATE & COMPUTED SIGNALS ("/state")
# =========================================================================

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
                ui.metric_card("Base Price", s_price, hover=ui.motion.hover(scale=1.03, translate_y=-4.0)),
                ui.metric_card("Tax Rate", s_tax, hover=ui.motion.hover(scale=1.03, translate_y=-4.0)),
                ui.metric_card("Computed Total", s_calc_total, delta="Automated DAG derivation", hover=ui.motion.hover(scale=1.03, translate_y=-4.0)),
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


# =========================================================================
# PAGE 6: REALTIME & SSE EVENT BROKER ("/transport")
# =========================================================================

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


# =========================================================================
# PAGE 7: BACKGROUND JOBS ("/jobs")
# =========================================================================

@app.page("/jobs")
def jobs_page():
    return ui.column(
        ui.heading("Distributed Background Jobs with Monotonic Fencing", level=1),
        ui.text("Execute heavy background tasks across worker pools with lease renewal, heartbeat fencing, and live browser telemetry."),
        ui.card(
            ui.heading("Background Job Execution Sandbox", level=3),
            ui.row(
                ui.metric_card("Worker State", s_job_status, hover=ui.motion.hover(scale=1.03, translate_y=-4.0)),
                ui.metric_card("Execution Progress", f"{int(s_job_progress.value * 100)}%", hover=ui.motion.hover(scale=1.03, translate_y=-4.0)),
                gap=16,
            ),
            ui.progress_bar(value=s_job_progress.value * 100.0, variant="primary"),
            ui.row(
                ui.button("Start 10-Second Worker Job", command="job.start", variant="primary"),
                ui.button("Cancel Active Job", command="job.cancel", variant="danger"),
                gap=12,
            ),
            title="Durable Job Runner Control Plane",
            hover=ui.motion.hover(scale=1.015, translate_y=-2.0),
        ),
        gap=16,
        stagger_children=0.05,
    )


# =========================================================================
# PAGE 8: AI AGENT & MCP PROTOCOLS ("/ai")
# =========================================================================

@app.page("/ai")
def ai_page():
    return ui.column(
        ui.heading("Autonomous AI Agents & Model Context Protocol (MCP)", level=1),
        ui.text("RADUI integrates native streaming generative UI (A2UI), Model Context Protocol tool descriptors, and human-in-the-loop approval workflows."),
        ui.grid(
            ui.card(
                ui.chat_view(
                    ui.chat_message("Hello! I am your RADUI autonomous agent. I can query databases and trigger cluster operations.", role="assistant"),
                    ui.chat_message("Can you run the daily revenue aggregation query?", role="user"),
                    ui.chat_message("I have prepared the tool execution. Please authorize the action below.", role="assistant"),
                    title="Agent Conversation Stream",
                ),
                title="Agent Conversation Stream",
                hover=ui.motion.hover(scale=1.015, translate_y=-2.0),
            ),
            ui.card(
                ui.heading("Human-in-the-Loop Action Card", level=4),
                ui.text("The agent has requested permission to execute a privileged database operation:"),
                ui.action_card(
                    title="Execute Revenue Aggregation Query?",
                    description="Target: 'SELECT SUM(amount) FROM daily_orders WHERE date = CURRENT_DATE;'",
                    approve_command="agent.approve_demo",
                    reject_command="agent.reject_demo",
                ),
                title="Privileged Action Authorization",
                hover=ui.motion.hover(scale=1.015, translate_y=-2.0),
            ),
            columns=2,
            gap=16,
        ),
        gap=16,
        stagger_children=0.05,
    )


# =========================================================================
# PAGE 9: DEVELOPER CLI REFERENCE ("/cli")
# =========================================================================

@app.page("/cli")
def cli_page():
    return ui.column(
        ui.heading("Developer CLI Reference (All 45 Subcommands)", level=1),
        ui.text("Explore all 45 registered command-line subcommands for project scaffolding, local development, auditing, inspection, and production deployment:"),
        ui.table(
            headers=["Command", "Domain", "Syntax", "Description"],
            rows=[[c["cmd"], c["domain"], f"`{c['syntax']}`", c["description"]] for c in CLI_COMMANDS],
        ),
        gap=16,
        stagger_children=0.05,
    )


# =========================================================================
# PAGE 10: 12 ARCHITECTURE DECISION RECORDS ("/adrs")
# =========================================================================

@app.page("/adrs")
def adrs_page():
    return ui.column(
        ui.heading("12 Architectural Decision Records (ADRs)", level=1),
        ui.text("RADUI development adheres strictly to formal, immutable architectural specifications:"),
        ui.table(
            headers=["Record", "Title", "Domain Scope", "Invariant Enforced"],
            rows=[[a["id"], a["title"], a["scope"], a["invariant"]] for a in ADRS],
        ),
        gap=16,
        stagger_children=0.05,
    )


# =========================================================================
# COMMAND HANDLERS (Business Logic & Reactive State Mutations)
# =========================================================================

@app.command("comp.apply_props")
def on_apply_props(ctx: ui.CommandContext):
    ui.notify("Applied inspector parameters to live component!", variant="success")


@app.command("calc.update")
def on_calc_update(ctx: ui.CommandContext):
    ui.notify("Derived computed state updated!", variant="info")


@app.command("demo.inc")
def on_demo_inc(ctx: ui.CommandContext):
    current = ctx.read(s_counter)
    ctx.write(s_counter, current + 1)
    ui.notify(f"Counter incremented to {current + 1}", variant="success")


@app.command("demo.dec")
def on_demo_dec(ctx: ui.CommandContext):
    current = ctx.read(s_counter)
    ctx.write(s_counter, current - 1)


@app.command("comp.select_button")
def on_select_button(ctx: ui.CommandContext):
    ctx.write(s_active_comp, "button")
    ctx.write(s_prop_label, "Execute Command")


@app.command("comp.select_badge")
def on_select_badge(ctx: ui.CommandContext):
    ctx.write(s_active_comp, "badge")
    ctx.write(s_prop_label, "v1.0.0 Verified")


@app.command("comp.select_callout")
def on_select_callout(ctx: ui.CommandContext):
    ctx.write(s_active_comp, "callout")
    ctx.write(s_prop_label, "Production AST pipeline verified.")


@app.command("comp.select_metric")
def on_select_metric(ctx: ui.CommandContext):
    ctx.write(s_active_comp, "metric_card")
    ctx.write(s_prop_label, "0.039 ms")


@app.command("comp.select_progress")
def on_select_progress(ctx: ui.CommandContext):
    ctx.write(s_active_comp, "progress_bar")


@app.command("comp.test_trigger")
def on_comp_test(ctx: ui.CommandContext):
    ui.notify("Interactive component triggered successfully!", variant="info")


@app.command("job.start")
def on_job_start(ctx: ui.CommandContext):
    ctx.write(s_job_status, "RUNNING")
    ctx.write(s_job_progress, 0.45)
    ui.notify("Background worker lease acquired!", variant="info")


@app.command("job.cancel")
def on_job_cancel(ctx: ui.CommandContext):
    ctx.write(s_job_status, "CANCELLED")
    ctx.write(s_job_progress, 0.0)
    ui.notify("Background job cancelled.", variant="warning")


@app.command("agent.approve_demo")
def on_agent_approve(ctx: ui.CommandContext):
    ui.notify("Agent query authorized! Executing aggregation...", variant="success")


@app.command("agent.reject_demo")
def on_agent_reject(ctx: ui.CommandContext):
    ui.notify("Agent action declined by operator.", variant="danger")




# =========================================================================
# APPLICATION ENTRYPOINT
# =========================================================================

if __name__ == "__main__":
    app.run(port=3000)
