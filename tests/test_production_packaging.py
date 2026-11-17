from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest
from starlette.testclient import TestClient

import radui as gx
from radui.core.auth import User
from radui.core.config import ConfigurationError, RadUIConfig, redact_secrets
from radui.core.logging import RedactingJsonFormatter, log_structured


def test_config_precedence_production_defaults_and_validation():
    # 1. Production defaults: secure cookie=True, untrusted tenant headers=False
    prod_cfg = RadUIConfig.from_env(
        {
            "RADUI_ENV": "production",
            "RADUI_SESSION_SECRET": "a" * 32,
        }
    )
    assert prod_cfg.environment == "production"
    assert prod_cfg.session_cookie_secure is True
    assert prod_cfg.allow_untrusted_tenant_headers is False
    assert prod_cfg.debug is False

    # 2. Explicit kwargs override env vars
    overridden = RadUIConfig.from_env(
        {"RADUI_ENV": "staging", "RADUI_SESSION_SECRET": "a" * 32, "RADUI_LOG_LEVEL": "WARNING"},
        log_level="ERROR",
        drain_timeout=9.0,
    )
    assert overridden.log_level == "ERROR"
    assert overridden.drain_timeout == 9.0

    # 3. Missing session_secret in production fails closed
    with pytest.raises(ConfigurationError, match="RADUI_SESSION_SECRET"):
        RadUIConfig.from_env({"RADUI_ENV": "production"})

    # 4. debug=True in production fails closed
    with pytest.raises(ConfigurationError, match="debug=True is forbidden"):
        RadUIConfig.from_env(
            {"RADUI_ENV": "production", "RADUI_SESSION_SECRET": "a" * 32, "RADUI_DEBUG": "true"}
        )


def test_secret_redaction_in_config_and_structured_logs():
    cfg = RadUIConfig.from_env(
        {"RADUI_ENV": "production", "RADUI_SESSION_SECRET": "super-secret-value-at-least-32-chars"}
    )
    summary = cfg.safe_summary()
    assert summary["session_secret"] == "***REDACTED***"
    assert "super-secret-value" not in json.dumps(summary)

    redacted = redact_secrets({"api_key": "sk-123", "nested": {"password": "pw", "ok": 1}})
    assert redacted == {"api_key": "***REDACTED***", "nested": {"password": "***REDACTED***", "ok": 1}}

    fmt = RedactingJsonFormatter()
    rec = logging.LogRecord("radui", logging.INFO, __file__, 1, "app.startup", (), None)
    rec.radui_fields = {"token": "tok-xyz", "app_id": "demo"}
    out = fmt.format(rec)
    assert "tok-xyz" not in out
    assert "***REDACTED***" in out

    # Adversarial logging security: Authorization headers, cookies, bearer tokens, DB DSNs, exceptions, custom fields
    adv_payload = {
        "headers": {
            "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.secretpayload.sig",
            "Cookie": "RADUI_session=signed_cookie_secret_value",
        },
        "db_dsn": "postgresql://admin:hunter2_pass@db.internal:5432/prod",
        "custom_credential": "my-custom-cred-999",
        "nested": [{"api_key": "sk-live-secret-123"}],
    }
    scrubbed = redact_secrets(adv_payload)
    dumped = json.dumps(scrubbed)
    for secret in ("secretpayload", "signed_cookie_secret_value", "hunter2_pass", "my-custom-cred-999", "sk-live-secret-123"):
        assert secret not in dumped

    # Exception message & raw log message scrubbing
    try:
        raise RuntimeError("Failed connecting to redis://user:redis_pw@cache:6379/0 with Bearer tok_abc_123")
    except RuntimeError:
        import sys as _sys
        exc_rec = logging.LogRecord(
            "radui",
            logging.ERROR,
            __file__,
            1,
            "Auth failed Authorization=Basic dXNlcjpwYXNz password=raw_pw_1",
            (),
            _sys.exc_info(),
        )
        formatted = fmt.format(exc_rec)
        for secret in ("redis_pw", "tok_abc_123", "dXNlcjpwYXNz", "raw_pw_1"):
            assert secret not in formatted

    # Formatter failure fallback never leaks unredacted data
    class BadObj:
        def __str__(self) -> str:
            raise ValueError("secret_in_str_error")

    bad_rec = logging.LogRecord("radui", logging.INFO, __file__, 1, "msg", (), None)
    bad_rec.radui_fields = {"ok": BadObj()}
    bad_out = fmt.format(bad_rec)
    assert "secret_in_str_error" not in bad_out
    assert "redacted for safety" in bad_out


