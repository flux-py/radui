from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request

import pytest
import uvicorn
import websockets
from fastapi.testclient import TestClient

import radui as gx
from radui.interactions import act, on
from radui.resumability import (
    RESUMABILITY_SCHEMA_VERSION,
    ExecutionDescriptor,
    ResumableBoundarySnapshot,
    StateMigrationRegistry,
    compute_auth_scope,
    restore_boundary,
    serialize_boundary,
)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_resumability_schema_security_migration_and_endpoint():
    scope_alice = compute_auth_scope(session_id="sess-1", user_id="alice", tenant_id="t1")
    scope_bob = compute_auth_scope(session_id="sess-1", user_id="bob", tenant_id="t1")
    assert scope_alice != scope_bob

    # Secret keys & prototype pollution rejected
    with pytest.raises(ValueError):
        ResumableBoundarySnapshot(
            boundary_id="b1",
            component_kind="column",
            route="/",
            auth_scope=scope_alice,
            local_state={"api_key": "12345"},
        )
    with pytest.raises(ValueError):
        ResumableBoundarySnapshot(
            boundary_id="b1",
            component_kind="column",
            route="/",
            auth_scope=scope_alice,
            local_state={"constructor": "bad"},
        )

    snap = ResumableBoundarySnapshot(
        boundary_id="b1",
        component_kind="column",
        route="/dash",
        auth_scope=scope_alice,
        local_state={"count": 3},
        bind_local={"text": "count"},
        descriptors=(
            ExecutionDescriptor(
                descriptor_id="b1-d0",
                kind="local_interaction",
                event="click",
                action=act.increment("count"),
                state_keys=("count",),
            ),
        ),
    )
    raw = serialize_boundary(snap)
    restored = restore_boundary(raw, expected_route="/dash", expected_auth_scope=scope_alice)
    assert restored == snap

    # Auth / route mismatch rejected
    with pytest.raises(PermissionError):
        restore_boundary(raw, expected_route="/dash", expected_auth_scope=scope_bob)
    with pytest.raises(PermissionError):
        restore_boundary(raw, expected_route="/other", expected_auth_scope=scope_alice)

    # Schema migration 0.9 -> 1.0
    reg = StateMigrationRegistry()
    reg.register("0.9", RESUMABILITY_SCHEMA_VERSION, lambda p: {**p, "local_state": {**p.get("local_state", {}), "migrated": True}})
    old_payload = snap.model_dump()
    old_payload["schema_version"] = "0.9"
    migrated = restore_boundary(json.dumps(old_payload), migrations=reg)
    assert migrated.schema_version == RESUMABILITY_SCHEMA_VERSION
    assert migrated.local_state["migrated"] is True

    # Endpoint CSRF & auth validation
    user_holder = {"uid": "alice"}
    app = gx.App("M20Server", user_id_resolver=lambda _r: user_holder["uid"])

    @app.page("/")
    def home():
        return gx.column(
            gx.text("0", id="cnt", bind_local={"text": "count"}),
            gx.button("+", id="btn-inc", interactions=(on("click", act.increment("count")),)),
            id="res-box",
            local_state={"count": 5},
            resumable=True,
        )

    client = TestClient(app.asgi())
    page_resp = client.get("/")
    assert page_resp.status_code == 200
    assert 'id="gx-resumable-state"' in page_resp.text
    csrf = page_resp.text.split('name="gx-csrf" content="')[1].split('"')[0]
    snap_json = json.loads(page_resp.text.split('id="gx-resumable-state">')[1].split("</script>")[0])[0]

    # Missing CSRF -> 403
    assert client.post("/_gx/resume", json={"snapshot": snap_json, "expected_route": "/"}).status_code == 403
    # Valid CSRF + matching user -> 200
    ok_res = client.post(
        "/_gx/resume",
        json={"snapshot": snap_json, "expected_route": "/"},
        headers={"X-GX-CSRF": csrf},
    )
    assert ok_res.status_code == 200
    assert ok_res.json()["ok"] is True

    # User changed -> 403
    user_holder["uid"] = "eve"
    assert (
        client.post(
            "/_gx/resume",
            json={"snapshot": snap_json, "expected_route": "/"},
            headers={"X-GX-CSRF": csrf},
        ).status_code
        == 403
    )


async def _cdp_call(ws, msg_id: int, method: str, params: dict | None = None) -> dict:
    await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    while True:
        raw = await ws.recv()
        data = json.loads(raw)
        if data.get("id") == msg_id:
            if "error" in data:
                raise RuntimeError(f"CDP error for {method}: {data['error']}")
            return data.get("result", {})


