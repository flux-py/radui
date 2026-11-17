from __future__ import annotations

import asyncio
import radui as gx
from radui.compiler import compile_app
from radui.interactions import act, on

app = gx.App("RadUI M2.0-M2.3 Unified Demo")


@app.web_component(
    "radui-kpi",
    shadow_mode="open",
    observed_attributes=("value",),
    styles=":host { display: inline-block; padding: 8px 12px; border: 1px solid var(--gx-border, #ccc); border-radius: 8px; }",
    template_html='<strong data-gx-prop="value">0</strong> <slot></slot>',
)
def radui_kpi():
    pass


async def load_live_metrics():
    await asyncio.sleep(0.05)
    return gx.column(
        gx.custom_element("radui-kpi", gx.text("Active Users"), props={"value": "1,248"}, id="kpi-users"),
        gx.column(
            gx.text("0", id="res-count", bind_local={"text": "clicks"}),
            gx.button("Local Resume +1", id="res-btn", interactions=(on("click", act.increment("clicks")),)),
            id="res-panel",
            local_state={"clicks": 0},
            resumable=True,
        ),
        id="streamed-metrics",
    )


@app.page("/", title="Unified M2.0-M2.3 Dashboard", stream=True, ssg=False)
def index():
    return gx.column(
        gx.heading("RadUI M2.0-M2.3 Unified Architecture", id="main-h1"),
        gx.suspense(load_live_metrics, fallback=gx.text("Streaming metrics...", id="metrics-fb"), id="b-metrics"),
        gx.link("Static About", "/about", id="lnk-about"),
    )


@app.page("/about", title="About")
def about():
    return gx.column(gx.heading("About RadUI", id="about-h1"), id="about-root")


if __name__ == "__main__":
    plan = compile_app(app)
    print(f"Compiled {len(plan.routes)} routes (hash={plan.content_hash}, time={plan.compile_time_ms:.2f}ms)")
