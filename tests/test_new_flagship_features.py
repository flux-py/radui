import shutil
import tempfile
from pathlib import Path
import pytest
import radui as ui
from radui import (
    DevTools,
    DevToolsConfig,
    TimeTravelDebugger,
    PresenceManager,
    PresenceUser,
    get_global_presence_manager,
    CanvasStream,
    canvas_stream,
    PresenceBar,
    presence_bar,
    presence,
    WasmExportEngine,
    export_wasm_bundle,
)


def test_devtools_time_travel_debugger():
    debugger = TimeTravelDebugger(max_entries=10)
    assert debugger.can_undo is False
    assert debugger.can_redo is False

    # Record 3 mutations
    debugger.record_change("cart.qty", old_val=1, new_val=2, command_name="cart.increment")
    debugger.record_change("cart.qty", old_val=2, new_val=3, command_name="cart.increment")
    debugger.record_change("user.name", old_val="Alice", new_val="Bob", command_name="user.rename")

    assert debugger.can_undo is True
    history = debugger.get_history()
    assert len(history) == 3
    assert history[0]["key"] == "user.name"

    # Rollback 1 step
    restorations = debugger.rollback_steps(steps=1)
    assert restorations == [("user.name", "Alice")]
    assert debugger.can_redo is True

    # Fast forward 1 step
    reapp = debugger.fast_forward_steps(steps=1)
    assert reapp == [("user.name", "Bob")]

    # Rollback 2 steps
    restorations = debugger.rollback_steps(steps=2)
    assert len(restorations) == 2
    assert restorations[0] == ("user.name", "Alice")
    assert restorations[1] == ("cart.qty", 2)


def test_collaborative_presence_manager():
    pm = PresenceManager()
    user1 = PresenceUser(user_id="u1", username="Alice", color="#10b981")
    user2 = PresenceUser(user_id="u2", username="Bob", color="#3b82f6")

    # Join room
    active = pm.join("room-alpha", user1)
    assert len(active) == 1
    assert active[0].username == "Alice"

    pm.join("room-alpha", user2)
    active = pm.get_active_users("room-alpha")
    assert len(active) == 2

    # Heartbeat & cursor coordinates
    pm.heartbeat("room-alpha", "u1", current_field="title_input", cursor=(120.0, 340.0))
    users = pm.get_active_users("room-alpha")
    alice = [u for u in users if u.user_id == "u1"][0]
    assert alice.current_field == "title_input"
    assert alice.cursor == (120.0, 340.0)

    # Field locking
    locked = pm.lock_field("room-alpha", "title_input", "u1", timeout_seconds=10.0)
    assert locked is True
    assert pm.get_field_lock("room-alpha", "title_input") == "u1"

    # User 2 tries to lock the same field -> rejected
    locked2 = pm.lock_field("room-alpha", "title_input", "u2", timeout_seconds=10.0)
    assert locked2 is False

    # Unlock field
    assert pm.unlock_field("room-alpha", "title_input", "u1") is True
    assert pm.get_field_lock("room-alpha", "title_input") is None

    # Leave room
    pm.leave("room-alpha", "u1")
    active = pm.get_active_users("room-alpha")
    assert len(active) == 1
    assert active[0].username == "Bob"


def test_presence_bar_and_canvas_stream_rendering():
    app = ui.App(title="Render Test")

    # Presence Bar
    pm = get_global_presence_manager()
    pm.join("telemetry-room", PresenceUser(user_id="dev1", username="Elena", color="#ec4899"))
    p_bar = ui.presence_bar("telemetry-room", max_avatars=3, show_names=True)
    html = app.renderer.render_component(p_bar)
    assert "gx-presence-bar" in html
    assert "Elena" in html
    assert "telemetry-room" in html

    # Canvas Stream
    c_stream = ui.canvas_stream("market.trades", width="100%", height=400, mode="waveform", buffer_size=50000)
    html = app.renderer.render_component(c_stream)
    assert "gx-canvas-stream" in html
    assert "market.trades" in html
    assert "waveform" in html
    assert "50000" in html


def test_wasm_export_engine():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "wasm_dist"
        engine = WasmExportEngine(app_path="app.py", output_dir=str(out_dir))
        exported_path = engine.export()

        assert (out_dir / "index.html").exists()
        assert (out_dir / "wasm-worker.js").exists()
        assert (out_dir / "service-worker.js").exists()

        index_content = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "WebAssembly & Pyodide" in index_content
        assert "wasm-worker.js" in index_content
