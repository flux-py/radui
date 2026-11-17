from __future__ import annotations

import time
import uuid

import pytest
from starlette.testclient import TestClient

import radui as gx
from radui.core.auth import User
from radui.core.config import RadUIConfig
from radui.state.backend import RedisStateBackend, StateBackendUnavailableError
from radui.transport.events import EventBroker, RedisEventBackend
from tests.chaos_harness import DisposableRedisContainer, poll_until


def _docker_available() -> bool:
    import subprocess

    try:
        res = subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3.0)
        return res.returncode == 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _docker_available(), reason="NOT EXECUTED: Docker daemon unavailable")


def test_chaos_redis_unavailable_at_startup_fails_closed():
    from tests.chaos_harness import free_port

    dead_url = f"redis://127.0.0.1:{free_port()}/0"
    cfg = RadUIConfig(
        environment="production",
        session_secret="super-secret-prod-key-at-least-32-chars!",
        trusted_origins=("https://example.com",),
        backend="redis",
        redis_url=dead_url,
    )
    app = gx.App("DeadRedisStartup", config=cfg)
    with pytest.raises(RuntimeError, match="connectivity check failed"):
        with TestClient(app.asgi()):
            pass


def test_chaos_redis_outage_and_repeated_recovery_without_worker_restart():
    container = DisposableRedisContainer()
    redis_url = container.start()
    try:
        inspector = User(id="insp", username="insp", roles=("inspector",))
        cfg = RadUIConfig(
            environment="testing",
            backend="redis",
            redis_url=redis_url,
            session_secret="x" * 32,
            sse_governance_fail_open=False,
        )
        app = gx.App("OutageApp", config=cfg, user_resolver=lambda _r: inspector)
        app.diagnostics.cache_ttl_seconds = 0.0
        app.add_readiness_check(lambda: app.state_runtime.backend.ping())

        @app.page("/")
        def index():
            return gx.text("ok")

        with TestClient(app.asgi()) as client:
            assert client.get("/").status_code == 200
            assert client.get("/health").status_code == 200
            assert client.get("/ready").status_code == 200

            for cycle in range(2):
                # Stop live Redis mid-run
                t_stop = time.perf_counter()
                container.stop()

                # /health stays 200 (process alive), /ready reports 503
                assert client.get("/health").status_code == 200
                assert client.get("/ready").status_code == 503

                # State fails closed without silent split-brain
                with pytest.raises(StateBackendUnavailableError):
                    app.state_runtime.backend.set("session", "s1", "k", f"v-{cycle}")

                # SSE admission fails closed (503) by default
                ok, _, status = app.events.try_acquire_connection("s1", "10.0.0.1")
                assert ok is False and status == 503

                # Telemetry publication fails safely without crashing worker
                assert app.observability.publish_snapshot() is False

                # Diagnostics distinguish unavailable data from zero values
                rt = client.get("/_gx/inspect/runtime").json()
                assert rt["status"] == "unavailable"
                assert rt["redis"]["connected"] is False
                assert rt["cluster"]["available"] is False
                assert rt["cluster"]["jobs"]["queue_depth"] is None

                jb = client.get("/_gx/inspect/jobs").json()
                assert jb["available"] is False
                assert jb["queue_depth"] is None

                # Restart Redis -> worker reconnects & recovers without process restart
                t_rec_start = time.perf_counter()
                container.restart()

                def _recovered() -> bool:
                    sb_ok = app.state_runtime.backend.reconnect()
                    ev_ok = app.events.backend.reconnect()
                    jb_ok = app.jobs.reconnect() if hasattr(app.jobs, "reconnect") else True
                    return bool(sb_ok and ev_ok and jb_ok)

                poll_until(_recovered, timeout=10.0, interval=0.2, description="worker Redis reconnection")
                _ = time.perf_counter() - t_rec_start

                assert client.get("/ready").status_code == 200
                app.state_runtime.backend.set("session", "s1", "k", f"recovered-{cycle}")
                assert app.state_runtime.backend.get("session", "s1", "k") == f"recovered-{cycle}"
                assert app.observability.publish_snapshot() is True
                ok2, _, status2 = app.events.try_acquire_connection("s1", "10.0.0.1", connection_id=f"c-{cycle}")
                assert ok2 is True and status2 == 200
                app.events.release_connection("s1", "10.0.0.1", connection_id=f"c-{cycle}")

                rt_up = client.get("/_gx/inspect/runtime").json()
                assert rt_up["status"] == "healthy"
                assert rt_up["redis"]["connected"] is True
                _ = t_stop
    finally:
        container.remove()
