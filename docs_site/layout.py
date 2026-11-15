"""Shared documentation navigation and page frame."""

from __future__ import annotations

import radui as ui
from docs_site.core import app

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
    """A quiet, responsive global navigation bar with transparent logo and theme toggle."""
    return ui.row(
        ui.row(
            ui.heading("radui", level=3, id="docs-brand-logo"),
            ui.badge("docs", variant="primary"),
            gap=10,
            align="center",
            id="docs-logo-link",
        ),
        ui.row(
            ui.link("Quickstart", "getting-started.html"),
            ui.link("Components", "components.html"),
            ui.link("Architecture", "architecture.html"),
            ui.theme_toggle("Theme", id="theme-toggle"),
            ui.link("GitHub >", "https://github.com/flux-py/radui", external=True),
            gap=12,
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
