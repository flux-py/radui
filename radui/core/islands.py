from __future__ import annotations

import copy
from html import escape
import json
import math
import re
from typing import Any, Callable, Literal, Mapping

from pydantic import Field, model_validator

from radui.components.nodes import Component

HydrationStrategy = Literal["fetch", "sse", "none"]
ActivationTrigger = Literal["eager", "visible", "interaction"]

VALID_HYDRATION_STRATEGIES: frozenset[str] = frozenset({"fetch", "sse", "none"})
VALID_ACTIVATION_TRIGGERS: frozenset[str] = frozenset({"eager", "visible", "interaction"})

_ISLAND_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_ISLAND_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")

_FORBIDDEN_STATE_KEYS: frozenset[str] = frozenset({
    "password",
    "passwd",
    "secret",
    "session_secret",
    "session_id",
    "gx_session_id",
    "csrf",
    "csrf_token",
    "gx_csrf_token",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "private_key",
    "__proto__",
    "__class__",
    "constructor",
    "prototype",
})


def validate_island_name(name: str) -> str:
    if not isinstance(name, str) or not _ISLAND_NAME_RE.fullmatch(name):
        raise ValueError(
            "island name must start with a letter and contain only letters, "
            "numbers, '_', '.', ':' or '-' (max 128 chars)"
        )
    return name


def validate_island_id(island_id: str) -> str:
    if not isinstance(island_id, str) or not _ISLAND_ID_RE.fullmatch(island_id):
        raise ValueError("island id must be 1-128 characters of [A-Za-z0-9_.:-]")
    return island_id


def validate_island_config(
    hydration: str,
    trigger: str,
) -> tuple[HydrationStrategy, ActivationTrigger]:
    """Validate hydration strategy and activation trigger as independent dimensions."""
    if hydration not in VALID_HYDRATION_STRATEGIES:
        raise ValueError(
            f"Invalid hydration strategy {hydration!r}; expected one of: fetch, sse, none"
        )
    if trigger not in VALID_ACTIVATION_TRIGGERS:
        raise ValueError(
            f"Invalid activation trigger {trigger!r}; expected one of: eager, visible, interaction"
        )
    if hydration == "none" and trigger != "eager":
        raise ValueError(
            f"Invalid island combination: hydration='none' cannot use deferred trigger={trigger!r}"
        )
    return hydration, trigger  # type: ignore[return-value]


def _validate_json_safe(value: Any, *, path: str = "root") -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Non-finite float {value!r} is not JSON-serializable at {path}")
        return value
    if isinstance(value, (list, tuple)):
        return [_validate_json_safe(item, path=f"{path}[]") for item in value]
    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError(f"Island payload keys must be strings (got {type(k).__name__} at {path})")
            lowered = k.lower()
            if lowered in _FORBIDDEN_STATE_KEYS or k.startswith("__"):
                raise ValueError(f"Forbidden or sensitive key {k!r} in island payload")
            clean[k] = _validate_json_safe(v, path=f"{path}.{k}")
        return clean
    raise TypeError(
        f"Unsupported non-JSON-serializable type {type(value).__name__!r} at {path} in island payload"
    )


def sanitize_island_state(data: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate, deep-copy, and strip/reject sensitive keys from island state/props."""
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise TypeError("Island state/props must be a mapping")
    cleaned = _validate_json_safe(data)
    return copy.deepcopy(cleaned)


class Island(Component):
    """Independently identifiable and hydratable UI island boundary."""

    kind: Literal["island"] = "island"
    name: str
    hydration: HydrationStrategy = "fetch"
    trigger: ActivationTrigger = "eager"
    initial_state: dict[str, Any] = Field(default_factory=dict)
    props: dict[str, Any] = Field(default_factory=dict)
    children: tuple[Component, ...] = ()
    fallback: Component | None = None

    @model_validator(mode="after")
    def _validate_island(self) -> Island:
        validate_island_name(self.name)
        validate_island_config(self.hydration, self.trigger)
        effective_id = self.id or f"island-{self.name}"
        validate_island_id(effective_id)
        object.__setattr__(self, "id", effective_id)
        object.__setattr__(self, "initial_state", sanitize_island_state(self.initial_state))
        object.__setattr__(self, "props", sanitize_island_state(self.props))
        return self


def island(
    name: str,
    *children: Component,
    id: str | None = None,
    hydration: HydrationStrategy = "fetch",
    trigger: ActivationTrigger = "eager",
    initial_state: Mapping[str, Any] | None = None,
    props: Mapping[str, Any] | None = None,
    fallback: Component | None = None,
    **kwargs: Any,
) -> Island:
    """Create a Hybrid Island boundary around server-rendered child components."""
    return Island(
        id=id or f"island-{name}",
        name=name,
        hydration=hydration,
        trigger=trigger,
        initial_state=sanitize_island_state(initial_state),
        props=sanitize_island_state(props),
        children=tuple(children),
        fallback=fallback,
        **kwargs,
    )


def render_island(
    component: Island,
    registry: Any,
    state_context: object | None = None,
    csrf_token: str | None = None,
) -> str:
    """Render an Island boundary preserving SSR initial HTML and safe metadata."""
    island_id = component.id or f"island-{component.name}"
    safe_id = escape(island_id, quote=True)
    safe_name = escape(component.name, quote=True)
    safe_hydration = escape(component.hydration, quote=True)
    safe_trigger = escape(component.trigger, quote=True)

    attrs = [
        'class="gx-island"',
        f'id="{safe_id}"',
        f'data-gx-id="{safe_id}"',
        f'data-gx-island="{safe_name}"',
        f'data-gx-hydration="{safe_hydration}"',
        f'data-gx-trigger="{safe_trigger}"',
        'data-gx-island-status="ssr"',
    ]

    if component.hydration != "none":
        if component.initial_state:
            raw_state = json.dumps(component.initial_state, separators=(",", ":"), ensure_ascii=False)
            raw_state = raw_state.replace("</", "<\\/")
            attrs.append(f'data-gx-state="{escape(raw_state, quote=True)}"')
        if component.props:
            raw_props = json.dumps(component.props, separators=(",", ":"), ensure_ascii=False)
            raw_props = raw_props.replace("</", "<\\/")
            attrs.append(f'data-gx-props="{escape(raw_props, quote=True)}"')

    def _render_children() -> str:
        return "".join(
            registry.render(child, state_context, csrf_token)
            for child in component.children
        )

    if state_context is not None and hasattr(state_context, "track_component"):
        with state_context.track_component(island_id):
            inner_html = _render_children()
    else:
        inner_html = _render_children()

    return f'<div {" ".join(attrs)}>{inner_html}</div>'
