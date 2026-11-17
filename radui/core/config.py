from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
from typing import Any, Literal, Mapping, Sequence

EnvironmentMode = Literal["development", "testing", "staging", "production"]
BackendMode = Literal["memory", "sqlite", "redis"]
VALID_ENVIRONMENTS: frozenset[str] = frozenset({"development", "testing", "staging", "production"})
VALID_BACKENDS: frozenset[str] = frozenset({"memory", "sqlite", "redis"})

_SENSITIVE_KEY_PARTS: tuple[str, ...] = (
    "secret",
    "password",
    "passwd",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "cookie",
    "authorization",
    "credential",
    "dsn",
    "connection_string",
)

_BEARER_RE = re.compile(r"\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_DB_DSN_RE = re.compile(r"\b(postgres(?:ql)?|mysql|redis|rediss|amqp|mongodb)://([^:/@\s]+):([^@\s]+)@", re.IGNORECASE)
_KV_SECRET_RE = re.compile(
    r"\b(password|passwd|secret|token|api_key|apikey|authorization|cookie|session_secret|private_key)\s*([:=])\s*([^\s,;'\"]+)",
    re.IGNORECASE,
)


def scrub_secret_strings(text: str) -> str:
    """Mask bearer tokens, database credentials, and inline secret key-values in strings."""
    text = _BEARER_RE.sub(lambda m: f"{m.group(1)} ***REDACTED***", text)
    text = _DB_DSN_RE.sub(lambda m: f"{m.group(1)}://{m.group(2)}:***REDACTED***@", text)
    text = _KV_SECRET_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***REDACTED***", text)
    return text


class ConfigurationError(ValueError):
    """Raised when application configuration is invalid or unsafe for the target environment."""


def redact_secrets(data: Any) -> Any:
    """Recursively mask sensitive fields and inline secret patterns for safe logging."""
    if isinstance(data, str):
        return scrub_secret_strings(data)
    if isinstance(data, Mapping):
        clean: dict[str, Any] = {}
        for k, v in data.items():
            key_str = str(k)
            lowered = key_str.lower()
            if any(part in lowered for part in _SENSITIVE_KEY_PARTS):
                clean[key_str] = "***REDACTED***" if v not in (None, "") else None
            else:
                clean[key_str] = redact_secrets(v)
        return clean
    if isinstance(data, (list, tuple)):
        return [redact_secrets(item) for item in data]
    return data


def _parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    val = raw.strip().lower()
    if val in {"1", "true", "yes", "on"}:
        return True
    if val in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"Invalid boolean configuration value: {raw!r}")


