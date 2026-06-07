from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


TraceCategory = Literal["render", "state", "command", "job", "event", "error", "security"]


@dataclass(frozen=True)
class TraceRecord:
    id: str
    timestamp: str
    category: TraceCategory
    name: str
    session_id: str | None = None
    view_id: str | None = None
    duration_ms: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "category": self.category,
            "name": self.name,
            "session_id": self.session_id,
            "view_id": self.view_id,
            "duration_ms": self.duration_ms,
            "details": self.details,
        }


class TraceCollector:
    """Thread-safe circular telemetry collector for the RADUI runtime inspector."""

    def __init__(self, capacity: int = 500) -> None:
        self.capacity = capacity
        self._records: list[TraceRecord] = []
        self._lock = threading.Lock()
        self._listeners: list[Any] = []
        self._counter = 0
        self._exporter: Any | None = None

    def set_exporter(self, exporter: Any) -> None:
        """Register an OTLP or external telemetry exporter."""
        self._exporter = exporter

    def record(
        self,
        category: TraceCategory,
        name: str,
        *,
        session_id: str | None = None,
        view_id: str | None = None,
        duration_ms: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> TraceRecord:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._counter += 1
            trace_id = f"trc-{self._counter:06d}"
            rec = TraceRecord(
                id=trace_id,
                timestamp=now,
                category=category,
                name=name,
                session_id=session_id,
                view_id=view_id,
                duration_ms=duration_ms,
                details=details or {},
            )
            self._records.append(rec)
            if len(self._records) > self.capacity:
                self._records.pop(0)

        # Notify active inspector SSE subscribers
        for listener in list(self._listeners):
            try:
                listener(rec)
            except Exception:
                pass

        if self._exporter is not None:
            try:
                self._exporter.export([rec])
            except Exception:
                pass
        return rec

    def export_otlp(self, limit: int = 100) -> dict[str, Any]:
        """Format captured trace records into OpenTelemetry OTLP ResourceSpans payload."""
        from radui.inspector.otlp import OTLPExporter
        exporter = self._exporter if isinstance(self._exporter, OTLPExporter) else OTLPExporter()
        records = self.get_records(limit=limit)
        return exporter.format_otlp_payload(records)

    def get_records(
        self,
        *,
        category: TraceCategory | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[TraceRecord]:
        with self._lock:
            result = list(self._records)

        if category is not None:
            result = [r for r in result if r.category == category]
        if session_id is not None:
            result = [r for r in result if r.session_id == session_id]
        return result[-limit:]

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._records)
            by_category: dict[str, int] = {}
            for r in self._records:
                by_category[r.category] = by_category.get(r.category, 0) + 1
        return {
            "total_records": total,
            "by_category": by_category,
        }

