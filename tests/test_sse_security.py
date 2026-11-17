from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
import json
import time

import httpx
import itsdangerous
import pytest

import radui as gx
from radui.transport import EventBroker


def _make_app(
    *,
    trusted_origins: list[str] | None = None,
    session_ttl_seconds: int = 3600,
    max_per_session: int = 8,
    max_per_ip: int = 32,
    rate_limit: int = 30,
    rate_window: float = 60.0,
) -> gx.App:
    app = gx.App(
        "SSE Security Test",
        session_secret="super-secret-key-at-least-32-chars-long!",
        trusted_origins=trusted_origins,
        session_ttl_seconds=session_ttl_seconds,
        sse_max_connections_per_session=max_per_session,
        sse_max_connections_per_ip=max_per_ip,
        sse_connect_rate_limit=rate_limit,
        sse_connect_rate_window_seconds=rate_window,
    )

    @app.page("/")
    def index():
        return gx.text("ok")

    return app


def _sign_session_cookie(secret: str, payload: dict) -> str:
    signer = itsdangerous.TimestampSigner(secret)
    data = base64.b64encode(json.dumps(payload).encode("utf-8"))
    return signer.sign(data).decode("utf-8")


def _decode_session_cookie(secret: str, cookie_val: str) -> dict:
    signer = itsdangerous.TimestampSigner(secret)
    raw = signer.unsign(cookie_val)
    return json.loads(base64.b64decode(raw))


@asynccontextmanager
async def _open_sse_stream(
    asgi_app,
    *,
    cookie: str | None = None,
    headers: dict[str, str] | None = None,
    client_ip: str = "127.0.0.1",
):
    """Drive Starlette ASGI StreamingResponse directly without ASGITransport buffering."""
    recv_q: asyncio.Queue[dict] = asyncio.Queue()
    send_q: asyncio.Queue[dict] = asyncio.Queue()

    raw_headers: list[tuple[bytes, bytes]] = [(b"host", b"testserver")]
    if cookie:
        raw_headers.append((b"cookie", f"RADUI_session={cookie}".encode("latin-1")))
    for k, v in (headers or {}).items():
        raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/_gx/events",
        "raw_path": b"/_gx/events",
        "query_string": b"",
        "headers": raw_headers,
        "client": (client_ip, 12345),
        "server": ("testserver", 80),
    }

    async def receive():
        return await recv_q.get()

    async def send(msg: dict):
        await send_q.put(msg)

    task = asyncio.create_task(asgi_app(scope, receive, send))
    start_msg = await asyncio.wait_for(send_q.get(), timeout=2.0)
    assert start_msg["type"] == "http.response.start"
    status = start_msg["status"]

    async def next_chunk(timeout: float = 2.0) -> str:
        while True:
            msg = await asyncio.wait_for(send_q.get(), timeout=timeout)
            if msg["type"] == "http.response.body":
                body = msg.get("body", b"")
                if body:
                    return body.decode("utf-8")
                if not msg.get("more_body", False):
                    return ""

    try:
        yield status, next_chunk
    finally:
        await recv_q.put({"type": "http.disconnect"})
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except asyncio.TimeoutError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def test_sse_valid_signed_session_and_missing_origin_same_origin():
    app = _make_app()

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi()),
            base_url="http://testserver",
        ) as client:
            r = await client.get("/")
            assert r.status_code == 200
            cookie_val = client.cookies.get("RADUI_session")
            assert cookie_val is not None
            sid = _decode_session_cookie(app._session_secret, cookie_val)["gx_session_id"]

        app.events.publish(sid, "gx:patch", {"patches": []})
        async with _open_sse_stream(
            app.asgi(),
            cookie=cookie_val,
            headers={"Last-Event-ID": "0"},
        ) as (status, next_chunk):
            assert status == 200
            chunk = await next_chunk()
            assert "id: 1" in chunk

    asyncio.run(run())
    assert app.events.metrics()["active_connections"] == 0
    assert app.events.metrics()["disconnects"] == 1


def test_sse_rejects_missing_session():
    app = _make_app()

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi()),
            base_url="http://testserver",
        ) as client:
            resp = await client.get("/_gx/events")
            assert resp.status_code == 401

    asyncio.run(run())
    assert app.events.metrics()["rejected_connections"] >= 1


def test_sse_rejects_invalid_signature():
    app = _make_app()

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi()),
            base_url="http://testserver",
        ) as client:
            client.cookies.set("RADUI_session", "forged.invalid.signature")
            resp = await client.get("/_gx/events")
            assert resp.status_code == 401

    asyncio.run(run())


