from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CE_TAG_RE = re.compile(r"^[a-z][a-z0-9._-]*-[a-z0-9._-]*$")
_RESERVED_CE_TAGS = frozenset(
    {
        "annotation-xml",
        "color-profile",
        "font-face",
        "font-face-src",
        "font-face-uri",
        "font-face-format",
        "font-face-name",
        "missing-glyph",
    }
)
_SAFE_ATTR_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_SAFE_EVENT_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9:._-]{0,63}$")
_COMMAND_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


def validate_custom_element_tag(tag_name: str) -> str:
    low = tag_name.strip().lower()
    if low in _RESERVED_CE_TAGS or not _CE_TAG_RE.fullmatch(low):
        raise ValueError(f"Invalid Custom Element tag name: {tag_name!r}")
    return low


class WebComponentSpec(BaseModel):
    """Typed specification for a standards-compliant Custom Element / Shadow DOM component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tag_name: str
    shadow_mode: Literal["open", "closed", "none"] = "open"
    observed_attributes: tuple[str, ...] = ()
    events: tuple[str, ...] = ()
    event_commands: dict[str, str] = Field(default_factory=dict)
    styles: str = ""
    template_html: str = ""

    @field_validator("tag_name")
    @classmethod
    def _check_tag(cls, value: str) -> str:
        return validate_custom_element_tag(value)

    @field_validator("observed_attributes")
    @classmethod
    def _check_attrs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for a in values:
            if a.startswith("on") or not _SAFE_ATTR_RE.fullmatch(a):
                raise ValueError(f"Unsafe or invalid observed attribute: {a!r}")
        return values

    @field_validator("events")
    @classmethod
    def _check_events(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for ev in values:
            if not _SAFE_EVENT_RE.fullmatch(ev):
                raise ValueError(f"Invalid custom event name: {ev!r}")
        return values

    @field_validator("event_commands")
    @classmethod
    def _check_event_commands(cls, mapping: dict[str, str]) -> dict[str, str]:
        for ev, cmd in mapping.items():
            if not _SAFE_EVENT_RE.fullmatch(ev):
                raise ValueError(f"Invalid event name in event_commands: {ev!r}")
            if not _COMMAND_RE.fullmatch(cmd):
                raise ValueError(f"Invalid command ID in event_commands: {cmd!r}")
        return dict(mapping)
