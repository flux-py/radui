from __future__ import annotations

import copy
import re
from typing import Any, Callable, Generic, Literal, TypeVar, overload

from pydantic import TypeAdapter

from radui.state.runtime import StateContext, get_active_context

T = TypeVar("T")
StateScope = Literal["view", "session", "user", "tenant", "app", "global"]
_STATE_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


class TenantRequiredError(RuntimeError):
    """Raised when an operation requiring an active tenant_id is attempted without one."""


class UserRequiredError(RuntimeError):
    """Raised when an operation requiring an authenticated user_id is attempted without one."""


class StateRef(Generic[T]):
    """Typed reference to a value owned by a RADUI StateRuntime.

    ``ref.value`` requires an active StateContext. For explicit code, use
    ``context.read(ref)`` and ``context.write(ref, value)``.
    """

    __slots__ = ("_key", "_scope", "_default", "_annotation", "_adapter", "_type_key", "_sealed", "_is_global")

    def __init__(
        self,
        key: str,
        default: T,
        *,
        scope: StateScope = "session",
        value_type: Any | None = None,
        is_global: bool = False,
    ) -> None:
        if not isinstance(key, str) or not _STATE_KEY_RE.fullmatch(key):
            raise ValueError(
                "state key must start with a letter and contain only letters, "
                "numbers, '_', '.', ':' or '-' (maximum 128 characters)"
            )
        if scope not in {"view", "session", "user", "tenant", "app", "global"}:
            raise ValueError("scope must be one of: view, session, user, tenant, app, global")
        if default is None and value_type is None:
            raise TypeError("value_type is required when the default is None")

        annotation = value_type if value_type is not None else type(default)
        adapter = TypeAdapter(annotation)
        validated_default = adapter.validate_python(default, strict=True)

        object.__setattr__(self, "_key", key)
        object.__setattr__(self, "_scope", scope)
        object.__setattr__(self, "_default", copy.deepcopy(validated_default))
        object.__setattr__(self, "_annotation", annotation)
        object.__setattr__(self, "_adapter", adapter)
        object.__setattr__(self, "_type_key", str(annotation))
        object.__setattr__(self, "_is_global", is_global or (scope == "global"))
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: Any) -> None:
        # Preserve the intentional descriptor assignment ``ref.value = x``
        # while keeping the reference declaration itself immutable.
        if name == "value":
            descriptor = type(self).value
            descriptor.fset(self, value)
            return
        if getattr(self, "_sealed", False):
            raise AttributeError("StateRef is immutable")
        object.__setattr__(self, name, value)

    @property
    def key(self) -> str:
        return self._key

    @property
    def scope(self) -> StateScope:
        return self._scope

    @property
    def value(self) -> T:
        context = get_active_context()
        if context is None:
            raise RuntimeError(
                f"StateRef {self.key!r} can only be read inside an active StateContext"
            )
        return context.read(self)

    @value.setter
    def value(self, value: T) -> None:
        context = get_active_context()
        if context is None:
            raise RuntimeError(
                f"StateRef {self.key!r} can only be written inside an active StateContext"
            )
        context.write(self, value)

    @property
    def default(self) -> T:
        return copy.deepcopy(self._default)

    @property
    def type_key(self) -> str:
        return self._type_key

    def validate(self, value: Any) -> T:
        """Validate a native Python value without implicit coercion."""
        return self._adapter.validate_python(value, strict=True)

    def validate_form_value(self, value: str) -> T:
        """Parse a scalar HTML form value into this reference's declared type.

        This is deliberately separate from ``validate``: application code must
        use native Python types, while browser form controls necessarily submit
        strings. Complex values should be submitted through an explicit JSON API.
        """
        if not isinstance(value, str):
            raise TypeError("form values must be strings")
        return self._adapter.validate_strings(value, strict=True)

    def _state_key(self, context: StateContext) -> tuple[str, str | tuple[str, str], str]:
        t_prefix = f"{context.tenant_id}:" if context.tenant_id else ""
        if self.scope == "view":
            if not context.view_id:
                raise RuntimeError(f"state {self.key!r} requires a view_id")
            owner: str | tuple[str, str] = (f"{t_prefix}{context.session_id}", context.view_id)
        elif self.scope == "session":
            owner = f"{t_prefix}{context.session_id}"
        elif self.scope == "user":
            if not context.user_id:
                raise UserRequiredError(f"state {self.key!r} requires an authenticated user_id")
            owner = f"{t_prefix}{context.user_id}"
        elif self.scope == "tenant":
            if not context.tenant_id:
                raise TenantRequiredError(
                    f"state {self.key!r} with scope='tenant' requires an active tenant_id"
                )
            owner = f"tenant:{context.tenant_id}"
        elif getattr(self, "_is_global", False):
            # Explicitly global across all tenants (cluster/process-level singleton)
            owner = context.runtime.app_id
        else:
            # app scope partitions by tenant when tenant_id is active (backward-compatible)
            owner = f"{t_prefix}{context.runtime.app_id}"
        return (self.scope, owner, self.key)

    def __repr__(self) -> str:
        return f"StateRef(key={self.key!r}, scope={self.scope!r}, type={self.type_key})"


