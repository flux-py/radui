"""RADUI Showcase Application C: Enterprise SaaS Admin Platform.

Demonstrates:
- Multi-route application routing (/, /users, /settings, /maintenance)
- User CRUD lifecycle with Form commands, Badges, and Callouts
- Tabbed organizational settings via Tabs and TabItem components
- Modal dialogs for destructive/confirmation workflows
- Long-running background maintenance & backup jobs via JobPanel
- Responsive light/dark enterprise design system
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import radui as gx

# State definitions
org_name = gx.state("org_name", "Acme Corporation", scope="session")
security_mfa = gx.state("mfa_enforced", "true", scope="session")
session_timeout = gx.state("timeout_min", "30", scope="session")
new_user_name = gx.state("name", "", scope="session")
new_user_email = gx.state("email", "", scope="session")
new_user_role = gx.state("role", "Viewer", scope="session")
user_list = gx.state(
    "users",
    [
        {"id": "usr-1", "name": "Elena Rostova", "email": "elena@acme.corp", "role": "Super Admin", "status": "Active"},
        {"id": "usr-2", "name": "Marcus Vance", "email": "marcus@acme.corp", "role": "DevOps Lead", "status": "Active"},
        {"id": "usr-3", "name": "Aisha Patel", "email": "aisha@acme.corp", "role": "Data Engineer", "status": "Invited"},
        {"id": "usr-4", "name": "David Kim", "email": "david@acme.corp", "role": "Viewer", "status": "Suspended"},
    ],
    scope="session",
)
system_banner = gx.state("banner", "All systems operational across 3 availability regions.", scope="session")

app = gx.App("Enterprise SaaS Admin Platform", app_id="saas-admin-platform", debug=True)


@app.job("system.database_backup")
async def run_database_backup(ctx: gx.JobContext) -> dict:
    """Simulates background multi-region database snapshot and archival."""
    await ctx.progress(10, "Acquiring global table read locks...")
    await asyncio.sleep(0.3)
    await ctx.progress(35, "Streaming snapshot chunks to AWS S3 Glacier...")
    await asyncio.sleep(0.4)
    await ctx.progress(70, "Verifying SHA-256 integrity checksums...")
    await asyncio.sleep(0.3)
    await ctx.progress(100, "Backup snapshot encrypted and archived.")
    return {"backup_id": "bak-20261114-001", "size_bytes": 14_892_000_000}


@app.command("users.create")
def create_user(ctx: gx.CommandContext) -> None:
    name = (ctx.form_data.get("form.name") or ctx.form_data.get("name", "")).strip()
    email = (ctx.form_data.get("form.email") or ctx.form_data.get("email", "")).strip()
    role = ctx.form_data.get("form.role") or ctx.form_data.get("role", "Viewer")
    if not name or not email:
        return

    users = list(user_list.value)
    new_user = {
        "id": f"usr-{len(users) + 1}",
        "name": name,
        "email": email,
        "role": role,
        "status": "Active",
    }
    users.append(new_user)
    user_list.value = users
    new_user_name.value = ""
    new_user_email.value = ""
    system_banner.value = f"User '{name}' provisioned successfully."


@app.command("settings.update")
def update_settings(ctx: gx.CommandContext) -> None:
    new_org = (ctx.form_data.get("org.name") or ctx.form_data.get("org_name", "")).strip()
    if new_org:
        org_name.value = new_org
    timeout = (ctx.form_data.get("org.timeout_min") or ctx.form_data.get("timeout_min", "30")).strip()
    session_timeout.value = timeout
    system_banner.value = f"Configuration updated at {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC."


@app.command("system.trigger_backup")
async def trigger_backup(ctx: gx.CommandContext) -> None:
    await run_database_backup.submit(ctx, idempotency_key=ctx.action_id)


def _admin_nav(current_path: str):
    """Reusable top-level enterprise navigation bar."""
    items = [
        ("/", "Dashboard"),
        ("/users", "Users & Access"),
        ("/settings", "Organization Settings"),
        ("/maintenance", "System Operations"),
    ]
    links = [
        gx.link(
            label,
            href=path,
        )
        for path, label in items
    ]
    return gx.column(
        gx.row(
            gx.heading(f"Acme Enterprise: {org_name.value}", level=2),
            gx.row(*links, gap=10),
            justify="space-between",
            align="center",
        ),
        gx.callout(bind=system_banner, variant="info", id="admin-banner-callout"),
        gx.divider(),
    )


@app.page("/")
def admin_dashboard():
    users = user_list.value
    active_count = sum(1 for u in users if u["status"] == "Active")
    suspended_count = sum(1 for u in users if u["status"] == "Suspended")

    return gx.column(
        _admin_nav("/"),
        gx.heading("Executive System Health", level=1),
        gx.text("Real-time infrastructure and security posture overview.", variant="muted"),
        gx.spacer(16),
        gx.grid(
            gx.metric_card("Total Registered Users", str(len(users)), delta=f"{active_count} active", delta_type="positive", icon="users"),
            gx.metric_card("Security Enforcements", "100%", delta="MFA Mandatory", delta_type="positive", icon="shield"),
            gx.metric_card("System SLA Uptime", "99.995%", delta="Zero incidents H2", delta_type="positive", icon="latency"),
            gx.metric_card("Suspended Accounts", str(suspended_count), delta="Requires Audit", delta_type="negative", icon="alert"),
            columns=4,
            gap=16,
        ),
        gx.spacer(24),
        gx.card(
            gx.heading("Recent User Activity", level=3),
            gx.table(
                headers=["User ID", "Full Name", "Email Address", "Role", "Current Status"],
                rows=[[u["id"], u["name"], u["email"], u["role"], u["status"]] for u in users],
                id="dashboard-user-table",
            ),
        ),
    )


@app.page("/users")
def admin_users():
    users = user_list.value
    return gx.column(
        _admin_nav("/users"),
        gx.row(
            gx.heading("Users & Access Governance", level=1),
            gx.badge(f"{len(users)} Total Accounts", variant="primary"),
            justify="space-between",
            align="center",
        ),
        gx.text("Manage IAM credentials, assign security roles, and invite enterprise collaborators.", variant="muted"),
        gx.spacer(20),
        gx.grid(
            gx.card(
                gx.heading("Active Directory Roster", level=3),
                gx.table(
                    headers=["User ID", "Name", "Corporate Email", "Assigned Role", "Status"],
                    rows=[[u["id"], u["name"], u["email"], u["role"], u["status"]] for u in users],
                    id="users-management-table",
                ),
            ),
            gx.card(
                gx.heading("Provision New Enterprise Account", level=3),
                gx.form(
                    "users.create",
                    gx.column(
                        gx.input("Full Name", bind=new_user_name, placeholder="e.g. Maya Lin"),
                        gx.input("Work Email", bind=new_user_email, placeholder="e.g. maya@acme.corp"),
                        gx.select(
                            "Security Role",
                            bind=new_user_role,
                            options=["Super Admin", "DevOps Lead", "Data Engineer", "Viewer"],
                        ),
                        gx.spacer(10),
                        gx.button("Provision User", variant="primary"),
                    ),
                    id="create-user-form",
                ),
            ),
            columns=2,
            gap=20,
        ),
    )


@app.page("/settings")
def admin_settings():
    return gx.column(
        _admin_nav("/settings"),
        gx.heading("Organization Settings", level=1),
        gx.text("Configure global security policies, authentication providers, and identity rules.", variant="muted"),
        gx.spacer(20),
        gx.card(
            gx.tabs(
                [
                    gx.tab_item(
                        "General Profile",
                        gx.form(
                            "settings.update",
                            gx.column(
                                gx.input("org_name", label="Organization Name", state_ref=org_name),
                                gx.input("timeout_min", label="Session Inactivity Timeout (minutes)", state_ref=session_timeout),
                                gx.spacer(10),
                                gx.button("Save Profile Settings", variant="primary"),
                            ),
                            id="settings-form",
                        ),
                        tab_id="tab-general",
                    ),
                    gx.tab_item(
                        "Security & Compliance",
                        gx.column(
                            gx.callout("Hardware Security Keys (WebAuthn) and MFA enforced for all organization domains.", variant="success"),
                            gx.spacer(10),
                            gx.text("Data encryption at rest: AES-256 GCM. In transit: TLS 1.3 only."),
                            gx.text("Audit logging retention: 365 days compliant with SOC2 Type II."),
                        ),
                        tab_id="tab-security",
                    ),
                ],
                id="settings-tabs",
            ),
        ),
    )


@app.page("/maintenance")
def admin_maintenance():
    return gx.column(
        _admin_nav("/maintenance"),
        gx.heading("System Operations & Data Backup", level=1),
        gx.text("Perform routine database maintenance, snapshot migrations, and cluster diagnostics.", variant="muted"),
        gx.spacer(20),
        gx.grid(
            gx.card(
                gx.heading("Global Database Snapshots", level=3),
                gx.text("Triggers snapshot encryption and replication across S3 Glacier deep storage archives.", variant="muted"),
                gx.spacer(10),
                gx.form(
                    "system.trigger_backup",
                    gx.button("Execute Full Database Snapshot", variant="danger"),
                    id="backup-form",
                ),
                gx.spacer(14),
                gx.job_panel(run_database_backup, id="backup-job-panel"),
            ),
            gx.card(
                gx.heading("Cluster Diagnostic Health", level=3),
                gx.callout("All 12 Kubernetes node pools reporting healthy status (P99 CPU: 34%, Memory: 61%).", variant="success"),
                gx.spacer(10),
                gx.text("Storage engine: WAL journal synchronized across 3 Raft consensus quorums."),
            ),
            columns=2,
            gap=20,
        ),
    )


if __name__ == "__main__":
    app.run(port=8003)

