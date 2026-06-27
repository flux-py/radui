from enum import Enum
import pytest
from pydantic import BaseModel, Field
from starlette.testclient import TestClient

import radui as gx
from radui.components.model_forms import form_from_model
from radui.core.theme import Theme
from radui.testing import TestHarness


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DeploymentConfig(BaseModel):
    name: str = Field(..., description="Service name")
    replicas: int = Field(default=3, description="Number of instances")
    budget: float = Field(default=99.95, description="Cost limit")
    priority: Priority = Field(default=Priority.MEDIUM, description="Task priority")
    enabled: bool = Field(default=True, description="Enable automated rollout")
    notes: str = Field(default="", description="Deployment runbook notes")


def test_form_from_model():
    form = form_from_model(
        DeploymentConfig,
        command="deploy_service",
        submit_label="Deploy Now",
        defaults={"name": "analytics-worker"},
    )
    assert form.command == "deploy_service"
    assert form.id == "form_deployment_config"
    # Inspect children components
    ids = [c.id for c in form.children if hasattr(c, "id")]
    assert "field_name" in ids
    assert "field_replicas" in ids
    assert "field_priority" in ids
    assert "field_enabled" in ids

    # Check that priority generated a Select with 3 choices
    select_field = next(c for c in form.children if getattr(c, "id", None) == "field_priority")
    assert isinstance(select_field, gx.Select)
    assert len(select_field.options) == 3

    # Check checkbox for bool
    bool_field = next(c for c in form.children if getattr(c, "id", None) == "field_enabled")
    assert isinstance(bool_field, gx.Checkbox)
    assert bool_field.state_ref.default is True

    # Check default prefill
    name_field = next(c for c in form.children if getattr(c, "id", None) == "field_name")
    assert name_field.state_ref.default == "analytics-worker"


def test_skeleton_rendering():
    registry = gx.ComponentRegistry.builtins()
    renderer = gx.renderers.html.HTMLRenderer(registry)

    sk1 = gx.skeleton(width="200px", height="24px", shape="text", animated=True)
    html1 = renderer.render_component(sk1)
    assert "gx-skeleton" in html1
    assert "gx-skeleton-shimmer" in html1
    assert "gx-skeleton-text" in html1
    assert "width:200px" in html1
    assert "height:24px" in html1

    sk2 = gx.skeleton(width="48px", height="48px", shape="circle", animated=False)
    html2 = renderer.render_component(sk2)
    assert "gx-skeleton-circle" in html2
    assert "gx-skeleton-shimmer" not in html2


def test_empty_state_rendering():
    registry = gx.ComponentRegistry.builtins()
    renderer = gx.renderers.html.HTMLRenderer(registry)

    empty = gx.empty_state(
        title="No Deployments Found",
        description="Get started by launching your first serverless container.",
        icon="rocket",
    )
    html = renderer.render_component(empty)
    assert "gx-empty-state" in html
    assert "No Deployments Found" in html
    assert "Get started by launching" in html
    assert "rocket" in html


def test_file_upload_rendering():
    registry = gx.ComponentRegistry.builtins()
    renderer = gx.renderers.html.HTMLRenderer(registry)

    upload = gx.file_upload(
        id="dataset_upload",
        command="datasets.upload",
        accept=".csv,.parquet,.json",
        max_size_mb=25,
        multiple=True,
    )
    html = renderer.render_component(upload)
    assert "gx-file-upload" in html
    assert "Max size: 25 MB" in html
    assert 'accept=".csv,.parquet,.json"' in html
    assert "multiple" in html


def test_virtual_list_rendering():
    items = [f"Item record #{i}" for i in range(1000)]
    vl = gx.virtual_list(items=items, item_height=36, viewport_height=360, id="virtual_telemetry")
    registry = gx.ComponentRegistry.builtins()
    renderer = gx.renderers.html.HTMLRenderer(registry)
    html = renderer.render_component(vl)

    assert "gx-virtual-list" in html
    assert "height:360px" in html
    assert 'data-gx-item-height="36"' in html
    # Total spacer height: 1000 * 36 = 36000px
    assert "height:36000px" in html


def test_theme_toggle_rendering():
    tt = gx.theme_toggle(id="nav_theme_btn")
    registry = gx.ComponentRegistry.builtins()
    renderer = gx.renderers.html.HTMLRenderer(registry)
    html = renderer.render_component(tt)

    assert "gx-theme-toggle" in html
    assert 'id="nav_theme_btn"' in html
    assert "gx-theme-icon" in html


def test_responsive_grid():
    g = gx.grid(
        gx.text("Card 1"),
        gx.text("Card 2"),
        columns={"sm": 1, "md": 2, "lg": 4},
        gap=16,
    )
    registry = gx.ComponentRegistry.builtins()
    renderer = gx.renderers.html.HTMLRenderer(registry)
    html = renderer.render_component(g)

    assert "gx-grid-responsive" in html
    assert "--gx-cols-sm:1" in html
    assert "--gx-cols-md:2" in html
    assert "--gx-cols-lg:4" in html


def test_theme_presets_and_css():
    dark_theme = Theme.dark()
    assert dark_theme.mode == "dark"
    assert dark_theme.primary == "#3b82f6"
    css = dark_theme.to_css()
    assert '[data-theme="dark"] {' in css
    assert "--gx-primary: #3b82f6;" in css
    assert "--gx-bg: #0f172a;" in css

    emerald = Theme.emerald()
    assert emerald.primary == "#059669"
    emerald_css = emerald.to_css()
    assert "--gx-primary: #059669;" in emerald_css


def test_app_theme_integration_and_embed_endpoint():
    app = gx.App(name="Themed App", theme=Theme.indigo())

    @app.page("/")
    def index():
        return gx.heading("Themed Heading")

    client = TestClient(app.asgi())
    res = client.get("/")
    assert res.status_code == 200
    assert "--gx-primary: #6366f1;" in res.text
    assert "Themed Heading" in res.text

    # Micro-frontend script
    embed_res = client.get("/_gx/embed.js")
    assert embed_res.status_code == 200
    assert "RADUI-view" in embed_res.text
    assert embed_res.headers["content-type"].startswith("application/javascript")


def test_test_harness():
    app = gx.App(name="Test Harness App")
    last_query = gx.state("last_query", "", scope="session")

    @app.page("/")
    def home():
        return gx.column(
            gx.heading("Dashboard Home"),
            gx.form(
                "search_query",
                gx.input("Search query", bind=gx.state("q", "radui", scope="session"), id="search_input"),
                gx.button("Search", id="submit_btn"),
                id="search_form",
            )
        )

    @app.command("search_query")
    def handle_search(ctx: gx.CommandContext):
        query = ctx.form_data.get("q", "")
        ctx.write(last_query, query)

    harness = TestHarness(app)
    html = harness.render("/")
    assert "Dashboard Home" in html

    harness.assert_contains("/", "Dashboard Home")
    harness.assert_component_exists("/", "search_input")

    forms = harness.get_forms("/")
    assert "search_query" in forms
    assert forms["search_query"]["id"] == "search_form"
    assert forms["search_query"]["inputs"]["q"] == "radui"

    # Dispatch command via harness
    res = harness.dispatch("search_query", {"q": "production ready"})
    assert res["ok"] is True
