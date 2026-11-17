from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import socket
import threading
import time
import uuid

import pytest
import redis
from starlette.testclient import TestClient

import radui as gx
from radui.core.auth import User
from radui.core.config import RadUIConfig
from radui.jobs.redis import RedisJobBackend
from radui.jobs.runtime import JobContext
from radui.observability import WorkerIdentity

REDIS_URL = "redis://127.0.0.1:6379/14"

INSPECTOR_ROUTES = (
    "/_gx/inspect",
    "/_gx/inspect/runtime",
    "/_gx/inspect/jobs",
    "/_gx/inspect/sse",
    "/_gx/inspect/traces",
    "/_gx/inspect/stats",
    "/_gx/inspect/dag",
    "/_gx/inspect/config",
    "/_gx/inspect/backends",
)


def _live_redis_available() -> bool:
    try:
        r = redis.from_url(REDIS_URL, socket_connect_timeout=0.5, socket_timeout=0.5)
        return bool(r.ping())
    except Exception:
        return False


def _cleanup_prefix(prefix: str) -> None:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    keys = list(r.scan_iter(f"{prefix}*"))
    if keys:
        r.delete(*keys)
    r.close()


# ---------------------------------------------------------------------------
# Security, Authorization & Redaction Tests
# ---------------------------------------------------------------------------


def test_inspector_disabled_by_default_in_production():
    cfg = RadUIConfig(
        environment="production",
        session_secret="super-secret-prod-key-at-least-32-chars!",
        trusted_origins=("https://example.com",),
    )
    assert cfg.is_inspector_enabled() is False
    admin = User(id="a1", username="admin", roles=("admin",))
    app = gx.App("ProdDisabled", config=cfg, user_resolver=lambda _req: admin)

    with TestClient(app.asgi()) as client:
        for route in INSPECTOR_ROUTES:
            res = client.get(route)
            assert res.status_code == 404, f"Expected 404 for {route} in production, got {res.status_code}"


def test_inspector_explicit_production_enablement_and_rbac_across_all_routes():
    cfg = RadUIConfig(
        environment="production",
        inspector_enabled=True,
        session_secret="super-secret-prod-key-at-least-32-chars!",
        trusted_origins=("https://example.com",),
    )
    current_user: list[User | None] = [None]
    app = gx.App("ProdEnabled", config=cfg, user_resolver=lambda _req: current_user[0])

    @app.page("/")
    def index():
        return gx.text("ok")

    with TestClient(app.asgi()) as client:
        # 1. No session -> 401 on every HTML and JSON inspector route
        for route in INSPECTOR_ROUTES:
            assert client.get(route).status_code == 401

        # Mint session, still unauthenticated -> 401
        assert client.get("/").status_code == 200
        for route in INSPECTOR_ROUTES:
            assert client.get(route).status_code == 401

        # 2. Non-inspector user -> 403 on every route
        current_user[0] = User(id="u1", username="viewer", roles=("viewer",))
        for route in INSPECTOR_ROUTES:
            assert client.get(route).status_code == 403

        # 3. Inspector user -> 200 on every route
        current_user[0] = User(id="insp1", username="inspector", roles=("inspector",))
        for route in INSPECTOR_ROUTES:
            assert client.get(route).status_code == 200


def test_diagnostics_redaction_and_ttl_honesty():
    secret = "ultra-secret-session-key-32-chars-minimum!"
    cfg = RadUIConfig(
        environment="testing",
        session_secret=secret,
        redis_url="redis://admin:dbpass123@localhost:6379/0",
    )
    inspector = User(id="insp", username="insp", roles=("inspector",))
    app = gx.App("RedactApp", config=cfg, user_resolver=lambda _req: inspector)

    @app.page("/")
    def index():
        return gx.text("ok")

    with TestClient(app.asgi()) as client:
        client.get("/")
        rt = client.get("/_gx/inspect/runtime")
        assert rt.status_code == 200
        body_text = rt.text
        assert secret not in body_text
        assert "dbpass123" not in body_text
        data = rt.json()
        assert data["cluster"]["state"]["ttl_expirations"]["available"] is False
        assert "not currently" in data["cluster"]["state"]["ttl_expirations"]["note"].lower()

        sse = client.get("/_gx/inspect/sse")
        assert sse.status_code == 200
        sse_data = sse.json()
        assert set(sse_data["metrics"].keys()) == {
            "active_connections",
            "active_subscribers",
            "rejected_connections",
            "connection_limit_violations",
            "rate_limit_violations",
            "disconnects",
            "queue_overflows",
            "reconnection_attempts",
            "events_published",
            "events_delivered",
            "backend_errors",
        }


