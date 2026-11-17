from __future__ import annotations

import copy
from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Hashable, Iterator, TYPE_CHECKING

from radui.state.dependencies import ContextIdentity, DependencyTracker
from radui.state.backend import StateBackend, InMemoryStateBackend
from radui.state.middleware import StateMiddleware

if TYPE_CHECKING:
    from radui.state.refs import StateRef, ComputedRef


@dataclass(frozen=True)
class Invalidation:
    """Components that should be reconsidered after a state change."""

    context: ContextIdentity
    component_ids: tuple[str, ...]


@dataclass(frozen=True)
class StateChange:
    """Result of writing a state reference."""

    key: str
    scope: str
    changed: bool
    revision: int
    previous: Any
    value: Any
    invalidations: tuple[Invalidation, ...]


@dataclass
class _Collector:
    context: ContextIdentity
    component_id: str
    dependencies: set[Hashable]


@dataclass
class RenderContext:
    """ContextVar-bound render/effect tracking scope layered over StateContext."""

    state_context: StateContext
    component_id: str | None = None
    tracked_keys: set[Hashable] = field(default_factory=set)
    parent: RenderContext | None = None


class BatchContext:
    """Context object representing an active batched mutation session."""

    def __init__(self, context: StateContext) -> None:
        self.context = context
        self.changes: list[StateChange] = []
        self.affected: dict[ContextIdentity, set[str]] = defaultdict(set)
        self.consolidated_invalidations: tuple[Invalidation, ...] = ()
        self.pending_signal_updates: dict[tuple[int, ContextIdentity], tuple[Any, ContextIdentity, Any, Any]] = {}


class TransactionContext:
    """Context object representing an active transactional state session."""

    def __init__(self, context: StateContext) -> None:
        self.context = context
        self.snapshots: dict[Hashable, tuple[bool, Any, int]] = {}
        self.changes: list[StateChange] = []
        self.pending_signal_updates: dict[tuple[int, ContextIdentity], tuple[Any, ContextIdentity, Any, Any]] = {}


_ACTIVE_CONTEXT: ContextVar[StateContext | None] = ContextVar(
    "RADUI_active_state_context", default=None
)
_ACTIVE_COLLECTORS: ContextVar[tuple[_Collector, ...]] = ContextVar(
    "RADUI_active_dependency_collectors", default=()
)
_ACTIVE_CHANGE_COLLECTORS: ContextVar[tuple[tuple[ContextIdentity, list[StateChange]], ...]] = ContextVar(
    "RADUI_active_change_collectors", default=()
)
_ACTIVE_COMPUTATIONS: ContextVar[tuple[tuple[ContextIdentity, str], ...]] = ContextVar(
    "RADUI_active_computations", default=()
)
_ACTIVE_BATCH: ContextVar[BatchContext | None] = ContextVar(
    "RADUI_active_batch", default=None
)
_ACTIVE_TRANSACTIONS: ContextVar[tuple[TransactionContext, ...]] = ContextVar(
    "RADUI_active_transactions", default=()
)
_ACTIVE_RENDER_CONTEXT: ContextVar[Any | None] = ContextVar(
    "RADUI_active_render_context", default=None
)


def get_active_context() -> StateContext | None:
    return _ACTIVE_CONTEXT.get()


