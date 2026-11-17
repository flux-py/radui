from __future__ import annotations

import asyncio
import hashlib
import inspect
import ipaddress
import logging
import os
from contextlib import asynccontextmanager
import re
import secrets
import time
from collections import OrderedDict
from threading import RLock
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import parse_qsl, urlsplit

import anyio
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import Match, Route

from radui.components.nodes import (
    ActionCard,
    Button,
    Checkbox,
    Component,
    CustomElement,
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
from radui.core.config import ConfigurationError, EnvironmentMode, RadUIConfig
from radui.core.logging import configure_logging, log_structured
from radui.core.ir import AppMetadata, ApplicationIR, CommandSpec, JobSpec, RouteSpec
from radui.resumability import collect_resumable_boundaries, compute_auth_scope, restore_boundary
from radui.streaming import collect_suspense_boundaries, stream_page_html
from radui.web_components import WebComponentSpec
from radui.core.islands import (
    ActivationTrigger,
    HydrationStrategy,
    Island,
    sanitize_island_state,
    validate_island_config,
    validate_island_id,
    validate_island_name,
)
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
    ssg: bool = True
    ssg_paths: Any = None
    description: str | None = None
    canonical_url: str | None = None
    og_metadata: Mapping[str, str] | None = None
    twitter_metadata: Mapping[str, str] | None = None
    meta: Mapping[str, str] | None = None
    loading: Callable[[], Component] | Component | None = None
    error_boundary: Callable[[Exception], Component] | Component | None = None
    guard: Callable[[Request], Any] | None = None
    stream: bool = False


@dataclass(frozen=True)
class CommandDefinition:
    command_id: str
    handler: Callable[["CommandContext"], Any]
    require_auth: bool = False
    require_role: str | None = None
    require_permission: str | None = None


@dataclass(frozen=True)
class IslandDefinition:
    name: str
    handler: Callable[..., Component]
    hydration: HydrationStrategy = "fetch"
    trigger: ActivationTrigger = "eager"
    require_auth: bool = False
    require_role: str | None = None
    require_permission: str | None = None
    allowed_state_keys: tuple[str, ...] = ()


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
        old_val = self.state.read(ref) if hasattr(self.state, "read") else None
        change = self.state.write(ref, value)
        try:
            if hasattr(self, "devtools") and self.devtools:
                ref_key = getattr(ref, "key", str(ref))
                ref_scope = getattr(ref, "scope", "session")
                self.devtools.record_change(
                    key=ref_key,
                    old_val=old_val,
                    new_val=value,
                    command_name=self.command_id,
                    scope=ref_scope,
                )
        except Exception:
            pass
        return change

    @property
    def devtools(self):
        """Access the runtime TimeTravelDebugger instance for state rollbacks and inspections."""
        app = getattr(self.request, "app", None)
        manager = getattr(app, "devtools_manager", None) if app else None
        if manager is None:
            from radui.inspector.devtools import TimeTravelDebugger
            manager = TimeTravelDebugger()
        return manager

    @property
    def presence(self):
        """Access the collaborative room PresenceManager."""
        from radui.core.presence import get_global_presence_manager
        return get_global_presence_manager()

    def batch(self):
        return self.state.batch()

    def transaction(self):
        return self.state.transaction()


def _read_island_allowed_state(state_context: StateContext, key: str) -> Any:
    """Read an allowlisted state key from StateContext without triggering declaration conflicts."""
    t_prefix = f"{state_context.tenant_id}:" if state_context.tenant_id else ""
    candidates = [
        ("session", f"{t_prefix}{state_context.session_id}", key),
        ("view", (f"{t_prefix}{state_context.session_id}", state_context.view_id), key),
        ("app", f"{t_prefix}{state_context.runtime.app_id}", key),
    ]
    with state_context.runtime._lock:
        for state_key in candidates:
            if state_key in state_context.runtime._values:
                return state_context.runtime._values[state_key]
    return state_context.get(key)


def _normalize_origin(raw: str | None) -> str | None:
    """Normalize an HTTP/HTTPS origin, stripping default ports (:80 / :443)."""
    if not raw or not isinstance(raw, str):
        return None
    val = raw.strip()
    if not val or val.lower() == "null":
        return None
    parts = urlsplit(val)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"} or not parts.hostname:
        return None
    if parts.path not in {"", "/"} or parts.query or parts.fragment or parts.username or parts.password:
        return None
    host = parts.hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError:
        return None
    if port is None or (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


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
        devtools: Any = None,
        trusted_origins: Sequence[str] | None = None,
        trusted_proxies: Sequence[str] | None = None,
        user_resolver: Callable[[Request], User | None] | None = None,
        inspector_authorizer: Callable[[Request, User | None], bool | Any] | None = None,
        session_ttl_seconds: int = 14 * 86400,
        sse_max_connections_per_session: int = 8,
        sse_max_connections_per_ip: int = 32,
        sse_connect_rate_limit: int = 30,
        sse_connect_rate_window_seconds: float = 60.0,
        config: RadUIConfig | None = None,
        environment: EnvironmentMode | None = None,
    ) -> None:
        if config is not None:
            self.config = config
        else:
            self.config = RadUIConfig.from_env(
                environment=environment,
                debug=debug if debug else None,
                session_secret=session_secret,
                session_cookie_secure=session_cookie_secure if session_cookie_secure else None,
                session_ttl_seconds=session_ttl_seconds,
                trusted_origins=trusted_origins,
                trusted_proxies=trusted_proxies,
                allow_untrusted_tenant_headers=allow_untrusted_tenant_headers,
                sse_max_connections_per_session=sse_max_connections_per_session,
                sse_max_connections_per_ip=sse_max_connections_per_ip,
                sse_connect_rate_limit=sse_connect_rate_limit,
                sse_connect_rate_window_seconds=sse_connect_rate_window_seconds,
            )
        configure_logging(self.config.log_level)

        effective_name = title or name
        normalized_id = app_id or _PAGE_ID_RE.sub("-", effective_name.strip().lower()).strip("-") or "RADUI-app"
        self.metadata = AppMetadata(id=normalized_id, name=effective_name)
        self.title = effective_name
        self.debug = self.config.debug
        self.multi_tenant = multi_tenant
        self.theme = theme
        self.command_palette = command_palette
        self.devtools = devtools
        if devtools is not None or debug:
            from radui.inspector.devtools import DevToolsConfig, TimeTravelDebugger
            cfg = devtools if isinstance(devtools, DevToolsConfig) else DevToolsConfig(enabled=True)
            self.devtools_manager = TimeTravelDebugger(max_entries=cfg.max_journal_entries)
        else:
            self.devtools_manager = None
        self.inspector = TraceCollector()
        if telemetry_endpoint:
            from radui.inspector.otlp import OTLPExporter
            self.inspector.set_exporter(OTLPExporter(endpoint=telemetry_endpoint, service_name=self.metadata.name))
        self.registry = ComponentRegistry.builtins()
        self.renderer = HTMLRenderer(self.registry)
        self.worker_id = f"worker-{secrets.token_hex(4)}"
        eff_state_backend = state_backend
        eff_event_backend = event_backend
        eff_job_backend = job_backend
        if self.config.backend == "redis":
            assert self.config.redis_url is not None
            if eff_state_backend is None:
                from radui.state.backend import RedisStateBackend
                eff_state_backend = RedisStateBackend(
                    self.config.redis_url,
                    allow_fallback=False,
                    ttl_seconds=self.config.state_ttl_seconds,
                )
            if eff_event_backend is None:
                from radui.transport.events import RedisEventBackend
                eff_event_backend = RedisEventBackend(
                    self.config.redis_url,
                    allow_fallback=False,
                )
            if eff_job_backend is None:
                from radui.jobs.redis import RedisJobBackend
                eff_job_backend = RedisJobBackend(
                    self.config.redis_url,
                    allow_fallback=False,
                    worker_id=self.worker_id,
                )
        elif self.config.backend == "sqlite":
            db_path = self.config.sqlite_path or "RADUI_state.db"
            if eff_state_backend is None:
                from radui.state.backend import SQLiteStateBackend
                eff_state_backend = SQLiteStateBackend(db_path=db_path)
            if eff_event_backend is None:
                from radui.transport.events import SQLiteEventBackend
                eff_event_backend = SQLiteEventBackend(db_path=db_path)
            if eff_job_backend is None:
                from radui.jobs.sqlite import SQLiteJobBackend
                eff_job_backend = SQLiteJobBackend(db_path=db_path)

        self.state_runtime = StateRuntime(self.metadata.id, backend=eff_state_backend)
        self.idempotency: IdempotencyBackend = idempotency_backend or InMemoryIdempotencyBackend()
        self.events = EventBroker(
            backend=eff_event_backend,
            max_connections_per_session=self.config.sse_max_connections_per_session,
            max_connections_per_ip=self.config.sse_max_connections_per_ip,
            connect_rate_limit=self.config.sse_connect_rate_limit,
            connect_rate_window_seconds=self.config.sse_connect_rate_window_seconds,
            worker_id=self.worker_id,
            sse_lease_ttl_seconds=self.config.sse_lease_ttl_seconds,
            sse_governance_fail_open=self.config.sse_governance_fail_open,
        )
        self._trusted_origins: set[str] = {
            norm for norm in (_normalize_origin(o) for o in self.config.trusted_origins) if norm is not None
        }
        self._trusted_proxies: set[str] = set(self.config.trusted_proxies)
        self._user_resolver = user_resolver
        self._inspector_authorizer = inspector_authorizer
        self._session_ttl_seconds = self.config.session_ttl_seconds
        self.outbox: TransactionalOutbox = outbox or TransactionalOutbox()
        self.jobs: JobBackend = eff_job_backend if eff_job_backend is not None else LocalJobBackend()
        self.jobs.bind_callbacks(
            on_update=self._on_job_update,
            on_state_changes=self._on_job_state_changes,
        )
        from radui.observability import WorkerIdentity, WorkerObservabilityPublisher
        self.worker_identity = WorkerIdentity.create(
            worker_id=self.worker_id,
            environment=self.config.environment,
            backend_mode=self.config.backend,
        )
        self.observability = WorkerObservabilityPublisher(
            self.worker_identity,
            self._collect_worker_observability,
            backend=self.events.backend if self.config.backend == "redis" else None,
            ttl_seconds=self.config.sse_lease_ttl_seconds,
        )
        from radui.diagnostics import DiagnosticsCollector
        self.diagnostics = DiagnosticsCollector()
        self._session_secret = self.config.session_secret or secrets.token_urlsafe(48)
        self._session_secret_is_ephemeral = self.config.session_secret is None
        self._session_cookie_secure = self.config.session_cookie_secure
        self._user_id_resolver = user_id_resolver
        self._tenant_id_resolver = tenant_id_resolver
        self._tenant_membership_validator = tenant_membership_validator
        self._allow_untrusted_tenant_headers = self.config.allow_untrusted_tenant_headers
        if max_form_bytes < 1024:
            raise ValueError("max_form_bytes must be at least 1024")
        self._max_form_bytes = max_form_bytes
        self._pages: dict[str, PageDefinition] = {}
        self._commands: dict[str, CommandDefinition] = {}
        self._jobs: dict[str, JobDefinition] = {}
        self._islands: dict[str, IslandDefinition] = {}
        self._web_components: dict[str, WebComponentSpec] = {}
        self._layouts: list[tuple[str, Callable[..., Component]]] = []
        self._redirects: list[Any] = []
        self._action_cache: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
        self._action_guard = RLock()
        self._actions_in_progress: set[tuple[str, str]] = set()
        self._action_cache_limit = 1024
        self._startup_hooks: list[Callable[..., Any]] = []
        self._shutdown_hooks: list[Callable[..., Any]] = []
        self._shutting_down: bool = False
        self._ready: bool = False
        self._startup_error: str | None = None
        self._readiness_checks: list[Callable[[], Any]] = []
        self._redis_reconnect_guard = RLock()
        self._last_redis_reconnect_attempt: float = 0.0
        self._redis_reconnect_cooldown_seconds: float = 0.5
        if self.config.backend == "redis":
            self._readiness_checks.append(self._default_redis_readiness_check)
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._active_commands_count: int = 0
        self.drain_timeout: float = self.config.drain_timeout
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
        ssg: bool = True,
        ssg_paths: Any = None,
        description: str | None = None,
        canonical_url: str | None = None,
        og_metadata: Mapping[str, str] | None = None,
        twitter_metadata: Mapping[str, str] | None = None,
        meta: Mapping[str, str] | None = None,
        loading: Callable[[], Component] | Component | None = None,
        error_boundary: Callable[[Exception], Component] | Component | None = None,
        guard: Callable[[Request], Any] | None = None,
        stream: bool = False,
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
                ssg=ssg,
                ssg_paths=ssg_paths,
                description=description,
                canonical_url=canonical_url,
                og_metadata=dict(og_metadata) if og_metadata is not None else None,
                twitter_metadata=dict(twitter_metadata) if twitter_metadata is not None else None,
                meta=dict(meta) if meta is not None else None,
                loading=loading,
                error_boundary=error_boundary,
                guard=guard,
                stream=stream,
            )
            self._asgi = None
            return handler

        return decorator

    def add_redirect(
        self,
        source: str,
        destination: str,
        status_code: int = 301,
        *,
        allow_external: bool = False,
    ) -> None:
        """Register a static redirect rule for SSG manifests."""
        from radui.core.ssg import validate_redirect_rule
        rule = validate_redirect_rule(source, destination, status_code, allow_external=allow_external)
        self._redirects.append(rule)

    def build_static(
        self,
        output_dir: str | os.PathLike[str] = "./dist",
        *,
        base_url: str = "",
        environment: str = "production",
        clean: bool = True,
        fingerprint_assets: bool = True,
        inline_css: bool = False,
        inline_js: bool = False,
        build_timestamp: str | None = None,
        assets_dir: str | os.PathLike[str] | None = None,
    ):
        """Run deterministic Static Site Generation (SSG) into output_dir."""
        from pathlib import Path
        from radui.core.ssg import SSGConfig, build_static_site

        cfg = SSGConfig(
            output_dir=Path(output_dir),
            base_url=base_url,
            environment=environment,
            clean=clean,
            fingerprint_assets=fingerprint_assets,
            inline_css=inline_css,
            inline_js=inline_js,
            build_timestamp=build_timestamp,
            assets_dir=Path(assets_dir) if assets_dir is not None else None,
        )
        return build_static_site(self, cfg)

    def layout(self, path_prefix: str = "/"):
        """Register a persistent nested layout wrapping pages that match path_prefix."""
        if not path_prefix.startswith("/"):
            raise ValueError("layout path_prefix must start with '/'")

        def decorator(handler: Callable[..., Component]):
            self._layouts.append((path_prefix, handler))
            self._asgi = None
            return handler

        return decorator

    def web_component(
        self,
        tag_name: str,
        *,
        shadow_mode: str = "open",
        observed_attributes: Sequence[str] = (),
        events: Sequence[str] = (),
        event_commands: Mapping[str, str] | None = None,
        styles: str = "",
        template_html: str = "",
    ):
        """Register a standards-compliant Web Component (Custom Element + Shadow DOM)."""
        spec = WebComponentSpec(
            tag_name=tag_name,
            shadow_mode=shadow_mode,  # type: ignore[arg-type]
            observed_attributes=tuple(observed_attributes),
            events=tuple(events),
            event_commands=dict(event_commands or {}),
            styles=styles,
            template_html=template_html,
        )
        self._web_components[spec.tag_name] = spec

        def decorator(fn: Any) -> Any:
            return fn

        return decorator

    def island(
        self,
        name: str,
        *,
        hydration: HydrationStrategy = "fetch",
        trigger: ActivationTrigger = "eager",
        require_auth: bool = False,
        require_role: str | None = None,
        require_permission: str | None = None,
        allowed_state_keys: Sequence[str] = (),
    ):
        """Register an independently hydratable Hybrid Island component."""
        validate_island_name(name)
        validate_island_config(hydration, trigger)
        safe_allowed = tuple(str(k) for k in allowed_state_keys)

        def decorator(handler: Callable[..., Component]):
            if name in self._islands:
                raise ValueError(f"island already registered: {name}")
            spec = IslandDefinition(
                name=name,
                handler=handler,
                hydration=hydration,
                trigger=trigger,
                require_auth=require_auth,
                require_role=require_role,
                require_permission=require_permission,
                allowed_state_keys=safe_allowed,
            )
            self._islands[name] = spec
            self._asgi = None

            def mount(
                *,
                id: str | None = None,
                initial_state: Mapping[str, Any] | None = None,
                fallback: Component | None = None,
                **props: Any,
            ) -> Island:
                from radui.state.runtime import get_active_context

                clean_props = sanitize_island_state(props)
                try:
                    rendered = handler(**clean_props)
                except Exception:
                    if fallback is not None:
                        rendered = fallback
                    else:
                        raise
                merged_state: dict[str, Any] = {}
                active_ctx = get_active_context()
                if active_ctx is not None and spec.allowed_state_keys:
                    for key in spec.allowed_state_keys:
                        val = _read_island_allowed_state(active_ctx, key)
                        if val is not None:
                            merged_state[key] = val
                if initial_state:
                    merged_state.update(initial_state)
                return Island(
                    id=id or f"island-{name}",
                    name=name,
                    hydration=hydration,
                    trigger=trigger,
                    initial_state=sanitize_island_state(merged_state),
                    props=clean_props,
                    children=(rendered,),
                    fallback=fallback,
                )

            return mount

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

    def register_background_task(self, task: asyncio.Task[Any]) -> asyncio.Task[Any]:
        """Track a background asyncio.Task for automatic cancellation on shutdown."""
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    def add_readiness_check(self, check: Callable[[], Any]) -> Callable[[], Any]:
        """Register a dependency readiness check evaluated by GET /ready."""
        self._readiness_checks.append(check)
        return check

    def set_ready(self, ready: bool) -> None:
        """Explicitly update application readiness state."""
        self._ready = bool(ready)

    def _collect_worker_observability(self) -> dict[str, Any]:
        """Collect bounded, secret-free aggregate metrics across all runtime subsystems."""
        if hasattr(self.state_runtime.backend, "observability_snapshot"):
            state_snap = self.state_runtime.backend.observability_snapshot()
        elif hasattr(self.state_runtime.backend, "metrics"):
            state_snap = self.state_runtime.backend.metrics()
        else:
            state_snap = {}
        ev_sse_snap = self.events.observability_snapshot()
        if hasattr(self.jobs, "observability_snapshot"):
            jobs_snap = self.jobs.observability_snapshot()
        elif hasattr(self.jobs, "metrics"):
            jobs_snap = self.jobs.metrics()
        else:
            jobs_snap = {}
        return {
            "state": state_snap,
            "events": ev_sse_snap.get("events", {}),
            "sse": ev_sse_snap.get("sse", {}),
            "jobs": jobs_snap,
        }

    async def _run_observability_heartbeat(self) -> None:
        interval = max(0.5, float(self.config.sse_heartbeat_interval_seconds))
        while True:
            await asyncio.sleep(interval)
            try:
                await asyncio.to_thread(self.observability.publish_snapshot)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass

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
        now = time.time()
        session_id = request.session.get("gx_session_id")
        expires_at = request.session.get("gx_session_expires_at")
        expired = isinstance(expires_at, (int, float)) and expires_at <= now
        if not isinstance(session_id, str) or len(session_id) < 24 or expired:
            session_id = secrets.token_urlsafe(32)
            request.session["gx_session_id"] = session_id
            request.session["gx_session_expires_at"] = now + self._session_ttl_seconds
        elif expires_at is None:
            request.session["gx_session_expires_at"] = now + self._session_ttl_seconds
        csrf_token = request.session.get("gx_csrf_token")
        if not isinstance(csrf_token, str) or len(csrf_token) < 24 or expired:
            csrf_token = secrets.token_urlsafe(32)
            request.session["gx_csrf_token"] = csrf_token
        return session_id, csrf_token

    def _validate_existing_session(self, request: Request) -> tuple[str | None, str | None]:
        """Validate an existing signed session without minting a new one."""
        session_id = request.session.get("gx_session_id")
        if not isinstance(session_id, str) or len(session_id) < 24:
            return None, "Missing or invalid session"
        expires_at = request.session.get("gx_session_expires_at")
        if not isinstance(expires_at, (int, float)) or expires_at <= time.time():
            return None, "Session expired"
        return session_id, None

    def _resolve_client_ip(self, request: Request) -> str | None:
        """Resolve client IP, trusting X-Forwarded-For only from configured proxies."""
        peer_ip = request.client.host if request.client else None
        if peer_ip and peer_ip in self._trusted_proxies:
            xff = request.headers.get("x-forwarded-for", "")
            if xff:
                hops = [h.strip() for h in xff.split(",") if h.strip()]
                # Walk right-to-left skipping known trusted proxies; take first untrusted valid IP
                for hop in reversed(hops):
                    try:
                        ipaddress.ip_address(hop)
                    except ValueError:
                        return peer_ip
                    if hop not in self._trusted_proxies:
                        return hop
                # All hops are valid trusted proxies; fall back to leftmost
                if hops:
                    try:
                        ipaddress.ip_address(hops[0])
                        return hops[0]
                    except ValueError:
                        return peer_ip
        return peer_ip

    def _validate_sse_origin(self, request: Request) -> tuple[bool, str | None]:
        """Validate Origin and Sec-Fetch-Site headers for SSE connections."""
        sec_fetch_site_raw = request.headers.get("sec-fetch-site")
        sec_fetch_site = sec_fetch_site_raw.strip().lower() if sec_fetch_site_raw is not None else None
        if sec_fetch_site is not None:
            if sec_fetch_site not in {"same-origin", "none", "cross-site", "same-site"}:
                return False, "Invalid Sec-Fetch-Site header"

        origin_raw = request.headers.get("origin")
        if origin_raw is not None:
            origin = _normalize_origin(origin_raw)
            if origin is None:
                return False, "Invalid Origin header"
            if origin in self._trusted_origins:
                return True, None
            if sec_fetch_site in {"cross-site", "same-site"}:
                return False, "Cross-origin SSE connection rejected"
            expected_origin = _normalize_origin(f"{request.url.scheme}://{request.url.netloc}")
            if expected_origin is None or origin != expected_origin:
                return False, "Untrusted Origin header"
            return True, None

        if sec_fetch_site in {"cross-site", "same-site"}:
            return False, "Cross-origin SSE connection rejected"
        return True, None

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
            for binding in getattr(node, "interactions", ()):
                for act_item in getattr(binding, "actions", ()):
                    if getattr(act_item, "op", None) == "dispatch_command" and act_item.key not in self._commands:
                        raise ValueError(f"Interaction references unregistered command: {act_item.key}")
            if isinstance(node, Button):
                if not inside_form:
                    if not node.command and not getattr(node, "interactions", ()):
                        raise ValueError("Button must be placed inside a Form")
                    if node.command and node.command not in self._commands:
                        raise ValueError(f"Button references unregistered command: {node.command}")
                return
            if isinstance(node, _FORM_CONTROL_TYPES) and not inside_form:
                if not getattr(node, "interactions", ()) and not getattr(node, "bind_local", None):
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
            if isinstance(node, CustomElement):
                for cmd_id in (node.event_commands or {}).values():
                    if cmd_id not in self._commands:
                        raise ValueError(f"CustomElement references unregistered command: {cmd_id}")
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
            elif isinstance(node, CustomElement) and command_id in (node.event_commands or {}).values():
                if result is None:
                    result = Form(command=command_id, children=())
            elif any(
                getattr(act_item, "op", None) == "dispatch_command" and getattr(act_item, "key", None) == command_id
                for b in getattr(node, "interactions", ())
                for act_item in getattr(b, "actions", ())
            ):
                if result is None:
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

    def _resolve_page_for_path(self, target_path: str) -> tuple[PageDefinition | None, dict[str, Any]]:
        """Resolve an application path against registered pages (supporting dynamic route params)."""
        candidates = [target_path]
        if target_path != "/" and target_path.endswith("/"):
            candidates.append(target_path.rstrip("/") or "/")
        for cand in candidates:
            if cand in self._pages:
                return self._pages[cand], {}
            scope = {"type": "http", "method": "GET", "path": cand}
            for page in self._pages.values():
                matcher = Route(page.path, endpoint=lambda _req: None, methods=["GET"])
                match, child_scope = matcher.matches(scope)
                if match == Match.FULL:
                    return page, dict(child_scope.get("path_params", {}))
        return None, {}

    async def _check_page_access(self, request: Request, page: PageDefinition) -> tuple[int, str] | None:
        """Enforce route auth/role/permission guards; returns (status_code, message) on denial."""
        if not (page.require_auth or page.require_role or page.require_permission):
            return None
        self._session(request)
        user_id = await self._user_id(request)
        user: User | None = None
        if self._user_id_resolver is not None:
            resolved = self._user_id_resolver(request)
            if resolved:
                user = User(id=resolved, username=resolved)
        elif user_id:
            user = User(id=user_id, username=user_id)

        if page.require_auth and user is None:
            return 401, "Authentication required"
        if page.require_role and (user is None or not user.has_role(page.require_role)):
            return 403, "Insufficient permissions"
        if page.require_permission and (user is None or not user.has_permission(page.require_permission)):
            return 403, "Insufficient permissions"
        return None

    async def _evaluate_page_guard(self, request: Request, page: PageDefinition) -> bool | str:
        """Run optional page-level navigation guard; returns True (allow), False (deny), or str (redirect)."""
        if page.guard is None:
            return True
        res = page.guard(request)
        if inspect.isawaitable(res):
            res = await res
        if isinstance(res, str):
            return res
        if res is False:
            return False
        return True

    def _render_page_loading(self, page: PageDefinition, state_context: StateContext, csrf_token: str) -> str:
        if page.loading is None:
            return ""
        comp = page.loading() if callable(page.loading) else page.loading
        if not isinstance(comp, Component):
            return ""
        return self.renderer.render_component(comp, state_context=state_context, csrf_token=csrf_token)

    def _render_page_error(
        self, page: PageDefinition, exc: Exception, state_context: StateContext | None, csrf_token: str | None
    ) -> str:
        if page.error_boundary is None:
            return ""
        comp = page.error_boundary(exc) if callable(page.error_boundary) else page.error_boundary
        if not isinstance(comp, Component):
            return ""
        return self.renderer.render_component(comp, state_context=state_context, csrf_token=csrf_token)

    async def _page_endpoint(self, request: Request, page: PageDefinition) -> Response:
        start_time = time.perf_counter()
        state_context: StateContext | None = None
        csrf_token: str | None = None
        try:
            denied = await self._check_page_access(request, page)
            if denied is not None:
                status, msg = denied
                heading = "401 Unauthorized" if status == 401 else "403 Forbidden"
                return HTMLResponse(f"<h1>{heading}</h1><p>{msg}</p>", status_code=status)

            guard_res = await self._evaluate_page_guard(request, page)
            if isinstance(guard_res, str):
                return RedirectResponse(guard_res, status_code=307)
            if guard_res is False:
                return HTMLResponse("<h1>403 Forbidden</h1><p>Navigation blocked by guard</p>", status_code=403)

            view_path = request.url.path
            state_context, csrf_token = await self._state_context(request, view_path)
            event_cursor = self.events.current_sequence(state_context.session_id)
            root = self._build_root(page, state_context, path_params=dict(request.path_params))
            custom_css = self.theme.to_css() if self.theme is not None else ""
            auth_scope = compute_auth_scope(
                session_id=state_context.session_id,
                user_id=state_context.identity.user_id,
            )
            resumable_snaps = [
                s.model_dump()
                for s in collect_resumable_boundaries(
                    root,
                    route=view_path,
                    auth_scope=auth_scope,
                    state_context=state_context,
                    tracker=self.state_runtime.dependencies,
                    identity=state_context.identity,
                )
            ]
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
                resumable_snapshots=resumable_snaps or None,
                web_components=[s.model_dump() for s in self._web_components.values()] or None,
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
            sec_headers = {
                "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; form-action 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "same-origin",
                "Cache-Control": "no-store",
            }
            if page.stream:
                suspense_tasks = collect_suspense_boundaries(root)
                if suspense_tasks:
                    sec_headers["X-Accel-Buffering"] = "no"
                    return StreamingResponse(
                        stream_page_html(
                            shell_html=html,
                            tasks=suspense_tasks,
                            renderer=self.renderer,
                            state_context=state_context,
                            csrf_token=csrf_token,
                            is_disconnected=request.is_disconnected,
                        ),
                        media_type="text/html; charset=utf-8",
                        headers=sec_headers,
                    )
            return HTMLResponse(html, headers=sec_headers)
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
            err_html = self._render_page_error(page, exc, state_context, csrf_token)
            if err_html:
                return HTMLResponse(err_html, status_code=500)
            return PlainTextResponse("Internal Server Error", status_code=500)

    async def _navigate_endpoint(self, request: Request) -> Response:
        """Serve client-side SPA route transitions with full server routing, layouts, and guards."""
        start_time = time.perf_counter()
        to = request.query_params.get("to", "").strip()
        if not to or not to.startswith("/") or to.startswith("//"):
            return _json_response({"ok": False, "status": 400, "fallback": True, "error": "Invalid navigation target"}, status_code=400)

        parsed = urlsplit(to)
        target_path = parsed.path or "/"
        page, path_params = self._resolve_page_for_path(target_path)
        if page is None:
            return _json_response({"ok": False, "status": 404, "fallback": True, "error": "Route not found"}, status_code=404)

        state_context: StateContext | None = None
        csrf_token: str | None = None
        try:
            denied = await self._check_page_access(request, page)
            if denied is not None:
                status, msg = denied
                return _json_response({"ok": False, "status": status, "fallback": True, "error": msg}, status_code=status)

            guard_res = await self._evaluate_page_guard(request, page)
            if isinstance(guard_res, str):
                return _json_response({"ok": False, "redirect": guard_res, "status": 307}, status_code=200)
            if guard_res is False:
                return _json_response({"ok": False, "status": 403, "fallback": True, "error": "Navigation blocked by guard"}, status_code=403)

            state_context, csrf_token = await self._state_context(request, target_path)
            event_cursor = self.events.current_sequence(state_context.session_id)
            root = self._build_root(page, state_context, path_params=path_params)
            html = self.renderer.render_component(root, state_context=state_context, csrf_token=csrf_token)
            loading_html = self._render_page_loading(page, state_context, csrf_token)
            self._reconcile_dependencies(root, state_context)
            self._reconcile_job_observers(root, state_context)

            matching_layouts = sorted(
                (
                    prefix
                    for prefix, _ in self._layouts
                    if page.path == prefix or page.path.startswith(prefix.rstrip("/") + "/") or prefix == "/"
                ),
                key=len,
            )
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            self.inspector.record(
                "navigate",
                target_path,
                session_id=state_context.session_id,
                view_id=target_path,
                duration_ms=round(duration_ms, 2),
                details={"title": page.title, "route": page.path},
            )
            auth_key = hashlib.sha256(
                f"{state_context.session_id}:{state_context.identity.user_id or ''}".encode("utf-8")
            ).hexdigest()[:16]
            is_protected = bool(page.require_auth or page.require_role or page.require_permission or page.guard is not None)
            auth_scope = compute_auth_scope(
                session_id=state_context.session_id,
                user_id=state_context.identity.user_id,
            )
            resumable_snaps = [
                s.model_dump()
                for s in collect_resumable_boundaries(
                    root,
                    route=target_path,
                    auth_scope=auth_scope,
                    state_context=state_context,
                    tracker=self.state_runtime.dependencies,
                    identity=state_context.identity,
                )
            ]
            return _json_response(
                {
                    "ok": True,
                    "path": to,
                    "route": page.path,
                    "title": page.title,
                    "view_id": target_path,
                    "csrf_token": csrf_token,
                    "auth_key": auth_key,
                    "cacheable": not is_protected,
                    "event_cursor": event_cursor,
                    "layouts": matching_layouts,
                    "loading_html": loading_html,
                    "resumable": resumable_snaps,
                    "html": html,
                }
            )
        except HTTPException as exc:
            return _json_response({"ok": False, "status": exc.status_code, "fallback": True, "error": exc.detail}, status_code=exc.status_code)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            self.inspector.record(
                "error",
                target_path,
                duration_ms=round(duration_ms, 2),
                details={"error": str(exc)},
            )
            _LOGGER.exception("SPA navigation failed")
            err_html = self._render_page_error(page, exc, state_context, csrf_token)
            if err_html:
                return _json_response(
                    {"ok": False, "status": 500, "fallback": False, "error_html": err_html, "error": str(exc)},
                    status_code=500,
                )
            return _json_response({"ok": False, "status": 500, "fallback": True, "error": "Internal Server Error"}, status_code=500)

    async def _resume_endpoint(self, request: Request) -> Response:
        """Validate and restore a serialized M2.0 resumable boundary snapshot."""
        session_id, csrf_token = self._session(request)
        header_csrf = request.headers.get("x-gx-csrf", "")
        if not header_csrf or not secrets.compare_digest(header_csrf, csrf_token):
            return _json_response({"ok": False, "error": "Invalid CSRF token"}, status_code=403)
        try:
            body = await request.json()
        except Exception:
            return _json_response({"ok": False, "error": "Invalid JSON body"}, status_code=400)
        if not isinstance(body, dict) or not isinstance(body.get("snapshot"), dict):
            return _json_response({"ok": False, "error": "Missing snapshot payload"}, status_code=400)

        user_id = await self._user_id(request)
        if self._user_id_resolver is not None:
            user_id = self._user_id_resolver(request) or user_id
        expected_auth = compute_auth_scope(session_id=session_id, user_id=user_id)
        expected_route = body.get("expected_route")
        try:
            import json as _json
            restored = restore_boundary(
                _json.dumps(body["snapshot"]),
                expected_route=expected_route if isinstance(expected_route, str) else None,
                expected_auth_scope=expected_auth,
            )
            return _json_response({"ok": True, "snapshot": restored.model_dump()})
        except PermissionError as exc:
            return _json_response({"ok": False, "error": str(exc)}, status_code=403)
        except ValueError as exc:
            return _json_response({"ok": False, "error": str(exc)}, status_code=400)

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
                {"status": "draining", "version": "1.0.0"},
                status_code=503,
            )
        return _json_response(
            {"status": "healthy", "version": "1.0.0"},
            status_code=200,
        )

    async def _gx_health_endpoint(self, request: Request) -> Response:
        if self._shutting_down:
            return _json_response(
                {"status": "draining", "version": "1.0.0", "worker_id": self.worker_id},
                status_code=503,
            )
        return _json_response(
            {"status": "healthy", "version": "1.0.0", "worker_id": self.worker_id},
            status_code=200,
        )

    def _probe_and_recover_redis(self) -> bool:
        """Check essential Redis backends and perform bounded, cooldown-guarded reconnects if degraded."""
        backends = [self.state_runtime.backend, self.events.backend]
        if hasattr(self.jobs, "ping"):
            backends.append(self.jobs)

        def _is_alive(b: Any) -> bool:
            try:
                return bool(b.ping()) if hasattr(b, "ping") else True
            except Exception:
                return False

        failing = [b for b in backends if not _is_alive(b)]
        if not failing:
            return True

        with self._redis_reconnect_guard:
            now = time.monotonic()
            if (now - self._last_redis_reconnect_attempt) < self._redis_reconnect_cooldown_seconds:
                return False
            self._last_redis_reconnect_attempt = now
            for b in failing:
                if hasattr(b, "reconnect"):
                    try:
                        b.reconnect()
                    except Exception:
                        pass
            return all(_is_alive(b) for b in backends)

    async def _default_redis_readiness_check(self) -> bool:
        return await asyncio.to_thread(self._probe_and_recover_redis)

    async def _ready_endpoint(self, request: Request) -> Response:
        if not self._ready or self._shutting_down:
            return _json_response(
                {"status": "not_ready", "version": "1.0.0"},
                status_code=503,
            )
        for check in self._readiness_checks:
            try:
                ok = check()
                if inspect.isawaitable(ok):
                    ok = await ok
                if not ok:
                    return _json_response({"status": "not_ready", "version": "1.0.0"}, status_code=503)
            except Exception:
                return _json_response({"status": "not_ready", "version": "1.0.0"}, status_code=503)
        return _json_response(
            {"status": "ready", "version": "1.0.0"},
            status_code=200,
        )

    async def _authorize_inspector(
        self,
        request: Request,
        *,
        permission: str = "inspect:runtime",
        html_error: bool = False,
    ) -> Response | None:
        if not self.config.is_inspector_enabled():
            if html_error:
                return HTMLResponse("<h1>404 Not Found</h1><p>Inspector is disabled.</p>", status_code=404)
            return _json_response({"ok": False, "error": "Inspector is disabled"}, status_code=404)

        if (
            self.config.environment == "development"
            and self.config.debug
            and self._user_resolver is None
            and self._inspector_authorizer is None
        ):
            return None

        session_id, session_err = self._validate_existing_session(request)
        if session_id is None:
            if html_error:
                return HTMLResponse("<h1>401 Unauthorized</h1>", status_code=401)
            return _json_response({"ok": False, "error": session_err or "Unauthorized"}, status_code=401)

        user = await self._resolve_user(request)
        if user is None:
            if html_error:
                return HTMLResponse("<h1>401 Authentication Required</h1>", status_code=401)
            return _json_response({"ok": False, "error": "Authentication required"}, status_code=401)

        if self._inspector_authorizer is not None:
            allowed = self._inspector_authorizer(request, user)
            if inspect.isawaitable(allowed):
                allowed = await allowed
        else:
            allowed = user.has_role("admin") or user.has_role("inspector") or user.has_permission(permission)

        if not allowed:
            if html_error:
                return HTMLResponse("<h1>403 Forbidden</h1>", status_code=403)
            return _json_response({"ok": False, "error": "Inspector authorization required"}, status_code=403)
        return None

    async def _inspect_config_endpoint(self, request: Request) -> Response:
        denied = await self._authorize_inspector(request, permission="inspect:config")
        if denied is not None:
            return denied
        return _json_response({"ok": True, "config": self.config.safe_summary()})

    async def _inspect_backends_endpoint(self, request: Request) -> Response:
        denied = await self._authorize_inspector(request, permission="inspect:backends")
        if denied is not None:
            return denied

        state_metrics = self.state_runtime.backend.metrics() if hasattr(self.state_runtime.backend, "metrics") else {}
        event_metrics = self.events.backend.metrics() if hasattr(self.events.backend, "metrics") else {}
        job_metrics = self.jobs.metrics() if hasattr(self.jobs, "metrics") else {}
        return _json_response({
            "ok": True,
            "backends": {
                "state": {"type": type(self.state_runtime.backend).__name__, **state_metrics},
                "events": {"type": type(self.events.backend).__name__, **self.events.metrics(), **event_metrics},
                "jobs": {"type": type(self.jobs).__name__, **job_metrics},
            },
        })

    async def _inspect_runtime_endpoint(self, request: Request) -> Response:
        denied = await self._authorize_inspector(request, permission="inspect:runtime")
        if denied is not None:
            return denied
        payload = await asyncio.to_thread(self.diagnostics.runtime_diagnostics, self)
        return _json_response(payload)

    async def _inspect_jobs_endpoint(self, request: Request) -> Response:
        denied = await self._authorize_inspector(request, permission="inspect:jobs")
        if denied is not None:
            return denied
        try:
            limit = int(request.query_params.get("limit", 25))
            offset = int(request.query_params.get("offset", 0))
            if limit < 1 or offset < 0:
                raise ValueError
        except ValueError:
            return _json_response({"ok": False, "error": "Invalid pagination parameters"}, status_code=400)
        payload = await asyncio.to_thread(self.diagnostics.job_diagnostics, self, limit=limit, offset=offset)
        return _json_response(payload)

    async def _events_endpoint(self, request: Request) -> Response:
        session_id, session_err = self._validate_existing_session(request)
        if session_id is None:
            self.events.record_rejection()
            return PlainTextResponse(session_err or "Unauthorized", status_code=401)

        origin_ok, origin_err = self._validate_sse_origin(request)
        if not origin_ok:
            self.events.record_rejection()
            return PlainTextResponse(origin_err or "Forbidden", status_code=403)

        raw_last_id = request.headers.get("last-event-id") or request.query_params.get("since")
        try:
            last_event_id = int(raw_last_id) if raw_last_id else None
            if last_event_id is not None and last_event_id < 0:
                raise ValueError
        except ValueError:
            self.events.record_rejection()
            return PlainTextResponse("Invalid Last-Event-ID", status_code=400)

        client_ip = self._resolve_client_ip(request)
        conn_id = secrets.token_hex(8)
        admitted, reject_reason, status_code = self.events.try_acquire_connection(
            session_id,
            client_ip,
            is_reconnect=(last_event_id is not None),
            connection_id=conn_id,
        )
        if not admitted:
            return PlainTextResponse(reject_reason or "Too Many Requests", status_code=status_code)

        released = False

        def release_once() -> None:
            nonlocal released
            if not released:
                released = True
                self.events.release_connection(session_id, client_ip, connection_id=conn_id)

        async def stream():
            try:
                async for event in self.events.stream(session_id, last_event_id=last_event_id):
                    yield event
            finally:
                release_once()

        try:
            return StreamingResponse(
                stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache, no-transform",
                    "X-Accel-Buffering": "no",
                },
            )
        except Exception:
            release_once()
            raise

    async def _resolve_user(self, request: Request) -> User | None:
        if self._user_resolver is not None:
            res = self._user_resolver(request)
            if inspect.isawaitable(res):
                res = await res
            return res
        user_id = await self._user_id(request)
        if user_id:
            return User(id=user_id, username=user_id)
        return None

    async def _inspect_sse_endpoint(self, request: Request) -> Response:
        denied = await self._authorize_inspector(request, permission="inspect:sse")
        if denied is not None:
            return denied
        return _json_response(self.diagnostics.sse_diagnostics(self))

    async def _island_endpoint(self, request: Request) -> Response:
        import json as _json

        island_id = request.path_params.get("island_id", "")
        try:
            validate_island_id(island_id)
        except ValueError:
            return _json_response({"ok": False, "error": "Invalid island id"}, status_code=400)

        island_name = request.query_params.get("name", "")
        spec = self._islands.get(island_name)
        if spec is None:
            return _json_response({"ok": False, "error": "Unknown island"}, status_code=404)

        session_id, session_err = self._validate_existing_session(request)
        if session_id is None:
            return _json_response({"ok": False, "error": session_err or "Unauthorized"}, status_code=401)

        origin_ok, origin_err = self._validate_sse_origin(request)
        if not origin_ok:
            return _json_response({"ok": False, "error": origin_err or "Forbidden"}, status_code=403)

        if spec.require_auth or spec.require_role or spec.require_permission:
            user = await self._resolve_user(request)
            if spec.require_auth and user is None:
                return _json_response({"ok": False, "error": "Authentication required"}, status_code=401)
            if spec.require_role and (user is None or not user.has_role(spec.require_role)):
                return _json_response({"ok": False, "error": "Insufficient permissions"}, status_code=403)
            if spec.require_permission and (user is None or not user.has_permission(spec.require_permission)):
                return _json_response({"ok": False, "error": "Insufficient permissions"}, status_code=403)

        raw_props = request.query_params.get("props")
        clean_props: dict[str, Any] = {}
        if raw_props:
            if len(raw_props) > 8192:
                return _json_response({"ok": False, "error": "Island props payload too large"}, status_code=400)
            try:
                parsed = _json.loads(raw_props)
                clean_props = sanitize_island_state(parsed)
                sig = inspect.signature(spec.handler)
                accepts_varkw = any(
                    p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
                )
                reserved = {"id", "initial_state", "allowed_state_keys", "state_context", "csrf_token"}
                for k in clean_props:
                    if k in reserved or (not accepts_varkw and k not in sig.parameters):
                        raise ValueError(f"Unexpected island prop: {k!r}")
            except (ValueError, TypeError):
                return _json_response({"ok": False, "error": "Invalid island props"}, status_code=400)

        view_id = request.query_params.get("view_id") or "/"
        state_context, csrf_token = await self._state_context(request, view_id)
        try:
            with state_context.activate():
                with state_context.track_component(island_id):
                    node = spec.handler(**clean_props)
                    self.registry.validate(node)
                    self._validate_commands(node)
                    inner_html = self.renderer.render_component(node, state_context, csrf_token)
                safe_state: dict[str, Any] = {}
                for key in spec.allowed_state_keys:
                    val = _read_island_allowed_state(state_context, key)
                    if val is not None:
                        safe_state[key] = val
                safe_state = sanitize_island_state(safe_state)
        except Exception:
            _LOGGER.exception("Island hydration failed for %s", island_id)
            return _json_response({"ok": False, "error": "Island hydration failed"}, status_code=500)

        return _json_response({
            "ok": True,
            "island_id": island_id,
            "name": spec.name,
            "html": inner_html,
            "state": safe_state,
        })

    async def _inspect_traces_endpoint(self, request: Request) -> Response:
        denied = await self._authorize_inspector(request, permission="inspect:traces")
        if denied is not None:
            return denied
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
        denied = await self._authorize_inspector(request, permission="inspect:stats")
        if denied is not None:
            return denied
        return _json_response({
            "ok": True,
            "stats": self.inspector.stats(),
        })

    async def _inspect_dag_endpoint(self, request: Request) -> Response:
        denied = await self._authorize_inspector(request, permission="inspect:dag")
        if denied is not None:
            return denied
        from radui.inspector.graph import extract_dag_structure, generate_dag_svg
        format_param = request.query_params.get("format", "").lower()
        accept_header = request.headers.get("accept", "").lower()
        if format_param == "json" or "application/json" in accept_header:
            data = extract_dag_structure(self.state_runtime.dependencies)
            return _json_response({"ok": True, **data})

        svg = generate_dag_svg(self.state_runtime.dependencies)
        return Response(content=svg, media_type="image/svg+xml")

    async def _inspect_page_endpoint(self, request: Request) -> Response:
        denied = await self._authorize_inspector(request, permission="inspect:dashboard", html_error=True)
        if denied is not None:
            return denied
        import html as html_lib
        from radui.diagnostics import render_inspector_dashboard_html
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
        runtime_data = await asyncio.to_thread(self.diagnostics.runtime_diagnostics, self)
        jobs_data = await asyncio.to_thread(self.diagnostics.job_diagnostics, self, limit=25, offset=0)
        sse_data = self.diagnostics.sse_diagnostics(self)
        html = render_inspector_dashboard_html(
            app_id=self.metadata.id,
            page_count=len(self._pages),
            command_count=len(self._commands),
            job_count=len(self._jobs),
            total_traces=int(stats.get("total_records", 0)),
            runtime_data=runtime_data,
            jobs_data=jobs_data,
            sse_data=sse_data,
            traces_rows_html=rows_html,
            dag_svg=dag_svg,
        )
        return HTMLResponse(html)

    async def _devtools_status_endpoint(self, request: Request) -> Response:
        mgr = self.devtools_manager
        return _json_response({
            "ok": True,
            "enabled": mgr is not None,
            "can_undo": mgr.can_undo if mgr else False,
            "can_redo": mgr.can_redo if mgr else False,
            "count": len(mgr._history) if mgr else 0,
        })

    async def _devtools_history_endpoint(self, request: Request) -> Response:
        mgr = self.devtools_manager
        history = mgr.get_history() if mgr else []
        return _json_response({"ok": True, "history": history})

    async def _devtools_rollback_endpoint(self, request: Request) -> Response:
        mgr = self.devtools_manager
        if not mgr:
            return _json_response({"ok": False, "error": "DevTools not enabled"}, status_code=400)
        form = await request.form()
        steps = int(form.get("steps", 1))
        restorations = mgr.rollback_steps(steps)
        session_id, _ = self._session(request)
        ctx = self.state_context(session_id=session_id)
        for k, v in restorations:
            ctx.set(k, v)
        return _json_response({"ok": True, "restored": restorations})

    async def _presence_heartbeat_endpoint(self, request: Request) -> Response:
        from radui.core.presence import get_global_presence_manager
        pm = get_global_presence_manager()
        form = await request.form()
        room = form.get("room", "default")
        user_id = form.get("user_id", "anon")
        field_id = form.get("field")
        active = pm.heartbeat(room, user_id, current_field=field_id)
        return _json_response({"ok": True, "users": [u.__dict__ for u in active]})

    async def _presence_join_endpoint(self, request: Request) -> Response:
        from radui.core.presence import get_global_presence_manager, PresenceUser
        pm = get_global_presence_manager()
        form = await request.form()
        room = form.get("room", "default")
        user = PresenceUser(
            user_id=form.get("user_id", secrets.token_hex(4)),
            username=form.get("username", "Anonymous"),
            color=form.get("color", "#10b981"),
        )
        active = pm.join(room, user)
        return _json_response({"ok": True, "user_id": user.user_id, "users": [u.__dict__ for u in active]})

    async def _presence_leave_endpoint(self, request: Request) -> Response:
        from radui.core.presence import get_global_presence_manager
        pm = get_global_presence_manager()
        form = await request.form()
        pm.leave(form.get("room", "default"), form.get("user_id", ""))
        return _json_response({"ok": True})

    async def _presence_users_endpoint(self, request: Request) -> Response:
        from radui.core.presence import get_global_presence_manager
        pm = get_global_presence_manager()
        room = request.query_params.get("room", "default")
        active = pm.get_active_users(room)
        return _json_response({"ok": True, "users": [u.__dict__ for u in active]})

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
            Route("/_gx/islands/{island_id}", self._island_endpoint, methods=["GET"]),
            Route("/_gx/navigate", self._navigate_endpoint, methods=["GET"]),
            Route("/_gx/resume", self._resume_endpoint, methods=["POST"]),
            Route("/_gx/refresh", self._refresh_endpoint, methods=["GET"]),
            Route("/_gx/commands/{command_id}", self._command_endpoint, methods=["POST"]),
            Route("/_gx/jobs/{job_id}/cancel", self._job_cancel_endpoint, methods=["POST"]),
            Route("/_gx/inspect", self._inspect_page_endpoint, methods=["GET"]),
            Route("/_gx/inspect/runtime", self._inspect_runtime_endpoint, methods=["GET"]),
            Route("/_gx/inspect/jobs", self._inspect_jobs_endpoint, methods=["GET"]),
            Route("/_gx/inspect/traces", self._inspect_traces_endpoint, methods=["GET"]),
            Route("/_gx/inspect/stats", self._inspect_stats_endpoint, methods=["GET"]),
            Route("/_gx/inspect/dag", self._inspect_dag_endpoint, methods=["GET"]),
            Route("/_gx/inspect/sse", self._inspect_sse_endpoint, methods=["GET"]),
            Route("/_gx/inspect/config", self._inspect_config_endpoint, methods=["GET"]),
            Route("/_gx/inspect/backends", self._inspect_backends_endpoint, methods=["GET"]),
            Route("/_gx/devtools/status", self._devtools_status_endpoint, methods=["GET"]),
            Route("/_gx/devtools/history", self._devtools_history_endpoint, methods=["GET"]),
            Route("/_gx/devtools/rollback", self._devtools_rollback_endpoint, methods=["POST"]),
            Route("/_gx/presence/heartbeat", self._presence_heartbeat_endpoint, methods=["POST"]),
            Route("/_gx/presence/join", self._presence_join_endpoint, methods=["POST"]),
            Route("/_gx/presence/leave", self._presence_leave_endpoint, methods=["POST"]),
            Route("/_gx/presence/users", self._presence_users_endpoint, methods=["GET"]),
            Route("/health", self._health_endpoint, methods=["GET"]),
            Route("/ready", self._ready_endpoint, methods=["GET"]),
            Route("/_gx/health", self._gx_health_endpoint, methods=["GET"]),
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
                max_age=self._session_ttl_seconds,
                same_site="lax",
                https_only=self._session_cookie_secure,
            ),
            *self._custom_middleware,
        ]
        @asynccontextmanager
        async def lifespan(_app: Starlette):
            self._shutting_down = False
            self._ready = False
            self._startup_error = None
            try:
                self.config.validate()
                if hasattr(self.state_runtime.backend, "ping") and not self.state_runtime.backend.ping():
                    raise RuntimeError("State backend connectivity check failed")
                if hasattr(self.events.backend, "ping") and not self.events.backend.ping():
                    raise RuntimeError("Event backend connectivity check failed")
                for hook in self._startup_hooks:
                    res = hook()
                    if inspect.iscoroutine(res):
                        await res
                await self.jobs.startup()
                from radui.transport.governance import RedisSSEGovernance
                if isinstance(self.events.governance, RedisSSEGovernance):
                    self.register_background_task(
                        asyncio.create_task(
                            self.events.run_governance_renewal_loop(
                                interval=self.config.sse_heartbeat_interval_seconds
                            )
                        )
                    )
                if self.config.backend == "redis":
                    await asyncio.to_thread(self.observability.publish_snapshot)
                    self.register_background_task(asyncio.create_task(self._run_observability_heartbeat()))
                self._ready = True
                log_structured(
                    _LOGGER,
                    logging.INFO,
                    "app.startup",
                    app_id=self.metadata.id,
                    environment=self.config.environment,
                )
            except Exception as exc:
                self._ready = False
                self._startup_error = str(exc)
                log_structured(
                    _LOGGER,
                    logging.ERROR,
                    "app.startup_error",
                    app_id=self.metadata.id,
                    error=str(exc),
                )
                for task in list(self._background_tasks):
                    task.cancel()
                if self._background_tasks:
                    await asyncio.gather(*self._background_tasks, return_exceptions=True)
                try:
                    await self.jobs.shutdown()
                    if self.config.backend == "redis":
                        await asyncio.to_thread(self.observability.deregister)
                except Exception:
                    pass
                raise
            try:
                yield
            finally:
                self._shutting_down = True
                self._ready = False
                log_structured(_LOGGER, logging.INFO, "app.shutdown", app_id=self.metadata.id)
                self.events.close_all()
                for task in list(self._background_tasks):
                    task.cancel()
                if self._background_tasks:
                    await asyncio.wait_for(
                        asyncio.gather(*self._background_tasks, return_exceptions=True),
                        timeout=max(0.1, self.drain_timeout),
                    )
                await self._drain_commands(timeout=self.drain_timeout)
                for hook in reversed(self._shutdown_hooks):
                    try:
                        res = hook()
                        if inspect.iscoroutine(res):
                            await res
                    except Exception:
                        _LOGGER.exception("Error executing shutdown hook")
                await self.jobs.shutdown()
                if self.config.backend == "redis":
                    await asyncio.to_thread(self.observability.deregister)
                for backend_obj in (self.state_runtime.backend, self.events.backend):
                    if hasattr(backend_obj, "close"):
                        try:
                            backend_obj.close()
                        except Exception:
                            pass
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
