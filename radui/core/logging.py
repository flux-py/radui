from __future__ import annotations

import json
import logging
from typing import Any

from radui.core.config import redact_secrets, scrub_secret_strings


class RedactingJsonFormatter(logging.Formatter):
    """Structured JSON log formatter that automatically masks sensitive fields and messages."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            payload: dict[str, Any] = {
                "level": record.levelname,
                "logger": record.name,
                "message": scrub_secret_strings(record.getMessage()),
            }
            extra_fields = getattr(record, "radui_fields", None)
            if isinstance(extra_fields, dict):
                payload["fields"] = redact_secrets(extra_fields)
            if record.exc_info:
                payload["exception"] = scrub_secret_strings(self.formatException(record.exc_info))
            return json.dumps(payload, separators=(",", ":"), default=lambda o: scrub_secret_strings(str(o)))
        except Exception:
            return json.dumps({
                "level": record.levelname,
                "logger": record.name,
                "message": "Log formatting failed (output redacted for safety)",
            })


def log_structured(
    logger: logging.Logger,
    level: int,
    event: str,
    **fields: Any,
) -> None:
    """Emit a structured log event with automatic secret redaction."""
    if not logger.isEnabledFor(level):
        return
    logger.log(level, event, extra={"radui_fields": redact_secrets(fields)})


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure the radui logger with RedactingJsonFormatter."""
    logger = logging.getLogger("radui")
    numeric = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric)
    if not any(isinstance(getattr(h, "formatter", None), RedactingJsonFormatter) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(RedactingJsonFormatter())
        logger.addHandler(handler)
    return logger
