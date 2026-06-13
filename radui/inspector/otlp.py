from __future__ import annotations

import json
import logging
import time
import urllib.request
import uuid
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from radui.inspector.collector import TraceRecord

_LOGGER = logging.getLogger("radui.inspector.otlp")


class OTLPExporter:
    """Exports RADUI runtime telemetry traces to OpenTelemetry OTLP/HTTP endpoints."""

    def __init__(
        self,
        endpoint: str | None = None,
        service_name: str = "RADUI-app",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.service_name = service_name
        self.headers = headers or {"Content-Type": "application/json"}
        self._exported_spans: list[dict[str, Any]] = []

    def span_from_record(self, record: TraceRecord) -> dict[str, Any]:
        """Convert a RADUI TraceRecord into an OpenTelemetry Span structure."""
        trace_seed = uuid.uuid5(uuid.NAMESPACE_DNS, f"{record.session_id or 'anon'}-{record.id}").hex
        span_seed = uuid.uuid5(uuid.NAMESPACE_DNS, record.id).hex[:16]

        now_ns = int(time.time() * 1e9)
        dur_ns = int((record.duration_ms or 1.0) * 1e6)
        start_ns = now_ns - dur_ns
        end_ns = now_ns

        kind = 1
        if record.category == "command":
            kind = 2  # SERVER
        elif record.category == "event":
            kind = 4  # PRODUCER
        elif record.category == "job":
            kind = 5  # CONSUMER

        attrs = [
            {"key": "radui.category", "value": {"stringValue": record.category}},
            {"key": "radui.trace_id", "value": {"stringValue": record.id}},
        ]
        if record.session_id:
            attrs.append({"key": "radui.session_id", "value": {"stringValue": record.session_id}})
        if record.view_id:
            attrs.append({"key": "radui.view_id", "value": {"stringValue": record.view_id}})
        if record.duration_ms is not None:
            attrs.append({"key": "radui.duration_ms", "value": {"doubleValue": record.duration_ms}})

        for k, v in record.details.items():
            str_v = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
            attrs.append({"key": f"radui.details.{k}", "value": {"stringValue": str_v}})

        status_code = 1  # Ok
        status_msg = ""
        if record.category == "error" or "error" in record.details:
            status_code = 2  # Error
            status_msg = str(record.details.get("error", "Error"))

        return {
            "traceId": trace_seed,
            "spanId": span_seed,
            "name": f"gx.{record.category}.{record.name}",
            "kind": kind,
            "startTimeUnixNano": str(start_ns),
            "endTimeUnixNano": str(end_ns),
            "attributes": attrs,
            "status": {
                "code": status_code,
                "message": status_msg,
            },
        }

    def format_otlp_payload(self, records: list[TraceRecord]) -> dict[str, Any]:
        """Wrap trace records into standard OpenTelemetry ResourceSpans format."""
        spans = [self.span_from_record(r) for r in records]
        return {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": self.service_name}},
                            {"key": "telemetry.sdk.language", "value": {"stringValue": "python"}},
                            {"key": "telemetry.sdk.name", "value": {"stringValue": "radui"}},
                            {"key": "telemetry.sdk.version", "value": {"stringValue": "0.9.0"}},
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {
                                "name": "radui.runtime.telemetry",
                                "version": "0.9.0",
                            },
                            "spans": spans,
                        }
                    ],
                }
            ]
        }

    def export(self, records: list[TraceRecord]) -> bool:
        """Send traces to OTLP endpoint or record in memory."""
        if not records:
            return False
        payload = self.format_otlp_payload(records)
        self._exported_spans.extend(
            payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
        )
        if not self.endpoint:
            return True
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=body,
            headers=self.headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                return resp.status in (200, 202)
        except Exception as exc:
            _LOGGER.debug("OTLP export failed to %s: %s", self.endpoint, exc)
            return False
