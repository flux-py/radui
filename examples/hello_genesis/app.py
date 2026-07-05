import radui as gx

app = gx.App("RADUI Research Workbench", app_id="research-workbench")


@app.page("/", title="Research Workbench")
def home():
    return gx.column(
        gx.card(
            gx.heading("A small beginning", level=1),
            gx.text(
                "RADUI Core 0.4 provides the static application model, server-rendered HTML, "
                "and a separate typed in-memory state runtime. State is not yet connected to "
                "browser rendering, commands, or jobs."
            ),
            gx.divider(),
            gx.heading("What works today", level=2),
            gx.text("• Typed component nodes validated with Pydantic"),
            gx.text("• Component registry with an explicit allowlist"),
            gx.text("• Escaped text and constrained link URLs"),
            gx.text("• HTML rendering through a Starlette ASGI application"),
            gx.link("Read the project README", "https://example.com"),
        ),
        gap=20,
    )


if __name__ == "__main__":
    app.run()
