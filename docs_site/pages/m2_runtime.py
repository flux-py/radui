"""Documentation pages for M1.8-M2.3 next-generation runtime capabilities."""

from __future__ import annotations

import radui as ui
from radui.interactions import act, on
from docs_site.core import app


@app.page("/interactions")
def interactions_page():
    return ui.column(
        ui.badge("M1.8 / M1.8.1 Client Engine", variant="primary"),
        ui.heading("Declarative Client-Side Interactions", level=1),
        ui.text(
            "Execute sub-millisecond local UI updates in the browser with zero HTTP round trips, zero eval/Function, "
            "WeakMap-backed state, and O(1) delegated listeners across all 73 component builders.",
            variant="lead",
        ),
        ui.card(
            ui.heading("Live Local Interaction Demo (Zero Server Round Trips)", level=3),
            ui.row(
                ui.text("0", id="docs-ix-count", bind_local={"text": "count"}),
                ui.button(
                    "+1 Local",
                    id="docs-ix-inc",
                    variant="primary",
                    interactions=(on("click", act.increment("count", by=1), act.announce("Incremented")),),
                ),
                ui.button(
                    "Toggle Details",
                    id="docs-ix-tog",
                    variant="secondary",
                    interactions=(on("click", act.toggle("open")),),
                ),
                gap=12,
                align="center",
            ),
            ui.text("Panel revealed locally via WeakMap state!", id="docs-ix-panel", bind_local={"visible": "open"}),
            id="docs-ix-scope",
            local_state={"count": 0, "open": False},
            title="Interactive Preview",
        ),
        ui.card(
            ui.heading("Python API", level=3),
            ui.code_block(
                'from radui.interactions import act, on\n\n'
                'ui.column(\n'
                '    ui.text("0", id="cnt", bind_local={"text": "count"}),\n'
                '    ui.button("+", interactions=(on("click", act.increment("count", by=1)),)),\n'
                '    local_state={"count": 0},\n'
                ')',
                language="python",
            ),
            title="local_state, interactions, bind_local",
        ),
        ui.card(
            ui.heading("Supported Surface & Measured Budget", level=3),
            ui.data_grid(
                headers=["Capability", "Count / Scope", "Verification"],
                rows=[
                    ["Delegated Events", "16 events", "click, dblclick, mouse/pointerenter/leave, focus, blur, input, change, keydown/up, submit, drag/drop"],
                    ["Allowlisted Actions", "19 actions", "toggle, set, increment, decrement, show, hide, open, close, enable, disable, *_class, set_text, set_attr, remove_attr, announce, focus, dispatch_command"],
                    ["bind_local Properties", "7 properties", "text, visible, hidden, disabled, open, pressed (aria-pressed), expanded (aria-expanded)"],
                    ["Chrome Latency", "p50=0.200 ms", "p95=0.400 ms over 500 clicks; 100 mount/unmount cycles verified"],
                ],
                searchable=False,
                sortable=False,
                page_size=10,
            ),
            title="Hardening Matrix (M1.8.1)",
        ),
        gap=16,
    )


@app.page("/navigation")
def navigation_page():
    return ui.column(
        ui.badge("M1.9 / M1.9.1 / M1.9.2", variant="primary"),
        ui.heading("Native SPA Navigation Engine", level=1),
        ui.text(
            "Zero-reload client navigation backed by Python server routing (GET /_gx/navigate), nested @app.layout, "
            "AbortController concurrency control, auth_key cache invalidation, and automatic server fallback.",
            variant="lead",
        ),
        ui.card(
            ui.heading("Python Routing, Guards & Link Prefetching", level=3),
            ui.code_block(
                '@app.page(\n'
                '    "/users/{user_id}",\n'
                '    title="User Profile",\n'
                '    loading=lambda: ui.text("Loading profile..."),\n'
                '    error_boundary=lambda exc: ui.text(f"Error: {exc}"),\n'
                '    guard=lambda req: True,\n'
                ')\n'
                'def user_profile(user_id: str):\n'
                '    return ui.heading(f"User {user_id}")\n\n'
                'ui.link("Profile", "/users/42", prefetch="viewport", spa=True)',
                language="python",
            ),
            title="Server & Link Controls",
        ),
        ui.card(
            ui.heading("Hardening & Benchmarks", level=3),
            ui.data_grid(
                headers=["Dimension", "Behavior / Measurement"],
                rows=[
                    ["Concurrency", "Monotonic _navSeq + AbortController cancels obsolete fetches; 4-hop redirect loop guard"],
                    ["Prefetch Cache", "16-entry / 15s TTL cache; protected routes marked cacheable=false; cleared on auth_key change or 401/403"],
                    ["Memory Stability", "1,050 consecutive navigations in Chrome: listeners 62->59, nodes=74, heap 0.79MB->0.71MB"],
                    ["Latency", "Uncached p50=6.300 ms / p95=10.700 ms; Prefetched p50=0.800 ms / p95=1.200 ms"],
                ],
                searchable=False,
                sortable=False,
                page_size=10,
            ),
            title="M1.9.1 & M1.9.2 Verification",
        ),
        gap=16,
    )


