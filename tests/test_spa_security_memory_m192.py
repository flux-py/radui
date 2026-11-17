from __future__ import annotations

import asyncio
import gzip
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from typing import Any

import pytest
import uvicorn
import websockets

import radui as gx
from radui.interactions import act, on
from radui.renderers.html import CLIENT_JS

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


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


def test_m192_auth_cache_invalidation_memory_1000_navs_and_brotli():
    # 1. Verify raw, gzip, and Brotli size of CLIENT_JS
    raw_bytes = CLIENT_JS.encode("utf-8")
    gz_bytes = gzip.compress(raw_bytes, compresslevel=9)
    assert len(raw_bytes) < 96_000
    assert len(gz_bytes) < 22_000

    node_bin = shutil.which("node")
    brotli_len: int | None = None
    if node_bin:
        p = subprocess.run(
            [
                node_bin,
                "-e",
                "const fs=require('fs'),zlib=require('zlib');console.log(zlib.brotliCompressSync(fs.readFileSync(0)).length)",
            ],
            input=raw_bytes,
            capture_output=True,
            check=True,
        )
        brotli_len = int(p.stdout.decode().strip())
        assert brotli_len < 19_000

    if not os.path.exists(CHROME_PATH):
        pytest.skip("Chrome binary not available")

    auth_state: dict[str, str | None] = {"user": "alice"}
    app = gx.App(
        "M192SecMemApp",
        user_id_resolver=lambda _req: auth_state["user"],
    )

    @app.page("/", title="Home")
    def home():
        return gx.column(
            gx.heading("Home", id="h1"),
            gx.link("Public", "/pub", id="lnk-pub"),
            gx.link("Secret", "/secret", id="lnk-sec"),
            gx.button("Local", id="btn-loc", interactions=(on("click", act.increment("n")),)),
            id="home-root",
            local_state={"n": 0},
        )

    @app.page("/pub", title="Public")
    def pub():
        return gx.heading("Public Page", id="h1")

    @app.page("/secret", title="Secret", require_auth=True)
    def secret():
        return gx.heading(f"Secret for {auth_state['user']}", id="h1")

    @app.page("/item/{idx}", title="Item")
    def item(idx: str):
        return gx.column(
            gx.heading(f"Item {idx}", id="h1"),
            gx.button("Act", id="act-btn", interactions=(on("click", act.toggle("open")),)),
            id=f"box-{idx}",
            local_state={"open": False},
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

    user_data = tempfile.mkdtemp(prefix="radui_m192_")
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

    async def run_browser() -> dict[str, Any]:
        async with websockets.connect(ws_url, max_size=10_000_000) as ws:
            await _cdp_call(ws, 1, "Runtime.enable")
            await _cdp_call(ws, 2, "Performance.enable")
            await _cdp_call(ws, 3, "HeapProfiler.enable")
            await asyncio.sleep(0.4)

            # 1. Prefetch /secret as alice, then navigate to /secret (works), then log out -> must NOT serve stale HTML
            res_alice = await _cdp_eval(ws, 3, """
                await window.RadUINavigator.prefetch("/secret");
                const r = await window.RadUINavigator.navigate("/secret");
                return { ok: r.ok, h1: document.getElementById("h1").textContent };
            """)
            assert res_alice == {"ok": True, "h1": "Secret for alice"}

            # Revoke auth on server and verify /_gx/navigate returns 401 fallback=True (no stale cache hit)
            auth_state["user"] = None
            res_revoked = await _cdp_eval(ws, 4, """
                const resp = await fetch("/_gx/navigate?to=/secret", { credentials: "same-origin" });
                const body = await resp.json();
                return { status: resp.status, fallback: body.fallback, ok: body.ok };
            """)
            assert res_revoked == {"status": 401, "fallback": True, "ok": False}

            # 2. 1,050 consecutive SPA navigations + listener/node/heap leak check
            await _cdp_eval(ws, 5, 'await window.RadUINavigator.navigate("/pub");')
            m_before = {m["name"]: m["value"] for m in (await _cdp_call(ws, 6, "Performance.getMetrics"))["metrics"]}

            nav_count = await _cdp_eval(ws, 7, """
                for (let i = 0; i < 1050; i++) {
                    const target = (i % 2 === 0) ? "/item/1" : "/pub";
                    const r = await window.RadUINavigator.navigate(target, { replace: true });
                    if (!r.ok) throw new Error("Navigation failed at " + i);
                }
                return 1050;
            """)
            assert nav_count == 1050

            await _cdp_call(ws, 8, "HeapProfiler.collectGarbage")
            m_after = {m["name"]: m["value"] for m in (await _cdp_call(ws, 9, "Performance.getMetrics"))["metrics"]}
            return {"before": m_before, "after": m_after}

    try:
        out = asyncio.run(run_browser())
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        server.should_exit = True
        srv_thread.join(timeout=3)
        shutil.rmtree(user_data, ignore_errors=True)

    listeners_before = out["before"].get("JSEventListeners", 0)
    listeners_after = out["after"].get("JSEventListeners", 0)
    nodes_after = out["after"].get("Nodes", 0)
    heap_before_mb = out["before"].get("JSHeapUsedSize", 0) / (1024 * 1024)
    heap_after_mb = out["after"].get("JSHeapUsedSize", 0) / (1024 * 1024)

    # O(1) listener delegation: listeners must not grow linearly with 1,050 navigations
    assert listeners_after <= listeners_before + 10
    assert nodes_after < 500
    assert heap_after_mb < heap_before_mb + 25.0

    print(
        f"\n[M1.9.2 Telemetry] CLIENT_JS raw={len(raw_bytes)} B, gzip={len(gz_bytes)} B, brotli={brotli_len} B | "
        f"1050 navs: listeners {listeners_before}->{listeners_after}, nodes={nodes_after}, "
        f"heap {heap_before_mb:.2f}MB->{heap_after_mb:.2f}MB"
    )
