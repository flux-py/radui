from __future__ import annotations

import radui as gx

app = gx.App("RadUI Declarative Interactions Demo")


@app.command("demo.save_note")
def save_note(ctx: gx.CommandContext) -> None:
    gx.notify("Saved authoritative state on server", variant="success")


@app.page("/")
def home():
    return gx.container(
        gx.heading("RadUI Local Interactions Demo", level=1),
        gx.card(
            gx.row(
                gx.text("0", id="demo-count", bind_local={"text": "count"}),
                gx.button(
                    "+1 Local",
                    id="demo-inc",
                    interactions=(gx.on("click", gx.act.increment("count"), gx.act.announce("Count incremented")),),
                ),
                gx.button(
                    "Toggle Details",
                    id="demo-toggle",
                    interactions=(gx.on("click", gx.act.toggle("show_details")),),
                ),
                gap=12,
            ),
            gx.text("Zero-latency client-side details panel.", id="demo-details", bind_local={"visible": "show_details"}),
            id="demo-card",
            local_state={"count": 0, "show_details": False},
        ),
        gx.tabs(
            gx.tab_item("Overview", gx.text("Keyboard accessible tabs (ArrowLeft/ArrowRight).")),
            gx.tab_item("Server Bridge", gx.button("Sync to Server", id="demo-sync", interactions=(gx.on("click", gx.act.command("demo.save_note")),))),
            id="demo-tabs",
        ),
        max_width="800px",
    )