def state(
    key: str,
    default: T,
    *,
    scope: StateScope = "session",
    value_type: Any | None = None,
    is_global: bool = False,
) -> StateRef[T]:
    """Create a typed state reference.

    For parameterized or nullable types, pass ``value_type`` explicitly, e.g.
    ``state('filters.tags', [], value_type=list[str])``.
    """

    return StateRef(key, default, scope=scope, value_type=value_type, is_global=is_global)


class CyclicDependencyError(RuntimeError):
    """Raised when a circular dependency is detected in computed state evaluations."""
    pass


class ComputedRef(StateRef[T]):
    """Derived reactive state calculated from upstream state references with memoization and cycle detection."""

    __slots__ = ("_fn",)

    def __init__(
        self,
        fn: Callable[[], T],
        *,
        key: str | None = None,
        scope: StateScope = "session",
        value_type: Any | None = None,
    ) -> None:
        effective_key = key or fn.__name__
        if not isinstance(effective_key, str) or not _STATE_KEY_RE.fullmatch(effective_key):
            raise ValueError(
                "computed state key must start with a letter and contain only letters, "
                "numbers, '_', '.', ':' or '-' (maximum 128 characters)"
            )
        if scope not in {"view", "session", "user", "tenant", "app"}:
            raise ValueError("scope must be one of: view, session, user, tenant, app")

        annotation = value_type or getattr(fn, "__annotations__", {}).get("return", Any)
        adapter = TypeAdapter(annotation) if annotation not in (Any, object) else None

        object.__setattr__(self, "_key", effective_key)
        object.__setattr__(self, "_scope", scope)
        object.__setattr__(self, "_default", None)
        object.__setattr__(self, "_annotation", annotation)
        object.__setattr__(self, "_adapter", adapter)
        object.__setattr__(self, "_type_key", str(annotation))
        object.__setattr__(self, "_fn", fn)
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "value":
            raise TypeError(f"Computed state {self.key!r} is read-only and cannot be assigned to")
        if getattr(self, "_sealed", False):
            raise AttributeError("ComputedRef is immutable")
        object.__setattr__(self, name, value)

    @property
    def value(self) -> T:
        context = get_active_context()
        if context is None:
            raise RuntimeError(
                f"ComputedRef {self.key!r} can only be read inside an active StateContext"
            )
        return context.read(self)

    @value.setter
    def value(self, val: Any) -> None:
        raise TypeError(f"Computed state {self.key!r} is read-only and cannot be assigned to")

    def validate(self, value: Any) -> T:
        if self._adapter is not None:
            return self._adapter.validate_python(value, strict=False)
        return value

    def validate_form_value(self, value: str) -> T:
        raise TypeError(f"Computed state {self.key!r} is read-only and cannot be bound to form inputs")

    def __repr__(self) -> str:
        return f"ComputedRef(key={self.key!r}, scope={self.scope!r}, type={self.type_key})"


@overload
def computed(fn: Callable[[], T]) -> ComputedRef[T]: ...

@overload
def computed(
    *,
    key: str | None = None,
    scope: StateScope = "session",
    value_type: Any | None = None,
) -> Callable[[Callable[[], T]], ComputedRef[T]]: ...

def computed(
    fn: Callable[[], T] | None = None,
    *,
    key: str | None = None,
    scope: StateScope = "session",
    value_type: Any | None = None,
) -> ComputedRef[T] | Callable[[Callable[[], T]], ComputedRef[T]]:
    """Declare a derived reactive state value with dependency tracking and memoization."""
    if fn is not None and callable(fn):
        return ComputedRef(fn, key=key, scope=scope, value_type=value_type)

    def decorator(func: Callable[[], T]) -> ComputedRef[T]:
        return ComputedRef(func, key=key, scope=scope, value_type=value_type)

    return decorator

