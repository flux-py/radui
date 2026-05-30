from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


AGUIEventType = Literal[
    "run_start",
    "run_end",
    "step_start",
    "step_end",
    "tool_call",
    "tool_result",
    "text_delta",
    "state_delta",
    "approval_request",
    "approval_response",
]


@dataclass(frozen=True)
class AGUIEvent:
    event_type: AGUIEventType
    run_id: str
    step_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": "ag-ui/1.0",
            "type": self.event_type,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }


class AGUIEventJournal:
    """Manages an active agent run's interaction events and builds UI timelines."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._events: list[AGUIEvent] = []

    def emit(
        self,
        event_type: AGUIEventType,
        *,
        step_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AGUIEvent:
        event = AGUIEvent(
            event_type=event_type,
            run_id=self.run_id,
            step_id=step_id,
            payload=payload or {},
        )
        self._events.append(event)
        return event

    def to_steps_timeline(self) -> list[tuple[str, str, str]]:
        """Converts journaled events to a (title, status, detail) tuple list for StepTimeline."""
        steps: list[tuple[str, str, str]] = []
        for ev in self._events:
            if ev.event_type == "tool_call":
                tool = ev.payload.get("tool", "tool")
                args = str(ev.payload.get("arguments", ""))
                steps.append((f"Tool Call: {tool}", "running", f"Args: {args}"))
            elif ev.event_type == "tool_result":
                tool = ev.payload.get("tool", "tool")
                res = str(ev.payload.get("result", ""))[:80]
                steps.append((f"Tool Result: {tool}", "completed", f"Output: {res}"))
            elif ev.event_type == "approval_request":
                action = ev.payload.get("action", "action")
                steps.append((f"Human Approval: {action}", "pending", "Waiting for operator confirmation"))
            elif ev.event_type == "step_end":
                desc = ev.payload.get("description", "Step finished")
                steps.append((desc, "completed", "Done"))
        return steps

