from __future__ import annotations

import asyncio
import gzip
import inspect
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
from radui.components import nodes as comp_nodes
from radui.interactions import (
    ALLOWED_BIND_TARGETS,
    ALLOWED_EVENT_TYPES,
    ActionOp,
    act,
    on,
    validate_bind_local,
    validate_local_state,
)
from radui.renderers.html import CLIENT_JS, HTMLRenderer

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _minimal_call_kwargs(name: str) -> tuple[list[Any], dict[str, Any]]:
    """Return minimal positional/keyword args to construct each Component builder."""
    d_node = comp_nodes.diagram_node("n1", "Node 1")
    d_edge = comp_nodes.diagram_edge("n1", "n1")
    t_node = comp_nodes.tree_node("t1", "Root")
    c_msg = comp_nodes.chat_message("hi", role="user")
    tab1 = comp_nodes.tab_item("Tab 1", comp_nodes.text("Body"))
    acc1 = comp_nodes.accordion_item("Item 1", comp_nodes.text("Acc"))
    bc1 = comp_nodes.breadcrumb_item("Home", "/")
    dm1 = comp_nodes.dropdown_menu_item("Action")
    child = comp_nodes.text("Child")

    class _DummyJob:
        name = "job-1"
        def latest_snapshot(self, session_id=None):
            return None
        def topic(self):
            return "job:job-1"

    ref = comp_nodes.StateRef("cb", False)
    special: dict[str, tuple[list[Any], dict[str, Any]]] = {
        "text": (["Hello"], {}),
        "heading": (["Title"], {}),
        "link": (["Go", "/"], {}),
        "column": ([child], {}),
        "row": ([child], {}),
        "card": ([child], {}),
        "grid": ([child], {}),
        "container": ([child], {}),
        "stack": ([child], {}),
        "button": (["Click"], {}),
        "form": ([child], {"command": "cmd.ok"}),
        "divider": ([], {}),
        "spacer": ([], {}),
        "badge": (["OK"], {}),
        "callout": (["Note"], {}),
        "tab_item": (["T1", child], {}),
        "tabs": ([tab1], {}),
        "modal": (["Modal", child], {}),
        "drawer": (["Drawer", child], {}),
        "input": ([], {"name": "inp"}),
        "textarea": ([], {"name": "ta"}),
        "select": ([[("a", "A")]], {"name": "sel"}),
        "switch": (["sw"], {}),
        "radio_group": (["rg"], {"options": [("a", "A")]}),
        "checkbox": (["Agree"], {"bind": ref}),
        "job_panel": ([_DummyJob()], {}),
        "metric_card": (["Users", "42"], {}),
        "table": ([["Col"], [["1"]]], {}),
        "plot": (["bar"], {"data": [{"x": "a", "y": 1}]}),
        "chat_message": (["hi"], {"role": "user"}),
        "chat_view": ([[c_msg]], {}),
        "chat_input": ([], {}),
        "streaming_text": (["tok"], {}),
        "action_card": (["Run"], {"approve_command": "cmd.run"}),
        "step_timeline": ([[{"label": "Step 1", "status": "done"}]], {}),
        "dynamic_card": ([{"title": "Card"}], {}),
        "diagram": ([[d_node], [d_edge]], {}),
        "code_block": (["print(1)"], {}),
        "tree_view": ([[t_node]], {}),
        "data_grid": ([["A"], [["1"]]], {}),
        "generative_slot": (["slot-1"], {}),
        "skeleton": ([], {}),
        "empty_state": (["Nothing here"], {}),
        "file_upload": ([], {}),
        "virtual_list": ([["Item 1"]], {}),
        "theme_toggle": ([], {}),
        "error_boundary": ([child], {}),
        "toast": (["Saved"], {}),
        "toast_container": ([], {}),
        "tooltip": (["Tip", child], {}),
        "popover": (["Pop", child], {}),
        "accordion_item": (["Acc", child], {}),
        "accordion": ([acc1], {}),
        "breadcrumb_item": (["Home", "/"], {}),
        "breadcrumb": ([bc1], {}),
        "pagination": ([1, 10], {}),
        "progress_bar": ([50], {}),
        "progress_circle": ([50], {}),
        "avatar": (["AK"], {}),
        "avatar_group": ([comp_nodes.avatar("AK")], {}),
        "date_picker": (["dt", ref], {}),
        "time_picker": (["tm", ref], {}),
        "slider": (["sl", ref], {}),
        "split_panel": ([child, child], {}),
        "dropdown_menu_item": (["Item"], {}),
        "dropdown_menu": (["Actions", [dm1]], {}),
        "kbd": (["Ctrl+K"], {}),
        "tag": (["v1"], {}),
        "presence_bar": (["room-1"], {}),
        "presence": (["room-1"], {}),
        "canvas_stream": (["stream-1"], {}),
        "custom_element": (["acme-card"], {}),
        "suspense": ([lambda: comp_nodes.text("ok")], {}),
    }
    return special[name]


