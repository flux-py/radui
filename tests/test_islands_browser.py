from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
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

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _build_browser_test_app() -> tuple[gx.App, list[str]]:
    app = gx.App("Browser Islands Test", session_secret="super-secret-key-at-least-32-chars-long!")
    hydration_calls: list[str] = []
    hydrated_flag = {"eager": False, "visible": False, "ptr": False, "kbd": False, "inner": False}

    @app.island("eager_w", hydration="fetch", trigger="eager")
    def eager_w():
        hydration_calls.append("eager")
        if hydrated_flag["eager"]:
            return gx.text("Eager Hydrated", id="eager-text")
        hydrated_flag["eager"] = True
        return gx.text("Eager SSR", id="eager-text")

    @app.island("visible_w", hydration="fetch", trigger="visible")
    def visible_w():
        hydration_calls.append("visible")
        if hydrated_flag["visible"]:
            return gx.text("Visible Hydrated")
        hydrated_flag["visible"] = True
        return gx.text("Visible SSR")

    @app.island("ptr_w", hydration="fetch", trigger="interaction")
    def ptr_w():
        hydration_calls.append("ptr")
        if hydrated_flag["ptr"]:
            return gx.button("Ptr Hydrated", command="noop")
        hydrated_flag["ptr"] = True
        return gx.button("Ptr SSR", command="noop")

    @app.island("kbd_w", hydration="fetch", trigger="interaction")
    def kbd_w():
        hydration_calls.append("kbd")
        if hydrated_flag["kbd"]:
            return gx.button("Kbd Hydrated", command="noop")
        hydrated_flag["kbd"] = True
        return gx.button("Kbd SSR", command="noop")

    @app.island("inner_w", hydration="fetch", trigger="eager")
    def inner_w():
        hydration_calls.append("inner")
        return gx.text("Inner Hydrated")

    @app.island("outer_w", hydration="fetch", trigger="eager")
    def outer_w():
        if hydrated_flag["inner"]:
            return gx.container(inner_w(id="isl-inner"))
        hydrated_flag["inner"] = True
        return gx.text("Outer SSR")

    @app.island("fail_w", hydration="fetch", trigger="eager")
    def fail_w():
        if hydrated_flag.get("fail_on_hydrate"):
            raise RuntimeError("boom")
        hydrated_flag["fail_on_hydrate"] = True
        return gx.text("Fail SSR")

    @app.island("sse_w", hydration="sse", trigger="interaction")
    def sse_w():
        return gx.button("Activate SSE", command="noop")

    @app.command("noop")
    def on_noop(_ctx):
        return None

    @app.page("/islands-only")
    def islands_only():
        return gx.column(
            gx.button("Outside", command="noop", id="outside-btn"),
            eager_w(id="isl-eager"),
            ptr_w(id="isl-ptr"),
            kbd_w(id="isl-kbd"),
            outer_w(id="isl-outer"),
            fail_w(id="isl-fail"),
            *[gx.spacer(128) for _ in range(20)],
            visible_w(id="isl-remove"),
            visible_w(id="isl-visible"),
        )

    @app.page("/islands-sse")
    def islands_sse():
        return gx.column(sse_w(id="isl-sse"))

    @app.page("/legacy")
    def legacy():
        return gx.column(gx.text("Legacy Page"), gx.form(gx.button("Go"), command="noop"))

    return app, hydration_calls