def test_jobs_pagination_and_payload_exclusion():
    inspector = User(id="insp", username="insp", roles=("inspector",))
    app = gx.App(
        "JobDiagApp",
        config=RadUIConfig(environment="testing", session_secret="x" * 32),
        user_resolver=lambda _req: inspector,
    )

    @app.page("/")
    def index():
        return gx.text("ok")

    # Seed local job snapshots with sensitive args/kwargs/results
    from radui.jobs.runtime import JobSnapshot, JobStatus

    for i in range(5):
        app.jobs._latest[f"job-{i}"] = JobSnapshot(
            id=f"job-{i}",
            name="secret_job",
            status=JobStatus.RUNNING if i < 3 else JobStatus.FAILED,
            session_id="secret-sess-id",
            user_id="secret-user",
            progress=50 if i < 3 else None,
            message="token=abc123",
            result_text="should_not_leak",
            result_available=True,
            error_type="RuntimeError" if i >= 3 else None,
            created_at="2026-11-17T00:00:00Z",
            updated_at="2026-11-17T00:00:01Z",
        )

    with TestClient(app.asgi()) as client:
        client.get("/")
        assert client.get("/_gx/inspect/jobs?limit=0").status_code == 400
        assert client.get("/_gx/inspect/jobs?offset=-1").status_code == 400

        r = client.get("/_gx/inspect/jobs?limit=2&offset=1")
        assert r.status_code == 200
        payload = r.json()
        assert payload["active_count"] == 3
        assert payload["dlq_depth"] == 2
        assert len(payload["active_jobs"]) == 2
        assert len(payload["dlq_jobs"]) == 1
        assert "should_not_leak" not in r.text
        assert "abc123" not in r.text

        # Clamping limit > 100
        r_clamp = client.get("/_gx/inspect/jobs?limit=999")
        assert r_clamp.status_code == 200
        assert r_clamp.json()["pagination"]["limit"] == 100


def test_dashboard_html_and_concurrent_requests():
    inspector = User(id="insp", username="insp", roles=("inspector",))
    app = gx.App(
        "DashApp",
        config=RadUIConfig(environment="testing", session_secret="y" * 32),
        user_resolver=lambda _req: inspector,
    )

    @app.page("/")
    def index():
        return gx.text("ok")

    with TestClient(app.asgi()) as client:
        client.get("/")
        dash = client.get("/_gx/inspect")
        assert dash.status_code == 200
        assert "RADUI Runtime Inspector" in dash.text
        assert "gx-refresh-btn" in dash.text
        assert "gx-autorefresh-toggle" in dash.text
        assert "Worker Roster" in dash.text
        assert "SSE Governance" in dash.text
        lowered = dash.text.lower()
        assert "<script src=" not in lowered
        assert "cdn." not in lowered

        def fetch_rt(_i: int) -> int:
            return client.get("/_gx/inspect/runtime").status_code

        with ThreadPoolExecutor(max_workers=6) as pool:
            statuses = list(pool.map(fetch_rt, range(10)))
        assert all(s == 200 for s in statuses)


