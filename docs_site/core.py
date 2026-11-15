"""Shared app configuration and reactive state for the documentation site."""

from __future__ import annotations

import radui as ui
from docs_site.theme import CUSTOM_CSS

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

s_active_comp = ui.state("docs.active_comp", default="button", scope="session")
s_counter = ui.state("demo.counter", default=42, scope="session")
s_prop_label = ui.state("prop.label", default="Launch Cluster", scope="session")
s_prop_variant = ui.state("prop.variant", default="primary", scope="session")
s_prop_disabled = ui.state("prop.disabled", default=False, scope="session")
s_price = ui.state("calc.price", default=100.0, scope="session")
s_tax = ui.state("calc.tax", default=0.20, scope="session")
s_job_status = ui.state("job.status", default="IDLE", scope="session")
s_job_progress = ui.state("job.progress", default=0.0, scope="session")

@ui.computed
def s_calc_total() -> float:
    """Dynamically calculates total with tax using reactive dependency tracking."""
    return round(s_price.value * (1.0 + s_tax.value), 2)
