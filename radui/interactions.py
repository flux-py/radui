from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
_FORBIDDEN_STATE_KEYS: frozenset[str] = frozenset({"__proto__", "constructor", "prototype"})
_CLASS_RE = re.compile(r"^[A-Za-z_-][A-Za-z0-9_-]{0,63}$")
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_COMMAND_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")

ALLOWED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "click",
        "dblclick",
        "mouseenter",
        "mouseleave",
        "pointerenter",
        "pointerleave",
        "focus",
        "blur",
        "input",
        "change",
        "keydown",
        "keyup",
        "submit",
        "dragstart",
        "dragover",
        "drop",
    }
)

EventType = Literal[
    "click",
    "dblclick",
    "mouseenter",
    "mouseleave",
    "pointerenter",
    "pointerleave",
    "focus",
    "blur",
    "input",
    "change",
    "keydown",
    "keyup",
    "submit",
    "dragstart",
    "dragover",
    "drop",
]

ActionOp = Literal[
    "toggle",
    "set",
    "increment",
    "decrement",
    "show",
    "hide",
    "open",
    "close",
    "enable",
    "disable",
    "add_class",
    "remove_class",
    "toggle_class",
    "set_text",
    "set_attr",
    "remove_attr",
    "announce",
    "focus",
    "dispatch_command",
]

ALLOWED_SAFE_ATTRS: frozenset[str] = frozenset(
    {
        "hidden",
        "disabled",
        "title",
        "placeholder",
        "tabindex",
        "role",
        "aria-label",
        "aria-labelledby",
        "aria-describedby",
        "aria-expanded",
        "aria-selected",
        "aria-pressed",
        "aria-hidden",
        "aria-live",
        "aria-busy",
        "aria-controls",
        "aria-current",
        "data-gx-state",
    }
)

LocalScalar = int | float | bool | str | None


def _is_safe_attr_name(name: str) -> bool:
    lowered = name.strip().lower()
    if lowered.startswith("on"):
        return False
    if lowered in ALLOWED_SAFE_ATTRS:
        return True
    if lowered.startswith(("aria-", "data-gx-state-")):
        return bool(_KEY_RE.fullmatch(lowered))
    return False


class InteractionAction(BaseModel):
    """Strictly validated, serializable declarative client-side action (zero arbitrary JS)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    op: ActionOp
    key: str | None = Field(default=None, min_length=1, max_length=128)
    value: LocalScalar = None
    target: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("target")
    @classmethod
    def validate_target(cls, v: str | None) -> str | None:
        if v is not None and not _ID_RE.fullmatch(v):
            raise ValueError("target must be a valid component id")
        return v

    @field_validator("key")
    @classmethod
    def validate_key(cls, v: str | None) -> str | None:
        if v is not None and not _COMMAND_RE.fullmatch(v):
            raise ValueError("key contains invalid characters")
        return v

    def model_post_init(self, __context: Any) -> None:
        if self.op in {"toggle", "set", "increment", "decrement"} and not self.key:
            raise ValueError(f"Action op {self.op!r} requires a state key")
        if self.op in {"add_class", "remove_class", "toggle_class"}:
            if not self.key or not _CLASS_RE.fullmatch(self.key):
                raise ValueError(f"Action op {self.op!r} requires a valid CSS class name in key")
        if self.op in {"set_attr", "remove_attr"}:
            if not self.key or not _is_safe_attr_name(self.key):
                raise ValueError(f"Attribute {self.key!r} is not allowlisted for {self.op!r}")
        if self.op == "dispatch_command":
            if not self.key or not _COMMAND_RE.fullmatch(self.key):
                raise ValueError("dispatch_command requires a valid command id in key")
        if self.op == "focus" and not self.target:
            raise ValueError("focus action requires a target component id")
        if self.op == "announce" and (self.value is None or str(self.value).strip() == ""):
            raise ValueError("announce action requires a non-empty message value")

    def to_wire(self) -> dict[str, Any]:
        out: dict[str, Any] = {"op": self.op}
        if self.key is not None:
            out["key"] = self.key
        if self.value is not None:
            out["value"] = self.value
        if self.target is not None:
            out["target"] = self.target
        return out


class InteractionBinding(BaseModel):
    """Declarative event-to-action binding attached to a RadUI Component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event: EventType
    actions: tuple[InteractionAction, ...] = Field(min_length=1, max_length=16)
    key_filter: str | None = Field(default=None, min_length=1, max_length=32)
    prevent_default: bool = False
    stop_propagation: bool = False

    def to_wire(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "event": self.event,
            "actions": [a.to_wire() for a in self.actions],
        }
        if self.key_filter is not None:
            out["key_filter"] = self.key_filter
        if self.prevent_default:
            out["prevent_default"] = True
        if self.stop_propagation:
            out["stop_propagation"] = True
        return out


