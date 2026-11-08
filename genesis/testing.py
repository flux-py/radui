from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from starlette.testclient import TestClient

from radui.core.app import App
from radui.core.registry import ComponentRegistry
from radui.renderers.html import HTMLRenderer


class _FormExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        if tag == "form":
            self._current = {
                "id": data.get("id", ""),
                "action": data.get("action", ""),
                "command": data.get("data-gx-command", ""),
                "fields": {},
            }
            self.forms.append(self._current)
        elif tag == "input" and self._current is not None:
            name = data.get("name")
            if name:
                self._current["fields"][name] = data.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._current = None


class TestHarness:
    """High-level component and application testing harness for RADUI applications."""

    __test__ = False

    def __init__(self, app: App | None = None) -> None:
        self.app = app
        self._client: TestClient | None = None
        self.renderer = HTMLRenderer(ComponentRegistry.builtins())

    @property
    def client(self) -> TestClient:
        if self.app is None:
            raise ValueError("TestHarness requires an App instance to create a test client")
        if self._client is None:
            self._client = TestClient(self.app.asgi())
        return self._client

    def render_component(self, component: Any) -> str:
        """Render a single component directly to HTML without starting a server."""
        return self.renderer.render_component(component)

    def get_page(self, path: str = "/") -> str:
        """Fetch a page via the test client and return its HTML text."""
        res = self.client.get(path)
        if res.status_code != 200:
            raise AssertionError(f"GET {path} returned status {res.status_code}")
        return res.text

    def render(self, path: str = "/") -> str:
        """Alias for get_page."""
        return self.get_page(path)

    def assert_contains(self, path: str, text: str) -> None:
        """Assert that the rendered page HTML contains a specific substring."""
        html = self.get_page(path)
        if text not in html:
            raise AssertionError(f"Expected {text!r} in GET {path} response HTML")

    def assert_component_exists(self, path: str, component_id: str) -> None:
        """Assert that an element with data-gx-id or id matching component_id exists in page."""
        html = self.get_page(path)
        marker = f'id="{component_id}"'
        marker2 = f'data-gx-id="{component_id}"'
        if marker not in html and marker2 not in html:
            raise AssertionError(f"Component with id {component_id!r} not found in GET {path}")

    def extract_form(self, html: str, command: str) -> tuple[str, dict[str, str]]:
        """Extract action endpoint and pre-filled hidden tokens for a command form."""
        parser = _FormExtractor()
        parser.feed(html)
        for f in parser.forms:
            if f["command"] == command:
                return f["action"], dict(f["fields"])
        raise AssertionError(f"Form with command {command!r} not found in page HTML")

    def get_forms(self, path: str = "/") -> dict[str, dict[str, Any]]:
        """Extract all forms on the page keyed by command name."""
        html = self.get_page(path)
        parser = _FormExtractor()
        parser.feed(html)
        forms_by_cmd: dict[str, dict[str, Any]] = {}
        for f in parser.forms:
            cmd = f["command"]
            forms_by_cmd[cmd] = {
                "id": f["id"],
                "action": f["action"],
                "inputs": dict(f["fields"]),
            }
        return forms_by_cmd

    def dispatch_form(
        self,
        command_name: str,
        fields: dict[str, Any] | None = None,
        path: str = "/",
    ) -> dict[str, Any]:
        """Locate a form on the page, populate submitted fields, dispatch POST, and return JSON."""
        page_html = self.get_page(path)
        action, form_fields = self.extract_form(page_html, command_name)
        if fields:
            for k, v in fields.items():
                form_fields[k] = str(v)
        res = self.client.post(action, data=form_fields)
        return res.json()

    def dispatch(
        self,
        command_name: str,
        fields: dict[str, Any] | None = None,
        path: str = "/",
    ) -> dict[str, Any]:
        """Alias for dispatch_form."""
        return self.dispatch_form(command_name, fields, path=path)
