"""Enterprise, security, and developer infrastructure guides:
Authentication, RBAC Policies, SWR Data Engine, and Headless Testing Harness.
"""

from __future__ import annotations

import radui as ui
from docs_site.core import app

# =========================================================================
# 1. AUTHENTICATION, RBAC & MULTI-TENANCY
# =========================================================================

@app.page("/auth")
def auth_page():
    return ui.column(
        ui.badge("Security & Governance", variant="primary"),
        ui.heading("Authentication, RBAC & Multi-Tenancy", level=1),
        ui.text(
            "RADUI provides built-in enterprise authorization primitives, user identity abstraction, "
            "role-based access control (RBAC), multi-tenant fence validation, and request rate limiting.",
            variant="lead",
        ),
        ui.spacer(size=16),

        # Section 1: User Identity & RBAC Policies
        ui.card(
            ui.heading("1. User Model & RBAC Policy Manager", level=3),
            ui.text(
                "The `ui.User` dataclass encapsulates authenticated identity, roles, permissions, and tenant metadata. "
                "`ui.RBACPolicy` evaluates hierarchical permissions with wildcard ('*') support:"
            ),
            ui.code_block(
                "from radui import User, RBACPolicy\n\n"
                "# Define custom role permissions\n"
                "policy = RBACPolicy()\n"
                "policy.register_role('operator', ['read', 'cluster.scale', 'cluster.restart'])\n"
                "policy.register_role('viewer', ['read'])\n\n"
                "# Construct user identity\n"
                "user = User(\n"
                "    id='usr_94821',\n"
                "    username='arman@flux.py',\n"
                "    roles=frozenset({'operator'}),\n"
                "    permissions=frozenset({'cluster.scale'}),\n"
                "    metadata={'dept': 'Infrastructure'}\n"
                ")\n\n"
                "# Evaluation\n"
                "can_scale = user.has_permission('cluster.scale')  # -> True\n"
                "is_admin = user.has_role('admin')               # -> False\n"
                "allowed = policy.check_permission(user.roles, 'cluster.restart')  # -> True",
                language="python",
                copyable=True,
            ),
            ui.spacer(size=12),
            ui.card(
                ui.badge("INTERACTIVE PERMISSION EVALUATOR", variant="success"),
                ui.row(
                    ui.badge("Role: operator", variant="primary"),
                    ui.badge("Status: Authenticated", variant="success"),
                    ui.badge("Tenant: prod-cluster-east", variant="neutral"),
                    gap=8,
                ),
                ui.spacer(size=8),
                ui.row(
                    ui.button("Execute Scale (Allowed)", variant="primary", command="comp.test_trigger"),
                    ui.button("Delete Tenant (Requires Admin)", variant="outline", command="comp.test_trigger", disabled=True),
                    gap=10,
                ),
            ),
            hover=ui.motion.hover(scale=1.01, translate_y=-1.0),
        ),
        ui.spacer(size=16),

        # Section 2: Route & Command Protection Decorators
        ui.card(
            ui.heading("2. Route & Server Command Protection", level=3),
            ui.text(
                "Secure entire views or specific command endpoints with `require_auth`, `require_role`, or `require_permission`. "
                "RADUI automatically enforces policies before evaluating view functions or invoking handlers:"
            ),
            ui.code_block(
                "import radui as ui\n\n"
                "app = ui.App(title='Cluster Management Console')\n\n"
                "# 1. Guard a page route by role\n"
                "@app.page('/admin/settings', require_auth=True, require_role='admin')\n"
                "def admin_settings():\n"
                "    return ui.heading('Administrator Settings')\n\n"
                "# 2. Guard an interactive command dispatch\n"
                "@app.command('cluster.restart', require_auth=True, require_role='operator')\n"
                "def restart_cluster(ctx: ui.CommandContext):\n"
                "    # Access resolved user inside handler\n"
                "    operator = ctx.current_user\n"
                "    print(f'Restart dispatched by {operator.username}')\n"
                "    ui.notify(f'Cluster restart queued by {operator.username}!', variant='warning')\n\n"
                "# 3. Shorthand decorator variants\n"
                "@app.require_auth('export.telemetry')\n"
                "def export_telemetry(ctx: ui.CommandContext):\n"
                "    ...\n\n"
                "@app.require_role('admin')\n"
                "def purge_database(ctx: ui.CommandContext):\n"
                "    ...",
                language="python",
                copyable=True,
            ),
            hover=ui.motion.hover(scale=1.01, translate_y=-1.0),
        ),
        ui.spacer(size=16),

        # Section 3: Multi-Tenancy & Fencing
        ui.card(
            ui.heading("3. Multi-Tenancy & Rate Limiting", level=3),
            ui.text(
                "Configure tenant resolution, authorization membership validators, and token-bucket sliding-window rate limiters:"
            ),
            ui.code_block(
                "import radui as ui\n"
                "from radui.core.security import RateLimiter, RateLimitMiddleware\n\n"
                "# Custom resolvers\n"
                "def resolve_user(request):\n"
                "    return request.headers.get('X-User-ID')\n\n"
                "def resolve_tenant(request):\n"
                "    return request.headers.get('X-Tenant-ID')\n\n"
                "def validate_membership(request, user_id, tenant_id):\n"
                "    return user_id in db.get_tenant_members(tenant_id)\n\n"
                "app = ui.App(\n"
                "    user_id_resolver=resolve_user,\n"
                "    tenant_id_resolver=resolve_tenant,\n"
                "    tenant_membership_validator=validate_membership,\n"
                ")\n\n"
                "# Enforce 120 requests/minute per client IP with burst tolerance\n"
                "app.add_middleware(RateLimitMiddleware, requests_per_minute=120, burst=30)",
                language="python",
                copyable=True,
            ),
            hover=ui.motion.hover(scale=1.01, translate_y=-1.0),
        ),
        gap=16,
        stagger_children=0.05,
    )

