from __future__ import annotations

import asyncio
import copy
import itertools
import threading
import weakref
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Hashable, Iterator, Sequence, TypeVar

from radui.state.dependencies import ContextIdentity
from radui.state.refs import StateRef, StateScope
from radui.state.runtime import (
    _ACTIVE_BATCH,
    _ACTIVE_COLLECTORS,
    _ACTIVE_RENDER_CONTEXT,
    _ACTIVE_TRANSACTIONS,
    RenderContext,
    StateChange,
    StateContext,
    _safe_equal,
    get_active_context,
)

T = TypeVar("T")

_SIGNAL_COUNTER = itertools.count(1)


class _MissingSentinel:
    pass


_MISSING = _MissingSentinel()


def normalize_path(path: str | Sequence[str | int]) -> tuple[str | int, ...]:
    """Normalize a dot-separated path or sequence of keys/indices into a tuple."""
    if isinstance(path, str):
        if not path:
            return ()
        parts: list[str | int] = []
        for segment in path.split("."):
            if segment == "":
                raise ValueError(f"Invalid empty segment in path {path!r}")
            parts.append(int(segment) if segment.isdigit() else segment)
        return tuple(parts)
    return tuple(path)


def resolve_path(container: Any, path: tuple[str | int, ...], default: Any = _MISSING) -> Any:
    """Safely traverse a nested dict/list/object by path."""
    curr = container
    for segment in path:
        if isinstance(curr, dict) and segment in curr:
            curr = curr[segment]
        elif isinstance(curr, (list, tuple)) and isinstance(segment, int) and -len(curr) <= segment < len(curr):
            curr = curr[segment]
        elif isinstance(segment, str) and hasattr(curr, segment):
            curr = getattr(curr, segment)
        else:
            if default is _MISSING:
                raise KeyError(segment)
            return copy.deepcopy(default)
    return copy.deepcopy(curr)


def update_path(container: Any, path: tuple[str | int, ...], value: Any) -> Any:
    """Return a deep-copied container with the nested path updated."""
    if not path:
        return copy.deepcopy(value)
    root = copy.deepcopy(container)
    curr = root
    for segment in path[:-1]:
        if isinstance(curr, dict):
            if segment not in curr or curr[segment] is None:
                curr[segment] = {}
            curr = curr[segment]
        elif isinstance(curr, list) and isinstance(segment, int):
            curr = curr[segment]
        else:
            raise KeyError(f"Cannot traverse segment {segment!r} on {type(curr).__name__}")

    leaf = path[-1]
    if isinstance(curr, dict):
        curr[leaf] = copy.deepcopy(value)
    elif isinstance(curr, list) and isinstance(leaf, int):
        curr[leaf] = copy.deepcopy(value)
    else:
        raise KeyError(f"Cannot assign leaf {leaf!r} on {type(curr).__name__}")
    return root


def get_active_render_context() -> RenderContext | None:
    return _ACTIVE_RENDER_CONTEXT.get()


@contextmanager
def render_context(
    state_context: StateContext,
    component_id: str | None = None,
) -> Iterator[RenderContext]:
    """Activate an exception-safe RenderContext bound to the current async/thread task."""
    parent = _ACTIVE_RENDER_CONTEXT.get()
    ctx = RenderContext(state_context=state_context, component_id=component_id, parent=parent)
    token: Token[RenderContext | None] = _ACTIVE_RENDER_CONTEXT.set(ctx)
    try:
        yield ctx
    finally:
        _ACTIVE_RENDER_CONTEXT.reset(token)


@dataclass
class _SubscriberEntry:
    sub_id: int
    callback: Callable[[Any, Any], Any] | None
    weak_ref: Any | None
    context_identity: ContextIdentity | None
    path: tuple[str | int, ...] | None
    loop: asyncio.AbstractEventLoop | None

    def resolve(self) -> Callable[[Any, Any], Any] | None:
        if self.callback is not None:
            return self.callback
        if self.weak_ref is not None:
            return self.weak_ref()
        return None