@app.page("/resumability")
def resumability_page():
    return ui.column(
        ui.badge("M2.0 Resumable Runtime", variant="primary"),
        ui.heading("Resumable Application Execution", level=1),
        ui.text(
            "Opt-in resumable boundaries (resumable=True) serialize versioned state and typed execution descriptors "
            "into #gx-resumable-state so the browser performs zero eager hydration on load and activates boundaries lazily on interaction.",
            variant="lead",
        ),
        ui.card(
            ui.heading("Usage Example", level=3),
            ui.code_block(
                'ui.column(\n'
                '    ui.text("10", id="b1-val", bind_local={"text": "n"}),\n'
                '    ui.button("Inc", interactions=(on("click", act.increment("n", by=2)),)),\n'
                '    id="boundary-1",\n'
                '    local_state={"n": 10},\n'
                '    resumable=True,\n'
                ')',
                language="python",
            ),
            title="Lazy Boundary Restoration",
        ),
        ui.card(
            ui.heading("Security & Restoration Protocol", level=3),
            ui.text(
                "Resumable snapshots enforce schema_version='1.0' (with StateMigrationRegistry for upgrades), reject secret keys "
                "(password, token, api_key, secret) and prototype-pollution keys, and validate CSRF + auth_scope at POST /_gx/resume."
            ),
            title="Server-Validated Restoration",
        ),
        gap=16,
    )


@app.page("/compiler")
def compiler_page():
    return ui.column(
        ui.badge("M2.1 Compiler", variant="primary"),
        ui.heading("Compiler-Assisted Reactive Optimization", level=1),
        ui.text(
            "Python-native AST & Component IR compiler (radui.compiler) that indexes static state dependencies, detects circular "
            "dependencies, and caches pure-static HTML fragments while preserving runtime DependencyTracker for dynamic branches.",
            variant="lead",
        ),
        ui.card(
            ui.heading("CLI & Programmatic Compilation", level=3),
            ui.code_block(
                "# Compile app into content-addressed .radui-cache/compiled_manifest.json\n"
                "radui compile app.py --out-dir .radui-cache\n\n"
                "# Run compiler optimization pass during static build\n"
                "radui build app.py --output ./dist --optimize",
                language="bash",
            ),
            title="Zero-Transpilation Python Optimization",
        ),
        gap=16,
    )


@app.page("/web-components")
def web_components_page():
    return ui.column(
        ui.badge("M2.2 Web Components", variant="primary"),
        ui.heading("Native Web Components & Shadow DOM Interoperability", level=1),
        ui.text(
            "Embed standards-based Custom Elements with open or closed Shadow DOM, <slot> projection, RadUI CSS token inheritance, "
            "and a CSRF-protected custom DOM event bridge to Python @app.command handlers.",
            variant="lead",
        ),
        ui.card(
            ui.heading("Register & Host a Custom Element", level=3),
            ui.code_block(
                '@app.web_component(\n'
                '    "acme-rating",\n'
                '    shadow_mode="open",\n'
                '    observed_attributes=("label",),\n'
                '    events=("rating-change",),\n'
                '    styles=":host { color: var(--gx-primary); }",\n'
                '    template_html=\'<span data-gx-prop="label">Init</span><slot></slot>\',\n'
                ')\n'
                'def acme_rating(): pass\n\n'
                'ui.custom_element("acme-rating", ui.text("Slotted"), props={"label": "Stars"}, event_commands={"rating-change": "rating.save"})',
                language="python",
            ),
            title="@app.web_component & ui.custom_element",
        ),
        gap=16,
    )


@app.page("/streaming-ssr")
def streaming_ssr_page():
    return ui.column(
        ui.badge("M2.3 Streaming SSR", variant="primary"),
        ui.heading("Progressive & Streaming Server-Side Rendering", level=1),
        ui.text(
            "Flush the page shell immediately while async ui.suspense(...) boundaries resolve concurrently out-of-order, "
            "streaming nonce-verified <template> replacements with per-boundary timeouts, error fallbacks, and disconnect cancellation.",
            variant="lead",
        ),
        ui.card(
            ui.heading("Streaming Route Example", level=3),
            ui.code_block(
                'async def load_metrics():\n'
                '    await asyncio.sleep(0.05)\n'
                '    return ui.metric_card("Throughput", "1,420 rps")\n\n'
                '@app.page("/dashboard", stream=True, ssg=False)\n'
                'def dashboard():\n'
                '    return ui.column(\n'
                '        ui.heading("Live Dashboard"),\n'
                '        ui.suspense(load_metrics, fallback=ui.skeleton(height="80px"), timeout_s=3.0),\n'
                '    )',
                language="python",
            ),
            title="ui.suspense + @app.page(..., stream=True)",
        ),
        gap=16,
    )