# =========================================================================
# 2. DATA ENGINE & SWR QUERY CACHING
# =========================================================================

@app.page("/data-engine")
def data_engine_page():
    return ui.column(
        ui.badge("Data Engine", variant="primary"),
        ui.heading("Data Engine, SWR Caching & Client Downloads", level=1),
        ui.text(
            "RADUI includes a thread-safe Stale-While-Revalidate (SWR) query engine, asynchronous deduplication, "
            "deterministic pagination helpers, and zero-server client download triggers.",
            variant="lead",
        ),
        ui.spacer(size=16),

        # Section 1: SWR Caching
        ui.card(
            ui.heading("1. SWR Query Caching (`@cached` & `query`)", level=3),
            ui.text(
                "Cache expensive database queries or third-party API results in memory. Returns stale cached data immediately "
                "while asynchronously revalidating in the background when the stale window expires:"
            ),
            ui.code_block(
                "import radui as ui\n"
                "from radui.data import cached, query, aquery, invalidate_query\n\n"
                "# 1. Decorator-driven SWR query cache\n"
                "@cached(ttl=120.0, stale_time=30.0)\n"
                "def get_cluster_metrics(region: str):\n"
                "    # Expensive SQL or telemetry call\n"
                "    return db.fetch_metrics(region)\n\n"
                "# 2. Direct program query\n"
                "metrics = query('metrics.us-east', lambda: db.fetch('us-east'), ttl=60.0)\n\n"
                "# 3. Async SWR query fetcher\n"
                "async def fetch_remote():\n"
                "    async with httpx.AsyncClient() as client:\n"
                "        return (await client.get('https://api.domain.com/status')).json()\n\n"
                "# Invalidate cache on mutations\n"
                "@app.command('cluster.sync')\n"
                "def on_sync(ctx: ui.CommandContext):\n"
                "    invalidate_query('metrics.us-east')\n"
                "    ui.notify('Cluster metrics cache invalidated', variant='info')",
                language="python",
                copyable=True,
            ),
            hover=ui.motion.hover(scale=1.01, translate_y=-1.0),
        ),
        ui.spacer(size=16),

        # Section 2: Pagination & Browser Downloads
        ui.card(
            ui.heading("2. Array Pagination & Client Downloads", level=3),
            ui.text(
                "`paginate` handles slicing, boundary clamping, and page count calculations. "
                "`download_button` triggers instant client-side file downloads directly from memory without a dedicated server route:"
            ),
            ui.code_block(
                "import radui as ui\n"
                "from radui.data import paginate, download_button\n\n"
                "# Deterministic slice helper\n"
                "records = [{'id': i, 'val': f'item-{i}'} for i in range(100)]\n"
                "page_slice, total_pages, total_items = paginate(records, page=1, page_size=10)\n\n"
                "# Client-side CSV download button\n"
                "csv_content = 'id,status,latency\\n1,ACTIVE,0.039ms\\n2,HEALTHY,0.042ms'\n"
                "download_btn = download_button(\n"
                "    'Export Telemetry CSV',\n"
                "    filename='cluster-telemetry.csv',\n"
                "    content=csv_content,\n"
                "    mime_type='text/csv',\n"
                "    variant='primary',\n"
                ")",
                language="python",
                copyable=True,
            ),
            hover=ui.motion.hover(scale=1.01, translate_y=-1.0),
        ),
        gap=16,
        stagger_children=0.05,
    )

