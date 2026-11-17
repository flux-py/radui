from __future__ import annotations

import hashlib
import json
from typing import Any

from radui.components.nodes import Component
from radui.resumability.schema import (
    RESUMABILITY_SCHEMA_VERSION,
    ExecutionDescriptor,
    ResumableBoundarySnapshot,
    StateMigrationRegistry,
    _SECRET_KEY_RE,
)


def compute_auth_scope(*, session_id: str, user_id: str | None = None, tenant_id: str | None = None) -> str:
    """Compute a non-reversible authorization scope digest for resumable boundary validation."""
    raw = f"{session_id}:{user_id or ''}:{tenant_id or ''}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def serialize_boundary(snapshot: ResumableBoundarySnapshot) -> str:
    """Serialize a validated ResumableBoundarySnapshot to compact JSON."""
    return snapshot.model_dump_json()


def restore_boundary(
    raw_json: str,
    *,
    expected_route: str | None = None,
    expected_auth_scope: str | None = None,
    migrations: StateMigrationRegistry | None = None,
) -> ResumableBoundarySnapshot:
    """Validate, migrate if needed, and restore a ResumableBoundarySnapshot safely."""
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed resumable state JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Resumable state payload must be a JSON object")

    ver = str(payload.get("schema_version", ""))
    if ver != RESUMABILITY_SCHEMA_VERSION:
        if migrations is None:
            raise ValueError(f"Resumability schema mismatch: got {ver!r}, expected {RESUMABILITY_SCHEMA_VERSION!r}")
        payload = migrations.migrate(payload, RESUMABILITY_SCHEMA_VERSION)

    snapshot = ResumableBoundarySnapshot.model_validate(payload)
    if expected_route is not None and snapshot.route != expected_route:
        raise PermissionError(f"Route mismatch during restoration: {snapshot.route!r} != {expected_route!r}")
    if expected_auth_scope is not None and snapshot.auth_scope != expected_auth_scope:
        raise PermissionError("Authorization scope mismatch during restoration")
    return snapshot


def collect_resumable_boundaries(
    root: Component,
    *,
    route: str,
    auth_scope: str,
    state_context: Any | None = None,
    tracker: Any | None = None,
    identity: Any | None = None,
) -> list[ResumableBoundarySnapshot]:
    """Extract validated ResumableBoundarySnapshots for components marked resumable=True."""
    snapshots: list[ResumableBoundarySnapshot] = []
    idx = 0

    def walk(node: Component) -> None:
        nonlocal idx
        if getattr(node, "resumable", False):
            idx += 1
            bid = node.id or f"gx-res-{idx}"
            descriptors: list[ExecutionDescriptor] = []
            for b_i, binding in enumerate(getattr(node, "interactions", ()) or ()):
                for a_i, action in enumerate(binding.actions):
                    kind = "server_command" if action.op == "dispatch_command" else "local_interaction"
                    descriptors.append(
                        ExecutionDescriptor(
                            descriptor_id=f"{bid}-d{b_i}_{a_i}",
                            kind=kind,
                            event=binding.event,
                            action=action,
                            command=action.key if action.op == "dispatch_command" else None,
                            state_keys=(action.key,) if action.key and action.op in {"toggle", "set", "increment", "decrement"} else (),
                            activation=getattr(node, "resumable_activation", "lazy"),
                        )
                    )
            scoped: dict[str, Any] = {}
            binding_key = getattr(node, "binding_key", None)
            if binding_key and state_context is not None and not _SECRET_KEY_RE.search(str(binding_key)):
                try:
                    val = state_context.get(binding_key, scope=getattr(node, "binding_scope", "session"))
                    if isinstance(val, (int, float, bool, str)) or val is None:
                        scoped[str(binding_key)] = val
                except Exception:
                    pass

            deps: tuple[str, ...] = ()
            if tracker is not None and identity is not None:
                try:
                    deps = tuple(sorted(tracker.component_dependencies(identity, bid)))
                except Exception:
                    deps = ()

            snapshots.append(
                ResumableBoundarySnapshot(
                    boundary_id=bid,
                    component_kind=node.kind,
                    route=route,
                    auth_scope=auth_scope,
                    activation=getattr(node, "resumable_activation", "lazy"),
                    local_state=dict(getattr(node, "local_state", None) or {}),
                    scoped_state=scoped,
                    bind_local=dict(getattr(node, "bind_local", None) or {}),
                    descriptors=tuple(descriptors),
                    deps=deps,
                )
            )
        for child in getattr(node, "children", ()):
            walk(child)
        for attr in ("first", "second"):
            if hasattr(node, attr):
                val = getattr(node, attr)
                if isinstance(val, Component):
                    walk(val)

    walk(root)
    return snapshots