@pytest.mark.skipif(not Path(CHROME_PATH).exists(), reason="Chrome binary not installed")
def test_real_browser_islands_lifecycle_and_network():
    app, _calls = _build_browser_test_app()
    port = _free_port()
    config = uvicorn.Config(app.asgi(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for uvicorn to listen
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/_gx/health", timeout=0.5):
                break
        except Exception:
            time.sleep(0.05)

    cdp_port = _free_port()
    user_data_dir = tempfile.mkdtemp(prefix="radui-cdp-")
    chrome_proc = subprocess.Popen(
        [
            CHROME_PATH,
            f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={user_data_dir}",
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
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
                    page_targets = [t for t in targets if t.get("type") == "page"]
                    if page_targets:
                        ws_url = page_targets[0]["webSocketDebuggerUrl"]
                        break
            except Exception:
                time.sleep(0.1)
        assert ws_url is not None, "Chrome CDP endpoint did not start"

        async def run_cdp():
            async with websockets.connect(ws_url, max_size=4 * 1024 * 1024) as ws:
                seq = 0
                network_urls: list[str] = []

                async def cdp(method: str, params: dict | None = None):
                    nonlocal seq
                    seq += 1
                    msg_id = seq
                    await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
                    while True:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        pkt = json.loads(raw)
                        if pkt.get("method") == "Network.requestWillBeSent":
                            network_urls.append(pkt["params"]["request"]["url"])
                        if pkt.get("id") == msg_id:
                            assert "error" not in pkt, pkt.get("error")
                            return pkt.get("result", {})

                async def eval_js(expr: str):
                    res = await cdp(
                        "Runtime.evaluate",
                        {"expression": expr, "returnByValue": True, "awaitPromise": True},
                    )
                    return res["result"].get("value")

                await cdp("Page.enable")
                await cdp("Network.enable")
                await cdp("Runtime.enable")
                await cdp("Emulation.setDeviceMetricsOverride", {"width": 1280, "height": 800, "deviceScaleFactor": 1, "mobile": False})

                # 1. Navigate to /islands-only
                await cdp("Page.navigate", {"url": f"http://127.0.0.1:{port}/islands-only"})
                await asyncio.sleep(0.5)

                # Attach unrelated listener on #outside-btn
                await eval_js("window._outsideClicked = 0; document.getElementById('outside-btn').addEventListener('click', () => window._outsideClicked++);")

                # Eager + nested inner island hydrated; fail island marked error; visible/ptr/kbd NOT hydrated; ZERO /_gx/events!
                state = await eval_js("""(() => ({
                    eagerText: document.getElementById('isl-eager').innerText,
                    eagerStatus: document.getElementById('isl-eager').getAttribute('data-gx-island-status'),
                    eagerCount: document.querySelectorAll('#isl-eager').length,
                    outerHtml: document.getElementById('isl-outer').innerHTML,
                    innerStatus: document.getElementById('isl-inner')?.getAttribute('data-gx-island-status'),
                    failStatus: document.getElementById('isl-fail').getAttribute('data-gx-island-status'),
                    visibleStatus: document.getElementById('isl-visible').getAttribute('data-gx-island-status'),
                    ptrStatus: document.getElementById('isl-ptr').getAttribute('data-gx-island-status'),
                    kbdStatus: document.getElementById('isl-kbd').getAttribute('data-gx-island-status'),
                }))()""")

                assert "Eager Hydrated" in state["eagerText"]
                assert state["eagerStatus"] == "hydrated"
                assert state["eagerCount"] == 1
                assert "Inner Hydrated" in state["outerHtml"]
                assert state["innerStatus"] == "hydrated"
                assert state["failStatus"] == "error"
                assert state["visibleStatus"] == "ssr"
                assert state["ptrStatus"] == "ssr"
                assert state["kbdStatus"] == "ssr"
                assert not any("/_gx/events" in u for u in network_urls)

                # Remove #isl-remove before scrolling -> must NEVER hydrate
                await eval_js("document.getElementById('isl-remove').remove();")

                # 2. Scroll #isl-visible into view -> IntersectionObserver triggers hydration
                await eval_js("document.getElementById('isl-visible').scrollIntoView();")
                await asyncio.sleep(0.4)
                assert await eval_js("document.getElementById('isl-visible').getAttribute('data-gx-island-status')") == "hydrated"
                assert "Visible Hydrated" in await eval_js("document.getElementById('isl-visible').innerText")
                assert not any("/_gx/islands/isl-remove" in u for u in network_urls)

                # 3. Pointer interaction on #isl-ptr -> hydrates once; repeated pointerdown does not re-fetch
                await eval_js("document.getElementById('isl-ptr').dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));")
                await asyncio.sleep(0.3)
                await eval_js("document.getElementById('isl-ptr').dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));")
                await asyncio.sleep(0.2)
                assert await eval_js("document.getElementById('isl-ptr').getAttribute('data-gx-island-status')") == "hydrated"
                assert sum(1 for u in network_urls if "/_gx/islands/isl-ptr" in u) == 1

                # 4. Keyboard interaction on #isl-kbd -> hydrates once
                await eval_js("document.getElementById('isl-kbd').dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));")
                await asyncio.sleep(0.3)
                assert await eval_js("document.getElementById('isl-kbd').getAttribute('data-gx-island-status')") == "hydrated"
                assert sum(1 for u in network_urls if "/_gx/islands/isl-kbd" in u) == 1

                # Unrelated listener still works
                await eval_js("document.getElementById('outside-btn').click();")
                assert await eval_js("window._outsideClicked") == 1

                # 5. /islands-sse: zero /_gx/events before click, opens 1 /_gx/events on interaction
                network_urls.clear()
                await cdp("Page.navigate", {"url": f"http://127.0.0.1:{port}/islands-sse"})
                await asyncio.sleep(0.4)
                assert not any("/_gx/events" in u for u in network_urls)
                await eval_js("document.getElementById('isl-sse').dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));")
                await asyncio.sleep(0.4)
                assert await eval_js("document.getElementById('isl-sse').getAttribute('data-gx-island-status')") == "hydrated"
                assert sum(1 for u in network_urls if "/_gx/events" in u) == 1

                # 6. /legacy: opens /_gx/events immediately (backward compatible)
                network_urls.clear()
                await cdp("Page.navigate", {"url": f"http://127.0.0.1:{port}/legacy"})
                await asyncio.sleep(0.4)
                assert await eval_js("document.readyState") in ("interactive", "complete")
                assert sum(1 for u in network_urls if "/_gx/events" in u) == 1

        asyncio.run(run_cdp())
    finally:
        chrome_proc.terminate()
        try:
            chrome_proc.wait(timeout=3)
        except Exception:
            chrome_proc.kill()
        server.should_exit = True
        thread.join(timeout=3)
        shutil.rmtree(user_data_dir, ignore_errors=True)
