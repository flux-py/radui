"""RADUI Showcase Application B: Data Science & Analytics Dashboard.

Demonstrates:
- Reactive multi-dimensional filtering (region, metric, live toggle)
- KPI MetricCards with positive/negative delta indicators
- Interactive pure SVG chart rendering (bar, line, and scatter plots)
- Tabular data presentation with formatted Table components
- Asynchronous data aggregation background jobs with JobPanel
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import radui as gx

# State definitions
selected_region = gx.state("region", "North America", scope="session")
selected_metric = gx.state("metric", "Revenue ($k)", scope="session")
live_sync = gx.state("live_sync", "true", scope="session")
refresh_timestamp = gx.state("last_refresh", "Initial Load", scope="session")

# Dataset mock
DATASETS = {
    "North America": {
        "kpi_revenue": ("$1,482,900", "+14.2% vs last month"),
        "kpi_users": ("42,810", "+8.7% vs last month"),
        "kpi_latency": ("42 ms", "-12.5% improvement"),
        "chart_data": [
            {"x": "Jan", "y": 120},
            {"x": "Feb", "y": 145},
            {"x": "Mar", "y": 190},
            {"x": "Apr", "y": 210},
            {"x": "May", "y": 260},
            {"x": "Jun", "y": 310},
        ],
        "table_rows": [
            ["US-East-1", "99.99%", "24,100 req/s", "Optimal"],
            ["US-West-2", "99.95%", "12,400 req/s", "Optimal"],
            ["CA-Central-1", "99.98%", "6,310 req/s", "Optimal"],
        ],
    },
    "Europe": {
        "kpi_revenue": ("€980,400", "+6.1% vs last month"),
        "kpi_users": ("28,450", "+4.2% vs last month"),
        "kpi_latency": ("58 ms", "-3.1% improvement"),
        "chart_data": [
            {"x": "Jan", "y": 95},
            {"x": "Feb", "y": 110},
            {"x": "Mar", "y": 130},
            {"x": "Apr", "y": 155},
            {"x": "May", "y": 180},
            {"x": "Jun", "y": 220},
        ],
        "table_rows": [
            ["EU-West-1 (Dublin)", "99.99%", "18,200 req/s", "Optimal"],
            ["EU-Central-1 (Frankfurt)", "99.97%", "14,100 req/s", "Optimal"],
            ["EU-West-3 (Paris)", "99.91%", "5,200 req/s", "Degraded"],
        ],
    },
    "Asia-Pacific": {
        "kpi_revenue": ("$740,200", "+22.8% vs last month"),
        "kpi_users": ("36,120", "+19.4% vs last month"),
        "kpi_latency": ("74 ms", "-8.0% improvement"),
        "chart_data": [
            {"x": "Jan", "y": 60},
            {"x": "Feb", "y": 85},
            {"x": "Mar", "y": 115},
            {"x": "Apr", "y": 140},
            {"x": "May", "y": 195},
            {"x": "Jun", "y": 270},
        ],
        "table_rows": [
            ["AP-Northeast-1 (Tokyo)", "99.99%", "16,400 req/s", "Optimal"],
            ["AP-Southeast-1 (Singapore)", "99.98%", "11,800 req/s", "Optimal"],
            ["AP-South-1 (Mumbai)", "99.94%", "9,200 req/s", "Optimal"],
        ],
    },
}

app = gx.App("Data Science & Analytics Dashboard", app_id="analytics-dashboard", debug=True)


@app.job("analytics.recompute_aggregates")
async def recompute_aggregates(ctx: gx.JobContext) -> dict:
    """Simulates background OLAP rollups and query generation."""
    await ctx.progress(15, "Connecting to data warehouse...")
    await asyncio.sleep(0.3)
    await ctx.progress(45, "Running query partition scans...")
    await asyncio.sleep(0.35)
    await ctx.progress(80, "Calculating percentile distributions & deltas...")
    await asyncio.sleep(0.25)
    await ctx.progress(100, "Aggregates updated.")
    refresh_timestamp.value = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return {"status": "ok", "timestamp": refresh_timestamp.value}


@app.command("filters.apply")
def apply_filters(ctx: gx.CommandContext) -> None:
    region = ctx.form_data.get("filter.region") or ctx.form_data.get("region", "North America")
    if region in DATASETS:
        selected_region.value = region
    metric = ctx.form_data.get("filter.metric") or ctx.form_data.get("metric", "Revenue ($k)")
    selected_metric.value = metric


@app.command("analytics.refresh")
async def trigger_refresh(ctx: gx.CommandContext) -> None:
    await recompute_aggregates.submit(ctx, idempotency_key=ctx.action_id)


@app.page("/")
def dashboard_home():
    current_region = selected_region.value
    region_data = DATASETS.get(current_region, DATASETS["North America"])

    rev_val, rev_delta = region_data["kpi_revenue"]
    usr_val, usr_delta = region_data["kpi_users"]
    lat_val, lat_delta = region_data["kpi_latency"]

    return gx.column(
        gx.row(
            gx.heading("Executive Analytics Cockpit", level=1),
            gx.row(
                gx.badge(current_region, variant="primary"),
                gx.badge("Live Ingestion", variant="success"),
            ),
            justify="space-between",
            align="center",
        ),
        gx.text(
            f"Multi-region business intelligence and cluster performance telemetry. Last refreshed: {refresh_timestamp.value}",
            variant="muted",
        ),
        gx.divider(),

        # Filter bar
        gx.card(
            gx.form(
                "filters.apply",
                gx.row(
                    gx.select(
                        "region",
                        options=["North America", "Europe", "Asia-Pacific"],
                        label="Select Region",
                        state_ref=selected_region,
                    ),
                    gx.select(
                        "metric",
                        options=["Revenue ($k)", "Daily Active Users", "P99 Latency (ms)"],
                        label="Primary Metric",
                        state_ref=selected_metric,
                    ),
                    gx.button("Apply Filter", variant="primary"),
                    align="end",
                    gap=16,
                ),
                id="filter-form",
            ),
        ),
        gx.spacer(20),

        # KPI Metrics Grid
        gx.grid(
            gx.metric_card("Total Revenue", rev_val, delta=rev_delta, delta_type="positive", icon="revenue", id="kpi-rev"),
            gx.metric_card("Active Users", usr_val, delta=usr_delta, delta_type="positive", icon="users", id="kpi-users"),
            gx.metric_card("P99 Response Time", lat_val, delta=lat_delta, delta_type="positive", icon="latency", id="kpi-lat"),
            columns=3,
            gap=16,
        ),
        gx.spacer(24),

        # Charts and Analysis
        gx.grid(
            gx.card(
                gx.heading(f"{selected_metric.value} Trajectory (H1 2026)", level=3),
                gx.plot(
                    type="line",
                    data=region_data["chart_data"],
                    x_key="x",
                    y_key="y",
                    title="Monthly Growth Velocity",
                    color="#38bdf8",
                    id="chart-velocity",
                ),
            ),
            gx.card(
                gx.heading("Volume Distribution by Month", level=3),
                gx.plot(
                    type="bar",
                    data=region_data["chart_data"],
                    x_key="x",
                    y_key="y",
                    title="Segment Throughput",
                    color="#6366f1",
                    id="chart-distribution",
                ),
            ),
            columns=2,
            gap=20,
        ),
        gx.spacer(24),

        # Cluster Health Table and Background Refresh
        gx.grid(
            gx.card(
                gx.heading("Regional Cluster Availability", level=3),
                gx.table(
                    headers=["Cluster Zone", "Uptime SLA", "Traffic Density", "Health Status"],
                    rows=region_data["table_rows"],
                    id="cluster-table",
                ),
            ),
            gx.card(
                gx.heading("OLAP Warehouse Sync", level=3),
                gx.text("Recompute historical aggregations across all data partitions.", variant="muted"),
                gx.spacer(8),
                gx.form(
                    "analytics.refresh",
                    gx.button("Trigger Full Warehouse Sync", variant="secondary"),
                    id="sync-form",
                ),
                gx.spacer(12),
                gx.job_panel(recompute_aggregates, id="sync-job-panel"),
            ),
            columns=2,
            gap=20,
        ),
    )


if __name__ == "__main__":
    app.run(port=8002)

