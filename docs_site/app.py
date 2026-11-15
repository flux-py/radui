"""RadUI documentation app entry point.

Page content, theme, navigation, shared state, and handlers live in focused
modules and are registered here for the RadUI CLI and static exporter.
"""

from docs_site.core import (
    app,
    s_active_comp,
    s_counter,
    s_prop_label,
    s_prop_variant,
    s_prop_disabled,
    s_price,
    s_tax,
    s_calc_total,
    s_job_status,
    s_job_progress,
)
import docs_site.layout as _layout
import docs_site.pages as _pages
import docs_site.commands as _commands

__all__ = [
    "app",
    "s_active_comp",
    "s_counter",
    "s_prop_label",
    "s_prop_variant",
    "s_prop_disabled",
    "s_price",
    "s_tax",
    "s_calc_total",
    "s_job_status",
    "s_job_progress",
]

if __name__ == "__main__":
    app.run(port=3000)
