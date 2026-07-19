"""Unit and integration test runner for RADUI Audit Developer Experience Experiments."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from audit.experiments.beginner_app import app as beginner_app
from audit.experiments.intermediate_app import app as intermediate_app
from audit.experiments.advanced_app import app as advanced_app, custom_backend


def test_beginner_app_routes_and_forms():
    with TestClient(beginner_app.asgi()) as client:
        # 1. Main survey page
        res = client.get("/")
        assert res.status_code == 200
        assert "Developer Experience Survey" in res.text
        assert "Alex Developer" in res.text
        assert "Satisfaction Score" in res.text

        # 2. Docs subpage
        res_docs = client.get("/docs")
        assert res_docs.status_code == 200
        assert "Documentation &amp; Help" in res_docs.text or "Documentation & Help" in res_docs.text


def test_intermediate_app_routes_and_components():
    with TestClient(intermediate_app.asgi()) as client:
        # 1. Root / Dashboard with persistent layout
        res = client.get("/")
        assert res.status_code == 200
        assert "TelemetryOps Platform" in res.text
        assert "Throughput (QPS)" in res.text
        assert "48,200" in res.text
        assert "us-east-cluster-01" in res.text
        assert "Fault-Tolerant Inspection Module" in res.text

        # 2. Analytics page
        res_analytics = client.get("/analytics")
        assert res_analytics.status_code == 200
        assert "Cluster Performance Analytics" in res_analytics.text
        assert "TelemetryOps Platform" in res_analytics.text  # persistent shell layout preserved

        # 3. Settings page
        res_settings = client.get("/settings")
        assert res_settings.status_code == 200
        assert "Operational Settings" in res_settings.text
        assert "User Role Title" in res_settings.text


def test_advanced_app_custom_components_and_backend():
    with TestClient(advanced_app.asgi()) as client:
        # 1. Test custom component rendering
        res = client.get("/")
        assert res.status_code == 200
        assert "gx-terminal-card" in res.text
        assert "Primary Host Terminal (pts/0)" in res.text
        assert "Kernel initialized." in res.text
        assert "● READY" in res.text

        # 2. Verify AuditingStateBackend tracked reads
        assert len(custom_backend.audit_trail) > 0
        get_events = [e for e in custom_backend.audit_trail if e["op"] == "GET"]
        assert len(get_events) > 0

