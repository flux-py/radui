from __future__ import annotations

import inspect
import logging
import os
from contextlib import asynccontextmanager
import re
import secrets
import time
from collections import OrderedDict
from threading import RLock
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.parse import parse_qsl

import anyio
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route

from radui.components.nodes import (
    ActionCard,
    Button,
    Checkbox,
    Component,
    Diagram,
    Form,
    Input,
    JobPanel,
    RadioGroup,
    Select,
    Switch,
    Textarea,
    TreeView,
)
from radui.core.auth import RBACPolicy, User
from radui.core.ir import AppMetadata, ApplicationIR, CommandSpec, JobSpec, RouteSpec
from radui.core.registry import ComponentRegistry
from radui.core.theme import Theme
from radui.inspector.collector import TraceCollector
from radui.renderers.html import CLIENT_JS, EMBED_JS, HTMLRenderer
from radui.state import StateBackend, StateChange, StateContext, StateRuntime
from radui.jobs import JobBackend, JobDefinition, JobNotFoundError, JobSnapshot, LocalJobBackend
from radui.transport import EventBackend, EventBroker
from radui.core.idempotency import (
    IdempotencyBackend,
    InMemoryIdempotencyBackend,
    IdempotencyBackendUnavailableError,
    StaleLeaseError,
    compute_payload_fingerprint,
)
from radui.core.outbox import TransactionalOutbox


_PAGE_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")
_COMMAND_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_ACTION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_PAGE_COMPONENT_ID = "__page__"
_FORM_CONTROL_TYPES = (Input, Checkbox, Textarea, Select, Switch, RadioGroup)
_LOGGER = logging.getLogger("radui")
DEFAULT_PORT = int(os.environ.get("RADUI_PORT", "3000"))
_ACTIVE_APP: App | None = None


def notify(
    message: str,
    title: str = "",
    variant: str = "info",
    duration: int = 4000,
    session_id: str | None = None,
) -> list[EventRecord]:
    """Publish a global real-time toast notification via the active app's SSE event broker."""
    if _ACTIVE_APP is not None:
        return _ACTIVE_APP.notify(message, title=title, variant=variant, duration=duration, session_id=session_id)
    return []



