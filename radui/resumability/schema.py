from __future__ import annotations

import re
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from radui.interactions import (
    EventType,
    InteractionAction,
    LocalScalar,
    validate_bind_local,
    validate_local_state,
)

RESUMABILITY_SCHEMA_VERSION = "1.0"

_SECRET_KEY_RE = re.compile(r"(password|secret|token|api_?key|private_?key|credential|cookie|session_key)", re.I)
_SAFE_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_FORBIDDEN_KEYS = frozenset({"__proto__", "constructor", "prototype"})

ActivationPolicy = Literal["lazy", "visible", "eager", "interaction"]
DescriptorKind = Literal[
    "local_interaction",
    "server_command",
    "state_binding",
    "component_action",
    "island_activation",
]


def _assert_safe_state_dict(mapping: dict[str, Any], label: str) -> dict[str, LocalScalar]:
    validated = validate_local_state(mapping) or {}
    for key in validated:
        if key in _FORBIDDEN_KEYS or _SECRET_KEY_RE.search(key):
            raise ValueError(f"Forbidden or sensitive key in {label}: {key!r}")
    return validated


class ExecutionDescriptor(BaseModel):
    """Typed, versioned, JSON-safe execution descriptor (zero closures or eval)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    descriptor_id: str = Field(min_length=1, max_length=128)
    kind: DescriptorKind
    event: EventType | None = None
    action: InteractionAction | None = None
    command: str | None = Field(default=None, min_length=1, max_length=128)
    state_keys: tuple[str, ...] = ()
    activation: ActivationPolicy = "lazy"
    deps: tuple[str, ...] = ()

    @field_validator("descriptor_id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not _SAFE_KEY_RE.fullmatch(value):
            raise ValueError(f"Invalid descriptor_id: {value!r}")
        return value

    @field_validator("state_keys", "deps")
    @classmethod
    def _validate_keys(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for k in values:
            if k in _FORBIDDEN_KEYS or _SECRET_KEY_RE.search(k):
                raise ValueError(f"Sensitive or forbidden key in descriptor: {k!r}")
        return values


class ResumableBoundarySnapshot(BaseModel):
    """Serializable state and descriptor snapshot for a resumable component boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = RESUMABILITY_SCHEMA_VERSION
    boundary_id: str = Field(min_length=1, max_length=128)
    component_kind: str = Field(min_length=1, max_length=64)
    route: str = Field(min_length=1, max_length=256)
    auth_scope: str = Field(min_length=8, max_length=128)
    activation: ActivationPolicy = "lazy"
    local_state: dict[str, LocalScalar] = Field(default_factory=dict)
    scoped_state: dict[str, LocalScalar] = Field(default_factory=dict)
    bind_local: dict[str, str] = Field(default_factory=dict)
    descriptors: tuple[ExecutionDescriptor, ...] = ()
    deps: tuple[str, ...] = ()
    island_hydrated: bool = False

    @field_validator("boundary_id")
    @classmethod
    def _validate_boundary_id(cls, value: str) -> str:
        if not _SAFE_KEY_RE.fullmatch(value):
            raise ValueError(f"Invalid boundary_id: {value!r}")
        return value

    @field_validator("local_state", "scoped_state")
    @classmethod
    def _validate_states(cls, value: dict[str, Any]) -> dict[str, LocalScalar]:
        return _assert_safe_state_dict(value, "resumable_state")

    @field_validator("bind_local")
    @classmethod
    def _validate_binds(cls, value: dict[str, str]) -> dict[str, str]:
        return validate_bind_local(value) or {}


class StateMigrationRegistry:
    """Explicit schema version migration registry for resumable boundary payloads."""

    def __init__(self) -> None:
        self._migrations: dict[tuple[str, str], Callable[[dict[str, Any]], dict[str, Any]]] = {}

    def register(
        self,
        from_version: str,
        to_version: str,
        migrator: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        self._migrations[(from_version, to_version)] = migrator

    def migrate(self, payload: dict[str, Any], target_version: str = RESUMABILITY_SCHEMA_VERSION) -> dict[str, Any]:
        cur = dict(payload)
        ver = str(cur.get("schema_version", ""))
        if ver == target_version:
            return cur
        visited: set[str] = {ver}
        while ver != target_version:
            nxt = next(
                ((to_v, fn) for (from_v, to_v), fn in self._migrations.items() if from_v == ver and to_v not in visited),
                None,
            )
            if nxt is None:
                raise ValueError(f"Unsupported resumability schema version {ver!r} (expected {target_version!r})")
            to_v, fn = nxt
            cur = dict(fn(cur))
            cur["schema_version"] = to_v
            ver = to_v
            visited.add(ver)
        return cur
