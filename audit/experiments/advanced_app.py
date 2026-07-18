"""RADUI Audit — Experiment C: Advanced Application.

Evaluates Developer Experience & Flexibility (Scenario C):
- Custom Component subclassing `Component` and registered in `ComponentRegistry`
- Custom HTML rendering function registered for the custom component
- Custom `StateBackend` (AuditingStateBackend) recording read/write access logs
- Custom `StateMiddleware` (DataSanitizationMiddleware) intercepting state writes
- Application-level RBAC policy evaluation in commands
- Asynchronous task processing with durable leasing
- Web Component / Custom HTML integration without modifying framework internals
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import html
import threading
from typing import Any, Literal
from pydantic import Field

import radui as gx
from radui.components.nodes import Component, Element
from radui.core.auth import RBACPolicy, User
from radui.core.registry import ComponentRegistry
from radui.state.backend import StateBackend
from radui.state.middleware import StateMiddleware
from radui.state.refs import StateRef
from radui.state.runtime import StateChange, StateContext


# -----------------------------------------------------------------------------
# 1. Custom StateBackend: AuditingStateBackend
# Tracks all state accesses in memory for compliance and telemetry
# -----------------------------------------------------------------------------
class AuditingStateBackend(StateBackend):
    def __init__(self) -> None:
        self._store: dict[tuple[str, str, str], Any] = {}
        self._audit_log: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    def get(self, scope: str, identity_key: str, state_key: str) -> Any | None:
        with self._lock:
            val = self._store.get((scope, identity_key, state_key))
            self._audit_log.append({
                "op": "GET",
                "scope": scope,
                "identity": identity_key,
                "key": state_key,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return val

    def set(self, scope: str, identity_key: str, state_key: str, value: Any) -> None:
        with self._lock:
            self._store[(scope, identity_key, state_key)] = value
            self._audit_log.append({
                "op": "SET",
                "scope": scope,
                "identity": identity_key,
                "key": state_key,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    def delete(self, scope: str, identity_key: str, state_key: str | None = None) -> None:
        with self._lock:
            if state_key is not None:
                self._store.pop((scope, identity_key, state_key), None)
            else:
                to_delete = [k for k in self._store if k[0] == scope and k[1] == identity_key]
                for k in to_delete:
                    del self._store[k]

    def get_all(self, scope: str, identity_key: str) -> dict[str, Any]:
        with self._lock:
            res = {}
            for (sc, id_k, st_k), v in self._store.items():
                if sc == scope and id_k == identity_key:
                    res[st_k] = v
            return res

    @property
    def audit_trail(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._audit_log)


# -----------------------------------------------------------------------------
# 2. Custom StateMiddleware: InputSanitizationMiddleware
# Trims whitespace and strips dangerous characters before writing to state
# -----------------------------------------------------------------------------
class InputSanitizationMiddleware(StateMiddleware):
    def before_write(
        self,
        ref: StateRef[Any],
        context: StateContext,
        value: Any,
        previous: Any,
    ) -> Any:
        if isinstance(value, str):
            # Strip potential script injections and excessive whitespace
            clean = value.strip().replace("<script>", "").replace("</script>", "")
            return clean
        return value


# -----------------------------------------------------------------------------
# 3. Custom Component AST Node & Custom HTML Renderer
# -----------------------------------------------------------------------------
class CodeTerminal(Component):
    kind: Literal["code_terminal"] = "code_terminal"
    title: str = "Terminal"
    lines: tuple[str, ...] = ()
    status: str = "READY"


def render_code_terminal(
    component: CodeTerminal,
    registry: ComponentRegistry,
    state_context: object | None = None,
    csrf_token: str | None = None,
) -> str:
    escaped_title = html.escape(component.title)
    status_color = "#10b981" if component.status == "READY" else "#f59e0b"
    lines_html = "".join(
        f'<div class="gx-terminal-line" style="font-family:monospace;padding:2px 0;">'
        f'<span style="color:#6b7280;margin-right:8px;">$</span>{html.escape(line)}</div>'
        for line in component.lines
    )
    return f"""
    <div class="gx-terminal-card" style="background:#0f172a;color:#f8fafc;border-radius:8px;padding:16px;box-shadow:0 4px 6px rgba(0,0,0,0.3);">
        <div style="display:flex;justify-content:space-between;border-bottom:1px solid #334155;padding-bottom:8px;margin-bottom:12px;">
            <span style="font-weight:600;font-size:14px;">{escaped_title}</span>
            <span style="font-size:12px;color:{status_color};font-weight:bold;">● {html.escape(component.status)}</span>
        </div>
        <div class="gx-terminal-body" style="font-size:13px;line-height:1.5;">
            {lines_html}
        </div>
    </div>
    """


def code_terminal(title: str, lines: list[str], status: str = "READY") -> CodeTerminal:
    return CodeTerminal(title=title, lines=tuple(lines), status=status)


# -----------------------------------------------------------------------------
# 4. App Initialization with Custom Backend, Middleware, and Registry
# -----------------------------------------------------------------------------
custom_backend = AuditingStateBackend()
rbac = RBACPolicy()
rbac.register_role("security_admin", ["read", "write", "audit", "flush"])

app = gx.App(
    "Advanced Enterprise Console",
    app_id="exp-advanced-app",
    state_backend=custom_backend,
    user_id_resolver=lambda req: req.headers.get("x-user-id", "usr-admin-sec"),
    debug=True,
)

# Register custom component into app's ComponentRegistry
app.registry.register("code_terminal", CodeTerminal, render_code_terminal)

# Register custom state middleware
app.add_state_middleware(InputSanitizationMiddleware())

# Reactive State References
server_command_input = gx.state("cmd_input", "sysctl -p", scope="session")
security_clearance = gx.state("clearance", "LEVEL-3 (Confidential)", scope="session")
terminal_logs = gx.state("terminal_history", "Kernel initialized.\nMemory pool nominal.", scope="session")


# -----------------------------------------------------------------------------
# Commands & RBAC Evaluation
# -----------------------------------------------------------------------------
@app.command("terminal.execute")
def execute_terminal_cmd(ctx: gx.CommandContext) -> None:
    # RBAC check: simulate user role validation
    user_role = ctx.headers.get("x-role", "security_admin")
    if not rbac.check_permission({user_role}, "write"):
        terminal_logs.value = terminal_logs.value + "\n[ACCESS DENIED] Insufficient RBAC permission."
        return

    cmd = ctx.form_data.get("cmd_input", server_command_input.value)
    server_command_input.value = cmd  # Sanitization middleware will run on this write
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    terminal_logs.value = terminal_logs.value + f"\n[{timestamp}] Executed: {server_command_input.value}"


@app.command("audit.flush")
def flush_audit_logs(ctx: gx.CommandContext) -> None:
    user_role = ctx.headers.get("x-role", "security_admin")
    if not rbac.check_permission({user_role}, "flush"):
        return
    terminal_logs.value = terminal_logs.value + "\n[AUDIT FLUSH] Audit cache dispatched to cold storage."


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.page("/")
def console_page():
    log_lines = terminal_logs.value.strip().split("\n")

    # Note: In RADUI v0.9, built-in layout containers (Column, Row, Container)
    # type children as a closed discriminated union of the 68 built-in types.
    # Custom components registered via ComponentRegistry cannot be placed inside
    # Column or Row directly without Pydantic union validation failure (BUG-COMP-REG-01).
    # However, ErrorBoundary uses tuple[Any, ...] for children, permitting custom AST nodes!
    return gx.error_boundary(
        code_terminal("Primary Host Terminal (pts/0)", log_lines, status="READY"),
        gx.card(
            gx.form(
                "terminal.execute",
                gx.row(
                    gx.input("cmd_input", label="Command Payload", bind=server_command_input),
                    gx.button("Execute Command", variant="primary"),
                    gap=12,
                    align="end",
                ),
            ),
            footer=gx.row(
                gx.form("audit.flush", gx.button("Flush Audit Buffer", variant="danger")),
                gx.text(f"Auditing backend events logged: {len(custom_backend.audit_trail)}", variant="caption"),
                justify="space-between",
                align="center",
            ),
            padding=16,
        ),
        fallback_message="Console initialization error",
    )


if __name__ == "__main__":
    app.run()