def test_all_component_builders_support_interactions():
    from radui.state.runtime import ContextIdentity, StateContext, StateRuntime

    non_components = {"_ix", "_resolve_binding", "diagram_node", "diagram_edge", "tree_node"}
    renderer = HTMLRenderer()
    sc = StateContext(StateRuntime("test"), ContextIdentity(app_id="test", session_id="s1", view_id="/", user_id="u1"))
    ix = (on("click", act.toggle("flag")),)
    ls = {"flag": False}
    bl = {"pressed": "flag"}

    checked = 0
    for name, fn in inspect.getmembers(comp_nodes, inspect.isfunction):
        if fn.__module__ != comp_nodes.__name__ or name in non_components or name.startswith("_"):
            continue
        pos, kw = _minimal_call_kwargs(name)
        kw.update({"local_state": ls, "interactions": ix, "bind_local": bl})
        comp = fn(*pos, **kw)
        assert comp.local_state == ls, f"{name} dropped local_state"
        assert comp.interactions == ix, f"{name} dropped interactions"
        assert comp.bind_local == bl, f"{name} dropped bind_local"
        html = renderer.render_component(comp, state_context=sc, csrf_token="test-csrf")
        if name != "tab_item":
            assert "data-gx-local-state" in html, f"{name} HTML missing data-gx-local-state"
            assert "data-gx-interactions" in html, f"{name} HTML missing data-gx-interactions"
            assert "data-gx-bind-local" in html, f"{name} HTML missing data-gx-bind-local"
        checked += 1

    assert checked == 73, f"Expected 73 component builders checked, got {checked}"


def test_adversarial_interaction_security():
    # 1. Python descriptor validation blocks prototype pollution & unsafe attrs
    with pytest.raises(ValueError):
        validate_local_state({"__proto__": {"polluted": True}})
    with pytest.raises(ValueError):
        validate_local_state({"constructor": "bad"})
    with pytest.raises(ValueError):
        validate_local_state({"prototype": "bad"})
    with pytest.raises(ValueError):
        on("onload", act.set("x", 1))
    with pytest.raises(ValueError):
        act.set_attr("onclick", "alert(1)")
    with pytest.raises(ValueError):
        act.set_attr("srcdoc", "<script>alert(1)</script>")
    with pytest.raises(ValueError):
        validate_bind_local({"innerHTML": "evil"})

    # 2. Server-side command dispatch authorization + CSRF checks
    app = gx.App("M181SecurityApp")

    @app.command("page1.act")
    def page1_act(ctx: gx.CommandContext):
        ctx.state["ran"] = True

    @app.command("page2.secret")
    def page2_secret(ctx: gx.CommandContext):
        ctx.state["secret"] = True

    @app.page("/p1")
    def p1():
        return gx.button(
            "Trigger",
            id="p1-btn",
            interactions=(on("click", act.dispatch_command("page1.act")),),
        )

    @app.page("/p2")
    def p2():
        return gx.button("Secret", id="p2-btn", command="page2.secret")

    client = TestClient(app.asgi())
    r1 = client.get("/p1")
    assert r1.status_code == 200
    assert 'name="gx-csrf"' in r1.text
    csrf = r1.text.split('name="gx-csrf" content="')[1].split('"')[0]

    # Missing/bad CSRF -> 403
    bad_csrf = client.post(
        "/_gx/commands/page1.act",
        data={"_csrf": "invalid-token"},
    )
    assert bad_csrf.status_code == 403

    # Cross-page command dispatch from /p1 to page2.secret -> rejected (400/403/404)
    cross_page = client.post(
        "/_gx/commands/page2.secret",
        data={"_csrf": csrf, "_gx_view_id": "/p1", "_gx_action_id": "act-000001"},
    )
    assert cross_page.status_code in (400, 403, 404)

    # Authorized dispatch on /p1 -> 200
    ok_resp = client.post(
        "/_gx/commands/page1.act",
        data={"_csrf": csrf, "_gx_view_id": "/p1", "_gx_action_id": "act-000002"},
    )
    assert ok_resp.status_code == 200


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