def test_sse_rejects_expired_session():
    app = _make_app(session_ttl_seconds=60)
    expired_cookie = _sign_session_cookie(
        app._session_secret,
        {
            "gx_session_id": "a" * 32,
            "gx_csrf_token": "b" * 32,
            "gx_session_expires_at": time.time() - 10,
        },
    )

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi()),
            base_url="http://testserver",
        ) as client:
            client.cookies.set("RADUI_session", expired_cookie)
            resp = await client.get("/_gx/events")
            assert resp.status_code == 401

    asyncio.run(run())


def test_sse_origin_and_fetch_metadata_validation():
    app = _make_app(trusted_origins=["https://trusted.example.com"])

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi()),
            base_url="http://testserver",
        ) as client:
            assert (await client.get("/")).status_code == 200
            cookie_val = client.cookies.get("RADUI_session")
            assert cookie_val is not None
            sid = _decode_session_cookie(app._session_secret, cookie_val)["gx_session_id"]

            # 5. Invalid Origin
            r_bad_origin = await client.get("/_gx/events", headers={"Origin": "https://evil.example.com"})
            assert r_bad_origin.status_code == 403

            # Null Origin
            r_null_origin = await client.get("/_gx/events", headers={"Origin": "null"})
            assert r_null_origin.status_code == 403

            # 8. Invalid Fetch Metadata (cross-site without trusted origin, and malformed value)
            r_cross = await client.get("/_gx/events", headers={"Sec-Fetch-Site": "cross-site"})
            assert r_cross.status_code == 403
            r_malformed = await client.get("/_gx/events", headers={"Sec-Fetch-Site": "unknown-mode"})
            assert r_malformed.status_code == 403

        # 6. Valid configured trusted Origin (even if Sec-Fetch-Site is cross-site)
        app.events.publish(sid, "gx:ping", {"ok": True})
        async with _open_sse_stream(
            app.asgi(),
            cookie=cookie_val,
            headers={
                "Origin": "https://trusted.example.com",
                "Sec-Fetch-Site": "cross-site",
                "Last-Event-ID": "0",
            },
        ) as (status, next_chunk):
            assert status == 200
            chunk = await next_chunk()
            assert "id: 1" in chunk

    asyncio.run(run())


def test_sse_per_session_and_per_ip_limits_and_concurrent_admission():
    # Per-session limit = 2, per-IP limit = 3
    app = _make_app(max_per_session=2, max_per_ip=3, rate_limit=50)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi()),
            base_url="http://testserver",
        ) as c1, httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi()),
            base_url="http://testserver",
        ) as c2:
            await c1.get("/")
            await c2.get("/")
            cookie1 = c1.cookies.get("RADUI_session")
            cookie2 = c2.cookies.get("RADUI_session")

        async with (
            _open_sse_stream(app.asgi(), cookie=cookie1) as (st1a, _),
            _open_sse_stream(app.asgi(), cookie=cookie1) as (st1b, _),
        ):
            assert st1a == 200
            assert st1b == 200
            assert app.events.metrics()["active_connections"] == 2

            # 3rd concurrent connection for session 1 must hit per-session limit (429)
            async with _open_sse_stream(app.asgi(), cookie=cookie1) as (st1c, _):
                assert st1c == 429

            # Session 2 on same IP can open 1 stream (total IP = 3); 2nd hits per-IP limit (429)
            async with _open_sse_stream(app.asgi(), cookie=cookie2) as (st2a, _):
                assert st2a == 200
                assert app.events.metrics()["active_connections"] == 3
                async with _open_sse_stream(app.asgi(), cookie=cookie2) as (st2b, _):
                    assert st2b == 429

        metrics = app.events.metrics()
        assert metrics["active_connections"] == 0
        assert metrics["active_subscribers"] == 0
        assert metrics["connection_limit_violations"] == 2

    asyncio.run(run())


def test_sse_concurrent_admission_race_and_rate_limit():
    app = _make_app(max_per_session=2, max_per_ip=10, rate_limit=100)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi()),
            base_url="http://testserver",
        ) as client:
            await client.get("/")
            sid = _decode_session_cookie(app._session_secret, client.cookies.get("RADUI_session"))["gx_session_id"]

            results = await asyncio.gather(
                *[asyncio.to_thread(app.events.try_acquire_connection, sid, "10.0.0.1") for _ in range(6)]
            )
            admitted = [ok for ok, _msg, _code in results if ok]
            rejected = [code for ok, _msg, code in results if not ok]
            assert len(admitted) == 2
            assert rejected == [429, 429, 429, 429]
            app.events.release_connection(sid, "10.0.0.1")
            app.events.release_connection(sid, "10.0.0.1")
            assert app.events.metrics()["active_connections"] == 0

    asyncio.run(run())

    # Rate-limit enforcement
    rl_app = _make_app(max_per_session=10, max_per_ip=10, rate_limit=2, rate_window=60.0)

    async def run_rl():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=rl_app.asgi()),
            base_url="http://testserver",
        ) as client:
            await client.get("/")
            cookie_val = client.cookies.get("RADUI_session")

        async with _open_sse_stream(rl_app.asgi(), cookie=cookie_val) as (st1, _):
            assert st1 == 200
        async with _open_sse_stream(rl_app.asgi(), cookie=cookie_val) as (st2, _):
            assert st2 == 200
        async with _open_sse_stream(rl_app.asgi(), cookie=cookie_val) as (st3, _):
            assert st3 == 429
        assert rl_app.events.metrics()["rate_limit_violations"] == 1

    asyncio.run(run_rl())