def _parse_csv(raw: str | None) -> tuple[str, ...]:
    if not raw or not raw.strip():
        return ()
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class RadUIConfig:
    """Production configuration with explicit precedence: kwargs > env > secure defaults."""

    environment: EnvironmentMode = "development"
    debug: bool = False
    session_secret: str | None = field(default=None, repr=False)
    session_cookie_secure: bool = False
    session_ttl_seconds: int = 14 * 86400
    trusted_origins: tuple[str, ...] = ()
    trusted_proxies: tuple[str, ...] = ()
    allow_untrusted_tenant_headers: bool = True
    drain_timeout: float = 5.0
    request_timeout: float = 30.0
    log_level: str = "INFO"
    sse_max_connections_per_session: int = 8
    sse_max_connections_per_ip: int = 32
    sse_connect_rate_limit: int = 30
    sse_connect_rate_window_seconds: float = 60.0
    sse_lease_ttl_seconds: float = 30.0
    sse_heartbeat_interval_seconds: float = 10.0
    sse_governance_fail_open: bool = False
    backend: BackendMode = "memory"
    redis_url: str | None = field(default=None, repr=False)
    sqlite_path: str | None = None
    state_ttl_seconds: int | None = None
    inspector_enabled: bool | None = None

    def is_inspector_enabled(self) -> bool:
        """Return whether /_gx/inspect* routes are enabled (disabled by default in production)."""
        if self.inspector_enabled is not None:
            return bool(self.inspector_enabled)
        return self.environment != "production"

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        environment: EnvironmentMode | None = None,
        debug: bool | None = None,
        session_secret: str | None = None,
        session_cookie_secure: bool | None = None,
        session_ttl_seconds: int | None = None,
        trusted_origins: Sequence[str] | None = None,
        trusted_proxies: Sequence[str] | None = None,
        allow_untrusted_tenant_headers: bool | None = None,
        drain_timeout: float | None = None,
        request_timeout: float | None = None,
        log_level: str | None = None,
        sse_max_connections_per_session: int | None = None,
        sse_max_connections_per_ip: int | None = None,
        sse_connect_rate_limit: int | None = None,
        sse_connect_rate_window_seconds: float | None = None,
        sse_lease_ttl_seconds: float | None = None,
        sse_heartbeat_interval_seconds: float | None = None,
        sse_governance_fail_open: bool | None = None,
        backend: BackendMode | None = None,
        redis_url: str | None = None,
        sqlite_path: str | None = None,
        state_ttl_seconds: int | None = None,
        inspector_enabled: bool | None = None,
    ) -> RadUIConfig:
        environ = env if env is not None else os.environ

        eff_env = (environment or environ.get("RADUI_ENV") or "development").strip().lower()
        if eff_env not in VALID_ENVIRONMENTS:
            raise ConfigurationError(
                f"Invalid RADUI_ENV {eff_env!r}; expected one of: {', '.join(sorted(VALID_ENVIRONMENTS))}"
            )
        is_prod_like = eff_env in {"production", "staging"}

        eff_debug = debug if debug is not None else _parse_bool(environ.get("RADUI_DEBUG"), False)
        eff_secret = session_secret if session_secret is not None else environ.get("RADUI_SESSION_SECRET")
        if eff_secret == "":
            eff_secret = None
        eff_cookie_secure = (
            session_cookie_secure
            if session_cookie_secure is not None
            else _parse_bool(environ.get("RADUI_SESSION_COOKIE_SECURE"), is_prod_like)
        )
        eff_ttl = (
            session_ttl_seconds
            if session_ttl_seconds is not None
            else int(environ.get("RADUI_SESSION_TTL_SECONDS", 14 * 86400))
        )
        eff_origins = (
            tuple(trusted_origins)
            if trusted_origins is not None
            else _parse_csv(environ.get("RADUI_TRUSTED_ORIGINS"))
        )
        eff_proxies = (
            tuple(trusted_proxies)
            if trusted_proxies is not None
            else _parse_csv(environ.get("RADUI_TRUSTED_PROXIES"))
        )
        eff_untrusted_tenants = (
            allow_untrusted_tenant_headers
            if allow_untrusted_tenant_headers is not None
            else _parse_bool(environ.get("RADUI_ALLOW_UNTRUSTED_TENANT_HEADERS"), not is_prod_like)
        )
        eff_drain = (
            drain_timeout
            if drain_timeout is not None
            else float(environ.get("RADUI_DRAIN_TIMEOUT", 5.0))
        )
        eff_req_timeout = (
            request_timeout
            if request_timeout is not None
            else float(environ.get("RADUI_REQUEST_TIMEOUT", 30.0))
        )
        eff_log_level = (log_level or environ.get("RADUI_LOG_LEVEL") or "INFO").strip().upper()
        eff_sse_sess = (
            sse_max_connections_per_session
            if sse_max_connections_per_session is not None
            else int(environ.get("RADUI_SSE_MAX_PER_SESSION", 8))
        )
        eff_sse_ip = (
            sse_max_connections_per_ip
            if sse_max_connections_per_ip is not None
            else int(environ.get("RADUI_SSE_MAX_PER_IP", 32))
        )
        eff_sse_rl = (
            sse_connect_rate_limit
            if sse_connect_rate_limit is not None
            else int(environ.get("RADUI_SSE_RATE_LIMIT", 30))
        )
        eff_sse_rw = (
            sse_connect_rate_window_seconds
            if sse_connect_rate_window_seconds is not None
            else float(environ.get("RADUI_SSE_RATE_WINDOW", 60.0))
        )
        eff_sse_lease = (
            sse_lease_ttl_seconds
            if sse_lease_ttl_seconds is not None
            else float(environ.get("RADUI_SSE_LEASE_TTL_SECONDS", 30.0))
        )
        eff_sse_hb = (
            sse_heartbeat_interval_seconds
            if sse_heartbeat_interval_seconds is not None
            else float(environ.get("RADUI_SSE_HEARTBEAT_INTERVAL_SECONDS", 10.0))
        )
        eff_sse_fail_open = (
            sse_governance_fail_open
            if sse_governance_fail_open is not None
            else _parse_bool(environ.get("RADUI_SSE_GOVERNANCE_FAIL_OPEN"), False)
        )
        eff_backend = (backend or environ.get("RADUI_BACKEND") or "memory").strip().lower()
        if eff_backend not in VALID_BACKENDS:
            raise ConfigurationError(
                f"Invalid RADUI_BACKEND {eff_backend!r}; expected one of: {', '.join(sorted(VALID_BACKENDS))}"
            )
        eff_redis_url = redis_url if redis_url is not None else environ.get("RADUI_REDIS_URL")
        if eff_redis_url == "":
            eff_redis_url = None
        eff_sqlite_path = sqlite_path if sqlite_path is not None else environ.get("RADUI_SQLITE_PATH")
        raw_ttl = environ.get("RADUI_STATE_TTL_SECONDS")
        eff_state_ttl = state_ttl_seconds if state_ttl_seconds is not None else (int(raw_ttl) if raw_ttl else None)
        eff_inspector = (
            inspector_enabled
            if inspector_enabled is not None
            else (_parse_bool(environ.get("RADUI_INSPECTOR_ENABLED"), False) if "RADUI_INSPECTOR_ENABLED" in environ else None)
        )

        cfg = cls(
            environment=eff_env,  # type: ignore[arg-type]
            debug=eff_debug,
            session_secret=eff_secret,
            session_cookie_secure=eff_cookie_secure,
            session_ttl_seconds=eff_ttl,
            trusted_origins=eff_origins,
            trusted_proxies=eff_proxies,
            allow_untrusted_tenant_headers=eff_untrusted_tenants,
            drain_timeout=eff_drain,
            request_timeout=eff_req_timeout,
            log_level=eff_log_level,
            sse_max_connections_per_session=eff_sse_sess,
            sse_max_connections_per_ip=eff_sse_ip,
            sse_connect_rate_limit=eff_sse_rl,
            sse_connect_rate_window_seconds=eff_sse_rw,
            sse_lease_ttl_seconds=eff_sse_lease,
            sse_heartbeat_interval_seconds=eff_sse_hb,
            sse_governance_fail_open=eff_sse_fail_open,
            backend=eff_backend,  # type: ignore[arg-type]
            redis_url=eff_redis_url,
            sqlite_path=eff_sqlite_path,
            state_ttl_seconds=eff_state_ttl,
            inspector_enabled=eff_inspector,
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.session_secret is not None and len(self.session_secret) < 32:
            raise ConfigurationError("session_secret must contain at least 32 characters")
        if self.session_ttl_seconds < 1:
            raise ConfigurationError("session_ttl_seconds must be at least 1")
        if self.drain_timeout < 0:
            raise ConfigurationError("drain_timeout must be non-negative")
        if self.request_timeout <= 0:
            raise ConfigurationError("request_timeout must be positive")
        if self.backend == "redis" and not self.redis_url:
            raise ConfigurationError("RADUI_REDIS_URL (or explicit redis_url) is required when backend='redis'")
        if self.state_ttl_seconds is not None and self.state_ttl_seconds < 1:
            raise ConfigurationError("state_ttl_seconds must be at least 1")
        if self.sse_lease_ttl_seconds < 3.0:
            raise ConfigurationError("sse_lease_ttl_seconds must be at least 3.0")
        if self.sse_heartbeat_interval_seconds <= 0 or self.sse_heartbeat_interval_seconds >= self.sse_lease_ttl_seconds:
            raise ConfigurationError("sse_heartbeat_interval_seconds must be > 0 and < sse_lease_ttl_seconds")
        if self.environment == "production":
            if self.debug:
                raise ConfigurationError("debug=True is forbidden when RADUI_ENV='production'")
            if not self.session_secret:
                raise ConfigurationError(
                    "RADUI_SESSION_SECRET (or explicit session_secret >= 32 chars) is required in production"
                )

    def safe_summary(self) -> dict[str, Any]:
        """Return a redacted configuration summary safe for inspector/log output."""
        return redact_secrets({
            "environment": self.environment,
            "debug": self.debug,
            "session_secret": self.session_secret,
            "session_cookie_secure": self.session_cookie_secure,
            "session_ttl_seconds": self.session_ttl_seconds,
            "trusted_origins": list(self.trusted_origins),
            "trusted_proxies": list(self.trusted_proxies),
            "allow_untrusted_tenant_headers": self.allow_untrusted_tenant_headers,
            "drain_timeout": self.drain_timeout,
            "request_timeout": self.request_timeout,
            "log_level": self.log_level,
            "sse_max_connections_per_session": self.sse_max_connections_per_session,
            "sse_max_connections_per_ip": self.sse_max_connections_per_ip,
            "sse_connect_rate_limit": self.sse_connect_rate_limit,
            "sse_connect_rate_window_seconds": self.sse_connect_rate_window_seconds,
            "backend": self.backend,
            "redis_url": self.redis_url,
            "sqlite_path": self.sqlite_path,
            "state_ttl_seconds": self.state_ttl_seconds,
        })
