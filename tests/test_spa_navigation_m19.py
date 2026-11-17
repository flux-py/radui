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
from typing import Any

import pytest
import uvicorn
import websockets
from fastapi.testclient import TestClient

import radui as gx
from radui.interactions import act, on

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_spa_navigate_endpoint_routing_layouts_guards_loading_and_error():
    app = gx.App("M19ServerNav")

    @app.layout("/")
    def root_layout(outlet):
        return gx.column(gx.text("RootShell", id="root-shell"), outlet, id="layout-root")

    @app.layout("/admin")
    def admin_layout(outlet):
        return gx.column(gx.text("AdminNav", id="admin-nav"), outlet, id="layout-admin")

    @app.page(
        "/admin/users/{user_id}",
        title="Admin User",
        loading=lambda: gx.text("Loading user...", id="user-loading"),
    )
    def admin_user(user_id: str):
        return gx.text(f"User:{user_id}", id="user-detail")

    @app.page("/protected", title="Secret", require_auth=True)
    def protected():
        return gx.text("Secret Data", id="sec-data")

    @app.page("/guarded-redirect", guard=lambda _req: "/admin/users/1")
    def guarded_redirect():
        return gx.text("Never", id="never")

    @app.page("/guarded-block", guard=lambda _req: False)
    def guarded_block():
        return gx.text("Blocked", id="blocked")

    @app.page(
        "/boom",
        error_boundary=lambda exc: gx.text(f"Recovered: {exc}", id="err-fallback"),
    )
    def boom():
        raise RuntimeError("route exploded")

    client = TestClient(app.asgi())

    # 1. Nested layouts + dynamic route param + loading_html
    res = client.get("/_gx/navigate?to=/admin/users/42")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["route"] == "/admin/users/{user_id}"
    assert data["view_id"] == "/admin/users/42"
    assert data["title"] == "Admin User"
    assert data["layouts"] == ["/", "/admin"]
    assert "RootShell" in data["html"]
    assert "AdminNav" in data["html"]
    assert "User:42" in data["html"]
    assert "Loading user..." in data["loading_html"]

    # 2. Auth guard -> 401 + fallback=True
    r_auth = client.get("/_gx/navigate?to=/protected")
    assert r_auth.status_code == 401
    assert r_auth.json()["fallback"] is True

    # 3. Server redirect guard
    r_redir = client.get("/_gx/navigate?to=/guarded-redirect")
    assert r_redir.status_code == 200
    assert r_redir.json()["redirect"] == "/admin/users/1"

    # 4. Server block guard
    r_blk = client.get("/_gx/navigate?to=/guarded-block")
    assert r_blk.status_code == 403
    assert r_blk.json()["fallback"] is True

    # 5. Route error boundary
    r_err = client.get("/_gx/navigate?to=/boom")
    assert r_err.status_code == 500
    err_data = r_err.json()
    assert err_data["fallback"] is False
    assert "Recovered: route exploded" in err_data["error_html"]

    # 6. Unknown route & external/open-redirect protection -> fallback=True
    assert client.get("/_gx/navigate?to=/missing").status_code == 404
    assert client.get("/_gx/navigate?to=//evil.com").status_code == 400


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