# ---------------------------------------------------------------------------
# Live Redis 7.4.11 Multi-Worker, Stale, Malformed & Outage Diagnostics Tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _live_redis_available(), reason="NOT EXECUTED: live Redis server unavailable")
def test_live_redis_runtime_diagnostics_states_and_jobs():
    ns = f"test:diag:{uuid.uuid4().hex[:8]}:"
    obs_prefix = f"{ns}obs:worker:"
    job_prefix = f"{ns}jobs:"
    r = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        inspector = User(id="insp", username="insp", roles=("inspector",))
        jb = RedisJobBackend(REDIS_URL, prefix=job_prefix, client=r, worker_id="diag-w1")
        cfg = RadUIConfig(
            environment="testing",
            backend="redis",
            redis_url=REDIS_URL,
            session_secret="z" * 32,
        )
        app = gx.App("LiveDiag", config=cfg, job_backend=jb, user_resolver=lambda _req: inspector)
        app.observability.prefix = obs_prefix
        app.diagnostics.cache_ttl_seconds = 0.0

        @app.page("/")
        def index():
            return gx.text("ok")

        with TestClient(app.asgi()) as client:
            client.get("/")

            # 1. Zero-worker cluster (after deregistering or clearing obs keys)
            _cleanup_prefix(obs_prefix)
            rt_zero = client.get("/_gx/inspect/runtime").json()
            assert rt_zero["cluster"]["available"] is True
            assert rt_zero["cluster"]["active_workers"] == 0
            assert rt_zero["status"] == "degraded"
            assert any("zero active workers" in w.lower() for w in rt_zero["warnings"])

            # 2. Healthy multi-worker + stale + malformed snapshots
            assert app.observability.publish_snapshot() is True
            stale_ts = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
            r.set(
                f"{obs_prefix}stale-worker",
                json.dumps(
                    {
                        "worker": WorkerIdentity(
                            worker_id="stale-worker",
                            hostname="h2",
                            pid=999,
                            started_at=stale_ts,
                            environment="testing",
                            backend_mode="redis",
                        ).to_dict(),
                        "status": "active",
                        "timestamp": stale_ts,
                        "subsystems": {"state": {}, "events": {}, "sse": {}, "jobs": {}},
                    }
                ),
                ex=30,
            )
            r.set(f"{obs_prefix}bad-worker", "{malformed-json", ex=30)

            rt_deg = client.get("/_gx/inspect/runtime").json()
            assert rt_deg["redis"]["connected"] is True
            assert rt_deg["redis"]["ping_ms"] >= 0.0
            assert rt_deg["cluster"]["active_workers"] == 2
            assert rt_deg["cluster"]["stale_workers"] == 1
            assert rt_deg["cluster"]["malformed_snapshots"] == 1
            assert rt_deg["status"] == "degraded"

            # 3. Job diagnostics with active lease & DLQ without exposing args/kwargs
            r.set(f"{job_prefix}job:j1", json.dumps({"id": "j1", "name": "work", "status": "running", "attempt": 1, "max_retries": 3, "args": ["secret-arg"]}))
            r.sadd(f"{job_prefix}active", "j1")
            r.set(f"{job_prefix}lock:j1", "diag-w1", ex=25)
            r.set(f"{job_prefix}job:j2", json.dumps({"id": "j2", "name": "dead", "status": "failed", "attempt": 4, "max_retries": 3, "error_type": "TimeoutError", "kwargs": {"token": "secret-kw"}}))
            r.rpush(f"{job_prefix}dlq", "j2")

            jb_res = client.get("/_gx/inspect/jobs")
            assert jb_res.status_code == 200
            jb_data = jb_res.json()
            assert jb_data["available"] is True
            assert jb_data["active_count"] == 1
            assert jb_data["dlq_depth"] == 1
            assert jb_data["active_jobs"][0]["owner_worker_id"] == "diag-w1"
            assert jb_data["active_jobs"][0]["lease_remaining_seconds"] > 0
            assert "secret-arg" not in jb_res.text
            assert "secret-kw" not in jb_res.text

            # 4. Simulated Redis outage & recovery
            saved_ev_cli = app.events.backend._client
            saved_st_cli = app.state_runtime.backend._client
            saved_jb_cli = app.jobs._redis_client
            app.events.backend._client = None
            app.state_runtime.backend._client = None
            app.jobs._redis_client = None

            rt_down = client.get("/_gx/inspect/runtime").json()
            assert rt_down["status"] == "unavailable"
            assert rt_down["redis"]["connected"] is False
            assert rt_down["cluster"]["available"] is False
            assert rt_down["cluster"]["jobs"]["queue_depth"] is None

            jb_down = client.get("/_gx/inspect/jobs").json()
            assert jb_down["available"] is False
            assert jb_down["queue_depth"] is None

            # Restore
            app.events.backend._client = saved_ev_cli
            app.state_runtime.backend._client = saved_st_cli
            app.jobs._redis_client = saved_jb_cli
            r.delete(f"{obs_prefix}stale-worker", f"{obs_prefix}bad-worker")

            rt_up = client.get("/_gx/inspect/runtime").json()
            assert rt_up["status"] == "healthy"
            assert rt_up["redis"]["connected"] is True
    finally:
        r.close()
        _cleanup_prefix(ns)