class StateRuntime:
    """In-memory typed state runtime with scope isolation, dependency tracking and computed values.

    This implementation coordinates reactive states, computed derivations with cycle detection,
    batched invalidations, transactional rollback, and pluggable state middleware.
    """

    def __init__(
        self,
        app_id: str,
        backend: StateBackend | None = None,
        middleware: list[StateMiddleware] | None = None,
    ) -> None:
        if not app_id:
            raise ValueError("app_id cannot be empty")
        self.app_id = app_id
        self.backend = backend if backend is not None else InMemoryStateBackend()
        self._shared_backend = not isinstance(self.backend, InMemoryStateBackend)
        self.dependencies = DependencyTracker()
        self._lock = RLock()
        self._values: dict[Hashable, Any] = {}
        self._revisions: dict[Hashable, int] = {}
        self._declarations: dict[tuple[str, str], tuple[str, Any]] = {}
        self._computed_cache: dict[Hashable, tuple[Any, dict[Hashable, int]]] = {}
        self._middleware: list[StateMiddleware] = list(middleware or [])

    def add_middleware(self, mw: StateMiddleware) -> None:
        """Register a state middleware."""
        self._middleware.append(mw)

    def context(
        self,
        *,
        session_id: str,
        user_id: str | None = None,
        view_id: str = "default",
        tenant_id: str | None = None,
    ) -> StateContext:
        if not session_id:
            raise ValueError("session_id cannot be empty")
        if not view_id:
            raise ValueError("view_id cannot be empty")
        return StateContext(
            runtime=self,
            identity=ContextIdentity(
                app_id=self.app_id,
                session_id=session_id,
                user_id=user_id,
                view_id=view_id,
                tenant_id=tenant_id,
            ),
        )

    def _register(self, ref: StateRef[Any]) -> None:
        declaration_key = (ref.scope, ref.key)
        with self._lock:
            existing = self._declarations.get(declaration_key)
            signature = (ref.type_key, getattr(ref, "_default", None))
            if existing is None:
                self._declarations[declaration_key] = copy.deepcopy(signature)
                return
            existing_type, existing_default = existing
            if existing_type != ref.type_key or not _safe_equal(existing_default, getattr(ref, "_default", None)):
                raise TypeError(
                    f"conflicting declarations for state {ref.scope}:{ref.key}; "
                    "all references to the same state key must use the same type and default"
                )

    def _peek(self, ref: StateRef[Any], context: StateContext) -> Any:
        """Read a StateRef or Signal without registering reactive dependencies."""
        if hasattr(ref, "_fn") and callable(getattr(ref, "_fn")):
            return self._read(ref, context)
        self._register(ref)
        state_key = ref._state_key(context)
        owner = state_key[1]
        owner_str = owner if isinstance(owner, str) else f"{owner[0]}:{owner[1]}"
        with self._lock:
            if self._shared_backend or state_key not in self._values:
                stored = self.backend.get(ref.scope, owner_str, ref.key)
                if stored is not None:
                    try:
                        self._values[state_key] = ref.validate(stored)
                        self._revisions.setdefault(state_key, 1)
                    except Exception:
                        self._values[state_key] = ref.default
                        self._revisions.setdefault(state_key, 0)
                elif state_key not in self._values:
                    self._values[state_key] = ref.default
                    self._revisions[state_key] = 0
            return copy.deepcopy(self._values[state_key])

    def _read(self, ref: StateRef[Any], context: StateContext) -> Any:
        from radui.state.refs import CyclicDependencyError

        # Check if ref is a ComputedRef
        if hasattr(ref, "_fn") and callable(getattr(ref, "_fn")):
            state_key = ref._state_key(context)
            computation_id = (context.identity, ref.key)
            current_stack = _ACTIVE_COMPUTATIONS.get()

            if computation_id in current_stack:
                chain = [item[1] for item in current_stack] + [ref.key]
                raise CyclicDependencyError(f"Cyclic dependency detected: {' -> '.join(chain)}")

            for mw in self._middleware:
                mw.before_read(ref, context)

            with self._lock:
                cached_entry = self._computed_cache.get(state_key)

            if cached_entry is not None:
                cached_val, dep_revs = cached_entry
                is_valid = True
                with self._lock:
                    for dep_key, expected_rev in dep_revs.items():
                        if self._revisions.get(dep_key, 0) != expected_rev:
                            is_valid = False
                            break
                if is_valid:
                    collectors = _ACTIVE_COLLECTORS.get()
                    if collectors and collectors[-1].context == context.identity:
                        collectors[-1].dependencies.add(state_key)
                    val = copy.deepcopy(cached_val)
                    for mw in reversed(self._middleware):
                        val = mw.after_read(ref, context, val)
                    return val

            # Cache miss or stale dependency: compute value
            comp_collector = _Collector(context.identity, f"__computed__{ref.key}", set())
            collector_token = _ACTIVE_COLLECTORS.set(_ACTIVE_COLLECTORS.get() + (comp_collector,))
            stack_token = _ACTIVE_COMPUTATIONS.set(current_stack + (computation_id,))
            try:
                with context.activate():
                    raw_val = ref._fn()
            finally:
                _ACTIVE_COMPUTATIONS.reset(stack_token)
                _ACTIVE_COLLECTORS.reset(collector_token)

            validated_val = ref.validate(raw_val)
            with self._lock:
                upstream_revs = {
                    dep_key: self._revisions.get(dep_key, 0)
                    for dep_key in comp_collector.dependencies
                }
                self._computed_cache[state_key] = (validated_val, upstream_revs)
                self._revisions[state_key] = self._revisions.get(state_key, 0) + 1
                self.dependencies.register_computed_dependencies(state_key, comp_collector.dependencies)

            collectors = _ACTIVE_COLLECTORS.get()
            if collectors and collectors[-1].context == context.identity:
                collectors[-1].dependencies.add(state_key)

            final_val = copy.deepcopy(validated_val)
            for mw in reversed(self._middleware):
                final_val = mw.after_read(ref, context, final_val)
            return final_val

        # Standard StateRef read
        for mw in self._middleware:
            mw.before_read(ref, context)

        self._register(ref)
        state_key = ref._state_key(context)
        owner = state_key[1]
        owner_str = owner if isinstance(owner, str) else f"{owner[0]}:{owner[1]}"
        with self._lock:
            if self._shared_backend or state_key not in self._values:
                stored = self.backend.get(ref.scope, owner_str, ref.key)
                if stored is not None:
                    try:
                        self._values[state_key] = ref.validate(stored)
                        self._revisions.setdefault(state_key, 1)
                    except Exception:
                        self._values[state_key] = ref.default
                        self._revisions.setdefault(state_key, 0)
                elif state_key not in self._values:
                    self._values[state_key] = ref.default
                    self._revisions[state_key] = 0
            value = copy.deepcopy(self._values[state_key])

        collectors = _ACTIVE_COLLECTORS.get()
        if collectors and collectors[-1].context == context.identity:
            collectors[-1].dependencies.add(state_key)

        rctx = _ACTIVE_RENDER_CONTEXT.get()
        if rctx is not None and rctx.state_context.identity == context.identity:
            rctx.tracked_keys.add(state_key)

        for mw in reversed(self._middleware):
            value = mw.after_read(ref, context, value)
        return value

    def _update_with(
        self,
        ref: StateRef[Any],
        context: StateContext,
        updater: Any,
    ) -> StateChange:
        """Atomically read, transform, and write under lock, then notify outside lock."""
        with self._lock:
            current = self._peek(ref, context)
            updated = updater(current)
            change, notifications = self._write_internal(ref, context, updated, defer_notify=True)
        if change.changed:
            collectors = _ACTIVE_CHANGE_COLLECTORS.get()
            if collectors and collectors[-1][0] == context.identity:
                collectors[-1][1].append(change)
        for notify_fn in notifications:
            notify_fn()
        return change

    def _write(self, ref: StateRef[Any], context: StateContext, value: Any) -> StateChange:
        change, notifications = self._write_internal(ref, context, value, defer_notify=False)
        for notify_fn in notifications:
            notify_fn()
        return change

    def _write_internal(
        self,
        ref: StateRef[Any],
        context: StateContext,
        value: Any,
        *,
        defer_notify: bool = False,
    ) -> tuple[StateChange, list[Any]]:
        if hasattr(ref, "_fn") and callable(getattr(ref, "_fn")):
            raise TypeError(f"Computed state {ref.key!r} is read-only and cannot be written to")

        self._register(ref)
        state_key = ref._state_key(context)
        owner = state_key[1]
        owner_str = owner if isinstance(owner, str) else f"{owner[0]}:{owner[1]}"

        with self._lock:
            if self._shared_backend or state_key not in self._values:
                stored = self.backend.get(ref.scope, owner_str, ref.key)
                if stored is not None:
                    self._values[state_key] = ref.validate(stored)
                elif state_key not in self._values:
                    self._values[state_key] = ref.default
                self._revisions.setdefault(state_key, 0)
            previous = copy.deepcopy(self._values[state_key])

        for mw in self._middleware:
            value = mw.before_write(ref, context, value, previous)

        validated = ref.validate(value)

        # Transaction tracking snapshot
        active_txs = _ACTIVE_TRANSACTIONS.get()
        if active_txs:
            curr_tx = active_txs[-1]
            if state_key not in curr_tx.snapshots:
                curr_tx.snapshots[state_key] = (
                    state_key in self._values,
                    copy.deepcopy(previous),
                    self._revisions.get(state_key, 0),
                )

        with self._lock:
            if _safe_equal(previous, validated):
                change = StateChange(
                    key=ref.key,
                    scope=ref.scope,
                    changed=False,
                    revision=self._revisions[state_key],
                    previous=previous,
                    value=copy.deepcopy(previous),
                    invalidations=(),
                )
                for mw in reversed(self._middleware):
                    mw.after_write(ref, context, change)
                return change, []

            self._values[state_key] = copy.deepcopy(validated)
            revision = self._revisions.get(state_key, 0) + 1
            self._revisions[state_key] = revision
            self.backend.set(ref.scope, owner_str, ref.key, copy.deepcopy(validated))

            # Invalidate cached computed values that depend on this state key
            transitive_comp = self.dependencies.get_transitive_computed_dependents(state_key)
            for comp_key in transitive_comp:
                self._computed_cache.pop(comp_key, None)

            affected = self.dependencies.dependents(state_key)
            path_keys = self.dependencies.path_keys_for(state_key)
            if path_keys:
                from radui.state.signals import _MISSING, resolve_path
                for pkey in path_keys:
                    _, path_tuple = pkey
                    prev_sub = resolve_path(previous, path_tuple, default=_MISSING)
                    curr_sub = resolve_path(validated, path_tuple, default=_MISSING)
                    if not _safe_equal(prev_sub, curr_sub):
                        for p_ctx, p_cids in self.dependencies.dependents(pkey).items():
                            existing_cids = set(affected.get(p_ctx, ()))
                            existing_cids.update(p_cids)
                            affected[p_ctx] = tuple(sorted(existing_cids))

        invalidations = tuple(
            Invalidation(context=identity, component_ids=component_ids)
            for identity, component_ids in sorted(
                affected.items(),
                key=lambda item: (
                    item[0].session_id,
                    item[0].view_id,
                    item[0].user_id or "",
                ),
            )
        )
        change = StateChange(
            key=ref.key,
            scope=ref.scope,
            changed=True,
            revision=revision,
            previous=previous,
            value=copy.deepcopy(validated),
            invalidations=invalidations,
        )

        # Batch tracking
        active_batch = _ACTIVE_BATCH.get()
        if active_batch is not None and active_batch.context.identity == context.identity:
            active_batch.changes.append(change)
            for inv in invalidations:
                active_batch.affected[inv.context].update(inv.component_ids)

        # Transaction tracking
        if active_txs:
            active_txs[-1].changes.append(change)

        for mw in reversed(self._middleware):
            mw.after_write(ref, context, change)

        notifications: list[Any] = []
        if hasattr(ref, "_collect_notifications"):
            if active_txs:
                _record_coalesced_signal_update(
                    active_txs[-1].pending_signal_updates,
                    ref,
                    context.identity,
                    previous,
                    validated,
                )
            elif active_batch is not None and active_batch.context.identity == context.identity:
                _record_coalesced_signal_update(
                    active_batch.pending_signal_updates,
                    ref,
                    context.identity,
                    previous,
                    validated,
                )
            else:
                notifications = ref._collect_notifications(context.identity, previous, validated)

        return change, notifications

    def drop_view(self, session_id: str, view_id: str) -> None:
        """Remove view-scoped values and dependency registrations for a view."""
        if not session_id or not view_id:
            raise ValueError("session_id and view_id are required")
        with self._lock:
            keys = [
                key for key in self._values
                if key[0] == "view" and key[1] == (session_id, view_id)
            ]
            for key in keys:
                self._values.pop(key, None)
                self._revisions.pop(key, None)
            comp_keys = [
                key for key in self._computed_cache
                if key[0] == "view" and key[1] == (session_id, view_id)
            ]
            for key in comp_keys:
                self._computed_cache.pop(key, None)
        self.backend.delete("view", f"{session_id}:{view_id}")
        self.dependencies.remove_view(self.app_id, session_id, view_id)

    def drop_session(self, session_id: str) -> None:
        """Remove session/view state and dependencies; user/app state is retained."""
        if not session_id:
            raise ValueError("session_id cannot be empty")
        with self._lock:
            keys = [
                key for key in self._values
                if (key[0] == "session" and key[1] == session_id)
                or (key[0] == "view" and isinstance(key[1], tuple) and key[1][0] == session_id)
            ]
            for key in keys:
                self._values.pop(key, None)
                self._revisions.pop(key, None)
            comp_keys = [
                key for key in self._computed_cache
                if (key[0] == "session" and key[1] == session_id)
                or (key[0] == "view" and isinstance(key[1], tuple) and key[1][0] == session_id)
            ]
            for key in comp_keys:
                self._computed_cache.pop(key, None)
        self.backend.delete("session", session_id)
        self.dependencies.remove_session(self.app_id, session_id)

    def drop_user(self, user_id: str) -> None:
        """Remove all process-local user-scoped state and dependencies for a user."""
        if not user_id:
            raise ValueError("user_id is required")
        with self._lock:
            keys = [key for key in self._values if key[0] == "user" and key[1] == user_id]
            for key in keys:
                self._values.pop(key, None)
                self._revisions.pop(key, None)
            comp_keys = [key for key in self._computed_cache if key[0] == "user" and key[1] == user_id]
            for key in comp_keys:
                self._computed_cache.pop(key, None)
        self.backend.delete("user", user_id)
        self.dependencies.remove_user(self.app_id, user_id)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()
            self._revisions.clear()
            self._declarations.clear()
            self._computed_cache.clear()
        self.dependencies.clear()
        if hasattr(self.backend, "_store"):
            self.backend._store.clear()


