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

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_declarative_interactions_browser_a11y_security_and_perf():
    if not os.path.exists(CHROME_PATH):
        pytest.skip("Chrome binary not available")

    app = gx.App("M18BrowserApp")
    server_hits: list[str] = []

    @app.command("server.ping")
    def server_ping(ctx: gx.CommandContext):
        server_hits.append("ping")

    @app.page("/")
    def index():
        return gx.column(
            # 1. Local counter + toggle + conditional visibility + announcements (zero HTTP)
            gx.column(
                gx.text("0", id="count-val", bind_local={"text": "count"}),
                gx.text("Hidden Panel", id="secret-panel", bind_local={"visible": "open"}),
                gx.button(
                    "Increment",
                    id="btn-inc",
                    interactions=(
                        on("click", act.increment("count", by=1), act.announce("Count updated")),
                    ),
                ),
                gx.button(
                    "Toggle Panel",
                    id="btn-toggle",
                    interactions=(on("click", act.toggle("open")),),
                ),
                gx.button(
                    "Reset",
                    id="btn-reset",
                    interactions=(
                        on("dblclick", act.set("count", 0)),
                        on("click", act.add_class("gx-highlighted", target="peer-box"), act.set_text("Peer Updated", target="peer-box")),
                    ),
                ),
                gx.text("Initial Peer", id="peer-box"),
                id="local-scope",
                local_state={"count": 0, "open": False},
            ),
            # 2. Keyboard shortcut (Ctrl+K) + focus
            gx.button(
                "Shortcut Host",
                id="shortcut-btn",
                interactions=(on("keydown", act.set_text("Shortcut Fired", target="peer-box"), key="ctrl+k", prevent_default=True),),
            ),
            # 3. Accessible Tabs, Modal, Drawer, Tag
            gx.tabs(
                gx.tab_item("Alpha", gx.text("Panel Alpha")),
                gx.tab_item("Beta", gx.text("Panel Beta")),
                id="tabs-1",
            ),
            gx.drawer(
                "Nav Drawer",
                gx.button("Inside Drawer", id="drawer-inner-btn", interactions=(on("click", act.announce("Drawer action")),)),
                trigger_label="Open Drawer",
                id="drawer-1",
            ),
            gx.tag("Removable", removable=True, id="tag-1"),
            # 4. Server command bridge (must still hit server with CSRF)
            gx.button(
                "Server Ping",
                id="btn-server-ping",
                interactions=(on("click", act.command("server.ping")),),
            ),
        )

    app_port = _free_port()
    cdp_port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app.asgi(), host="127.0.0.1", port=app_port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", app_port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)

    user_data = tempfile.mkdtemp(prefix="radui-m18-chrome-")
    proc = subprocess.Popen(
        [
            CHROME_PATH,
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
                    pages = [t for t in json.loads(resp.read().decode("utf-8")) if t.get("type") == "page"]
                    if pages:
                        ws_url = pages[0]["webSocketDebuggerUrl"]
                        break
            except Exception:
                time.sleep(0.1)
        assert ws_url is not None

        async def run_cdp() -> None:
            network_urls: list[str] = []
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
                        if data.get("method") == "Network.requestWillBeSent":
                            network_urls.append(data["params"]["request"]["url"])
                        if data.get("id") == cid:
                            return data.get("result", {})

                await cdp("Page.enable")
                await cdp("Runtime.enable")
                await cdp("Network.enable")
                await cdp("Page.navigate", {"url": f"http://127.0.0.1:{app_port}/"})
                await asyncio.sleep(0.6)

                # Clear initial page-load network list
                network_urls.clear()

                # 1. Local state & conditional visibility (zero HTTP requests)
                hidden_init = (await cdp("Runtime.evaluate", {"expression": "document.getElementById('secret-panel').hidden", "returnByValue": True}))["result"]["value"]
                assert hidden_init is True

                await cdp("Runtime.evaluate", {"expression": "document.getElementById('btn-inc').click(); document.getElementById('btn-inc').click();"})
                await cdp("Runtime.evaluate", {"expression": "document.getElementById('btn-toggle').click();"})
                await asyncio.sleep(0.1)

                cnt_val = (await cdp("Runtime.evaluate", {"expression": "document.getElementById('count-val').textContent", "returnByValue": True}))["result"]["value"]
                hidden_after = (await cdp("Runtime.evaluate", {"expression": "document.getElementById('secret-panel').hidden", "returnByValue": True}))["result"]["value"]
                live_msg = (await cdp("Runtime.evaluate", {"expression": "document.getElementById('gx-live-region').textContent", "returnByValue": True}))["result"]["value"]
                assert cnt_val == "2"
                assert hidden_after is False
                assert live_msg == "Count updated"
                assert not any("/_gx/commands/" in u for u in network_urls)  # Zero server command round trips!

                # 2. Component-to-component targeting & class/text updates + dblclick reset
                await cdp("Runtime.evaluate", {"expression": "document.getElementById('btn-reset').click()"})
                await cdp("Runtime.evaluate", {"expression": "document.getElementById('btn-reset').dispatchEvent(new MouseEvent('dblclick', {bubbles:true}))"})
                peer_txt = (await cdp("Runtime.evaluate", {"expression": "document.getElementById('peer-box').textContent", "returnByValue": True}))["result"]["value"]
                peer_cls = (await cdp("Runtime.evaluate", {"expression": "document.getElementById('peer-box').classList.contains('gx-highlighted')", "returnByValue": True}))["result"]["value"]
                cnt_reset = (await cdp("Runtime.evaluate", {"expression": "document.getElementById('count-val').textContent", "returnByValue": True}))["result"]["value"]
                assert peer_txt == "Peer Updated"
                assert peer_cls is True
                assert cnt_reset == "0"

                # 3. Keyboard shortcut (Ctrl+K)
                await cdp("Runtime.evaluate", {"expression": "document.getElementById('shortcut-btn').dispatchEvent(new KeyboardEvent('keydown', {key:'k', ctrlKey:true, bubbles:true}))"})
                assert (await cdp("Runtime.evaluate", {"expression": "document.getElementById('peer-box').textContent", "returnByValue": True}))["result"]["value"] == "Shortcut Fired"

                # 4. Accessible Tabs keyboard navigation (ArrowRight)
                await cdp("Runtime.evaluate", {"expression": "const t = document.querySelector('#tabs-1 [role=\"tab\"]'); t.focus(); t.dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowRight', bubbles:true}));"})
                tab2_sel = (await cdp("Runtime.evaluate", {"expression": "document.querySelectorAll('#tabs-1 [role=\"tab\"]')[1].getAttribute('aria-selected')", "returnByValue": True}))["result"]["value"]
                assert tab2_sel == "true"

                # 5. Accessible Drawer open -> focus -> Escape -> focus restored
                await cdp("Runtime.evaluate", {"expression": "document.querySelector('#drawer-1 [data-gx-drawer-open]').click()"})
                assert (await cdp("Runtime.evaluate", {"expression": "document.querySelector('#drawer-1 [data-gx-drawer-open]').getAttribute('aria-expanded')", "returnByValue": True}))["result"]["value"] == "true"
                await cdp("Runtime.evaluate", {"expression": "document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}))"})
                assert (await cdp("Runtime.evaluate", {"expression": "document.querySelector('#drawer-1 [data-gx-drawer-open]').getAttribute('aria-expanded')", "returnByValue": True}))["result"]["value"] == "false"
                assert (await cdp("Runtime.evaluate", {"expression": "document.activeElement === document.querySelector('#drawer-1 [data-gx-drawer-open]')", "returnByValue": True}))["result"]["value"] is True

                # 6. Delegated Tag removal (no inline onclick)
                await cdp("Runtime.evaluate", {"expression": "document.querySelector('#tag-1 [data-gx-tag-remove]').click()"})
                assert (await cdp("Runtime.evaluate", {"expression": "document.getElementById('tag-1') === null", "returnByValue": True}))["result"]["value"] is True

                # 7. Performance: 100 local click interactions in browser
                perf_ms = (await cdp("Runtime.evaluate", {"expression": "(() => { const b = document.getElementById('btn-inc'); const t0 = performance.now(); for (let i = 0; i < 100; i++) b.click(); return performance.now() - t0; })()", "returnByValue": True}))["result"]["value"]
                assert float(perf_ms) < 250.0
                print(f"BROWSER_100_INTERACTIONS_MS={float(perf_ms):.3f}")

                # 8. Server command bridge
                await cdp("Runtime.evaluate", {"expression": "document.getElementById('btn-server-ping').click()"})
                await asyncio.sleep(0.3)
                assert any("/_gx/commands/server.ping" in u for u in network_urls)

        asyncio.run(run_cdp())
        assert server_hits == ["ping"]
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3.0)
        except Exception:
            proc.kill()
        shutil.rmtree(user_data, ignore_errors=True)
        server.should_exit = True
        thread.join(timeout=2.0)