def test_dashboard_browser_refresh_and_autorefresh():
    import asyncio
    import os
    import shutil
    import subprocess
    import tempfile
    import urllib.request
    import websockets
    import uvicorn

    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not os.path.exists(chrome_path):
        pytest.skip("Chrome binary not available")

    app = gx.App("BrowserDash", debug=True)

    @app.page("/")
    def index():
        return gx.text("ok")

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    cdp_sock = socket.socket()
    cdp_sock.bind(("127.0.0.1", 0))
    cdp_port = cdp_sock.getsockname()[1]
    cdp_sock.close()

    server = uvicorn.Server(uvicorn.Config(app.asgi(), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)

    user_data = tempfile.mkdtemp(prefix="radui-diag-chrome-")
    proc = subprocess.Popen(
        [
            chrome_path,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={user_data}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        ws_url = None
        for _ in range(50):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json/list", timeout=0.5) as resp:
                    targets = json.loads(resp.read().decode("utf-8"))
                    pages = [t for t in targets if t.get("type") == "page"]
                    if pages:
                        ws_url = pages[0]["webSocketDebuggerUrl"]
                        break
            except Exception:
                time.sleep(0.1)
        assert ws_url is not None

        async def run_cdp() -> None:
            async with websockets.connect(ws_url) as ws:
                msg_id = 0

                async def cdp(method: str, params: dict | None = None):
                    nonlocal msg_id
                    msg_id += 1
                    cid = msg_id
                    await ws.send(json.dumps({"id": cid, "method": method, "params": params or {}}))
                    while True:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        data = json.loads(raw)
                        if data.get("id") == cid:
                            return data.get("result", {})

                await cdp("Page.enable")
                await cdp("Runtime.enable")
                await cdp("Network.enable")
                await cdp("Page.navigate", {"url": f"http://127.0.0.1:{port}/_gx/inspect"})
                await asyncio.sleep(0.6)

                title_res = await cdp("Runtime.evaluate", {"expression": "document.querySelector('h1').innerText", "returnByValue": True})
                assert "RADUI Runtime Inspector" in title_res["result"]["value"]

                ts1 = (await cdp("Runtime.evaluate", {"expression": "document.getElementById('gx-last-refresh').innerText", "returnByValue": True}))["result"]["value"]
                await asyncio.sleep(1.1)
                await cdp("Runtime.evaluate", {"expression": "document.getElementById('gx-refresh-btn').click()"})
                await asyncio.sleep(0.5)
                ts2 = (await cdp("Runtime.evaluate", {"expression": "document.getElementById('gx-last-refresh').innerText", "returnByValue": True}))["result"]["value"]
                assert ts2 != ts1

                await cdp("Runtime.evaluate", {"expression": "document.getElementById('gx-autorefresh-toggle').click()"})
                checked = (await cdp("Runtime.evaluate", {"expression": "document.getElementById('gx-autorefresh-toggle').checked", "returnByValue": True}))["result"]["value"]
                assert checked is True

        asyncio.run(run_cdp())
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3.0)
        except Exception:
            proc.kill()
        shutil.rmtree(user_data, ignore_errors=True)
        server.should_exit = True
        thread.join(timeout=2.0)
