"""RADUI Audit — Experiment A: Beginner Application.

Evaluates Developer Experience (Scenario A):
- Minimal learning curve
- Standard components: Layout, Input, Slider, Select, Form, Button, Navigation
- Scoped reactive state with surgical updates
"""

from __future__ import annotations

import radui as gx

app = gx.App("Beginner Feedback App", app_id="exp-beginner-app")

# Scoped reactive state variables
user_name = gx.state("user_name", "Alex Developer", scope="session")
satisfaction_score = gx.state("satisfaction_score", 8.0, scope="session")
category = gx.state("category", "performance", scope="session")
submitted_feedback = gx.state("submitted_feedback", "", scope="session")


@app.command("feedback.submit")
def submit_feedback(ctx: gx.CommandContext) -> None:
    """Handles feedback form submission and writes to reactive state."""
    name = ctx.form_data.get("name", user_name.value).strip()
    cat = ctx.form_data.get("category", category.value)
    user_name.value = name
    category.value = cat
    submitted_feedback.value = f"Thank you, {name}! Your {cat} rating ({satisfaction_score.value}/10) was recorded."


@app.command("score.reset")
def reset_score(ctx: gx.CommandContext) -> None:
    satisfaction_score.value = 5.0
    submitted_feedback.value = "Score reset to default."


@app.page("/")
def home():
    feedback_banner = (
        gx.callout(submitted_feedback.value, variant="success")
        if submitted_feedback.value
        else gx.callout("Please rate your framework experience below.", variant="info")
    )

    return gx.container(
        gx.card(
            gx.heading("Developer Experience Survey", level=2),
            gx.text(f"Logged in as: {user_name.value}", variant="muted"),
            feedback_banner,
            gx.form(
                "feedback.submit",
                gx.column(
                    gx.input("name", label="Your Name", bind=user_name),
                    gx.select(
                        "category",
                        label="Category",
                        bind=category,
                        options=[
                            ("API Simplicity", "simplicity"),
                            ("Runtime Performance", "performance"),
                            ("Documentation Quality", "docs"),
                            ("Extensibility", "extensibility"),
                        ],
                    ),
                    gx.slider("Satisfaction Score (1-10)", bind=satisfaction_score, min_value=1.0, max_value=10.0, step=0.5),
                    gx.row(
                        gx.button("Submit Survey", variant="primary"),
                        gx.button("Reset Score", command="score.reset", variant="secondary"),
                        gap=12,
                    ),
                    gap=16,
                ),
            ),
            footer=gx.row(
                gx.link("View Documentation", href="/docs"),
                gx.text("RADUI Audit Experiment A", variant="caption"),
                justify="space-between",
            ),
        ),
        max_width="700px",
    )


@app.page("/docs")
def docs_page():
    return gx.container(
        gx.card(
            gx.heading("Documentation & Help", level=2),
            gx.text("This page verifies multi-page routing for the beginner workflow."),
            gx.link("← Return to Survey", href="/"),
        ),
        max_width="700px",
    )


if __name__ == "__main__":
    app.run()
