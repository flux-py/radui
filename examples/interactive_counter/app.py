"""Small interactive RADUI demo.

Run with: python examples/interactive_counter/app.py
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import radui as gx

app = gx.App(
    "RADUI Interactive Counter",
    app_id="interactive-counter",
    # Supply a stable random secret through your deployment secret manager in production.
    session_secret="development-only-change-this-secret-before-deploying",
)

count = gx.state("counter.value", 0, scope="session")
name = gx.state("profile.name", "Ada", scope="session")
notifications = gx.state("profile.notifications", True, scope="session")


@app.command("counter.increment")
def increment(ctx: gx.CommandContext) -> None:
    count.value += 1


@app.command("counter.reset")
async def reset(ctx: gx.CommandContext) -> None:
    count.value = 0


@app.page("/", title="RADUI Interactive Counter")
def home():
    return gx.column(
        gx.heading("RADUI Interactivity 0.4", level=1),
        gx.text("A typed state value is rendered as a component binding:"),
        gx.card(
            gx.text(bind=count, format="Current count: {value}"),
            gx.form(
                "counter.increment",
                gx.input("Your name", bind=name, placeholder="Enter a name"),
                gx.checkbox("Enable notifications", bind=notifications),
                gx.button("Increment"),
            ),
            gx.form(
                "counter.reset",
                gx.button("Reset counter"),
            ),
        ),
        gx.text("Refresh the page: the session state remains available."),
        gap=18,
    )


if __name__ == "__main__":
    app.run()
