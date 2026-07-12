"""RADUI 0.4 background-work example.

Run from the repository root:
    python examples/research_workbench/app.py
"""

from __future__ import annotations

import asyncio
import os

import radui as gx


app = gx.App(
    "RADUI Research Workbench",
    app_id="RADUI-research-workbench",
    # Use a stable secret from your deployment's secret manager in production.
    session_secret=os.environ.get(
        "RADUI_SESSION_SECRET",
        "local-development-secret-do-not-use-in-production-12345",
    ),
)

research_topic = gx.state(
    "research.topic",
    "Python frontend frameworks",
    scope="session",
)


@app.job("research.analyze")
async def analyze_research(ctx: gx.JobContext, topic: str) -> dict[str, str]:
    """Pretend to perform a multi-step research operation."""
    await ctx.progress(8, "Preparing research plan")
    await asyncio.sleep(0.8)

    await ctx.progress(35, "Collecting sources")
    await asyncio.sleep(1.0)

    await ctx.progress(68, "Comparing findings")
    await asyncio.sleep(1.0)

    await ctx.progress(92, "Writing summary")
    await asyncio.sleep(0.6)

    return {
        "topic": topic,
        "summary": f"Research workflow completed for: {topic}",
    }


@app.command("research.submit")
async def submit_research(ctx: gx.CommandContext) -> None:
    # The command action ID is also the job idempotency key. A browser retry
    # cannot accidentally create the same job twice within this session.
    await analyze_research.submit(
        ctx,
        ctx.form_data["research.topic"],
        idempotency_key=ctx.action_id,
    )


@app.page("/", title="Research Workbench")
def home():
    return gx.column(
        gx.heading("Research Workbench", level=1),
        gx.text(
            "This example demonstrates a long-running job whose status is "
            "independent of the browser request."
        ),
        gx.form(
            "research.submit",
            gx.input(
                "Research topic",
                bind=research_topic,
                input_type="search",
                placeholder="Enter a research topic",
            ),
            gx.button("Start research"),
        ),
        gx.job_panel(analyze_research, label="Research execution"),
        gap=18,
    )


if __name__ == "__main__":
    app.run()