def _launch_app_and_chrome(app: gx.App):
    port = _free_port()
    config = uvicorn.Config(app.asgi(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    srv_thread = threading.Thread(target=server.run, daemon=True)
    srv_thread.start()

    for _ in range(50):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.1)

    cdp_port = _free_port()
    user_data = tempfile.mkdtemp(prefix="radui_m181_")
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
    assert ws_url, "Chrome CDP failed to expose page target"
    return server, srv_thread, proc, user_data, ws_url, port


def test_all_events_actions_and_bindings_and_hardening_in_browser():
    if not os.path.exists(CHROME_PATH):
        pytest.skip("Chrome binary not available")

    app = gx.App("M181BrowserHardening")
    island_hits: list[str] = []

    @app.command("cmd.ping")
    def cmd_ping(ctx: gx.CommandContext):
        island_hits.append("ping")

    @app.command("cmd.form_noop")
    def cmd_form_noop(ctx: gx.CommandContext):
        pass

    @app.island("lazy-widget", hydration="fetch", trigger="eager")
    def lazy_widget():
        return gx.column(
            gx.text("0", id="island-count", bind_local={"text": "n"}),
            gx.button(
                "Island Inc",
                id="island-inc-btn",
                interactions=(on("click", act.increment("n", by=5)),),
            ),
            id="island-scope",
            local_state={"n": 10},
        )

    @app.page("/")
    def index():
        return gx.column(
            # Scope covering all 19 actions + 7 bind_local properties
            gx.column(
                gx.text("0", id="b-text", bind_local={"text": "count"}),
                gx.text("VisibleBox", id="b-visible", bind_local={"visible": "is_open"}),
                gx.text("HiddenBox", id="b-hidden", bind_local={"hidden": "is_open"}),
                gx.button("DisableTarget", id="b-disabled", bind_local={"disabled": "is_disabled"}, interactions=(on("click", act.announce("noop")),)),
                gx.button("ToggleTarget", id="b-aria", bind_local={"open": "is_open", "pressed": "is_pressed", "expanded": "is_open"}, interactions=(on("click", act.announce("noop")),)),
                gx.text("RawText", id="action-target"),
                gx.input(name="focus_inp", id="focus-target", interactions=(on("focus", act.add_class("got-focus", target="focus-target")),)),
                gx.button(
                    "AllActions",
                    id="btn-actions",
                    interactions=(
                        on(
                            "click",
                            act.toggle("is_open"),
                            act.set("is_pressed", True),
                            act.increment("count", by=3),
                            act.decrement("count", by=1),
                            act.show(target="action-target"),
                            act.open(target="action-target"),
                            act.enable(target="b-disabled"),
                            act.add_class("cls-a", target="action-target"),
                            act.toggle_class("cls-b", target="action-target"),
                            act.set_text("<img src=x onerror=window.__xss=1>", target="action-target"),
                            act.set_attr("aria-label", "SafeLabel", target="action-target"),
                            act.announce("Actions Executed"),
                            act.focus("focus-target"),
                            act.dispatch_command("cmd.ping"),
                        ),
                        on(
                            "dblclick",
                            act.hide(target="action-target"),
                            act.close(target="action-target"),
                            act.disable(target="b-disabled"),
                            act.remove_class("cls-a", target="action-target"),
                            act.remove_attr("aria-label", target="action-target"),
                        ),
                    ),
                ),
                id="main-scope",
                local_state={"count": 0, "is_open": False, "is_disabled": False, "is_pressed": False},
            ),
            # Event matrix host
            gx.column(
                gx.text("events:", id="ev-log"),
                gx.button(
                    "EventBox",
                    id="ev-box",
                    interactions=(
                        on("mouseenter", act.add_class("ev-me", target="ev-log")),
                        on("mouseleave", act.add_class("ev-ml", target="ev-log")),
                        on("pointerenter", act.add_class("ev-pe", target="ev-log")),
                        on("pointerleave", act.add_class("ev-pl", target="ev-log")),
                        on("focus", act.add_class("ev-foc", target="ev-log")),
                        on("blur", act.add_class("ev-blr", target="ev-log")),
                        on("keydown", act.add_class("ev-kd", target="ev-log")),
                        on("keyup", act.add_class("ev-ku", target="ev-log")),
                        on("dragstart", act.add_class("ev-ds", target="ev-log")),
                        on("dragover", act.add_class("ev-do", target="ev-log")),
                        on("drop", act.add_class("ev-dp", target="ev-log")),
                    ),
                ),
                gx.input(
                    name="ev_inp",
                    id="ev-inp",
                    interactions=(
                        on("input", act.add_class("ev-in", target="ev-log")),
                        on("change", act.add_class("ev-ch", target="ev-log")),
                    ),
                ),
                gx.form(
                    gx.button("Sub", id="ev-sub-btn", interactions=(on("click", act.announce("sub")),)),
                    command="cmd.form_noop",
                    id="ev-form",
                    interactions=(on("submit", act.add_class("ev-sub", target="ev-log"), prevent_default=True),),
                ),
                id="ev-scope",
                local_state={"x": 1},
            ),
            # Accessibility: Tabs + Modal
            gx.tabs(
                gx.tab_item("One", gx.text("P1")),
                gx.tab_item("Two", gx.text("P2")),
                id="a11y-tabs",
            ),
            gx.modal(
                "Confirm",
                gx.button("ModalInside", id="modal-inside-btn", interactions=(on("click", act.announce("m")),)),
                trigger_label="Open Modal",
                id="a11y-modal",
            ),
            # Hybrid Island
            lazy_widget(),
        )

    server, srv_thread, proc, user_data, ws_url, _ = _launch_app_and_chrome(app)

    async def run_checks() -> dict[str, Any]:
        async with websockets.connect(ws_url, max_size=10_000_000) as ws:
            await _cdp_call(ws, 1, "Runtime.enable")
            await _cdp_call(ws, 2, "Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
            await asyncio.sleep(0.5)

            # 1. Verify all 19 actions + 7 bind_local properties + XSS safety + live region + focus
            res_actions = await _cdp_eval(ws, 3, """
                document.getElementById("btn-actions").click();
                await new Promise(r => setTimeout(r, 150));
                const t = document.getElementById("action-target");
                const bText = document.getElementById("b-text").textContent;
                const bVisHidden = document.getElementById("b-visible").hidden;
                const bHidHidden = document.getElementById("b-hidden").hidden;
                const bAria = document.getElementById("b-aria");
                const live = document.getElementById("gx-live-region").textContent;
                const focusInside = document.activeElement ? Boolean(document.activeElement.closest("#focus-target")) : false;
                const hasCls = t.classList.contains("cls-a") && t.classList.contains("cls-b");
                const safeTxt = t.textContent;
                const safeLbl = t.getAttribute("aria-label");

                document.getElementById("btn-actions").dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
                await new Promise(r => setTimeout(r, 30));
                const afterDblDisabled = document.getElementById("b-disabled").disabled;
                const afterDblRemovedCls = !t.classList.contains("cls-a");
                const afterDblRemovedAttr = t.getAttribute("aria-label") === null;
                const afterDblHidden = t.hidden;
                return {
                    bText, bVisHidden, bHidHidden,
                    ariaPressed: bAria.getAttribute("aria-pressed"),
                    ariaExpanded: bAria.getAttribute("aria-expanded"),
                    dataOpen: bAria.classList.contains("open"),
                    live, focusInside, hasCls, safeTxt, safeLbl,
                    xss: Boolean(window.__xss),
                    afterDblDisabled, afterDblRemovedCls, afterDblRemovedAttr, afterDblHidden,
                    reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches
                };
            """)

            # 2. Verify all remaining delegated events
            res_events = await _cdp_eval(ws, 4, """
                const box = document.getElementById("ev-box");
                const inp = document.getElementById("ev-inp").querySelector("input") || document.getElementById("ev-inp");
                const form = document.getElementById("ev-form");
                box.dispatchEvent(new PointerEvent("pointerover", { bubbles: true }));
                box.dispatchEvent(new PointerEvent("pointerout", { bubbles: true }));
                box.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
                box.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
                box.dispatchEvent(new KeyboardEvent("keydown", { key: "a", bubbles: true }));
                box.dispatchEvent(new KeyboardEvent("keyup", { key: "a", bubbles: true }));
                box.dispatchEvent(new Event("dragstart", { bubbles: true }));
                box.dispatchEvent(new Event("dragover", { bubbles: true }));
                box.dispatchEvent(new Event("drop", { bubbles: true }));
                inp.dispatchEvent(new Event("input", { bubbles: true }));
                inp.dispatchEvent(new Event("change", { bubbles: true }));
                form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
                const cls = [...document.getElementById("ev-log").classList];
                return cls;
            """)

            # 3. Verify Hybrid Island hydration + interaction
            res_island = await _cdp_eval(ws, 5, """
                const btn = document.getElementById("island-inc-btn");
                const before = document.getElementById("island-count").textContent;
                btn.click();
                const after = document.getElementById("island-count").textContent;
                return { before, after };
            """)

            # 4. Adversarial DOM tampering in browser (malformed JSON, __proto__, forged on* attr)
            res_sec = await _cdp_eval(ws, 6, """
                const host = document.createElement("div");
                host.innerHTML = '<div id="evil-scope" data-gx-local-state="{bad json"><button id="evil-btn" data-gx-interactions="[{&quot;event&quot;:&quot;click&quot;,&quot;action&quot;:&quot;set_attr&quot;,&quot;attr&quot;:&quot;onclick&quot;,&quot;value&quot;:&quot;window.__pwn=1&quot;}]">Evil</button></div>';
                document.body.appendChild(host);
                document.getElementById("evil-btn").click();
                const hasOnclick = document.getElementById("evil-btn").hasAttribute("onclick");
                // Also test __proto__ key in JSON
                const pHost = document.createElement("div");
                pHost.setAttribute("data-gx-local-state", '{"__proto__":{"polluted":true},"x":1}');
                document.body.appendChild(pHost);
                const st = window.RadUIInteractions.getState(pHost);
                const polluted = ({}).polluted === true;
                host.remove();
                pHost.remove();
                return { hasOnclick, polluted, x: st.x, pwn: Boolean(window.__pwn) };
            """)

            # 5. Lifecycle stress (100 mount/unmount cycles) + 500-interaction latency benchmark
            res_stress = await _cdp_eval(ws, 7, """
                const root = document.createElement("div");
                document.body.appendChild(root);
                for (let i = 0; i < 100; i++) {
                    const el = document.createElement("div");
                    el.setAttribute("data-gx-local-state", JSON.stringify({ c: i }));
                    const sp = document.createElement("span");
                    sp.className = "v";
                    sp.setAttribute("data-gx-bind-local", JSON.stringify({ text: "c" }));
                    const btn = document.createElement("button");
                    btn.className = "b";
                    btn.setAttribute("data-gx-interactions", JSON.stringify([{ event: "click", actions: [{ op: "increment", key: "c", value: 1 }] }]));
                    el.appendChild(sp);
                    el.appendChild(btn);
                    root.appendChild(el);
                    window.RadUIInteractions.syncTree(el);
                    btn.click();
                    if (sp.textContent !== String(i + 1)) {
                        throw new Error("Lifecycle sync failed at cycle " + i);
                    }
                    el.remove();
                }
                root.remove();

                // Benchmark 500 clicks on a local counter
                const benchBtn = document.getElementById("btn-actions");
                const times = [];
                for (let i = 0; i < 500; i++) {
                    const t0 = performance.now();
                    benchBtn.click();
                    times.push(performance.now() - t0);
                }
                times.sort((a, b) => a - b);
                return {
                    cycles: 100,
                    p50_ms: times[Math.floor(times.length * 0.5)],
                    p95_ms: times[Math.floor(times.length * 0.95)],
                    bootstrapped: Boolean(window.__gxInteractionsBootstrapped),
                };
            """)

            # 6. Accessibility: Tabs keyboard + Modal Escape focus restore
            res_a11y = await _cdp_eval(ws, 8, """
                const tabs = document.querySelectorAll('#a11y-tabs [role="tab"]');
                tabs[0].focus();
                tabs[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
                const tab2Sel = tabs[1].getAttribute("aria-selected");

                const openBtn = document.querySelector("#a11y-modal [data-gx-modal-open]");
                openBtn.focus();
                openBtn.click();
                const backdrop = document.querySelector("#a11y-modal .gx-modal-backdrop");
                const isOpen = backdrop.classList.contains("open") && backdrop.getAttribute("aria-hidden") === "false";
                document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
                const isClosed = !backdrop.classList.contains("open") && backdrop.getAttribute("aria-hidden") === "true";
                return { tab2Sel, isOpen, isClosed };
            """)

            return {
                "actions": res_actions,
                "events": res_events,
                "island": res_island,
                "sec": res_sec,
                "stress": res_stress,
                "a11y": res_a1y if False else res_a11y,
            }

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

    # Assertions on actions & bindings
    act_out = out["actions"]
    assert act_out["bText"] == "2"  # 0 + 3 - 1
    assert act_out["bVisHidden"] is False
    assert act_out["bHidHidden"] is True
    assert act_out["ariaPressed"] == "true"
    assert act_out["ariaExpanded"] == "true"
    assert act_out["dataOpen"] is True
    assert act_out["live"] == "Actions Executed"
    assert act_out["focusInside"] is True
    assert act_out["hasCls"] is True
    assert act_out["safeTxt"] == "<img src=x onerror=window.__xss=1>"
    assert act_out["safeLbl"] == "SafeLabel"
    assert act_out["xss"] is False
    assert act_out["afterDblDisabled"] is True
    assert act_out["afterDblRemovedCls"] is True
    assert act_out["afterDblRemovedAttr"] is True
    assert act_out["afterDblHidden"] is True
    assert act_out["reducedMotion"] is True
    assert "ping" in island_hits

    # Assertions on all event classes
    expected_ev = {"ev-me", "ev-ml", "ev-pe", "ev-pl", "ev-foc", "ev-blr", "ev-kd", "ev-ku", "ev-ds", "ev-do", "ev-dp", "ev-in", "ev-ch", "ev-sub"}
    assert expected_ev.issubset(set(out["events"]))

    # Hybrid island
    assert out["island"] == {"before": "10", "after": "15"}

    # Adversarial browser security
    assert out["sec"]["hasOnclick"] is False
    assert out["sec"]["polluted"] is False
    assert out["sec"]["pwn"] is False

    # Stress & benchmark
    assert out["stress"]["cycles"] == 100
    assert out["stress"]["bootstrapped"] is True
    assert out["stress"]["p50_ms"] < 5.0
    assert out["stress"]["p95_ms"] < 20.0

    # Accessibility
    assert out["a11y"]["tab2Sel"] == "true"
    assert out["a11y"]["isOpen"] is True
    assert out["a11y"]["isClosed"] is True

    # Print benchmark & budget telemetry for M1.8.1 report
    raw_bytes = len(CLIENT_JS.encode("utf-8"))
    gz_bytes = len(gzip.compress(CLIENT_JS.encode("utf-8"), compresslevel=9))
    print(f"\n[M1.8.1 Telemetry] CLIENT_JS raw={raw_bytes} B, gzip={gz_bytes} B, p50={out['stress']['p50_ms']:.3f}ms, p95={out['stress']['p95_ms']:.3f}ms")
    from typing import get_args
    assert len(ALLOWED_EVENT_TYPES) == 16
    assert len(get_args(ActionOp)) == 19
    assert len(ALLOWED_BIND_TARGETS) == 7
