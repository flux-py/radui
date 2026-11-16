"""Command handlers for interactive documentation examples."""

from __future__ import annotations

import radui as ui
from docs_site.core import app, s_counter, s_active_comp, s_prop_label, s_job_status, s_job_progress
from docs_site.data import COMPONENTS

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

# Register dynamic component selector commands for all 70 primitives
for _comp in COMPONENTS:
    _name = _comp["name"]
    _cmd_key = f"comp.select_{_name}"
    if _cmd_key not in app._commands:
        def _factory(name: str):
            def _select_handler(ctx: ui.CommandContext):
                ctx.write(s_active_comp, name)
                ctx.write(s_prop_label, f"Demo {name.replace('_', ' ').title()}")
            return _select_handler
        app.command(_cmd_key)(_factory(_name))

