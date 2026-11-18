"""Dedicated CLI and command documentation, covering all 45 CLI commands,
step-by-step developer workflows, arguments, flags, and expected terminal outputs.
"""

from __future__ import annotations

import radui as ui
from docs_site.core import app
from docs_site.data import CLI_COMMANDS

@app.page("/cli")
def cli_page():
    return ui.column(
        ui.badge("Developer Toolchain", variant="primary"),
        ui.heading("RADUI CLI Command Directory (All 46 Commands)", level=1),
        ui.text(
            "The RADUI CLI provides 46 production-grade subcommands for project initialization, live development, "
            "AST compilation, static site builds, bundle packaging, security auditing, and cluster telemetry.",
            variant="lead",
        ),
        ui.spacer(size=14),

        # Quick Navigation Pills
        ui.row(
            ui.link("Scaffolding Workflows >", "cli-workflows.html"),
            ui.link("Static Export Guide >", "getting-started.html"),
            ui.link("Architecture Decisions >", "adrs.html"),
            gap=16,
        ),
        ui.spacer(size=16),

        # Searchable CLI Command Table
        ui.card(
            ui.heading("Complete Command Reference", level=3),
            ui.text("Search across all 46 registered subcommands by keyword, syntax, or architectural domain:"),
            ui.data_grid(
                headers=["Command", "Domain", "Syntax & Usage", "Description"],
                rows=[[c["cmd"], c["domain"], f"`{c['syntax']}`", c["description"]] for c in CLI_COMMANDS],
                searchable=True,
                sortable=True,
                page_size=10,
                empty_message="No CLI commands match your search query.",
            ),
            title="Registered Subcommands",
            hover=ui.motion.hover(scale=1.01, translate_y=-2.0),
        ),
        gap=16,
    )


@app.page("/cli-workflows")
def cli_workflows_page():
    return ui.column(
        ui.badge("Hands-On Workflows", variant="success"),
        ui.heading("Practical Developer CLI Workflows", level=1),
        ui.text(
            "Step-by-step practical guides, flags, and expected terminal outputs for common enterprise engineering tasks.",
            variant="lead",
        ),
        ui.spacer(size=16),

        # Workflow 1: Scaffolding & Setup
        ui.card(
            ui.heading("Workflow 1: Project Scaffolding & Module Installation", level=3),
            ui.text("Scaffold a new enterprise dashboard from templates and install optional extensions:"),
            ui.code_block(
                "# 1. Create a new RADUI project\n"
                "radui new analytics-portal --template dashboard\n\n"
                "# 2. Inspect generated structure\n"
                "cd analytics-portal\n"
                "radui info\n\n"
                "# 3. Add AI Model Context Protocol integration\n"
                "radui add mcp",
                language="bash",
                copyable=True,
            ),
            ui.text("Expected Terminal Output:", variant="caption"),
            ui.code_block(
                "[OK] Created new RADUI app in 'analytics-portal/' using 'dashboard' template.\n"
                "To run it:\n"
                "  cd analytics-portal\n"
                "  radui dev app.py --port 3000\n"
                "Adding RADUI module/integration: 'mcp'...\n"
                "Run: pip install mcp",
                language="text",
            ),
        ),
        ui.spacer(size=16),

        # Workflow 2: Development & Hot Reloading
        ui.card(
            ui.heading("Workflow 2: Local Development & Live Reloading", level=3),
            ui.text("Run the ASGI 3.0 development server with file watching and automatic browser launch:"),
            ui.code_block(
                "# Start development server on port 3000 with browser launch\n"
                "radui dev app.py --port 3000 --open\n\n"
                "# Or run in production multi-worker mode\n"
                "radui serve app.py --port 8080 --workers 4",
                language="bash",
                copyable=True,
            ),
            ui.text("Expected Terminal Output:", variant="caption"),
            ui.code_block(
                "INFO:     Started server process [8421]\n"
                "INFO:     Waiting for application startup.\n"
                "INFO:     RADUI ASGI Application startup complete. [AST Latency: 0.039ms]\n"
                "INFO:     Uvicorn running on http://127.0.0.1:3000 (Press CTRL+C to quit)\n"
                "INFO:     Opening default browser at http://localhost:3000...",
                language="text",
            ),
        ),
        ui.spacer(size=16),

        # Workflow 3: Auditing, Linting & Diagnostics
        ui.card(
            ui.heading("Workflow 3: Security Auditing & Diagnostics", level=3),
            ui.text("Verify tenant fencing, monotonic lease compliance, and component AST integrity:"),
            ui.code_block(
                "# Run full diagnostic health check on environment\n"
                "radui doctor\n\n"
                "# Audit state tenant fencing and ADR compliance\n"
                "radui audit\n\n"
                "# Validate component tree integrity\n"
                "radui validate app.py",
                language="bash",
                copyable=True,
            ),
            ui.text("Expected Terminal Output:", variant="caption"),
            ui.code_block(
                "[*] Checking Python environment... Python 3.12.3 [OK]\n"
                "[*] Checking ASGI backend... uvicorn 0.30.1 [OK]\n"
                "[*] Verifying 72 built-in component AST schemas... [OK]\n"
                "[*] Auditing tenant fencing rules (ADR-002)... 0 leaks detected [PASS]\n"
                "[*] Monotonic lease check (ADR-001)... [PASS]\n"
                "All 7 diagnostic gates verified successfully.",
                language="text",
            ),
        ),
        ui.spacer(size=16),

        # Workflow 4: Compilation & Static Export
        ui.card(
            ui.heading("Workflow 4: Static Export & Production Packaging", level=3),
            ui.text("Export the entire application to standalone static HTML for GitHub Pages or CDN hosting:"),
            ui.code_block(
                "# Export all routes to static HTML in ./dist_docs\n"
                "radui export app.py --static --output ./dist_docs\n\n"
                "# Package standalone wheel distribution bundle\n"
                "radui bundle",
                language="bash",
                copyable=True,
            ),
            ui.text("Expected Terminal Output:", variant="caption"),
            ui.code_block(
                "[OK] Exported static page '/' to: dist_docs/index.html\n"
                "[OK] Exported static page '/getting-started' to: dist_docs/getting-started.html\n"
                "[OK] Exported static page '/components' to: dist_docs/components.html\n"
                "[OK] Copied assets from 'docs_site/assets' to: dist_docs/assets\n"
                "Successfully exported 17 pages with zero build pipeline.",
                language="text",
            ),
        ),
        gap=16,
    )