# =========================================================================
# 3. HEADLESS TEST HARNESS
# =========================================================================

@app.page("/testing")
def testing_page():
    return ui.column(
        ui.badge("Testing & Verification", variant="primary"),
        ui.heading("Headless Component & Application Test Harness", level=1),
        ui.text(
            "Test RADUI components, layouts, reactive forms, and command workflows programmatically "
            "with zero browser dependencies using the built-in `TestHarness`.",
            variant="lead",
        ),
        ui.spacer(size=16),

        # Section 1: Unit Testing Components
        ui.card(
            ui.heading("1. Headless Component Unit Testing", level=3),
            ui.text(
                "`TestHarness` renders typed AST component nodes directly to HTML strings without starting an ASGI server or socket:"
            ),
            ui.code_block(
                "import pytest\n"
                "import radui as ui\n"
                "from radui.testing import TestHarness\n\n"
                "def test_button_rendering():\n"
                "    harness = TestHarness()\n"
                "    btn = ui.button('Deploy', variant='primary', id='deploy-btn')\n"
                "    html = harness.render_component(btn)\n\n"
                "    assert '<button' in html\n"
                "    assert 'gx-button-primary' in html\n"
                "    assert 'Deploy' in html\n"
                "    assert 'id=\"deploy-btn\"' in html\n\n"
                "def test_metric_card():\n"
                "    harness = TestHarness()\n"
                "    card = ui.metric_card('Latency', '0.039 ms', delta='-42%')\n"
                "    html = harness.render_component(card)\n\n"
                "    assert '0.039 ms' in html\n"
                "    assert '-42%' in html",
                language="python",
                copyable=True,
            ),
            hover=ui.motion.hover(scale=1.01, translate_y=-1.0),
        ),
        ui.spacer(size=16),

        # Section 2: End-to-End Application Testing
        ui.card(
            ui.heading("2. Integration & End-to-End Application Testing", level=3),
            ui.text(
                "Pass an active `App` instance to test routes, status codes, CSRF tokens, and command form submissions:"
            ),
            ui.code_block(
                "import pytest\n"
                "from radui.testing import TestHarness\n"
                "from my_project.app import app\n\n"
                "def test_dashboard_route():\n"
                "    harness = TestHarness(app)\n"
                "    # 1. Fetch rendered HTML\n"
                "    html = harness.get_page('/dashboard')\n\n"
                "    # 2. Text assertions\n"
                "    harness.assert_contains('/dashboard', 'Cluster Overview')\n\n"
                "    # 3. Component DOM existence assertion\n"
                "    harness.assert_component_exists('/dashboard', 'cluster-kpi-grid')\n\n"
                "def test_command_form_extraction():\n"
                "    harness = TestHarness(app)\n"
                "    html = harness.get_page('/settings')\n"
                "    action_url, hidden_fields = harness.extract_form(html, command='settings.save')\n\n"
                "    assert '_csrf' in hidden_fields\n"
                "    assert action_url.endswith('/_gx/commands/settings.save')",
                language="python",
                copyable=True,
            ),
            hover=ui.motion.hover(scale=1.01, translate_y=-1.0),
        ),
        gap=16,
        stagger_children=0.05,
    )
