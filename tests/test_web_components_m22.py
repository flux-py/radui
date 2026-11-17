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
from radui.web_components import WebComponentSpec, validate_custom_element_tag

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_web_component_spec_validation():
    assert validate_custom_element_tag("acme-card") == "acme-card"
    with pytest.raises(ValueError):
        validate_custom_element_tag("div")
    with pytest.raises(ValueError):
        validate_custom_element_tag("annotation-xml")
    with pytest.raises(ValueError):
        WebComponentSpec(tag_name="acme-btn", observed_attributes=("onclick",))
    with pytest.raises(ValueError):
        WebComponentSpec(tag_name="acme-btn", event_commands={"bad event!": "cmd.ok"})


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


def test_web_components_shadow_dom_events_resumable_and_spa_browser():
    if not os.path.exists(CHROME_PATH):
        pytest.skip("Chrome binary not available")

    app = gx.App("M22WebCompApp")
    received_scores: list[str] = []

    @app.command("rating.save")
    def save_rating(ctx: gx.CommandContext):
        received_scores.append(str(ctx.form_data.get("score", "")))

    @app.web_component(
        "acme-rating",
        shadow_mode="open",
        observed_attributes=("label",),
        events=("rating-change",),
        styles=":host { display: block; color: var(--gx-primary, rgb(37, 99, 235)); }",
        template_html='<div class="inner"><span data-gx-prop="label">Init</span><slot></slot></div>',
    )
    def acme_rating():
        pass

    @app.web_component(
        "acme-closed",
        shadow_mode="closed",
        styles=":host { display: inline-block; }",
        template_html="<span>Closed</span><slot></slot>",
    )
    def acme_closed():
        pass

    @app.page("/", title="WC Home")
    def home():
        return gx.column(
            gx.custom_element(
                "acme-rating",
                gx.text("Slotted Child", id="slotted-txt"),
                props={"label": "Stars"},
                event_commands={"rating-change": "rating.save"},
                id="wc-rating",
                resumable=True,
            ),
            gx.custom_element("acme-closed", gx.text("Inside Closed"), id="wc-closed"),
            gx.link("Next", "/wc-next", id="go-next"),
        )

    @app.page("/wc-next", title="WC Next")
    def wc_next():
        return gx.custom_element(
            "acme-rating",
            gx.text("Next Slotted", id="next-slotted"),
            props={"label": "NextStars"},
            id="wc-rating-2",
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

    user_data = tempfile.mkdtemp(prefix="radui_m22_")
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

            res = await _cdp_eval(ws, 2, """
                const el = document.getElementById("wc-rating");
                const closedEl = document.getElementById("wc-closed");
                const hasOpenShadow = Boolean(el.shadowRoot);
                const closedHidden = closedEl.shadowRoot === null;
                el.setAttribute("label", "UpdatedStars");
                const propText = el.shadowRoot.querySelector('[data-gx-prop="label"]').textContent;

                el.dispatchEvent(new CustomEvent("rating-change", { detail: { score: 5 }, bubbles: true }));
                await new Promise(r => setTimeout(r, 150));

                await window.RadUINavigator.navigate("/wc-next");
                const el2 = document.getElementById("wc-rating-2");
                return {
                    hasOpenShadow,
                    closedHidden,
                    propText,
                    resumed: el.getAttribute("data-gx-resumed"),
                    specs: window.RadUIWebComponents.specs(),
                    nextShadow: Boolean(el2 && el2.shadowRoot)
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

    assert out["hasOpenShadow"] is True
    assert out["closedHidden"] is True
    assert out["propText"] == "UpdatedStars"
    assert "acme-rating" in out["specs"]
    assert "acme-closed" in out["specs"]
    assert out["nextShadow"] is True
    assert "5" in received_scores