async def _cdp_eval(ws, msg_id: int, expr: str):
    res = await _cdp_call(
        ws,
        msg_id,
        "Runtime.evaluate",
        {"expression": f"(async () => {{ {expr} }})()", "awaitPromise": True, "returnByValue": True},
    )
    if "exceptionDetails" in res:
        raise RuntimeError(f"JS exception: {res['exceptionDetails']}")
    return res.get("result", {}).get("value")


def test_resumable_lazy_activation_and_spa_browser():
    if not os.path.exists(CHROME_PATH):
        pytest.skip("Chrome binary not available")

    app = gx.App("M20Browser")

    @app.page("/", title="Resumable Home")
    def home():
        return gx.column(
            gx.column(
                gx.text("10", id="b1-val", bind_local={"text": "n"}),
                gx.button("Inc 1", id="b1-btn", interactions=(on("click", act.increment("n", by=2)),)),
                id="boundary-1",
                local_state={"n": 10},
                resumable=True,
            ),
            gx.column(
                gx.text("20", id="b2-val", bind_local={"text": "m"}),
                gx.button("Inc 2", id="b2-btn", interactions=(on("click", act.increment("m", by=3)),)),
                id="boundary-2",
                local_state={"m": 20},
                resumable=True,
            ),
            gx.link("Next", "/next", id="go-next"),
        )

    @app.page("/next", title="Resumable Next")
    def nxt():
        return gx.column(
            gx.text("100", id="b3-val", bind_local={"text": "k"}),
            gx.button("Inc 3", id="b3-btn", interactions=(on("click", act.increment("k", by=5)),)),
            id="boundary-3",
            local_state={"k": 100},
            resumable=True,
        )

    port = _free_port()
    cdp_port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app.asgi(), host="127.0.0.1", port=port, log_level="error"))
    srv_thread = threading.Thread(target=server.run, daemon=True)
    srv_thread.start()
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.1)

    user_data = tempfile.mkdtemp(prefix="radui_m20_")
    proc = subprocess.Popen(
        [
            CHROME_PATH,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={user_data}",
            f"http://127.0.0.1:{port}/",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    ws_url = None
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json/list", timeout=1) as resp:
                targets = json.loads(resp.read().decode("utf-8"))
                page = next((t for t in targets if t.get("type") == "page"), None)
                if page and "webSocketDebuggerUrl" in page:
                    ws_url = page["webSocketDebuggerUrl"]
                    break
        except Exception:
            time.sleep(0.1)
    assert ws_url

    async def run_browser():
        async with websockets.connect(ws_url, max_size=10_000_000) as ws:
            await _cdp_call(ws, 1, "Runtime.enable")
            await asyncio.sleep(0.4)

            init_stats = await _cdp_eval(ws, 2, "return window.RadUIResumability.stats();")
            assert init_stats == {"registeredCount": 2, "activatedCount": 0}

            # Click boundary-1 only -> activates ONLY boundary-1
            res1 = await _cdp_eval(ws, 3, """
                const t0 = performance.now();
                document.getElementById("b1-btn").click();
                const dt = performance.now() - t0;
                return {
                    val1: document.getElementById("b1-val").textContent,
                    b1Resumed: document.getElementById("boundary-1").getAttribute("data-gx-resumed"),
                    b2Resumed: document.getElementById("boundary-2").getAttribute("data-gx-resumed"),
                    stats: window.RadUIResumability.stats(),
                    dt_ms: dt
                };
            """)
            assert res1["val1"] == "12"
            assert res1["b1Resumed"] == "1"
            assert res1["b2Resumed"] is None
            assert res1["stats"]["activatedCount"] == 1
            assert res1["dt_ms"] < 10.0

            # SPA navigate to /next and activate boundary-3
            res2 = await _cdp_eval(ws, 4, """
                await window.RadUINavigator.navigate("/next");
                document.getElementById("b3-btn").click();
                const srv = await window.RadUIResumability.restoreFromServer("boundary-3", "/next");
                return {
                    val3: document.getElementById("b3-val").textContent,
                    stats: window.RadUIResumability.stats(),
                    srvOk: srv.ok
                };
            """)
            assert res2["val3"] == "105"
            assert res2["stats"]["activatedCount"] == 2
            assert res2["srvOk"] is True

    try:
        asyncio.run(run_browser())
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        server.should_exit = True
        srv_thread.join(timeout=3)
        shutil.rmtree(user_data, ignore_errors=True)