def test_readiness_dependency_transitions_and_before_startup():
    dep_ok = [True]
    app = gx.App("Ready Transitions")
    app.add_readiness_check(lambda: dep_ok[0])

    # Before lifespan startup, _ready is False -> /ready must be 503 while /health is 200
    no_lifespan_client = TestClient(app.asgi())
    assert no_lifespan_client.get("/health").status_code == 200
    assert no_lifespan_client.get("/ready").status_code == 503

    with TestClient(app.asgi()) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200

        # Required dependency becomes unavailable -> /ready transitions to 503, /health stays 200
        dep_ok[0] = False
        assert client.get("/ready").status_code == 503
        assert client.get("/health").status_code == 200

        dep_ok[0] = True
        assert client.get("/ready").status_code == 200


def test_health_readiness_lifecycle_and_background_task_cleanup():
    events: list[str] = []
    bg_cancelled = [False]
    current_user: list[User | None] = [None]

    app = gx.App(
        "Lifecycle App",
        session_secret="super-secret-key-at-least-32-chars-long!",
        user_resolver=lambda _req: current_user[0],
    )

    @app.on_startup
    async def on_start():
        events.append("startup")

        async def bg_loop():
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                bg_cancelled[0] = True
                raise

        app.register_background_task(asyncio.create_task(bg_loop()))

    @app.on_shutdown
    async def on_stop():
        events.append("shutdown")

    @app.page("/")
    def home():
        return gx.text("ok")

    with TestClient(app.asgi()) as client:
        assert events == ["startup"]
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200
        assert client.get("/_gx/health").status_code == 200

        # /_gx/inspect/config requires inspector authorization
        assert client.get("/_gx/inspect/config").status_code == 401
        client.get("/")
        current_user[0] = User(id="u1", username="alice", roles=("viewer",))
        assert client.get("/_gx/inspect/config").status_code == 403
        current_user[0] = User(id="adm", username="root", roles=("admin",))
        r_cfg = client.get("/_gx/inspect/config")
        assert r_cfg.status_code == 200
        assert r_cfg.json()["config"]["session_secret"] == "***REDACTED***"

    assert events == ["startup", "shutdown"]
    assert bg_cancelled[0] is True


def test_lifespan_startup_error_and_sse_graceful_shutdown():
    app_err = gx.App("Broken Startup")

    @app_err.on_startup
    def bad_start():
        raise RuntimeError("db unreachable")

    with pytest.raises(RuntimeError, match="db unreachable"):
        with TestClient(app_err.asgi()):
            pass
    assert app_err._ready is False
    assert app_err._startup_error == "db unreachable"

    # Graceful shutdown closes active SSE subscribers cleanly
    app_sse = gx.App("SSE Shutdown")

    async def verify_sse_close():
        stream = app_sse.events.stream("s1", keepalive_seconds=10.0)
        waiter = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        assert app_sse.events.metrics()["active_subscribers"] == 1
        app_sse.events.close_all()
        ev = await asyncio.wait_for(waiter, timeout=1.0)
        assert "event: reset" in ev
        await stream.aclose()
        assert app_sse.events.metrics()["active_subscribers"] == 0

    asyncio.run(verify_sse_close())


def test_shared_static_js_extraction_reduces_html_size(tmp_path: Path):
    app = gx.App("Shared JS")
    app.page("/")(lambda: gx.heading("Static Home"))

    res = app.build_static(tmp_path / "dist")
    assert "radui.css" in res.assets
    assert "radui.static.js" in res.assets
    html = (tmp_path / "dist/index.html").read_text(encoding="utf-8")
    assert res.assets["radui.static.js"] in html
    assert len(html.encode("utf-8")) < 6_000


def test_wheel_and_sdist_packaging_and_cli_execution(tmp_path: Path):
    dist_dir = tmp_path / "pkg_dist"
    proc = subprocess.run(
        [sys.executable, "-m", "build", "--no-isolation", "--wheel", "--sdist", "--outdir", str(dist_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    wheels = list(dist_dir.glob("radui-*.whl"))
    sdists = list(dist_dir.glob("radui-*.tar.gz"))
    assert len(wheels) == 1
    assert len(sdists) == 1

    with zipfile.ZipFile(wheels[0]) as zf:
        names = zf.namelist()
        assert any(n.endswith("radui/core/config.py") for n in names)
        assert any(n.endswith("radui/core/ssg.py") for n in names)
        assert any(n.endswith("radui/core/islands.py") for n in names)

    # Verify CLI works cleanly from built wheel via PYTHONPATH
    cli_proc = subprocess.run(
        [sys.executable, "-m", "radui.cli", "version"],
        env={"PYTHONPATH": str(wheels[0]), "SYSTEMROOT": "C:\\Windows", "PATH": ""},
        capture_output=True,
        text=True,
        check=False,
    )
    assert cli_proc.returncode == 0, cli_proc.stderr
    assert "1.0.0" in cli_proc.stdout
