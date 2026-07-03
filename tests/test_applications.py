from __future__ import annotations

from html.parser import HTMLParser
from starlette.testclient import TestClient

import examples.ai_agent_workbench.app as agent_app_module
import examples.analytics_dashboard.app as analytics_app_module
import examples.saas_admin.app as saas_app_module


class FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, object]] = []
        self.current: dict[str, object] | None = None

    def handle_starttag(self, tag: str, attrs):
        data = dict(attrs)
        if tag == "form":
            self.current = {"action": data.get("action"), "command": data.get("data-gx-command"), "fields": {}}
            self.forms.append(self.current)
        elif tag in {"input", "textarea", "select"} and self.current is not None:
            name = data.get("name")
            if name:
                fields = self.current["fields"]
                assert isinstance(fields, dict)
                if data.get("type") == "checkbox":
                    if "checked" in data:
                        fields[name] = data.get("value", "on")
                else:
                    fields[name] = data.get("value", "")

    def handle_endtag(self, tag: str):
        if tag == "form":
            self.current = None


def get_form(html: str, command: str) -> tuple[str, dict[str, str]]:
    parser = FormParser()
    parser.feed(html)
    for form in parser.forms:
        if form["command"] == command:
            fields = form["fields"]
            assert isinstance(fields, dict)
            return str(form["action"]), {k: str(v) for k, v in fields.items()}
    raise AssertionError(f"form command not found in page: {command}")


def test_ai_agent_workbench_app():
    app = agent_app_module.app
    with TestClient(app.asgi()) as client:
        # 1. Page render
        res = client.get("/")
        assert res.status_code == 200
        assert "AI Agent" in res.text and "RAG Workbench" in res.text
        assert "Agent Conversation Stream" in res.text
        assert "Vector Store" in res.text

        # 2. Submit chat message command
        action, fields = get_form(res.text, "chat.send")
        fields["message"] = "How does RADUI reactive state work?"
        post_res = client.post(action, data=fields)
        assert post_res.status_code == 200
        data = post_res.json()
        assert data["ok"] is True
        assert len(data["patches"]) >= 1

        # 3. Trigger RAG indexing job
        res_after = client.get("/")
        rag_action, rag_fields = get_form(res_after.text, "rag.start_index")
        rag_res = client.post(rag_action, data=rag_fields)
        assert rag_res.status_code == 200
        assert rag_res.json()["ok"] is True

        # 4. Trigger human-in-the-loop approval
        app_action, app_fields = get_form(res_after.text, "action.approve")
        app_res = client.post(app_action, data=app_fields)
        assert app_res.status_code == 200
        assert app_res.json()["ok"] is True


def test_analytics_dashboard_app():
    app = analytics_app_module.app
    with TestClient(app.asgi()) as client:
        # 1. Page render
        res = client.get("/")
        assert res.status_code == 200
        assert "Executive Analytics Cockpit" in res.text
        assert "Total Revenue" in res.text
        assert "<svg" in res.text  # pure SVG charts rendered
        assert "Regional Cluster Availability" in res.text

        # 2. Apply region filter
        action, fields = get_form(res.text, "filters.apply")
        fields["region"] = "Europe"
        fields["metric"] = "Daily Active Users"
        post_res = client.post(action, data=fields)
        assert post_res.status_code == 200
        assert post_res.json()["ok"] is True

        # Verify page reflects Europe dataset
        res_eur = client.get("/")
        assert "Europe" in res_eur.text
        assert "€980,400" in res_eur.text

        # 3. Trigger background OLAP aggregation
        sync_action, sync_fields = get_form(res_eur.text, "analytics.refresh")
        sync_res = client.post(sync_action, data=sync_fields)
        assert sync_res.status_code == 200
        assert sync_res.json()["ok"] is True


def test_saas_admin_app():
    app = saas_app_module.app
    with TestClient(app.asgi()) as client:
        # 1. Dashboard page
        res = client.get("/")
        assert res.status_code == 200
        assert "Executive System Health" in res.text
        assert "Acme Enterprise" in res.text

        # 2. Users page
        res_users = client.get("/users")
        assert res_users.status_code == 200
        assert "Users" in res_users.text and "Access Governance" in res_users.text
        assert "Active Directory Roster" in res_users.text

        # Create new user
        action, fields = get_form(res_users.text, "users.create")
        fields["name"] = "Dr. Ada Lovelace"
        fields["email"] = "ada@acme.corp"
        fields["role"] = "Super Admin"
        post_res = client.post(action, data=fields)
        assert post_res.status_code == 200
        assert post_res.json()["ok"] is True

        # Verify new user is in roster
        res_users2 = client.get("/users")
        assert "Dr. Ada Lovelace" in res_users2.text

        # 3. Settings page
        res_settings = client.get("/settings")
        assert res_settings.status_code == 200
        assert "Organization Settings" in res_settings.text
        assert "General Profile" in res_settings.text
        assert "Security" in res_settings.text and "Compliance" in res_settings.text

        # Update settings
        action_s, fields_s = get_form(res_settings.text, "settings.update")
        fields_s["org_name"] = "Acme Global Industries"
        fields_s["timeout_min"] = "45"
        res_s = client.post(action_s, data=fields_s)
        assert res_s.status_code == 200
        assert res_s.json()["ok"] is True

        # 4. Maintenance page
        res_maint = client.get("/maintenance")
        assert res_maint.status_code == 200
        assert "System Operations" in res_maint.text and "Data Backup" in res_maint.text

        # Trigger backup job
        action_b, fields_b = get_form(res_maint.text, "system.trigger_backup")
        res_b = client.post(action_b, data=fields_b)
        assert res_b.status_code == 200
        assert res_b.json()["ok"] is True

