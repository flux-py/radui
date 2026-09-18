from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from radui.state.refs import StateRef
    from radui.state.runtime import StateChange, StateContext


class StateMiddleware:
    """Pluggable middleware intercepting state reads and mutations."""

    def before_read(self, ref: StateRef[Any], context: StateContext) -> None:
        """Called before reading a state reference."""
        pass

    def after_read(self, ref: StateRef[Any], context: StateContext, value: Any) -> Any:
        """Called after reading a state reference. May transform the returned value."""
        return value

    def before_write(
        self,
        ref: StateRef[Any],
        context: StateContext,
        value: Any,
        previous: Any,
    ) -> Any:
        """Called before writing a state reference. May transform or validate the value."""
        return value

    def after_write(
        self,
        ref: StateRef[Any],
        context: StateContext,
        change: StateChange,
    ) -> None:
        """Called after a state reference has been written."""
        pass
