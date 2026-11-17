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
from fastapi.testclient import TestClient

import radui as gx
from radui.interactions import act, on
from radui.renderers.html import CLIENT_JS

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_spa_routing_edge_cases_and_security():
    current_user = {"id": "alice"}

    app = gx.App(
        "M191EdgeSecApp",
        user_id_resolver=lambda _req: current_user["id"],
    )
    read_only_hits: list[str] = []

    @app.page("/about", title="About")
    def about():
        read_only_hits.append("about")
        return gx.heading("About", id="h1-about")

    @app.page("/search", title="Search")
    def search():
        return gx.text("Search Results", id="search-res")

    @app.page("/items/{item_id}", title="Item")
    def item(item_id: str):
        return gx.text(f"Item {item_id}", id="item-val")

    @app.page("/admin", title="Admin", require_auth=True)
    def admin():
        return gx.text("Admin Only", id="admin-txt")

    @app.page("/xss-safe", title="XSS Safe")
    def xss_safe():
        return gx.text("<script>window.__xss=1</script>", id="safe-txt")

    client = TestClient(app.asgi())

    # 1. Trailing slash normalization
    r_slash = client.get("/_gx/navigate?to=/about/")
    assert r_slash.status_code == 200
    assert r_slash.json()["route"] == "/about"

    # 2. Query params + URL encoding + dynamic params
    r_q = client.get("/_gx/navigate?to=/search%3Fq%3Dhello%2520world")
    assert r_q.status_code == 200
    assert r_q.json()["ok"] is True

    r_dyn = client.get("/_gx/navigate?to=/items/item-99")
    assert r_dyn.status_code == 200
    assert "Item item-99" in r_dyn.json()["html"]

    # 3. XSS payload escaped in server HTML
    r_xss = client.get("/_gx/navigate?to=/xss-safe")
    assert r_xss.status_code == 200
    assert "<script>" not in r_xss.json()["html"]
    assert "&lt;script&gt;" in r_xss.json()["html"]

    # 4. auth_key changes when user changes (cache invalidation key)
    k1 = client.get("/_gx/navigate?to=/admin").json()["auth_key"]
    current_user["id"] = "bob"
    k2 = client.get("/_gx/navigate?to=/admin").json()["auth_key"]
    assert k1 != k2

    # 5. Auth expiry -> 401 + fallback=True
    current_user["id"] = None  # type: ignore[assignment]
    r_exp = client.get("/_gx/navigate?to=/admin")
    assert r_exp.status_code == 401
    assert r_exp.json()["fallback"] is True

    # 6. Open redirect / bad URLs rejected
    assert client.get("/_gx/navigate?to=//evil.com").status_code == 400
    assert client.get("/_gx/navigate?to=https://evil.com").status_code == 400


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


