"""RADUI Audit — Experiment B: Intermediate Application.

Evaluates Developer Experience (Scenario B):
- Multi-page routing with persistent layouts (/dashboard, /analytics, /settings)
- Custom reusable composite component (MetricComparisonCard)
- External data integration with SWR caching (gx.query / gx.aquery)
- Persistent state management across session and user scopes
- Background asynchronous job with progress reporting (@app.job)
- Streaming simulated AI/telemetry updates
- Resilient error handling with ErrorBoundary
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from typing import Any
import radui as gx

app = gx.App(
    "Intermediate Production App",
    app_id="exp-intermediate-app",
    user_id_resolver=lambda req: req.headers.get("x-user-id", "user-analyst-1"),
    debug=True,
)

# -----------------------------------------------------------------------------
# Scoped State Definitions
# -----------------------------------------------------------------------------
user_role = gx.state("user_role", "Data Analyst", scope="user")
active_environment = gx.state("active_env", "Production", scope="session")
selected_cluster = gx.state("selected_cluster", "us-east-cluster-01", scope="session")
auto_refresh = gx.state("auto_refresh", True, scope="session")
job_output = gx.state("last_job_output", "No recent batch runs.", scope="session")
stream_status = gx.state("stream_status", "Idle", scope="session")


# -----------------------------------------------------------------------------
# Mock External Service & Data Caching (SWR)
# -----------------------------------------------------------------------------
EXTERNAL_TELEMETRY_DB = {
    "us-east-cluster-01": {"qps": 48200, "error_rate": "0.012%", "p99": "42ms", "status": "Healthy"},
    "eu-west-cluster-02": {"qps": 31400, "error_rate": "0.045%", "p99": "68ms", "status": "Degraded"},
    "ap-south-cluster-03": {"qps": 22100, "error_rate": "0.008%", "p99": "51ms", "status": "Healthy"},
}


def fetch_cluster_metrics(cluster_name: str) -> dict[str, Any]:
    """Simulates external HTTP API call with SWR caching."""
    return EXTERNAL_TELEMETRY_DB.get(
        cluster_name,
        {"qps": 0, "error_rate": "N/A", "p99": "N/A", "status": "Unknown"},
    )


def get_cached_telemetry(cluster: str) -> dict[str, Any]:
    return gx.query(f"telemetry:{cluster}", lambda: fetch_cluster_metrics(cluster), stale_time=5.0)


# -----------------------------------------------------------------------------
# Custom Component: MetricComparisonCard
# Demonstrates component composition without modifying framework internals
# -----------------------------------------------------------------------------
def metric_comparison_card(title: str, current: str, target: str, delta: str, is_positive: bool = True) -> gx.Component:
    badge_variant = "success" if is_positive else "danger"
    return gx.card(
        gx.column(
            gx.row(
                gx.text(title, variant="muted"),
                gx.badge(delta, variant=badge_variant),
                justify="space-between",
                align="center",
            ),
            gx.heading(current, level=3),
            gx.text(f"Target: {target}", variant="caption"),
            gap=8,
        ),
        padding=16,
    )


# -----------------------------------------------------------------------------
# Background Jobs
# -----------------------------------------------------------------------------
@app.job("cluster.rebalance")
async def cluster_rebalance_job(ctx: gx.JobContext) -> dict[str, Any]:
    """Background cluster workload migration & rebalancing job."""
    await ctx.progress(10, "Validating cluster quorum and health...")
    await asyncio.sleep(0.05)
    await ctx.progress(50, "Migrating tenant partitions across nodes...")
    await asyncio.sleep(0.05)
    await ctx.progress(85, "Flushing buffer cache and revalidating locks...")
    await asyncio.sleep(0.05)
    await ctx.progress(100, "Rebalance complete.")

    summary = f"Rebalance completed successfully at {datetime.now(timezone.utc).isoformat()}"
    job_output.value = summary
    return {"status": "success", "cluster": selected_cluster.value, "timestamp": summary}


# -----------------------------------------------------------------------------
# Interactive Commands
# -----------------------------------------------------------------------------
@app.command("cluster.select")
def select_cluster(ctx: gx.CommandContext) -> None:
    new_c = ctx.form_data.get("cluster", selected_cluster.value)
    if new_c in EXTERNAL_TELEMETRY_DB:
        selected_cluster.value = new_c
        gx.invalidate_query(f"telemetry:{new_c}")


@app.command("cluster.rebalance.start")
async def trigger_rebalance(ctx: gx.CommandContext) -> None:
    await cluster_rebalance_job.submit(ctx, idempotency_key=ctx.action_id)


@app.command("settings.save")
def save_settings(ctx: gx.CommandContext) -> None:
    role = ctx.form_data.get("user_role", user_role.value)
    user_role.value = role
    auto_ref = ctx.form_data.get("auto_refresh", auto_refresh.value)
    auto_refresh.value = auto_ref


@app.command("stream.simulate")
async def simulate_stream(ctx: gx.CommandContext) -> None:
    stream_status.value = "Streaming telemetry chunks..."
    # In RADUI, server actions can update reactive state
    stream_status.value = "Telemetry stream synchronized (400 packets ingested)."


# -----------------------------------------------------------------------------
# Persistent Shell Layout
# Note: In RADUI v0.9, App._build_root executes layout functions outside
# state_context.activate(), so reading StateRef.value directly in a layout
# raises RuntimeError (BUG-LAYOUT-CTX-01). We use static branding in the shell.
# -----------------------------------------------------------------------------
@app.layout("/")
def main_layout(outlet: gx.Component) -> gx.Component:
    return gx.container(
        gx.column(
            # Navigation Bar
            gx.row(
                gx.row(
                    gx.heading("TelemetryOps Platform", level=2),
                    gx.badge("Live Ingestion", variant="primary"),
                    align="center",
                    gap=12,
                ),
                gx.row(
                    gx.link("Dashboard", href="/"),
                    gx.link("Analytics", href="/analytics"),
                    gx.link("Settings", href="/settings"),
                    gx.avatar(name="Admin", size="sm"),
                    align="center",
                    gap=16,
                ),
                justify="space-between",
                align="center",
            ),
            gx.divider(),
            outlet,
            gx.divider(),
            gx.row(
                gx.text("RADUI Framework Audit — Experiment B", variant="caption"),
                gx.text("Environment: Enterprise Single-Node Hybrid", variant="caption"),
                justify="space-between",
            ),
            gap=20,
        ),
        max_width="1100px",
    )


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.page("/")
def dashboard_page():
    metrics = get_cached_telemetry(selected_cluster.value)

    return gx.column(
        gx.row(
            gx.form(
                "cluster.select",
                gx.row(
                    gx.select(
                        "cluster",
                        label="Target Cluster",
                        bind=selected_cluster,
                        options=[(c, c) for c in EXTERNAL_TELEMETRY_DB.keys()],
                    ),
                    gx.button("Switch Cluster", variant="secondary"),
                    gap=12,
                    align="end",
                ),
            ),
            gx.form(
                "cluster.rebalance.start",
                gx.button("Run Rebalance Job", variant="primary"),
            ),
            justify="space-between",
            align="end",
        ),
        gx.row(
            metric_comparison_card("Throughput (QPS)", f"{metrics['qps']:,}", "50,000", "+8.4%", is_positive=True),
            metric_comparison_card("Error Rate", metrics["error_rate"], "< 0.05%", "-14.2%", is_positive=True),
            metric_comparison_card("P99 Latency", metrics["p99"], "45ms", "+3.1%", is_positive=False),
            gap=16,
        ),
        gx.card(
            gx.heading("Background Job & Stream Status", level=4),
            gx.text(f"Latest Rebalance Status: {job_output.value}"),
            gx.text(f"Telemetry Ingest Stream: {stream_status.value}", variant="muted"),
            gx.form(
                "stream.simulate",
                gx.button("Simulate Stream Sync", variant="secondary"),
            ),
            padding=16,
        ),
        # Protected ErrorBoundary demo component
        gx.error_boundary(
            gx.card(
                gx.heading("Fault-Tolerant Inspection Module", level=4),
                gx.text(f"Cluster Status: {metrics['status']}"),
                padding=16,
            ),
            fallback_message="Inspection module temporarily unavailable due to telemetry timeout.",
        ),
        gap=20,
    )


@app.page("/analytics")
def analytics_page():
    return gx.column(
        gx.heading("Cluster Performance Analytics", level=2),
        gx.text("Historical time-series trend analysis across nodes."),
        gx.table(
            headers=["Cluster Name", "QPS", "Error Rate", "P99 Latency", "Health Status"],
            rows=[
                [name, f"{data['qps']:,}", data["error_rate"], data["p99"], data["status"]]
                for name, data in EXTERNAL_TELEMETRY_DB.items()
            ],
        ),
        gx.link("← Return to Dashboard", href="/"),
        gap=16,
    )


@app.page("/settings")
def settings_page():
    return gx.column(
        gx.heading("Operational Settings", level=2),
        gx.card(
            gx.form(
                "settings.save",
                gx.column(
                    gx.input("user_role", label="User Role Title", bind=user_role),
                    gx.text(f"Active Role: {user_role.value}", variant="muted"),
                    gx.switch("auto_refresh", label="Automatic SWR Cache Refresh", bind=auto_refresh),
                    gx.button("Save Settings", variant="primary"),
                    gap=16,
                ),
            ),
            padding=20,
        ),
        gx.link("← Return to Dashboard", href="/"),
        gap=16,
    )


if __name__ == "__main__":
    app.run()