class _Signal(StateRef[T], Generic[T]):
    """Internal fine-grained reactive signal built on top of StateRef and StateRuntime."""

    __slots__ = ("_sub_lock", "_subscribers", "_sub_seq")

    def __init__(
        self,
        default: T,
        *,
        key: str | None = None,
        scope: StateScope = "session",
        value_type: Any | None = None,
        is_global: bool = False,
    ) -> None:
        effective_key = key if key is not None else f"signal.{next(_SIGNAL_COUNTER)}"
        super().__init__(
            effective_key,
            default,
            scope=scope,
            value_type=value_type,
            is_global=is_global,
        )
        object.__setattr__(self, "_sub_lock", threading.RLock())
        object.__setattr__(self, "_subscribers", {})
        object.__setattr__(self, "_sub_seq", itertools.count(1))

    def _require_context(self, context: StateContext | None) -> StateContext:
        ctx = context if context is not None else get_active_context()
        if ctx is None:
            raise RuntimeError(
                f"Signal {self.key!r} requires an active StateContext or explicit context="
            )
        return ctx

    def peek(self, *, context: StateContext | None = None) -> T:
        """Read the current value without registering a reactive dependency."""
        ctx = self._require_context(context)
        return ctx.runtime._peek(self, ctx)

    def set(self, value: T, *, context: StateContext | None = None) -> StateChange:
        """Write a new value to the signal within the active or explicit StateContext."""
        ctx = self._require_context(context)
        return ctx.write(self, value)

    def update(self, fn: Callable[[T], T], *, context: StateContext | None = None) -> StateChange:
        """Atomically read-modify-write the signal value."""
        ctx = self._require_context(context)
        return ctx.runtime._update_with(self, ctx, fn)

    def get_path(
        self,
        path: str | Sequence[str | int],
        *,
        default: Any = _MISSING,
        context: StateContext | None = None,
    ) -> Any:
        """Read a nested path and register path-granular dependency tracking."""
        ctx = self._require_context(context)
        norm_path = normalize_path(path)
        full_val = ctx.runtime._peek(self, ctx)
        state_key = self._state_key(ctx)
        dep_key: Hashable = (state_key, norm_path) if norm_path else state_key

        collectors = _ACTIVE_COLLECTORS.get()
        if collectors and collectors[-1].context == ctx.identity:
            collectors[-1].dependencies.add(dep_key)

        rctx = _ACTIVE_RENDER_CONTEXT.get()
        if rctx is not None and rctx.state_context.identity == ctx.identity:
            rctx.tracked_keys.add(dep_key)

        return resolve_path(full_val, norm_path, default=default)

    def set_path(
        self,
        path: str | Sequence[str | int],
        value: Any,
        *,
        context: StateContext | None = None,
    ) -> StateChange:
        """Update a nested path and emit targeted invalidations."""
        ctx = self._require_context(context)
        norm_path = normalize_path(path)
        return ctx.runtime._update_with(
            self,
            ctx,
            lambda current: update_path(current, norm_path, value),
        )

    def subscribe(
        self,
        callback: Callable[[Any, Any], Any],
        *,
        context: StateContext | None = None,
        path: str | Sequence[str | int] | None = None,
        weak: bool = False,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> Callable[[], None]:
        """Subscribe to value changes. Returns an explicit unsubscribe callable."""
        if not callable(callback):
            raise TypeError("callback must be callable")
        norm_path = normalize_path(path) if path is not None else None
        ctx_identity = context.identity if context is not None else None
        sub_id = next(self._sub_seq)

        weak_ref: Any | None = None
        strong_cb: Callable[[Any, Any], Any] | None = callback
        if weak:
            strong_cb = None
            if hasattr(callback, "__self__") and hasattr(callback, "__func__"):
                weak_ref = weakref.WeakMethod(callback)
            else:
                weak_ref = weakref.ref(callback)

        entry = _SubscriberEntry(
            sub_id=sub_id,
            callback=strong_cb,
            weak_ref=weak_ref,
            context_identity=ctx_identity,
            path=norm_path,
            loop=loop,
        )
        with self._sub_lock:
            self._subscribers[sub_id] = entry

        def unsubscribe() -> None:
            with self._sub_lock:
                self._subscribers.pop(sub_id, None)

        return unsubscribe

    def subscriber_count(self) -> int:
        """Prune dead weakref subscribers and return active subscriber count."""
        with self._sub_lock:
            dead = [sid for sid, entry in self._subscribers.items() if entry.resolve() is None]
            for sid in dead:
                self._subscribers.pop(sid, None)
            return len(self._subscribers)

    def _collect_notifications(
        self,
        context_identity: ContextIdentity,
        previous: Any,
        current: Any,
    ) -> list[Callable[[], None]]:
        """Build thread-safe notification thunks for matching live subscribers."""
        tasks: list[Callable[[], None]] = []
        with self._sub_lock:
            dead: list[int] = []
            entries = list(self._subscribers.items())
            for sid, entry in entries:
                cb = entry.resolve()
                if cb is None:
                    dead.append(sid)
                    continue
                if entry.context_identity is not None and entry.context_identity != context_identity:
                    continue
                if entry.path is not None:
                    prev_sub = resolve_path(previous, entry.path, default=_MISSING)
                    curr_sub = resolve_path(current, entry.path, default=_MISSING)
                    if _safe_equal(prev_sub, curr_sub):
                        continue
                    prev_arg, curr_arg = prev_sub, curr_sub
                else:
                    prev_arg, curr_arg = copy.deepcopy(previous), copy.deepcopy(current)

                loop = entry.loop

                def _invoke(fn: Callable[[Any, Any], Any] = cb, n_val: Any = curr_arg, o_val: Any = prev_arg, target_loop: asyncio.AbstractEventLoop | None = loop) -> None:
                    if target_loop is not None and not target_loop.is_closed():
                        target_loop.call_soon_threadsafe(fn, n_val, o_val)
                    else:
                        fn(n_val, o_val)

                tasks.append(_invoke)

            for sid in dead:
                self._subscribers.pop(sid, None)

        return tasks

    def __repr__(self) -> str:
        return f"Signal(key={self.key!r}, scope={self.scope!r}, type={self.type_key})"


def signal(
    default: T,
    *,
    key: str | None = None,
    scope: StateScope = "session",
    value_type: Any | None = None,
    is_global: bool = False,
) -> _Signal[T]:
    """Create a fine-grained reactive signal integrated with RADUI StateRuntime."""
    return _Signal(
        default,
        key=key,
        scope=scope,
        value_type=value_type,
        is_global=is_global,
    )
