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

import radui as gx
from radui.interactions import act, on
from radui.streaming import stream_page_html

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_streaming_out_of_order_timeout_cancellation_and_ssg(tmp_path):
    app = gx.App("M23StreamUnit")

    async def fast_fn():
        await asyncio.sleep(0.02)
        return gx.text("Fast Ready", id="fast-resolved")

    async def slow_fn():
        await asyncio.sleep(0.20)
        return gx.text("Slow Ready", id="slow-resolved")

    async def timeout_fn():
        await asyncio.sleep(1.0)
        return gx.text("Never", id="never")

    @app.page("/stream", stream=True, ssg=False)
    def stream_page():
        return gx.column(
            gx.suspense(slow_fn, fallback=gx.text("Slow Loading...", id="slow-fb"), id="b-slow"),
            gx.suspense(fast_fn, fallback=gx.text("Fast Loading...", id="fast-fb"), id="b-fast"),
            gx.suspense(
                timeout_fn,
                fallback=gx.text("Wait...", id="to-fb"),
                error_fallback=gx.text("Timed Out Fallback", id="to-err"),
                timeout_s=0.05,
                id="b-timeout",
            ),
        )

    @app.page("/static-with-suspense", ssg=True)
    def static_page():
        return gx.suspense(fast_fn, fallback=gx.text("Static Fallback", id="st-fb"), id="b-st")

    # 1. Verify SSG remains deterministic
    build = app.build_static(tmp_path / "dist", build_timestamp="2026-11-17T00:00:00Z")
    st_html = (tmp_path / "dist" / "static-with-suspense" / "index.html").read_text(encoding="utf-8")
    assert "Static Fallback" in st_html

    # 2. Live streaming TTFB vs total completion & out-of-order chunk order
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app.asgi(), host="127.0.0.1", port=port, log_level="error"))
    srv_thread = threading.Thread(target=server.run, daemon=True)
    srv_thread.start()
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.05)

    try:
        t0 = time.perf_counter()
        chunks: list[tuple[float, str]] = []
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/stream", timeout=5) as resp:
            while True:
                buf = resp.read(4096)
                if not buf:
                    break
                chunks.append(((time.perf_counter() - t0) * 1000.0, buf.decode("utf-8", errors="replace")))
        full_body = "".join(c for _, c in chunks)
        ttfb_ms = chunks[0][0]
        total_ms = chunks[-1][0]
        # Shell arrives before slow boundary completes; fast arrives before slow
        assert "Slow Loading..." in full_body
        assert full_body.index("Fast Ready") < full_body.index("Slow Ready")
        assert "Timed Out Fallback" in full_body
        print(f"\n[M2.3 Telemetry] TTFB={ttfb_ms:.2f}ms | Total={total_ms:.2f}ms (out-of-order verified)")
    finally:
        server.should_exit = True
        srv_thread.join(timeout=3)


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


def test_streaming_browser_and_unified_m2_integration():
    if not os.path.exists(CHROME_PATH):
        pytest.skip("Chrome binary not available")

    app = gx.App("M23UnifiedApp")

    @app.web_component(
        "acme-kpi",
        shadow_mode="open",
        observed_attributes=("value",),
        template_html='<div class="kpi"><span data-gx-prop="value">0</span><slot></slot></div>',
    )
    def acme_kpi():
        pass

    async def deferred_widget():
        await asyncio.sleep(0.08)
        return gx.column(
            gx.text("50", id="def-count", bind_local={"text": "cnt"}),
            gx.button("Add", id="def-btn", interactions=(on("click", act.increment("cnt", by=5)),)),
            gx.custom_element("acme-kpi", gx.text("Live KPI"), props={"value": "99%"}, id="def-kpi"),
            id="def-box",
            local_state={"cnt": 50},
            resumable=True,
        )

    @app.page("/", title="Unified M2.0-M2.3", stream=True, ssg=False)
    def index():
        return gx.column(
            gx.heading("Unified Dashboard", id="main-h1"),
            gx.suspense(deferred_widget, fallback=gx.text("Streaming widget...", id="def-fb"), id="b-def"),
            gx.link("Static Page", "/other", id="lnk-other"),
        )

    @app.page("/other", title="Other Route")
    def other():
        return gx.heading("Other Heading", id="main-h1")

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
            time.sleep(0.05)

    user_data = tempfile.mkdtemp(prefix="radui_m23_")
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
            time.sleep(0.05)
    assert ws_url

    async def run_browser():
        async with websockets.connect(ws_url, max_size=10_000_000) as ws:
            await _cdp_call(ws, 1, "Runtime.enable")
            await asyncio.sleep(0.5)

            res = await _cdp_eval(ws, 2, """
                // Forged template with wrong nonce must be ignored/removed without modifying DOM
                const badTpl = document.createElement("template");
                badTpl.setAttribute("data-gx-stream-target", "def-box");
                badTpl.setAttribute("data-gx-stream-nonce", "forged");
                badTpl.innerHTML = "<p>EVIL</p>";
                document.body.appendChild(badTpl);
                await new Promise(r => setTimeout(r, 30));

                const btn = document.getElementById("def-btn");
                btn.click();
                const kpi = document.getElementById("def-kpi");
                const valAfter = document.getElementById("def-count").textContent;
                const kpiShadow = Boolean(kpi && kpi.shadowRoot);

                // SPA navigation from streamed page works cleanly
                const navRes = await window.RadUINavigator.navigate("/other");
                return {
                    valAfter,
                    kpiShadow,
                    evilPresent: document.body.textContent.includes("EVIL"),
                    navOk: navRes.ok,
                    h1: document.getElementById("main-h1").textContent
                };
            """)
            return res

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

    assert out == {
        "valAfter": "55",
        "kpiShadow": True,
        "evilPresent": False,
        "navOk": True,
        "h1": "Other Heading",
    }