def validate_local_state(state: dict[str, LocalScalar] | None) -> dict[str, LocalScalar] | None:
    if state is None:
        return None
    if len(state) > 32:
        raise ValueError("local_state may define at most 32 keys per component")
    for k, v in state.items():
        if not isinstance(k, str) or k in _FORBIDDEN_STATE_KEYS or not _KEY_RE.fullmatch(k):
            raise ValueError(f"Invalid local_state key: {k!r}")
        if v is not None and not isinstance(v, (int, float, bool, str)):
            raise ValueError(f"local_state value for {k!r} must be a scalar primitive")
    return dict(state)


ALLOWED_BIND_TARGETS: frozenset[str] = frozenset(
    {"text", "visible", "hidden", "disabled", "open", "pressed", "expanded"}
)


def validate_bind_local(bindings: dict[str, str] | None) -> dict[str, str] | None:
    if bindings is None:
        return None
    if len(bindings) > 16:
        raise ValueError("bind_local may define at most 16 bindings per component")
    for prop, key in bindings.items():
        if prop not in ALLOWED_BIND_TARGETS:
            raise ValueError(f"Unsupported bind_local target property: {prop!r}")
        if not isinstance(key, str) or key in _FORBIDDEN_STATE_KEYS or not _KEY_RE.fullmatch(key):
            raise ValueError(f"Invalid bind_local state key: {key!r}")
    return dict(bindings)


def on(
    event: EventType,
    *actions: InteractionAction,
    key: str | None = None,
    prevent_default: bool = False,
    stop_propagation: bool = False,
) -> InteractionBinding:
    """Create a declarative InteractionBinding for a RadUI component."""
    return InteractionBinding(
        event=event,
        actions=tuple(actions),
        key_filter=key,
        prevent_default=prevent_default,
        stop_propagation=stop_propagation,
    )


class _ActionNamespace:
    """Ergonomic factory namespace for strictly validated declarative actions."""

    @staticmethod
    def toggle(key: str = "open", *, target: str | None = None) -> InteractionAction:
        return InteractionAction(op="toggle", key=key, target=target)

    @staticmethod
    def set(key: str, value: LocalScalar, *, target: str | None = None) -> InteractionAction:
        return InteractionAction(op="set", key=key, value=value, target=target)

    @staticmethod
    def increment(key: str = "count", by: int | float = 1, *, target: str | None = None) -> InteractionAction:
        return InteractionAction(op="increment", key=key, value=by, target=target)

    @staticmethod
    def decrement(key: str = "count", by: int | float = 1, *, target: str | None = None) -> InteractionAction:
        return InteractionAction(op="decrement", key=key, value=by, target=target)

    @staticmethod
    def show(*, target: str | None = None) -> InteractionAction:
        return InteractionAction(op="show", target=target)

    @staticmethod
    def hide(*, target: str | None = None) -> InteractionAction:
        return InteractionAction(op="hide", target=target)

    @staticmethod
    def open(*, target: str | None = None) -> InteractionAction:
        return InteractionAction(op="open", target=target)

    @staticmethod
    def close(*, target: str | None = None) -> InteractionAction:
        return InteractionAction(op="close", target=target)

    @staticmethod
    def enable(*, target: str | None = None) -> InteractionAction:
        return InteractionAction(op="enable", target=target)

    @staticmethod
    def disable(*, target: str | None = None) -> InteractionAction:
        return InteractionAction(op="disable", target=target)

    @staticmethod
    def add_class(class_name: str, *, target: str | None = None) -> InteractionAction:
        return InteractionAction(op="add_class", key=class_name, target=target)

    @staticmethod
    def remove_class(class_name: str, *, target: str | None = None) -> InteractionAction:
        return InteractionAction(op="remove_class", key=class_name, target=target)

    @staticmethod
    def toggle_class(class_name: str, *, target: str | None = None) -> InteractionAction:
        return InteractionAction(op="toggle_class", key=class_name, target=target)

    @staticmethod
    def set_text(text: str, *, target: str | None = None) -> InteractionAction:
        return InteractionAction(op="set_text", value=text, target=target)

    @staticmethod
    def set_attr(attr: str, value: LocalScalar, *, target: str | None = None) -> InteractionAction:
        return InteractionAction(op="set_attr", key=attr, value=value, target=target)

    @staticmethod
    def remove_attr(attr: str, *, target: str | None = None) -> InteractionAction:
        return InteractionAction(op="remove_attr", key=attr, target=target)

    @staticmethod
    def announce(message: str) -> InteractionAction:
        return InteractionAction(op="announce", value=message)

    @staticmethod
    def focus(target: str) -> InteractionAction:
        return InteractionAction(op="focus", target=target)

    @staticmethod
    def command(command_id: str) -> InteractionAction:
        return InteractionAction(op="dispatch_command", key=command_id)

    @staticmethod
    def dispatch_command(command_id: str) -> InteractionAction:
        return InteractionAction(op="dispatch_command", key=command_id)


act = _ActionNamespace()
