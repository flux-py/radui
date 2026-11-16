"""RADUI In-Browser DevTools: Live Reactive Time-Travel Debugger & DAG Inspector."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class DevToolsConfig:
    """Configuration options for the in-browser RADUI DevTools HUD."""

    enabled: bool = True
    time_travel: bool = True
    highlight_morphs: bool = True
    max_journal_entries: int = 50
    allowed_roles: set[str] | None = None
    show_latency_watermark: bool = True
    dock_position: str = "bottom-right"  # "bottom-right", "bottom-left", "top-right"


# Convenience alias matching `ui.DevTools`
DevTools = DevToolsConfig


@dataclass
class StateSnapshot:
    """Immutable record of a state transaction snapshot for time-travel replay."""

    step_index: int
    timestamp: float
    command_name: str | None
    key: str
    old_value: Any
    new_value: Any
    scope: str = "session"


class TimeTravelDebugger:
    """In-memory time-travel recording and rollback manager.

    Maintains a rolling journal of state mutations with reverse-diff reconstruction,
    enabling instant state rollbacks and forward steps without full page reloads.
    """

    def __init__(self, max_entries: int = 50) -> None:
        self.max_entries = max_entries
        self._history: list[StateSnapshot] = []
        self._future: list[StateSnapshot] = []
        self._step_counter = 0

    def record_change(
        self,
        key: str,
        old_val: Any,
        new_val: Any,
        command_name: str | None = None,
        scope: str = "session",
    ) -> StateSnapshot:
        """Record a newly applied state mutation."""
        self._step_counter += 1
        snapshot = StateSnapshot(
            step_index=self._step_counter,
            timestamp=time.time(),
            command_name=command_name,
            key=key,
            old_value=old_val,
            new_value=new_val,
            scope=scope,
        )
        self._history.append(snapshot)
        if len(self._history) > self.max_entries:
            self._history.pop(0)
        # Any new mutation invalidates the redo/future branch
        self._future.clear()
        return snapshot

    def rollback_steps(self, steps: int = 1) -> list[tuple[str, Any]]:
        """Roll back `steps` mutations, returning a list of (key, target_value) restorations."""
        restorations: list[tuple[str, Any]] = []
        for _ in range(steps):
            if not self._history:
                break
            snapshot = self._history.pop()
            self._future.append(snapshot)
            restorations.append((snapshot.key, snapshot.old_value))
        return restorations

    def fast_forward_steps(self, steps: int = 1) -> list[tuple[str, Any]]:
        """Fast-forward (redo) `steps` mutations previously rolled back."""
        reapplications: list[tuple[str, Any]] = []
        for _ in range(steps):
            if not self._future:
                break
            snapshot = self._future.pop()
            self._history.append(snapshot)
            reapplications.append((snapshot.key, snapshot.new_value))
        return reapplications

    def get_history(self) -> list[dict[str, Any]]:
        """Return a JSON-serializable list of historical transactions."""
        return [
            {
                "step": s.step_index,
                "timestamp": s.timestamp,
                "command": s.command_name or "direct_write",
                "key": s.key,
                "old_value": str(s.old_value),
                "new_value": str(s.new_value),
                "scope": s.scope,
            }
            for s in reversed(self._history)
        ]

    def clear(self) -> None:
        """Clear all journal history."""
        self._history.clear()
        self._future.clear()
        self._step_counter = 0

    @property
    def can_undo(self) -> bool:
        return len(self._history) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._future) > 0


def render_devtools_markup(config: DevToolsConfig, can_undo: bool = False, can_redo: bool = False) -> str:
    """Generate the lightweight client HUD markup injected when DevTools is enabled."""
    if not config.enabled:
        return ""

    pos_class = f"gx-devtools-{config.dock_position}"
    return (
        f'<aside id="gx-devtools-root" class="gx-devtools {pos_class}" aria-label="RADUI DevTools">'
        f'<button type="button" class="gx-devtools-trigger" id="gx-devtools-toggle" title="Toggle RADUI Reactive DevTools">'
        f'<span class="gx-devtools-icon">🛠️</span>'
        f'<span class="gx-devtools-badge">DevTools</span>'
        f'</button>'
        f'<div class="gx-devtools-panel" id="gx-devtools-panel" style="display:none;" role="region" aria-label="DevTools Panel">'
        f'<div class="gx-devtools-header">'
        f'<div class="gx-devtools-title"><strong>RADUI DevTools</strong> <span class="gx-devtools-tag">Live Reactive DAG</span></div>'
        f'<button type="button" class="gx-devtools-close" id="gx-devtools-close" aria-label="Close DevTools">&times;</button>'
        f'</div>'
        f'<div class="gx-devtools-tabs">'
        f'<button type="button" class="gx-devtools-tab active" data-tab="dag">Signal DAG</button>'
        f'<button type="button" class="gx-devtools-tab" data-tab="timeline">Time Travel</button>'
        f'<button type="button" class="gx-devtools-tab" data-tab="metrics">Telemetry</button>'
        f'</div>'
        f'<div class="gx-devtools-content">'
        f'<div class="gx-devtools-pane active" id="gx-pane-dag">'
        f'<div class="gx-devtools-dag-view" id="gx-devtools-dag-svg"><span class="gx-text-muted">Loading reactive graph...</span></div>'
        f'</div>'
        f'<div class="gx-devtools-pane" id="gx-pane-timeline">'
        f'<div class="gx-devtools-controls">'
        f'<button type="button" class="gx-btn-sm" id="gx-tt-undo"{" disabled" if not can_undo else ""}>⏮ Rollback</button>'
        f'<button type="button" class="gx-btn-sm" id="gx-tt-redo"{" disabled" if not can_redo else ""}>Redo ⏭</button>'
        f'<button type="button" class="gx-btn-sm gx-btn-subtle" id="gx-tt-clear">Clear</button>'
        f'</div>'
        f'<ul class="gx-devtools-journal" id="gx-devtools-journal"><li class="gx-text-muted">No state mutations recorded yet.</li></ul>'
        f'</div>'
        f'<div class="gx-devtools-pane" id="gx-pane-metrics">'
        f'<div class="gx-devtools-metric-grid">'
        f'<div class="gx-metric-box"><span class="gx-metric-label">AST Render</span><span class="gx-metric-val">0.039 ms</span></div>'
        f'<div class="gx-metric-box"><span class="gx-metric-label">DAG Invalidation</span><span class="gx-metric-val">0.021 ms</span></div>'
        f'<div class="gx-metric-box"><span class="gx-metric-label">Sub-DOM Morph</span><span class="gx-metric-val">0.168 ms</span></div>'
        f'<div class="gx-metric-box"><span class="gx-metric-label">Transport SSE</span><span class="gx-metric-val">0.008 ms</span></div>'
        f'</div>'
        f'</div>'
        f'</div>'
        f'</div>'
        f'</aside>'
    )
