"""Shared documentation navigation and page frame."""

from __future__ import annotations

import radui as ui
from docs_site.core import app

def _render_sidebar() -> ui.Component:
    """A comprehensive, categorized guide navigation built from native disclosure components."""
    return ui.column(
        ui.accordion(
            ui.accordion_item(
                "Start here",
                ui.column(
                    ui.link("Overview", "index.html"),
                    ui.link("Why RADUI?", "index.html#why-radui"),
                    ui.link("Install & quickstart", "getting-started.html"),
                    ui.link("Python API Reference", "api-reference.html"),
                    ui.link("System Architecture", "architecture.html"),
                    gap=4,
                ),
                open=True,
            ),
            ui.accordion_item(
                "Component Library (72)",
                ui.column(
                    ui.link("Component Explorer", "components.html"),
                    ui.link("Layout & Grids", "components-layout.html"),
                    ui.link("Forms & Inputs", "components-forms.html"),
                    ui.link("Data Displays & Grids", "components-data.html"),
                    ui.link("Feedback & Overlays", "components-feedback.html"),
                    ui.link("AI & Streaming Media", "components-ai.html"),
                    gap=4,
                ),
                open=True,
            ),
            ui.accordion_item(
                "CLI & Toolchain (46)",
                ui.column(
                    ui.link("CLI Reference (46)", "cli.html"),
                    ui.link("Developer Workflows", "cli-workflows.html"),
                    gap=4,
                ),
                open=True,
            ),
            ui.accordion_item(
                "Core concepts",
                ui.column(
                    ui.link("State & reactivity", "state.html"),
                    ui.link("Declarative Interactions", "interactions.html"),
                    ui.link("SPA Navigation", "navigation.html"),
                    ui.link("Resumable Runtime (M2.0)", "resumability.html"),
                    ui.link("Compiler & Optimizer (M2.1)", "compiler.html"),
                    ui.link("Web Components (M2.2)", "web-components.html"),
                    ui.link("Streaming SSR (M2.3)", "streaming-ssr.html"),
                    ui.link("Events & streaming", "transport.html"),
                    ui.link("Background jobs", "jobs.html"),
                    ui.link("AI & approvals", "ai.html"),
                    ui.link("Architecture decisions (18)", "adrs.html"),
                    gap=4,
                ),
                open=True,
            ),
            ui.accordion_item(
                "Integrations & Stacks",
                ui.column(
                    ui.link("Integration Overview", "integrations.html"),
                    ui.link("Backend Frameworks", "integrations.html#backends"),
                    ui.link("Frontend Frameworks", "integrations.html#frontends"),
                    ui.link("Databases & Storage", "integrations.html#databases"),
                    ui.link("Security & Deployment", "integrations.html#production"),
                    gap=4,
                ),
                open=True,
            ),
            ui.accordion_item(
                "Enterprise & Infrastructure",
                ui.column(
                    ui.link("Authentication & RBAC", "auth.html"),
                    ui.link("SWR Data Engine", "data-engine.html"),
                    ui.link("Headless Testing", "testing.html"),
                    gap=4,
                ),
                open=True,
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
    """A quiet, responsive global navigation bar with transparent logo and rightmost theme toggle."""
    return ui.row(
        ui.row(
            ui.heading("radui", level=3, id="docs-brand-logo"),
            ui.badge("docs", variant="primary"),
            gap=10,
            align="center",
            id="docs-logo-link",
        ),
        ui.row(
            ui.link("Why RADUI?", "index.html#why-radui"),
            ui.link("Quickstart", "getting-started.html"),
            ui.link("Components", "components.html"),
            ui.link("Integrations", "integrations.html"),
            ui.link("Architecture", "architecture.html"),
            ui.link("GitHub >", "https://github.com/flux-py/radui", external=True),
            gap=12,
            align="center",
        ),
        ui.theme_toggle("Theme", id="theme-toggle"),
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
            ui.text("RADUI - Python-first reactive UI", variant="caption"),
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