def test_spa_concurrency_lifecycle_a11y_and_perf_in_browser():
    if not os.path.exists(CHROME_PATH):
        pytest.skip("Chrome binary not available")

    app = gx.App("M191BrowserHardening")

    @app.layout("/")
    def root_layout(outlet):
        return gx.column(
            gx.row(
                gx.link("Home", "/", id="lnk-home"),
                gx.link("Slow", "/slow", id="lnk-slow"),
                gx.link("Fast", "/fast", id="lnk-fast"),
                gx.link("Hash", "/fast#section-b", id="lnk-hash"),
                gx.link("Ext", "https://example.com", id="lnk-ext"),
                gx.link("Blank", "/fast", id="lnk-blank"),
            ),
            outlet,
            id="shell",
        )

    @app.page("/", title="Home")
    def home():
        return gx.column(
            gx.heading("Home Heading", id="main-h1"),
            gx.button("Local", id="local-btn", interactions=(on("click", act.increment("n")),)),
            id="home-box",
            local_state={"n": 0},
        )

    @app.page("/slow", title="Slow Route")
    def slow():
        time.sleep(0.25)
        return gx.heading("Slow Heading", id="main-h1")

    @app.page("/fast", title="Fast Route")
    def fast():
        return gx.column(
            gx.heading("Fast Heading", id="main-h1"),
            *[gx.spacer(size=128) for _ in range(10)],
            gx.heading("Section B", level=2, id="section-b"),
        )

    @app.page("/r/{idx}", title="Dynamic Route")
    def dyn_route(idx: str):
        return gx.heading(f"Route {idx}", id="main-h1")

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

    user_data = tempfile.mkdtemp(prefix="radui_m191_")
    proc = subprocess.Popen(
        [
            CHROME_PATH,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--window-size=1280,720",
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

    async def run_checks() -> dict[str, Any]:
        async with websockets.connect(ws_url, max_size=10_000_000) as ws:
            await _cdp_call(ws, 1, "Runtime.enable")
            await _cdp_call(ws, 2, "Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
            await asyncio.sleep(0.4)

            # 1. Concurrency: fire /slow then immediately /fast; /fast must win & /slow must be superseded/aborted
            res_conc = await _cdp_eval(ws, 3, """
                window.__m191Token = 1;
                const pSlow = window.RadUINavigator.navigate("/slow");
                const pFast = window.RadUINavigator.navigate("/fast");
                const [rSlow, rFast] = await Promise.all([pSlow, pFast]);
                await new Promise(r => setTimeout(r, 300));
                return {
                    slowSuperseded: Boolean(rSlow.superseded),
                    fastOk: Boolean(rFast.ok),
                    finalPath: location.pathname,
                    finalHeading: document.getElementById("main-h1").textContent,
                    ariaBusy: document.querySelector("[data-gx-root]").getAttribute("aria-busy"),
                    live: document.getElementById("gx-live-region").textContent,
                    activeId: document.activeElement ? document.activeElement.id : null,
                    token: window.__m191Token
                };
            """)

            # 2. Redirect loop protection + modifier-key / target="_blank" non-interception
            res_loop_and_links = await _cdp_eval(ws, 4, """
                const off = window.RadUINavigator.beforeEach((to) => {
                    if (to === "/loop-a") return "/loop-b";
                    if (to === "/loop-b") return "/loop-a";
                    return true;
                });
                const loopRes = await window.RadUINavigator.navigate("/loop-a");
                off();

                // Modifier click should NOT be prevented by SPA navigator
                const lnk = document.getElementById("lnk-home");
                const modEv = new MouseEvent("click", { bubbles: true, cancelable: true, ctrlKey: true });
                lnk.dispatchEvent(modEv);

                // target="_blank" should NOT be prevented
                const blank = document.getElementById("lnk-blank");
                blank.setAttribute("target", "_blank");
                const blankEv = new MouseEvent("click", { bubbles: true, cancelable: true });
                blank.dispatchEvent(blankEv);

                return {
                    redirectLoop: Boolean(loopRes.redirectLoop),
                    modDefaultPrevented: modEv.defaultPrevented,
                    blankDefaultPrevented: blankEv.defaultPrevented,
                    reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches
                };
            """)

            # 3. 100-navigation lifecycle stress + prefetched vs uncached latency benchmark
            res_perf = await _cdp_eval(ws, 5, """
                window.RadUINavigator.clearCache();
                const uncachedTimes = [];
                for (let i = 0; i < 30; i++) {
                    const t0 = performance.now();
                    await window.RadUINavigator.navigate("/r/" + i);
                    uncachedTimes.push(performance.now() - t0);
                }

                // Prefetch /fast and /home, then benchmark 100 prefetched navigations
                await window.RadUINavigator.prefetch("/fast");
                await window.RadUINavigator.prefetch("/");
                const prefetchedTimes = [];
                for (let i = 0; i < 100; i++) {
                    const target = (i % 2 === 0) ? "/fast" : "/";
                    const t0 = performance.now();
                    await window.RadUINavigator.navigate(target);
                    prefetchedTimes.push(performance.now() - t0);
                }
                uncachedTimes.sort((a, b) => a - b);
                prefetchedTimes.sort((a, b) => a - b);
                return {
                    uncached_p50_ms: uncachedTimes[Math.floor(uncachedTimes.length * 0.5)],
                    uncached_p95_ms: uncachedTimes[Math.floor(uncachedTimes.length * 0.95)],
                    prefetched_p50_ms: prefetchedTimes[Math.floor(prefetchedTimes.length * 0.5)],
                    prefetched_p95_ms: prefetchedTimes[Math.floor(prefetchedTimes.length * 0.95)],
                    bootstrapped: Boolean(window.__gxNavigatorBootstrapped),
                    token: window.__m191Token
                };
            """)

            return {"conc": res_conc, "loop": res_loop_and_links, "perf": res_perf}

    try:
        out = asyncio.run(run_checks())
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        server.should_exit = True
        srv_thread.join(timeout=3)
        shutil.rmtree(user_data, ignore_errors=True)

    # Concurrency & A11y assertions
    assert out["conc"]["slowSuperseded"] is True
    assert out["conc"]["fastOk"] is True
    assert out["conc"]["finalPath"] == "/fast"
    assert out["conc"]["finalHeading"] == "Fast Heading"
    assert out["conc"]["ariaBusy"] is None
    assert "Navigated to Fast Route" in out["conc"]["live"]
    assert out["conc"]["activeId"] == "main-h1"
    assert out["conc"]["token"] == 1

    # Redirect loop & link modifiers
    assert out["loop"]["redirectLoop"] is True
    assert out["loop"]["modDefaultPrevented"] is False
    assert out["loop"]["blankDefaultPrevented"] is False
    assert out["loop"]["reducedMotion"] is True

    # Lifecycle & performance
    assert out["perf"]["bootstrapped"] is True
    assert out["perf"]["token"] == 1
    assert out["perf"]["prefetched_p50_ms"] < 5.0

    raw_bytes = len(CLIENT_JS.encode("utf-8"))
    gz_bytes = len(gzip.compress(CLIENT_JS.encode("utf-8"), compresslevel=9))
    print(
        f"\n[M1.9.1 Telemetry] CLIENT_JS raw={raw_bytes} B, gzip={gz_bytes} B | "
        f"uncached p50={out['perf']['uncached_p50_ms']:.3f}ms p95={out['perf']['uncached_p95_ms']:.3f}ms | "
        f"prefetched p50={out['perf']['prefetched_p50_ms']:.3f}ms p95={out['perf']['prefetched_p95_ms']:.3f}ms"
    )
