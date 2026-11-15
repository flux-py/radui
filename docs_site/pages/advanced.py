"""Advanced workflow and reference pages."""

from __future__ import annotations

import radui as ui
from docs_site.core import app, s_job_status, s_job_progress
from docs_site.data import CLI_COMMANDS, ADRS

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