def _json_response(
    data: Any,
    *,
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    response = JSONResponse(data, status_code=status_code, headers=headers)
    response.headers["Cache-Control"] = "no-store"
    return response


@dataclass(frozen=True)
class PageDefinition:
    path: str
    title: str
    handler: Callable[..., Component]
    require_auth: bool = False
    require_role: str | None = None
    require_permission: str | None = None


@dataclass(frozen=True)
class CommandDefinition:
    command_id: str
    handler: Callable[["CommandContext"], Any]
    require_auth: bool = False
    require_role: str | None = None
    require_permission: str | None = None


@dataclass
class CommandContext:
    """Context passed to a registered command handler."""

    request: Request
    state: StateContext
    form_data: Mapping[str, str]
    command_id: str
    action_id: str
    fence_token: int = 1
    outbox: Any | None = None

    @property
    def session_id(self) -> str:
        return self.state.session_id

    @property
    def user_id(self) -> str | None:
        return self.state.user_id

    @property
    def current_user(self) -> User | None:
        user_resolver = getattr(self.request.app.state, "user_resolver", None) if hasattr(self.request, "app") and hasattr(self.request.app, "state") else None
        if user_resolver is not None:
            return user_resolver(self.request)
        if self.user_id:
            return User(id=self.user_id, username=self.user_id)
        return None

    def has_role(self, role: str) -> bool:
        user = self.current_user
        if user is None:
            return False
        return user.has_role(role)

    def has_permission(self, permission: str) -> bool:
        user = self.current_user
        if user is None:
            return False
        return user.has_permission(permission)

    @property
    def params(self) -> Mapping[str, str]:
        return self.form_data

    def read(self, ref: Any) -> Any:
        return self.state.read(ref)

    def write(self, ref: Any, value: Any) -> StateChange:
        return self.state.write(ref, value)

    def batch(self):
        return self.state.batch()

    def transaction(self):
        return self.state.transaction()


class App:
    """Python-first application registry and ASGI runtime.

    RADUI manages signed browser session identity, CSRF validation, command
    dispatch, state invalidation, job observation and SSE fan-out. The default
    job backend is process-local; authentication remains the host application's
    responsibility.
    """

    def __init__(
        self,
        name: str = "RADUI App",
        *,
        title: str | None = None,
        app_id: str | None = None,
        session_secret: str | None = None,
        session_cookie_secure: bool = False,
        user_id_resolver: Callable[[Request], str | None] | None = None,
        max_form_bytes: int = 64 * 1024,
        job_backend: JobBackend | None = None,
        debug: bool = False,
        theme: Theme | None = None,
        command_palette: bool = True,
        state_backend: StateBackend | None = None,
        idempotency_backend: IdempotencyBackend | None = None,
        event_backend: EventBackend | None = None,
        outbox: TransactionalOutbox | None = None,
        telemetry_endpoint: str | None = None,
        tenant_id_resolver: Callable[[Request], str | None] | None = None,
        tenant_membership_validator: Callable[[Request, str | None, str | None], bool | Any] | None = None,
        allow_untrusted_tenant_headers: bool = True,
        multi_tenant: bool = False,
    ) -> None:
        effective_name = title or name
        normalized_id = app_id or _PAGE_ID_RE.sub("-", effective_name.strip().lower()).strip("-") or "RADUI-app"
        self.metadata = AppMetadata(id=normalized_id, name=effective_name)
        self.title = effective_name
        self.debug = debug
        self.multi_tenant = multi_tenant
        self.theme = theme
        self.command_palette = command_palette
        self.inspector = TraceCollector()
        if telemetry_endpoint:
            from radui.inspector.otlp import OTLPExporter
            self.inspector.set_exporter(OTLPExporter(endpoint=telemetry_endpoint, service_name=self.metadata.name))
        self.registry = ComponentRegistry.builtins()
        self.renderer = HTMLRenderer(self.registry)
        self.state_runtime = StateRuntime(self.metadata.id, backend=state_backend)
        self.idempotency: IdempotencyBackend = idempotency_backend or InMemoryIdempotencyBackend()
        self.events = EventBroker(backend=event_backend)
        self.outbox: TransactionalOutbox = outbox or TransactionalOutbox()
        self.worker_id = f"worker-{secrets.token_hex(4)}"
        self.jobs: JobBackend = job_backend if job_backend is not None else LocalJobBackend()
        self.jobs.bind_callbacks(
            on_update=self._on_job_update,
            on_state_changes=self._on_job_state_changes,
        )
        if session_secret is not None and len(session_secret) < 32:
            raise ValueError("session_secret must contain at least 32 characters")
        self._session_secret = session_secret or secrets.token_urlsafe(48)
        self._session_secret_is_ephemeral = session_secret is None
        self._session_cookie_secure = session_cookie_secure
        self._user_id_resolver = user_id_resolver
        self._tenant_id_resolver = tenant_id_resolver
        self._tenant_membership_validator = tenant_membership_validator
        self._allow_untrusted_tenant_headers = allow_untrusted_tenant_headers
        if max_form_bytes < 1024:
            raise ValueError("max_form_bytes must be at least 1024")
        self._max_form_bytes = max_form_bytes
        self._pages: dict[str, PageDefinition] = {}
        self._commands: dict[str, CommandDefinition] = {}
        self._jobs: dict[str, JobDefinition] = {}
        self._layouts: list[tuple[str, Callable[..., Component]]] = []
        self._action_cache: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
        self._action_guard = RLock()
        self._actions_in_progress: set[tuple[str, str]] = set()
        self._action_cache_limit = 1024
        self._startup_hooks: list[Callable[..., Any]] = []
        self._shutdown_hooks: list[Callable[..., Any]] = []
        self._shutting_down: bool = False
        self._active_commands_count: int = 0
        self.drain_timeout: float = 5.0
        self._custom_middleware: list[Middleware] = []
        self._asgi: Starlette | None = None

        global _ACTIVE_APP
        _ACTIVE_APP = self

    def state_context(
        self,
        *,
        session_id: str,
        user_id: str | None = None,
        view_id: str = "default",
        tenant_id: str | None = None,
    ) -> StateContext:
        """Create an explicit state context for trusted host/session identities."""
        return self.state_runtime.context(
            session_id=session_id,
            user_id=user_id,
            view_id=view_id,
            tenant_id=tenant_id,
        )

    def page(
        self,
        path: str,
        *,
        title: str | None = None,
        require_auth: bool = False,
        require_role: str | None = None,
        require_permission: str | None = None,
    ):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("page path must be an absolute application path beginning with one '/'")
        if "?" in path or "#" in path:
            raise ValueError("page paths must not contain query strings or fragments")
        if path.startswith("/_gx"):
            raise ValueError("/_gx is reserved for RADUI runtime endpoints")

        def decorator(handler: Callable[..., Component]):
            if path in self._pages:
                raise ValueError(f"page already registered: {path}")
            page_title = title or self.metadata.name
            self._pages[path] = PageDefinition(
                path,
                page_title,
                handler,
                require_auth=require_auth,
                require_role=require_role,
                require_permission=require_permission,
            )
            self._asgi = None
            return handler

        return decorator

    def layout(self, path_prefix: str = "/"):
        """Register a persistent nested layout wrapping pages that match path_prefix."""
        if not path_prefix.startswith("/"):
            raise ValueError("layout path_prefix must start with '/'")

        def decorator(handler: Callable[..., Component]):
            self._layouts.append((path_prefix, handler))
            self._asgi = None
            return handler

        return decorator

    def notify(
        self,
        message: str,
        title: str = "",
        variant: str = "info",
        duration: int = 4000,
        session_id: str | None = None,
    ) -> list[EventRecord]:
        """Publish a global or session-specific real-time toast notification via SSE stream."""
        data = {
            "message": message,
            "title": title,
            "variant": variant,
            "duration": duration,
        }
        records = []
        if session_id:
            records.append(self.events.publish(session_id, "gx:toast", data))
        else:
            with self.events._lock:
                target_sessions = set(self.events._subscribers.keys()) | set(self.events._sequences.keys())
            if not target_sessions:
                target_sessions = {"global"}
            for sid in target_sessions:
                records.append(self.events.publish(sid, "gx:toast", data))
        return records

    def on_startup(self, handler: Callable[..., Any]) -> Callable[..., Any]:
        """Register a callback to run on application startup."""
        self._startup_hooks.append(handler)
        return handler

    def on_shutdown(self, handler: Callable[..., Any]) -> Callable[..., Any]:
        """Register a callback to run on application shutdown."""
        self._shutdown_hooks.append(handler)
        return handler

    def add_state_middleware(self, mw: Any) -> None:
        """Register a state middleware intercepting reactive state reads and writes."""
        self.state_runtime.add_middleware(mw)

    def add_middleware(self, middleware_class: Any, **options: Any) -> None:
        """Register a standard ASGI middleware component to the application pipeline."""
        if self._asgi is not None:
            raise RuntimeError("Cannot add middleware after ASGI application has been initialized")
        self._custom_middleware.append(Middleware(middleware_class, **options))

    def command(
        self,
        command_id: str,
        *,
        require_auth: bool = False,
        require_role: str | None = None,
        require_permission: str | None = None,
    ):
        if not _COMMAND_RE.fullmatch(command_id):
            raise ValueError("invalid command identifier")

        def decorator(handler: Callable[[CommandContext], Any]):
            if command_id in self._commands:
                raise ValueError(f"command already registered: {command_id}")
            self._commands[command_id] = CommandDefinition(
                command_id,
                handler,
                require_auth=require_auth,
                require_role=require_role,
                require_permission=require_permission,
            )
            self._asgi = None
            return handler

        return decorator

    def require_auth(self, command_id: str):
        return self.command(command_id, require_auth=True)

    def require_role(self, role: str):
        def wrapper(command_id: str):
            return self.command(command_id, require_role=role)
        return wrapper

    def job(self, job_id: str):
        """Register an asynchronous background job handler.

        The decorated name becomes a JobDefinition with ``submit()``, ``get()``
        and ``cancel()`` methods. Job handlers receive JobContext first.
        """
        if not _COMMAND_RE.fullmatch(job_id):
            raise ValueError("invalid job identifier")

        def decorator(handler: Callable[..., Any]) -> JobDefinition:
            if not inspect.iscoroutinefunction(handler):
                raise TypeError("RADUI job handlers must be async functions")
            if job_id in self._jobs:
                raise ValueError(f"job already registered: {job_id}")
            definition = JobDefinition(job_id, handler, self.jobs)
            self._jobs[job_id] = definition
            self._asgi = None
            return definition

        return decorator

    def _on_job_update(self, snapshot: JobSnapshot) -> None:
        self.inspector.record(
            "job",
            snapshot.name,
            session_id=snapshot.session_id,
            details={
                "job_id": snapshot.id,
                "status": snapshot.status.value,
                "progress": snapshot.progress,
            },
        )
        for view_id, component_ids in self.jobs.observers(snapshot.session_id, snapshot.name):
            self.events.publish(
                snapshot.session_id,
                "invalidate",
                {
                    "view_id": view_id,
                    "component_ids": list(component_ids),
                    "job_id": snapshot.id,
                    "job_status": snapshot.status.value,
                },
            )

    def _on_job_state_changes(self, changes: list[StateChange], context: StateContext) -> None:
        for change in changes:
            self.inspector.record(
                "state",
                change.key,
                session_id=context.session_id,
                details={
                    "previous": change.previous,
                    "value": change.value,
                    "revision": change.revision,
                },
            )
            for invalidation in change.invalidations:
                self.events.publish(
                    invalidation.context.session_id,
                    "invalidate",
                    {
                        "view_id": invalidation.context.view_id,
                        "component_ids": list(invalidation.component_ids),
                        "state": change.key,
                        "revision": change.revision,
                    },
                )

    def _session(self, request: Request) -> tuple[str, str]:
        session_id = request.session.get("gx_session_id")
        if not isinstance(session_id, str) or len(session_id) < 24:
            session_id = secrets.token_urlsafe(32)
            request.session["gx_session_id"] = session_id
        csrf_token = request.session.get("gx_csrf_token")
        if not isinstance(csrf_token, str) or len(csrf_token) < 24:
            csrf_token = secrets.token_urlsafe(32)
            request.session["gx_csrf_token"] = csrf_token
        return session_id, csrf_token

    async def _user_id(self, request: Request) -> str | None:
        if self._user_id_resolver is None:
            return None
        result = self._user_id_resolver(request)
        if inspect.isawaitable(result):
            result = await result
        if result is not None and (not isinstance(result, str) or not result):
            raise RuntimeError("user_id_resolver must return a non-empty string or None")
        return result

    async def _state_context(self, request: Request, view_id: str) -> tuple[StateContext, str]:
        session_id, csrf_token = self._session(request)
        user_id = await self._user_id(request)
        tenant_id = None
        if self._tenant_id_resolver is not None:
            tenant_id = self._tenant_id_resolver(request)
            if inspect.isawaitable(tenant_id):
                tenant_id = await tenant_id
        elif "x-tenant-id" in request.headers or "tenant-id" in request.headers:
            candidate = request.headers.get("x-tenant-id") or request.headers.get("tenant-id")
            if not self._allow_untrusted_tenant_headers and self._tenant_membership_validator is None:
                raise HTTPException(
                    status_code=403,
                    detail="Untrusted tenant headers are disabled. Configure tenant_id_resolver or tenant_membership_validator.",
                )
            tenant_id = candidate

        if tenant_id and self._tenant_membership_validator is not None:
            authorized = self._tenant_membership_validator(request, user_id, tenant_id)
            if inspect.isawaitable(authorized):
                authorized = await authorized
            if not authorized:
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied: user {user_id or 'anonymous'} is not an authorized member of tenant {tenant_id}",
                )

        if self.multi_tenant and tenant_id is None:
            raise HTTPException(
                status_code=403,
                detail="Tenant context required: multi-tenant application requires an authenticated tenant identity.",
            )

        return self.state_context(
            session_id=session_id,
            user_id=user_id,
            view_id=view_id,
            tenant_id=tenant_id,
        ), csrf_token

    def _reconcile_dependencies(self, root: Component, state_context: StateContext) -> None:
        retained = {_PAGE_COMPONENT_ID}

        def walk(node: Component) -> None:
            if node.id is not None:
                retained.add(node.id)
            for child in getattr(node, "children", ()):
                walk(child)

        walk(root)
        self.state_runtime.dependencies.reconcile_context(state_context.identity, retained)

    def _reconcile_job_observers(self, root: Component, state_context: StateContext) -> None:
        observed: dict[str, set[str]] = {}

        def walk(node: Component) -> None:
            if isinstance(node, JobPanel) and node.id is not None:
                observed.setdefault(node.job_name, set()).add(node.id)
            for child in getattr(node, "children", ()):
                walk(child)

        walk(root)
        self.jobs.reconcile_watchers(state_context.session_id, state_context.view_id, observed)

    def _match_pattern(self, pattern: str, url_path: str) -> dict[str, str] | None:
        regex = "^" + re.sub(r"\{([a-zA-Z0-9_]+)\}", r"(?P<\1>[^/]+)", pattern) + "$"
        match = re.match(regex, url_path)
        return match.groupdict() if match else None

    def _find_page(self, url_path: str) -> tuple[PageDefinition | None, dict[str, str]]:
        if url_path in self._pages:
            return self._pages[url_path], {}
        for pattern, page_def in self._pages.items():
            if "{" in pattern:
                match = self._match_pattern(pattern, url_path)
                if match is not None:
                    return page_def, match
        return None, {}

    def _build_root(
        self,
        page: PageDefinition,
        state_context: StateContext,
        path_params: dict[str, Any] | None = None,
    ) -> Component:
        with state_context.activate():
            with state_context.track_component(_PAGE_COMPONENT_ID):
                sig = inspect.signature(page.handler)
                if sig.parameters and path_params:
                    kwargs = {k: v for k, v in path_params.items() if k in sig.parameters}
                    root = page.handler(**kwargs)
                else:
                    root = page.handler()
            if not isinstance(root, Component):
                raise TypeError(f"page {page.path!r} must return a RADUI component")

            matching_layouts = [
                (prefix, l_fn)
                for prefix, l_fn in self._layouts
                if page.path == prefix or page.path.startswith(prefix.rstrip("/") + "/") or prefix == "/"
            ]
            matching_layouts.sort(key=lambda item: len(item[0]))
            for prefix, layout_fn in matching_layouts:
                layout_id = getattr(layout_fn, "_gx_layout_id", f"gx-layout-{prefix.strip('/') or 'root'}")
                with state_context.track_component(layout_id):
                    l_sig = inspect.signature(layout_fn)
                    if "outlet" in l_sig.parameters:
                        root = layout_fn(outlet=root)
                    else:
                        root = layout_fn(root)
                    if not isinstance(root, Component):
                        raise TypeError(f"layout for {page.path!r} must return a RADUI component")
                    if root.id is None:
                        root = root.model_copy(update={"id": layout_id})
                if root.id != layout_id:
                    state_context.runtime.dependencies.remap_component_id(
                        state_context.identity, layout_id, root.id
                    )

        seen: set[str] = set()

        def walk(node: Component) -> None:
            if node.id is not None:
                if node.id in seen:
                    raise ValueError(f"duplicate component id in page {page.path!r}: {node.id}")
                seen.add(node.id)
            for child in getattr(node, "children", ()):
                walk(child)
            for attr in ("first", "second"):
                if hasattr(node, attr):
                    val = getattr(node, attr)
                    if isinstance(val, Component):
                        walk(val)

        walk(root)
        self.registry.validate(root)
        self._validate_commands(root)
        return root

    def _validate_commands(self, root: Component) -> None:
        def walk(node: Component, inside_form: bool = False) -> None:
            if isinstance(node, Form):
                if inside_form:
                    raise ValueError("nested forms are not supported")
                if node.command not in self._commands:
                    raise ValueError(f"form references unregistered command: {node.command}")
                for child in node.children:
                    walk(child, True)
                return
            if isinstance(node, Button):
                if not inside_form:
                    if not node.command:
                        raise ValueError("Button must be placed inside a Form")
                    if node.command not in self._commands:
                        raise ValueError(f"Button references unregistered command: {node.command}")
                return
            if isinstance(node, _FORM_CONTROL_TYPES) and not inside_form:
                raise ValueError(f"{type(node).__name__} must be placed inside a Form")
            if isinstance(node, JobPanel):
                if node.job_name not in self._jobs:
                    raise ValueError(f"JobPanel references unregistered job: {node.job_name}")
                if node.id is None:
                    raise ValueError("JobPanel requires a stable component id")
            if isinstance(node, ActionCard):
                if node.approve_command not in self._commands:
                    raise ValueError(f"ActionCard references unregistered command: {node.approve_command}")
                if node.reject_command and node.reject_command not in self._commands:
                    raise ValueError(f"ActionCard references unregistered command: {node.reject_command}")
            if isinstance(node, Diagram):
                if node.on_node_click and node.on_node_click not in self._commands:
                    raise ValueError(f"Diagram references unregistered command: {node.on_node_click}")
            if isinstance(node, TreeView):
                if node.on_select_command and node.on_select_command not in self._commands:
                    raise ValueError(f"TreeView references unregistered command: {node.on_select_command}")
            for child in getattr(node, "children", ()):
                walk(child, inside_form)
            for attr in ("first", "second"):
                if hasattr(node, attr):
                    val = getattr(node, attr)
                    if isinstance(val, Component):
                        walk(val, inside_form)
        walk(root)

    def _find_form(self, root: Component, command_id: str) -> Form | None:
        result: Form | None = None

        def walk(node: Component) -> None:
            nonlocal result
            if isinstance(node, Form) and node.command == command_id:
                if result is not None:
                    raise ValueError(f"multiple forms use command {command_id!r} on one page")
                result = node
            elif isinstance(node, Button) and node.command == command_id:
                if result is not None:
                    raise ValueError(f"multiple triggers use command {command_id!r} on one page")
                result = Form(command=command_id, children=())
            elif isinstance(node, ActionCard) and (node.approve_command == command_id or node.reject_command == command_id):
                if result is not None:
                    raise ValueError(f"multiple forms use command {command_id!r} on one page")
                result = Form(command=command_id, children=())
            elif isinstance(node, Diagram) and node.on_node_click == command_id:
                if result is not None:
                    raise ValueError(f"multiple triggers use command {command_id!r} on one page")
                result = Form(command=command_id, children=())
            elif isinstance(node, TreeView) and node.on_select_command == command_id:
                if result is not None:
                    raise ValueError(f"multiple triggers use command {command_id!r} on one page")
                result = Form(command=command_id, children=())
            for child in getattr(node, "children", ()):
                walk(child)
            for attr in ("first", "second"):
                if hasattr(node, attr):
                    val = getattr(node, attr)
                    if isinstance(val, Component):
                        walk(val)
        walk(root)
        return result

    def _form_controls(self, form: Form) -> tuple[Any, ...]:
        controls: list[Any] = []

        def walk(node: Component) -> None:
            if isinstance(node, _FORM_CONTROL_TYPES):
                controls.append(node)
            for child in getattr(node, "children", ()):
                walk(child)
        walk(form)
        names = [control.name for control in controls]
        if len(names) != len(set(names)):
            raise ValueError("form contains duplicate bound field names")
        return tuple(controls)

    def _collect_form_updates(
        self, form: Form, submitted: Mapping[str, str]
    ) -> tuple[tuple[Any, Any], ...]:
        updates: list[tuple[Any, Any]] = []
        for control in self._form_controls(form):
            if isinstance(control, (Checkbox, Switch)):
                raw = "true" if control.name in submitted else "false"
            else:
                if control.name not in submitted:
                    raise ValueError(f"missing form field: {control.name}")
                raw = submitted[control.name]
            parsed = control.state_ref.validate_form_value(raw)
            updates.append((control.state_ref, parsed))
        return tuple(updates)

    async def _invoke_command(
        self,
        command: CommandDefinition,
        command_context: CommandContext,
        updates: tuple[tuple[Any, Any], ...],
    ) -> list[StateChange]:
        handler = command.handler
        state_context = command_context.state

        async def invoke_async() -> list[StateChange]:
            with state_context.activate(), state_context.capture_changes() as changes:
                for ref, value in updates:
                    state_context.write(ref, value)
                result = handler(command_context)
                if inspect.isawaitable(result):
                    await result
                return list(changes)

        if inspect.iscoroutinefunction(handler):
            return await invoke_async()

        def invoke_sync() -> list[StateChange]:
            with state_context.activate(), state_context.capture_changes() as changes:
                for ref, value in updates:
                    state_context.write(ref, value)
                handler(command_context)
                return list(changes)

        return await anyio.to_thread.run_sync(invoke_sync)

    def _reserve_action(self, key: tuple[str, str]) -> str:
        """Atomically reserve an action without holding an async lock across awaits.

        The guard is a short-lived threading lock so concurrent requests arriving
        on different event loops/threads cannot execute the same action twice.
        """
        with self._action_guard:
            cached = self._action_cache.get(key)
            if cached is not None:
                self._action_cache.move_to_end(key)
                return "replayed"
            if key in self._actions_in_progress:
                return "in_progress"
            self._actions_in_progress.add(key)
            return "execute"

    def _release_action(self, key: tuple[str, str]) -> None:
        with self._action_guard:
            self._actions_in_progress.discard(key)

    def _remember_action(self, key: tuple[str, str], result: dict[str, Any]) -> None:
        with self._action_guard:
            self._action_cache[key] = result
            self._action_cache.move_to_end(key)
            while len(self._action_cache) > self._action_cache_limit:
                self._action_cache.popitem(last=False)

    def drop_session(self, session_id: str) -> None:
        """Clear process-local state, replay history and idempotency entries on logout."""
        self.state_runtime.drop_session(session_id)
        self.jobs.drop_session(session_id)
        self.events.forget_session(session_id)
        with self._action_guard:
            for key in tuple(self._action_cache):
                if key[0] == session_id:
                    self._action_cache.pop(key, None)
            # An in-flight handler cannot safely be interrupted by session cleanup.
            # It releases its reservation in the request's finally block.

    def _patches(
        self,
        page: PageDefinition,
        state_context: StateContext,
        csrf_token: str,
        component_ids: set[str],
        path_params: dict[str, str] | None = None,
    ) -> list[dict[str, str]]:
        root = self._build_root(page, state_context, path_params=path_params)
        # Re-render once to refresh all dependency edges after conditional UI changes.
        with state_context.activate():
            self.renderer.render_component(root, state_context, csrf_token)
        self._reconcile_dependencies(root, state_context)
        self._reconcile_job_observers(root, state_context)
        return self.renderer.render_patch(
            page.title,
            root,
            component_ids,
            state_context=state_context,
            csrf_token=csrf_token,
        )

    def _publish_other_invalidations(
        self,
        changes: list[StateChange],
        current_context: StateContext,
    ) -> set[str]:
        current_ids: set[str] = set()
        for change in changes:
            for invalidation in change.invalidations:
                identity = invalidation.context
                if identity == current_context.identity:
                    current_ids.update(invalidation.component_ids)
                    continue
                self.events.publish(
                    identity.session_id,
                    "invalidate",
                    {
                        "view_id": identity.view_id,
                        "component_ids": list(invalidation.component_ids),
                        "state": change.key,
                        "revision": change.revision,
                    },
                )
        return current_ids

    async def _page_endpoint(self, request: Request, page: PageDefinition) -> Response:
        start_time = time.perf_counter()
        try:
            # Check route guards
            if page.require_auth or page.require_role or page.require_permission:
                session_id, _ = self._session(request)
                user_id = await self._user_id(request)
                user: User | None = None
                if self._user_id_resolver is not None:
                    resolved = self._user_id_resolver(request)
                    if resolved:
                        user = User(id=resolved, username=resolved)
                elif user_id:
                    user = User(id=user_id, username=user_id)

                if page.require_auth and user is None:
                    return HTMLResponse("<h1>401 Unauthorized</h1><p>Authentication required</p>", status_code=401)
                if page.require_role and (user is None or not user.has_role(page.require_role)):
                    return HTMLResponse("<h1>403 Forbidden</h1><p>Insufficient permissions</p>", status_code=403)
                if page.require_permission and (user is None or not user.has_permission(page.require_permission)):
                    return HTMLResponse("<h1>403 Forbidden</h1><p>Insufficient permissions</p>", status_code=403)

            view_path = request.url.path
            state_context, csrf_token = await self._state_context(request, view_path)
            event_cursor = self.events.current_sequence(state_context.session_id)
            root = self._build_root(page, state_context, path_params=dict(request.path_params))
            custom_css = self.theme.to_css() if self.theme is not None else ""
            html = self.renderer.render_document(
                page.title,
                root,
                state_context=state_context,
                csrf_token=csrf_token,
                view_id=view_path,
                event_cursor=event_cursor,
                debug=self.debug,
                custom_css=custom_css,
                command_palette=self.command_palette,
                direction=self.theme.direction if self.theme is not None else "ltr",
            )
            self._reconcile_dependencies(root, state_context)
            self._reconcile_job_observers(root, state_context)
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            self.inspector.record(
                "render",
                view_path,
                session_id=state_context.session_id,
                view_id=view_path,
                duration_ms=round(duration_ms, 2),
                details={"title": page.title},
            )
            return HTMLResponse(
                html,
                headers={
                    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; form-action 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'",
                    "X-Content-Type-Options": "nosniff",
                    "Referrer-Policy": "same-origin",
                    "Cache-Control": "no-store",
                },
            )
        except HTTPException as exc:
            return _json_response({"ok": False, "error": exc.detail}, status_code=exc.status_code)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            self.inspector.record(
                "error",
                page.path,
                duration_ms=round(duration_ms, 2),
                details={"error": str(exc)},
            )
            _LOGGER.exception("Page rendering failed")
            return PlainTextResponse("Internal Server Error", status_code=500)

    async def _command_endpoint(self, request: Request) -> Response:
        if self._shutting_down:
            return _json_response({"ok": False, "error": "Server is shutting down"}, status_code=503)

        self._active_commands_count += 1
        try:
            return await self._process_command(request)
        finally:
            self._active_commands_count -= 1

    async def _drain_commands(self, timeout: float = 5.0) -> None:
        start = time.monotonic()
        while self._active_commands_count > 0:
            if time.monotonic() - start >= timeout:
                _LOGGER.warning("Command draining timed out with %d active commands", self._active_commands_count)
                break
            await asyncio.sleep(0.02)

    async def _process_command(self, request: Request) -> Response:
        start_time = time.perf_counter()
        command_id = request.path_params["command_id"]
        command = self._commands.get(command_id)
        if command is None:
            return _json_response({"ok": False, "error": "Unknown command"}, status_code=404)
        if not request.headers.get("content-type", "").split(";", 1)[0].strip().lower() == "application/x-www-form-urlencoded":
            return _json_response({"ok": False, "error": "Unsupported form encoding"}, status_code=415)

        session_id, csrf_token = self._session(request)
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            return _json_response({"ok": False, "error": "Cross-origin request rejected"}, status_code=403)
        if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
            return _json_response({"ok": False, "error": "Cross-site request rejected"}, status_code=403)

        try:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > self._max_form_bytes:
                        return _json_response({"ok": False, "error": "Form body too large"}, status_code=413)
                except ValueError:
                    return _json_response({"ok": False, "error": "Invalid content length"}, status_code=400)

            # Consume the ASGI body incrementally so a missing or dishonest
            # Content-Length cannot force an unbounded request.body() allocation.
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > self._max_form_bytes:
                    return _json_response({"ok": False, "error": "Form body too large"}, status_code=413)
            decoded_body = body.decode("utf-8", errors="strict")
            if re.search(r"%(?![0-9A-Fa-f]{2})", decoded_body):
                return _json_response({"ok": False, "error": "Malformed form encoding"}, status_code=400)
            submitted_items = parse_qsl(
                decoded_body,
                keep_blank_values=True,
                max_num_fields=128,
                encoding="utf-8",
                errors="strict",
            )
            submitted: dict[str, str] = {}
            for key, value in submitted_items:
                if key in submitted:
                    return _json_response({"ok": False, "error": "Duplicate form fields are not supported"}, status_code=400)
                submitted[key] = value
        except ValueError as exc:
            if "Max number of fields" in str(exc):
                return _json_response({"ok": False, "error": "Too many form fields"}, status_code=400)
            return _json_response({"ok": False, "error": "Malformed form submission"}, status_code=400)
        except Exception:
            return _json_response({"ok": False, "error": "Malformed form submission"}, status_code=400)

        submitted_csrf = submitted.get("_csrf", "")
        if not secrets.compare_digest(submitted_csrf, csrf_token):
            return _json_response({"ok": False, "error": "Invalid CSRF token"}, status_code=403)
        action_id = submitted.get("_gx_action_id", "")
        if not _ACTION_ID_RE.fullmatch(action_id):
            return _json_response({"ok": False, "error": "Invalid action identifier"}, status_code=400)

        # The hidden view identifier is only a selector for a registered route;
        # it cannot create a new route or bypass the host's authentication logic.
        view_id = submitted.get("_gx_view_id", "")
        page, path_params = self._find_page(view_id)
        if page is None:
            return _json_response({"ok": False, "error": "Missing or invalid page context"}, status_code=400)

        owner_id = self.worker_id
        # Durable idempotency engine coordination
        fingerprint = compute_payload_fingerprint(command_id, submitted)
        try:
            durable_res = self.idempotency.begin(action_id, fingerprint=fingerprint, owner_id=owner_id)
        except IdempotencyBackendUnavailableError:
            return _json_response({"ok": False, "error": "Idempotency backend unavailable"}, status_code=503)

        if durable_res.conflict:
            return _json_response(
                {
                    "ok": False,
                    "error": "Action identifier re-used with differing payload fingerprint",
                    "conflict": True,
                    "error_code": "IDEMPOTENCY_PAYLOAD_MISMATCH",
                },
                status_code=409,
            )
        if durable_res.completed:
            resp = dict(durable_res.response or {"ok": True})
            resp["patches"] = []
            resp["replayed"] = True
            return _json_response(resp)
        if durable_res.in_progress:
            return _json_response(
                {
                    "ok": False,
                    "error": "This action is already processing; retry with the same action ID",
                    "error_code": "IDEMPOTENCY_IN_PROGRESS",
                },
                status_code=409,
                headers={"Retry-After": "1"},
            )

        fence_token = durable_res.fence_token
        key = (session_id, action_id)
        reservation = self._reserve_action(key)

        try:
            try:
                state_context, _ = await self._state_context(request, view_id)
                root = self._build_root(page, state_context, path_params=path_params)
                form = self._find_form(root, command_id)
                if form is None:
                    return _json_response({"ok": False, "error": "Command is not available on this page"}, status_code=404)
                controls = self._form_controls(form)
                allowed_fields = {"_csrf", "_gx_action_id", "_gx_view_id"}
                allowed_fields.update(control.name for control in controls)
                if not controls:
                    allowed_fields.update(k for k in submitted.keys() if not k.startswith("_gx_") and k != "_csrf")
                unexpected_fields = set(submitted) - allowed_fields
                if unexpected_fields:
                    return _json_response({"ok": False, "error": "Unexpected form fields"}, status_code=400)
                updates = self._collect_form_updates(form, submitted)
                command_context = CommandContext(
                    request=request,
                    state=state_context,
                    form_data={
                        key: value for key, value in submitted.items()
                        if not key.startswith("_")
                    },
                    command_id=command_id,
                    action_id=action_id,
                    fence_token=fence_token,
                    outbox=self.outbox,
                )
                if command.require_auth and not command_context.user_id:
                    return _json_response({"ok": False, "error": "Authentication required"}, status_code=401)
                if command.require_role and not command_context.has_role(command.require_role):
                    return _json_response({"ok": False, "error": f"Role required: {command.require_role}"}, status_code=403)
                if command.require_permission and not command_context.has_permission(command.require_permission):
                    return _json_response({"ok": False, "error": f"Permission required: {command.require_permission}"}, status_code=403)
                changes = await self._invoke_command(command, command_context, updates)
                for change in changes:
                    self.inspector.record(
                        "state",
                        change.key,
                        session_id=session_id,
                        view_id=view_id,
                        details={"previous": change.previous, "value": change.value, "revision": change.revision},
                    )
                current_ids = self._publish_other_invalidations(changes, state_context)
                reload_page = False
                try:
                    patches = self._patches(page, state_context, csrf_token, current_ids, path_params=path_params) if current_ids else []
                except Exception:
                    _LOGGER.exception("Command succeeded but rendering its UI patches failed")
                    patches = []
                    reload_page = True
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                self.inspector.record(
                    "command",
                    command_id,
                    session_id=session_id,
                    view_id=view_id,
                    duration_ms=round(duration_ms, 2),
                    details={"action_id": action_id, "form_data": command_context.form_data},
                )
                result = {"ok": True, "patches": patches, "reload": reload_page}
                self._remember_action(key, result)
                try:
                    self.idempotency.complete(action_id, result, fence_token=fence_token, owner_id=owner_id)
                except StaleLeaseError:
                    _LOGGER.warning("Command completed but idempotency lease was already reclaimed by another worker")
                except Exception:
                    pass
                return _json_response(result)
            except (ValueError, TypeError) as exc:
                try:
                    self.idempotency.fail(action_id, str(exc), fence_token=fence_token, owner_id=owner_id)
                except Exception:
                    pass
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                self.inspector.record(
                    "error",
                    command_id,
                    session_id=session_id,
                    view_id=view_id,
                    duration_ms=round(duration_ms, 2),
                    details={"error": str(exc)},
                )
                _LOGGER.info("RADUI command validation failed: %s", exc)
                return _json_response({"ok": False, "error": "Invalid command input"}, status_code=400)
            except HTTPException as exc:
                return _json_response({"ok": False, "error": exc.detail}, status_code=exc.status_code)
            except Exception as exc:
                try:
                    self.idempotency.fail(action_id, str(exc), fence_token=fence_token, owner_id=owner_id)
                except Exception:
                    pass
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                self.inspector.record(
                    "error",
                    command_id,
                    session_id=session_id,
                    view_id=view_id,
                    duration_ms=round(duration_ms, 2),
                    details={"error": str(exc)},
                )
                _LOGGER.exception("RADUI command failed")
                return _json_response({"ok": False, "error": "Command failed"}, status_code=500)
        finally:
            self._release_action(key)

    async def _refresh_endpoint(self, request: Request) -> Response:
        start_time = time.perf_counter()
        view_id = request.query_params.get("view_id", "")
        page, path_params = self._find_page(view_id)
        if page is None:
            return _json_response({"ok": False, "error": "Unknown view"}, status_code=404)
        ids = request.query_params.getlist("id")
        if len(ids) > 50 or any(not item or len(item) > 128 for item in ids):
            return _json_response({"ok": False, "error": "Invalid refresh request"}, status_code=400)
        try:
            state_context, csrf_token = await self._state_context(request, view_id)
            patches = self._patches(page, state_context, csrf_token, set(ids) or {_PAGE_COMPONENT_ID}, path_params=path_params)
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            self.inspector.record(
                "render",
                f"refresh:{view_id}",
                session_id=state_context.session_id,
                view_id=view_id,
                duration_ms=round(duration_ms, 2),
                details={"component_ids": list(ids)},
            )
            return _json_response({"ok": True, "patches": patches})
        except HTTPException as exc:
            return _json_response({"ok": False, "error": exc.detail}, status_code=exc.status_code)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            self.inspector.record(
                "error",
                f"refresh:{view_id}",
                duration_ms=round(duration_ms, 2),
                details={"error": str(exc)},
            )
            _LOGGER.exception("RADUI refresh failed")
            return _json_response({"ok": False, "error": "Refresh failed"}, status_code=500)

    async def _job_cancel_endpoint(self, request: Request) -> Response:
        session_id, csrf_token = self._session(request)
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            return _json_response({"ok": False, "error": "Cross-origin request rejected"}, status_code=403)
        if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
            return _json_response({"ok": False, "error": "Cross-site request rejected"}, status_code=403)
        supplied = request.headers.get("x-gx-csrf", "")
        if not secrets.compare_digest(supplied, csrf_token):
            return _json_response({"ok": False, "error": "Invalid CSRF token"}, status_code=403)
        try:
            if request.headers.get("content-length", "0") not in {"", "0"}:
                return _json_response({"ok": False, "error": "Unexpected request body"}, status_code=400)
            cancelled = await self.jobs.cancel(request.path_params["job_id"], session_id)
            return _json_response({"ok": True, "cancelled": cancelled})
        except JobNotFoundError:
            return _json_response({"ok": False, "error": "Job not found"}, status_code=404)
        except Exception:
            _LOGGER.exception("RADUI job cancellation failed")
            return _json_response({"ok": False, "error": "Cancellation failed"}, status_code=500)

    async def _health_endpoint(self, request: Request) -> Response:
        if self._shutting_down:
            return _json_response(
                {"status": "draining", "version": "1.0.0", "worker_id": self.worker_id},
                status_code=503,
            )
        return _json_response(
            {"status": "healthy", "version": "1.0.0", "worker_id": self.worker_id},
            status_code=200,
        )

    async def _events_endpoint(self, request: Request) -> Response:
        session_id, _ = self._session(request)
        raw_last_id = request.headers.get("last-event-id") or request.query_params.get("since")
        try:
            last_event_id = int(raw_last_id) if raw_last_id else None
            if last_event_id is not None and last_event_id < 0:
                raise ValueError
        except ValueError:
            return PlainTextResponse("Invalid Last-Event-ID", status_code=400)

        async def stream():
            async for event in self.events.stream(session_id, last_event_id=last_event_id):
                yield event

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    async def _inspect_traces_endpoint(self, request: Request) -> Response:
        limit = min(int(request.query_params.get("limit", 100)), 500)
        category = request.query_params.get("category")
        records = [r.to_dict() for r in self.inspector.get_records(category=category, limit=limit)]
        return _json_response({
            "ok": True,
            "records": records,
            "total": len(records),
            "stats": self.inspector.stats(),
        })

    async def _inspect_stats_endpoint(self, request: Request) -> Response:
        return _json_response({
            "ok": True,
            "stats": self.inspector.stats(),
        })

    async def _inspect_dag_endpoint(self, request: Request) -> Response:
        from radui.inspector.graph import extract_dag_structure, generate_dag_svg
        format_param = request.query_params.get("format", "").lower()
        accept_header = request.headers.get("accept", "").lower()
        if format_param == "json" or "application/json" in accept_header:
            data = extract_dag_structure(self.state_runtime.dependencies)
            return _json_response({"ok": True, **data})

        svg = generate_dag_svg(self.state_runtime.dependencies)
        return Response(content=svg, media_type="image/svg+xml")

    async def _inspect_page_endpoint(self, request: Request) -> Response:
        import html as html_lib
        from radui.inspector.graph import generate_dag_svg
        records = [r.to_dict() for r in self.inspector.get_records(limit=100)]
        stats = self.inspector.stats()
        rows = []
        for r in reversed(records[-50:]):
            cat = html_lib.escape(str(r.get("category", "")))
            name = html_lib.escape(str(r.get("name", "")))
            time_str = html_lib.escape(str(r.get("timestamp", ""))[-12:])
            sess = html_lib.escape(str(r.get("session_id", "") or "")[:8])
            dur = f"{r.get('duration_ms', 0):.1f}ms" if r.get("duration_ms") is not None else "-"
            det = html_lib.escape(str(r.get("details", "")))
            rows.append(f"<tr><td>{time_str}</td><td><span class='cat-badge cat-{cat}'>{cat}</span></td><td>{name}</td><td>{sess}</td><td>{dur}</td><td><small>{det}</small></td></tr>")
        rows_html = "".join(rows)
        dag_svg = generate_dag_svg(self.state_runtime.dependencies)
        html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>RADUI Inspector</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #090d16; color: #f8fafc; padding: 24px; margin: 0; }}
.stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; margin-bottom: 24px; }}
.stat-card {{ background: #111827; border-radius: 8px; padding: 16px; border: 1px solid #1e293b; }}
.stat-value {{ font-size: 24px; font-weight: 700; color: #38bdf8; margin-top: 4px; }}
table {{ width: 100%; border-collapse: collapse; font-family: ui-monospace, monospace; font-size: 13px; background: #111827; border-radius: 8px; overflow: hidden; }}
th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #1e293b; }}
th {{ background: #1f2937; color: #94a3b8; font-weight: 600; }}
.cat-badge {{ padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; }}
.cat-render {{ background: #1e3a8a; color: #93c5fd; }}
.cat-command {{ background: #14532d; color: #86efac; }}
.cat-state {{ background: #701a75; color: #f0abfc; }}
.cat-job {{ background: #78350f; color: #fde68a; }}
.cat-error {{ background: #7f1d1d; color: #fca5a5; }}
</style></head><body>
<div style="max-width: 1200px; margin: 0 auto;">
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
  <div>
    <h1 style="margin:0; font-size:22px;">RADUI Runtime Inspector</h1>
    <p style="margin:4px 0 0 0; color:#94a3b8; font-size:14px;">Live telemetry, execution traces and reactive stats</p>
  </div>
  <div>
    <a href="/_gx/inspect/dag" target="_blank" style="color:#a855f7; text-decoration:none; font-weight:600; margin-right: 18px;">Raw SVG DAG ↗</a>
    <a href="/" style="color:#38bdf8; text-decoration:none; font-weight:600;">← Back to App</a>
  </div>
</div>
<div class="stat-grid">
  <div class="stat-card"><div>Total Traces</div><div class="stat-value">{stats.get('total_records', 0)}</div></div>
  <div class="stat-card"><div>Application ID</div><div class="stat-value" style="font-size:18px">{self.metadata.id}</div></div>
  <div class="stat-card"><div>Pages</div><div class="stat-value">{len(self._pages)}</div></div>
  <div class="stat-card"><div>Commands</div><div class="stat-value">{len(self._commands)}</div></div>
  <div class="stat-card"><div>Jobs</div><div class="stat-value">{len(self._jobs)}</div></div>
</div>

<div style="margin-bottom: 24px;">
  <h2 style="font-size:17px; margin-bottom:12px;">Reactive Dependency Graph (SVG)</h2>
  <div style="background: #111827; border: 1px solid #1e293b; border-radius: 8px; padding: 16px; overflow-x: auto;">
    {dag_svg}
  </div>
</div>

<h2 style="font-size:17px; margin-bottom:12px;">Recent Execution Traces</h2>
<table>
<thead><tr><th>Time</th><th>Category</th><th>Name</th><th>Session</th><th>Duration</th><th>Details</th></tr></thead>
<tbody>{rows_html}</tbody>
</table>
</div>
</body></html>"""
        return HTMLResponse(html)
        return HTMLResponse(html)

    def to_ir(self, version: str = "0.4") -> ApplicationIR:
        route_specs = []
        export_session = "ir-export-session-" + secrets.token_urlsafe(8)
        export_user = "ir-export-user-" + secrets.token_urlsafe(8)
        try:
            for index, page in enumerate(self._pages.values()):
                # A static IR export cannot bind request/session state. It records
                # the declarative component tree as authored by the page function.
                context = self.state_context(
                    session_id=export_session,
                    user_id=export_user,
                    view_id=page.path,
                )
                root = self._build_root(page, context)
                route_specs.append(
                    RouteSpec(
                        id=f"route.{index + 1}",
                        path=page.path,
                        title=page.title,
                        root=root,
                    )
                )
            command_specs = tuple(CommandSpec(id=command_id) for command_id in sorted(self._commands))
            job_specs = tuple(JobSpec(id=job_id) for job_id in sorted(self._jobs))
            return ApplicationIR(
                version=version,
                app=self.metadata,
                routes=tuple(route_specs),
                commands=command_specs,
                jobs=job_specs,
            )
        finally:
            self.state_runtime.drop_session(export_session)
            self.state_runtime.drop_user(export_user)

    def asgi(self) -> Starlette:
        if self._asgi is not None:
            return self._asgi

        routes = [
            Route("/_gx/client.js", lambda request: PlainTextResponse(CLIENT_JS, media_type="application/javascript"), methods=["GET"]),
            Route("/_gx/embed.js", lambda request: PlainTextResponse(EMBED_JS, media_type="application/javascript"), methods=["GET"]),
            Route("/_gx/events", self._events_endpoint, methods=["GET"]),
            Route("/_gx/refresh", self._refresh_endpoint, methods=["GET"]),
            Route("/_gx/commands/{command_id}", self._command_endpoint, methods=["POST"]),
            Route("/_gx/jobs/{job_id}/cancel", self._job_cancel_endpoint, methods=["POST"]),
            Route("/_gx/inspect", self._inspect_page_endpoint, methods=["GET"]),
            Route("/_gx/inspect/traces", self._inspect_traces_endpoint, methods=["GET"]),
            Route("/_gx/inspect/stats", self._inspect_stats_endpoint, methods=["GET"]),
            Route("/_gx/inspect/dag", self._inspect_dag_endpoint, methods=["GET"]),
            Route("/_gx/health", self._health_endpoint, methods=["GET"]),
        ]
        for page in self._pages.values():
            async def endpoint(request: Request, registered_page: PageDefinition = page):
                return await self._page_endpoint(request, registered_page)
            routes.append(Route(page.path, endpoint, methods=["GET"]))

        middleware = [
            Middleware(
                SessionMiddleware,
                secret_key=self._session_secret,
                session_cookie="RADUI_session",
                same_site="lax",
                https_only=self._session_cookie_secure,
            ),
            *self._custom_middleware,
        ]
        @asynccontextmanager
        async def lifespan(_app: Starlette):
            for hook in self._startup_hooks:
                res = hook()
                if inspect.iscoroutine(res):
                    await res
            await self.jobs.startup()
            try:
                yield
            finally:
                self._shutting_down = True
                await self._drain_commands(timeout=self.drain_timeout)
                for hook in reversed(self._shutdown_hooks):
                    try:
                        res = hook()
                        if inspect.iscoroutine(res):
                            await res
                    except Exception:
                        _LOGGER.exception("Error executing shutdown hook")
                await self.jobs.shutdown()
                try:
                    self.outbox.close()
                except Exception:
                    pass

        self._asgi = Starlette(routes=routes, middleware=middleware, lifespan=lifespan)
        return self._asgi

    def run(self, *, host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> None:
        try:
            import uvicorn
        except ImportError as exc:
            raise RuntimeError("Install RADUI with the 'server' extra to run the development server") from exc
        uvicorn.run(self.asgi(), host=host, port=port)