def test_sse_cleanup_on_cancellation_and_exception():
    broker = EventBroker()

    async def run():
        stream = broker.stream("s-cancel", keepalive_seconds=5.0)
        task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        assert broker.metrics()["active_subscribers"] == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await stream.aclose()
        assert broker.metrics()["active_subscribers"] == 0

        class BrokenBackend:
            def current_sequence(self, session_id: str) -> int:
                return 5

            async def replay_after(self, session_id: str, cursor: int, limit: int = 128):
                raise RuntimeError("backend failure")

        broken_broker = EventBroker(backend=BrokenBackend())  # type: ignore[arg-type]
        broken_stream = broken_broker.stream("s-err", last_event_id=0)
        with pytest.raises(RuntimeError, match="backend failure"):
            await anext(broken_stream)
        assert broken_broker.metrics()["active_subscribers"] == 0

    asyncio.run(run())


def test_sse_slow_consumer_overflow_replay_and_reconnection():
    app = _make_app()
    app.events = EventBroker(history_size=16, subscriber_queue_size=2)

    async def run():
        # 15. Slow consumer queue overflow emits reset and increments queue_overflows
        stream = app.events.stream("slow-s", keepalive_seconds=1.0)
        waiter = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        for i in range(4):
            app.events.publish("slow-s", "gx:patch", {"i": i})
        await asyncio.sleep(0)
        first = await waiter
        if "event: reset" not in first:
            second = await asyncio.wait_for(anext(stream), timeout=1.0)
            assert "event: reset" in second
        await stream.aclose()
        assert app.events.metrics()["queue_overflows"] >= 1

        # 16 & 17. Last-Event-ID replay & reconnection after disconnect over HTTP
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi()),
            base_url="http://testserver",
        ) as client:
            await client.get("/")
            cookie_val = client.cookies.get("RADUI_session")
            sid = _decode_session_cookie(app._session_secret, cookie_val)["gx_session_id"]

        app.events.publish(sid, "gx:patch", {"n": 1})
        app.events.publish(sid, "gx:patch", {"n": 2})

        async with _open_sse_stream(
            app.asgi(),
            cookie=cookie_val,
            headers={"Last-Event-ID": "0"},
        ) as (st1, next1):
            assert st1 == 200
            chunk1 = await next1()
            assert "id: 1" in chunk1

        async with _open_sse_stream(
            app.asgi(),
            cookie=cookie_val,
            headers={"Last-Event-ID": "1"},
        ) as (st2, next2):
            assert st2 == 200
            chunk2 = await next2()
            assert "id: 2" in chunk2

        assert app.events.metrics()["reconnection_attempts"] == 2
        assert app.events.metrics()["active_connections"] == 0
        assert app.events.metrics()["disconnects"] == 2

    asyncio.run(run())


def test_sse_slot_remains_occupied_during_active_stream_and_releases_once():
    app = _make_app(max_per_session=2)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi()),
            base_url="http://testserver",
        ) as client:
            await client.get("/")
            cookie_val = client.cookies.get("RADUI_session")

        async with _open_sse_stream(app.asgi(), cookie=cookie_val) as (status, _):
            assert status == 200
            # Give the ASGI task a tick to enter EventBroker.stream()
            await asyncio.sleep(0.02)
            mid = app.events.metrics()
            assert mid["active_connections"] == 1
            assert mid["active_subscribers"] == 1
            assert mid["disconnects"] == 0

        after = app.events.metrics()
        assert after["active_connections"] == 0
        assert after["active_subscribers"] == 0
        assert after["disconnects"] == 1

    asyncio.run(run())