def test_spa_navigation_browser_end_to_end():
    if not os.path.exists(CHROME_PATH):
        pytest.skip("Chrome binary not available")

    app = gx.App("M19BrowserNav")
    cmd_hits: list[str] = []

    @app.layout("/")
    def root_layout(outlet):
        return gx.column(
            gx.row(
                gx.link("Home", "/", id="nav-home"),
                gx.link("User 7", "/users/7", id="nav-user7"),
                gx.link("About", "/about", id="nav-about", prefetch="viewport"),
                gx.link("Fallback", "/fallback-page", id="nav-fallback", spa=False),
            ),
            outlet,
            id="app-shell",
        )

    @app.page("/", title="Home Page")
    def home():
        return gx.column(
            gx.heading("Home", id="page-heading"),
            *[gx.spacer(size=128) for _ in range(15)],
            gx.link("Go User 7", "/users/7", id="bottom-link"),
        )

    @app.command("user.ping")
    def user_ping(ctx: gx.CommandContext):
        cmd_hits.append("ping")

    @app.page("/users/{uid}", title="User Detail")
    def user_detail(uid: str):
        return gx.column(
            gx.heading(f"Profile {uid}", id="page-heading"),
            gx.form(gx.button("Ping Server", id="ping-btn"), command="user.ping", id="ping-form"),
            id="user-box",
            local_state={"localVal": 1},
        )

    @app.page("/about", title="About RadUI")
    def about():
        return gx.heading("About Page", id="page-heading")

    @app.page("/fallback-page", title="Fallback Page")
    def fallback_page():
        return gx.heading("Full Reload Page", id="page-heading")

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

    user_data = tempfile.mkdtemp(prefix="radui_m19_")
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

    async def run_browser():
        async with websockets.connect(ws_url, max_size=10_000_000) as ws:
            await _cdp_call(ws, 1, "Runtime.enable")
            await asyncio.sleep(0.4)

            # Mark window token to prove zero full page reloads during SPA transitions
            await _cdp_eval(ws, 2, "window.__spaBootToken = 'alive'; window.scrollTo(0, 450);")
            await asyncio.sleep(0.1)

            # 1. Prefetch on hover + SPA click to /users/7
            res_u7 = await _cdp_eval(ws, 3, """
                const link = document.getElementById("nav-user7");
                link.dispatchEvent(new PointerEvent("pointerover", { bubbles: true }));
                await new Promise(r => setTimeout(r, 80));
                link.click();
                await new Promise(r => setTimeout(r, 150));
                return {
                    path: location.pathname,
                    title: document.title,
                    heading: document.getElementById("page-heading").textContent,
                    viewMeta: document.querySelector('meta[name="gx-view"]').getAttribute("content"),
                    token: window.__spaBootToken,
                    scrollY: window.scrollY
                };
            """)

            # 2. Execute server @app.command on dynamically navigated /users/7 page
            await _cdp_eval(ws, 4, """
                document.getElementById("ping-btn").click();
                await new Promise(r => setTimeout(r, 150));
            """)

            # 3. History back -> restores scrollY > 0 on '/' without reload; then forward
            res_hist = await _cdp_eval(ws, 5, """
                history.back();
                await new Promise(r => setTimeout(r, 200));
                const backState = {
                    path: location.pathname,
                    title: document.title,
                    scrollY: window.scrollY,
                    token: window.__spaBootToken
                };
                history.forward();
                await new Promise(r => setTimeout(r, 200));
                const fwdState = {
                    path: location.pathname,
                    heading: document.getElementById("page-heading").textContent,
                    token: window.__spaBootToken
                };
                return { backState, fwdState };
            """)

            # 4. Client navigation guards (block + redirect)
            res_guards = await _cdp_eval(ws, 6, """
                const off = window.RadUINavigator.beforeEach((to) => {
                    if (to === "/blocked") return false;
                    if (to === "/old") return "/about";
                    return true;
                });
                const blk = await window.RadUINavigator.navigate("/blocked");
                const redir = await window.RadUINavigator.navigate("/old");
                off();
                return {
                    blkCancelled: blk.cancelled,
                    redirOk: redir.ok,
                    path: location.pathname,
                    title: document.title,
                    token: window.__spaBootToken
                };
            """)

            # 5. Fallback to full server navigation when data-gx-spa="false"
            await _cdp_eval(ws, 7, """
                document.getElementById("nav-fallback").click();
            """)
            await asyncio.sleep(0.5)
            res_fb = await _cdp_eval(ws, 8, """
                return {
                    path: location.pathname,
                    heading: document.getElementById("page-heading").textContent,
                    tokenAfterReload: window.__spaBootToken || null
                };
            """)

            return {"u7": res_u7, "hist": res_hist, "guards": res_guards, "fb": res_fb}

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

    assert out["u7"]["path"] == "/users/7"
    assert out["u7"]["title"] == "User Detail"
    assert out["u7"]["heading"] == "Profile 7"
    assert out["u7"]["viewMeta"] == "/users/7"
    assert out["u7"]["token"] == "alive"
    assert out["u7"]["scrollY"] == 0

    assert "ping" in cmd_hits

    assert out["hist"]["backState"]["path"] == "/"
    assert out["hist"]["backState"]["scrollY"] > 0
    assert out["hist"]["backState"]["token"] == "alive"
    assert out["hist"]["fwdState"]["path"] == "/users/7"
    assert out["hist"]["fwdState"]["heading"] == "Profile 7"
    assert out["hist"]["fwdState"]["token"] == "alive"

    assert out["guards"]["blkCancelled"] is True
    assert out["guards"]["redirOk"] is True
    assert out["guards"]["path"] == "/about"
    assert out["guards"]["title"] == "About RadUI"
    assert out["guards"]["token"] == "alive"

    assert out["fb"]["path"] == "/fallback-page"
    assert out["fb"]["heading"] == "Full Reload Page"
    assert out["fb"]["tokenAfterReload"] is None