class StateContext:
    """Session/view identity used for typed state reads, writes and tracking."""

    def __init__(self, runtime: StateRuntime, identity: ContextIdentity) -> None:
        self.runtime = runtime
        self.identity = identity

    @property
    def session_id(self) -> str:
        return self.identity.session_id

    @property
    def user_id(self) -> str | None:
        return self.identity.user_id

    @property
    def view_id(self) -> str:
        return self.identity.view_id

    @property
    def tenant_id(self) -> str | None:
        return self.identity.tenant_id

    def read(self, ref: StateRef[Any]) -> Any:
        return self.runtime._read(ref, self)

    def write(self, ref: StateRef[Any], value: Any) -> StateChange:
        change = self.runtime._write(ref, self, value)
        collectors = _ACTIVE_CHANGE_COLLECTORS.get()
        if collectors and collectors[-1][0] == self.identity and change.changed:
            collectors[-1][1].append(change)
        return change

    def __getitem__(self, key: str | Any) -> Any:
        from radui.state.refs import StateRef
        ref = key if isinstance(key, StateRef) else StateRef(key, default="", scope="session", value_type=Any)
        return self.read(ref)

    def __setitem__(self, key: str | Any, value: Any) -> None:
        from radui.state.refs import StateRef
        ref = key if isinstance(key, StateRef) else StateRef(key, default=value, scope="session", value_type=Any)
        self.write(ref, value)

    def get(self, key: str | Any, default: Any = None) -> Any:
        try:
            val = self[key]
            return val if val is not None else default
        except Exception:
            return default

    def __contains__(self, key: str | Any) -> bool:
        return self.get(key) is not None

    @contextmanager
    def batch(self) -> Iterator[BatchContext]:
        """Group multiple state writes into a single invalidation pass."""
        existing = _ACTIVE_BATCH.get()
        if existing is not None:
            yield existing
            return

        batch_ctx = BatchContext(self)
        token = _ACTIVE_BATCH.set(batch_ctx)
        try:
            yield batch_ctx
        finally:
            _ACTIVE_BATCH.reset(token)
            consolidated = tuple(
                Invalidation(context=identity, component_ids=tuple(sorted(component_ids)))
                for identity, component_ids in sorted(
                    batch_ctx.affected.items(),
                    key=lambda item: (
                        item[0].session_id,
                        item[0].view_id,
                        item[0].user_id or "",
                    ),
                )
            )
            batch_ctx.consolidated_invalidations = consolidated
            pending_updates = dict(batch_ctx.pending_signal_updates)
            batch_ctx.pending_signal_updates.clear()
            _flush_coalesced_signal_updates(pending_updates)

    @contextmanager
    def transaction(self) -> Iterator[TransactionContext]:
        """Atomic state modifications with automatic rollback on unhandled exceptions."""
        tx_ctx = TransactionContext(self)
        current_stack = _ACTIVE_TRANSACTIONS.get()
        token = _ACTIVE_TRANSACTIONS.set(current_stack + (tx_ctx,))
        try:
            yield tx_ctx
        except Exception:
            with self.runtime._lock:
                for state_key, (existed, prev_val, prev_rev) in reversed(list(tx_ctx.snapshots.items())):
                    scope, owner, key = state_key
                    owner_str = owner if isinstance(owner, str) else f"{owner[0]}:{owner[1]}"
                    if existed:
                        self.runtime._values[state_key] = copy.deepcopy(prev_val)
                        self.runtime._revisions[state_key] = prev_rev
                        self.runtime.backend.set(scope, owner_str, key, copy.deepcopy(prev_val))
                    else:
                        self.runtime._values.pop(state_key, None)
                        self.runtime._revisions.pop(state_key, None)
                        self.runtime.backend.delete(scope, owner_str, key)
                    for comp_key in self.runtime.dependencies.get_transitive_computed_dependents(state_key):
                        self.runtime._computed_cache.pop(comp_key, None)

            # Roll back any recorded changes from active change collectors
            collectors = _ACTIVE_CHANGE_COLLECTORS.get()
            if collectors and tx_ctx.changes:
                for target_ctx, change_list in collectors:
                    if target_ctx == self.identity:
                        for ch in tx_ctx.changes:
                            if ch in change_list:
                                change_list.remove(ch)
            tx_ctx.pending_signal_updates.clear()
            raise
        else:
            new_stack = _ACTIVE_TRANSACTIONS.get()[:-1]
            if new_stack:
                parent_tx = new_stack[-1]
                for k, v in tx_ctx.snapshots.items():
                    if k not in parent_tx.snapshots:
                        parent_tx.snapshots[k] = v
                parent_tx.changes.extend(tx_ctx.changes)
                for sig_key, (sig_ref, ctx_id, prev_v, curr_v) in tx_ctx.pending_signal_updates.items():
                    _record_coalesced_signal_update(
                        parent_tx.pending_signal_updates, sig_ref, ctx_id, prev_v, curr_v
                    )
            else:
                active_batch = _ACTIVE_BATCH.get()
                if active_batch is not None and active_batch.context.identity == self.identity:
                    for sig_key, (sig_ref, ctx_id, prev_v, curr_v) in tx_ctx.pending_signal_updates.items():
                        _record_coalesced_signal_update(
                            active_batch.pending_signal_updates, sig_ref, ctx_id, prev_v, curr_v
                        )
                else:
                    _flush_coalesced_signal_updates(tx_ctx.pending_signal_updates)
        finally:
            _ACTIVE_TRANSACTIONS.reset(token)

    @contextmanager
    def capture_changes(self) -> Iterator[list[StateChange]]:
        """Collect state changes made in this context, including StateRef.value writes."""
        changes: list[StateChange] = []
        stack = _ACTIVE_CHANGE_COLLECTORS.get()
        token = _ACTIVE_CHANGE_COLLECTORS.set(stack + ((self.identity, changes),))
        try:
            yield changes
        finally:
            _ACTIVE_CHANGE_COLLECTORS.reset(token)

    @contextmanager
    def activate(self) -> Iterator[StateContext]:
        token: Token[StateContext | None] = _ACTIVE_CONTEXT.set(self)
        try:
            yield self
        finally:
            _ACTIVE_CONTEXT.reset(token)

    @contextmanager
    def track_component(self, component_id: str) -> Iterator[None]:
        """Collect state reads for a component and replace its old dependencies.

        If rendering raises, the previously registered dependency set is kept.
        """
        if not component_id:
            raise ValueError("component_id cannot be empty")
        collector = _Collector(self.identity, component_id, set())
        context_token = _ACTIVE_CONTEXT.set(self)
        stack = _ACTIVE_COLLECTORS.get()
        collector_token = _ACTIVE_COLLECTORS.set(stack + (collector,))
        rctx = RenderContext(state_context=self, component_id=component_id, parent=_ACTIVE_RENDER_CONTEXT.get())
        render_token = _ACTIVE_RENDER_CONTEXT.set(rctx)
        try:
            yield
        except Exception:
            raise
        else:
            self.runtime.dependencies.replace_dependencies(
                self.identity, component_id, collector.dependencies
            )
        finally:
            _ACTIVE_RENDER_CONTEXT.reset(render_token)
            _ACTIVE_COLLECTORS.reset(collector_token)
            _ACTIVE_CONTEXT.reset(context_token)

    def unregister_component(self, component_id: str) -> None:
        self.runtime.dependencies.remove_component(self.identity, component_id)


def _record_coalesced_signal_update(
    bucket: dict[tuple[int, ContextIdentity], tuple[Any, ContextIdentity, Any, Any]],
    ref: Any,
    context_identity: ContextIdentity,
    previous: Any,
    current: Any,
) -> None:
    key = (id(ref), context_identity)
    existing = bucket.get(key)
    if existing is None:
        bucket[key] = (ref, context_identity, previous, current)
    else:
        bucket[key] = (ref, context_identity, existing[2], current)


def _flush_coalesced_signal_updates(
    bucket: dict[tuple[int, ContextIdentity], tuple[Any, ContextIdentity, Any, Any]],
) -> None:
    for ref, ctx_id, first_prev, last_curr in bucket.values():
        if _safe_equal(first_prev, last_curr):
            continue
        for notify_fn in ref._collect_notifications(ctx_id, first_prev, last_curr):
            notify_fn()


def _safe_equal(left: Any, right: Any) -> bool:
    try:
        result = left == right
        return result if isinstance(result, bool) else bool(result)
    except Exception:
        return left is right