def test_sse_inspect_metrics_requires_inspector_authorization():
    from radui.core.auth import User

    current_user: list[User | None] = [None]
    app = gx.App(
        "SSE Inspect RBAC",
        session_secret="super-secret-key-at-least-32-chars-long!",
        user_resolver=lambda _req: current_user[0],
    )

    @app.page("/")
    def index():
        return gx.text("ok")

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi()),
            base_url="http://testserver",
        ) as client:
            # 1. No session -> 401
            assert (await client.get("/_gx/inspect/sse")).status_code == 401

            # Mint session, still no authenticated user -> 401
            await client.get("/")
            assert (await client.get("/_gx/inspect/sse")).status_code == 401

            # 2. Ordinary authenticated user -> 403
            current_user[0] = User(id="u1", username="alice", roles=("viewer",))
            assert (await client.get("/_gx/inspect/sse")).status_code == 403

            # 3. Authorized inspector -> 200 with safe integer metrics only
            current_user[0] = User(id="insp1", username="bob", roles=("inspector",))
            r_ok = await client.get("/_gx/inspect/sse")
            assert r_ok.status_code == 200
            payload = r_ok.json()
            assert payload["ok"] is True
            assert set(payload["metrics"].keys()) == {
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

    asyncio.run(run())


def test_sse_client_ip_resolution_trusted_proxies_and_spoofing():
    # Direct connection: spoofed X-Forwarded-For must be ignored
    direct_app = _make_app(max_per_session=10, max_per_ip=1, rate_limit=50)

    async def run_direct():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=direct_app.asgi()),
            base_url="http://testserver",
        ) as c1, httpx.AsyncClient(
            transport=httpx.ASGITransport(app=direct_app.asgi()),
            base_url="http://testserver",
        ) as c2:
            await c1.get("/")
            await c2.get("/")
            k1 = c1.cookies.get("RADUI_session")
            k2 = c2.cookies.get("RADUI_session")

        # Both spoof different X-Forwarded-For values, but share peer IP 127.0.0.1 -> 2nd rejected
        async with _open_sse_stream(
            direct_app.asgi(), cookie=k1, headers={"X-Forwarded-For": "203.0.113.10"}, client_ip="127.0.0.1"
        ) as (st1, _):
            assert st1 == 200
            async with _open_sse_stream(
                direct_app.asgi(), cookie=k2, headers={"X-Forwarded-For": "203.0.113.11"}, client_ip="127.0.0.1"
            ) as (st2, _):
                assert st2 == 429

    asyncio.run(run_direct())

    # Trusted proxy: uses valid untrusted hop, falls back on malformed XFF
    proxy_app = _make_app(max_per_session=10, max_per_ip=1, rate_limit=50)
    proxy_app._trusted_proxies = {"10.0.0.10"}

    async def run_proxy():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=proxy_app.asgi()),
            base_url="http://testserver",
        ) as c1, httpx.AsyncClient(
            transport=httpx.ASGITransport(app=proxy_app.asgi()),
            base_url="http://testserver",
        ) as c2:
            await c1.get("/")
            await c2.get("/")
            k1 = c1.cookies.get("RADUI_session")
            k2 = c2.cookies.get("RADUI_session")

        # Two different real client IPs behind trusted proxy 10.0.0.10 -> both allowed
        async with _open_sse_stream(
            proxy_app.asgi(), cookie=k1, headers={"X-Forwarded-For": "198.51.100.1, 10.0.0.10"}, client_ip="10.0.0.10"
        ) as (st1, _):
            assert st1 == 200
            async with _open_sse_stream(
                proxy_app.asgi(), cookie=k2, headers={"X-Forwarded-For": "198.51.100.2, 10.0.0.10"}, client_ip="10.0.0.10"
            ) as (st2, _):
                assert st2 == 200

        # Malformed XFF falls back to peer IP 10.0.0.10
        async with _open_sse_stream(
            proxy_app.asgi(), cookie=k1, headers={"X-Forwarded-For": "not-an-ip"}, client_ip="10.0.0.10"
        ) as (st_bad, _):
            assert st_bad == 200

    asyncio.run(run_proxy())


def test_sse_origin_default_port_normalization_and_rate_window_expiry():
    app = _make_app(
        trusted_origins=["https://trusted.example.com:443"],
        max_per_session=5,
        max_per_ip=5,
        rate_limit=1,
        rate_window=0.05,
    )

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi()),
            base_url="http://testserver",
        ) as client:
            await client.get("/")
            cookie_val = client.cookies.get("RADUI_session")

        # Default port :443 normalized to match https://trusted.example.com
        async with _open_sse_stream(
            app.asgi(),
            cookie=cookie_val,
            headers={"Origin": "https://trusted.example.com", "Sec-Fetch-Site": "cross-site"},
        ) as (st1, _):
            assert st1 == 200

        # Immediate 2nd connection hits rate limit 429 without leaking active_connections
        async with _open_sse_stream(app.asgi(), cookie=cookie_val) as (st2, _):
            assert st2 == 429
        assert app.events.metrics()["active_connections"] == 0

        # After rate window expires, same-origin with default :80 port succeeds
        await asyncio.sleep(0.08)
        async with _open_sse_stream(
            app.asgi(),
            cookie=cookie_val,
            headers={"Origin": "http://testserver:80"},
        ) as (st3, _):
            assert st3 == 200
        assert app.events.metrics()["active_connections"] == 0

    asyncio.run(run())
