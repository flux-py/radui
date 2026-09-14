from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from threading import RLock
from typing import Hashable


@dataclass(frozen=True)
class ContextIdentity:
    """Identity of one live view within an application session."""

    app_id: str
    session_id: str
    user_id: str | None
    view_id: str
    tenant_id: str | None = None


class DependencyTracker:
    """Tracks state-to-component dependencies, partitioned by view identity.

    A component's dependency set is replaced after a successful tracked render.
    Reverse indexes make cleanup and targeted invalidation efficient.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._by_state: dict[
            Hashable, dict[ContextIdentity, set[str]]
        ] = defaultdict(dict)
        self._by_component: dict[
            tuple[ContextIdentity, str], set[Hashable]
        ] = {}
        self._computed_by_state: dict[Hashable, set[Hashable]] = defaultdict(set)
        self._state_by_computed: dict[Hashable, set[Hashable]] = {}

    def register_computed_dependencies(
        self, computed_key: Hashable, upstream_keys: set[Hashable]
    ) -> None:
        with self._lock:
            old_upstream = self._state_by_computed.pop(computed_key, set())
            for u_key in old_upstream:
                if u_key in self._computed_by_state:
                    self._computed_by_state[u_key].discard(computed_key)
                    if not self._computed_by_state[u_key]:
                        self._computed_by_state.pop(u_key, None)
            if upstream_keys:
                clean_upstream = set(upstream_keys)
                self._state_by_computed[computed_key] = clean_upstream
                for u_key in clean_upstream:
                    self._computed_by_state[u_key].add(computed_key)

    def get_transitive_computed_dependents(self, state_key: Hashable) -> set[Hashable]:
        with self._lock:
            result: set[Hashable] = set()
            queue = [state_key]
            while queue:
                curr = queue.pop(0)
                for dep in self._computed_by_state.get(curr, ()):
                    if dep not in result:
                        result.add(dep)
                        queue.append(dep)
            return result

    def remove_computed(self, computed_key: Hashable) -> None:
        with self._lock:
            old_upstream = self._state_by_computed.pop(computed_key, set())
            for u_key in old_upstream:
                if u_key in self._computed_by_state:
                    self._computed_by_state[u_key].discard(computed_key)
                    if not self._computed_by_state[u_key]:
                        self._computed_by_state.pop(u_key, None)
            downstream = self._computed_by_state.pop(computed_key, set())
            for d_key in downstream:
                if d_key in self._state_by_computed:
                    self._state_by_computed[d_key].discard(computed_key)

    def replace_dependencies(
        self,
        context: ContextIdentity,
        component_id: str,
        dependencies: set[Hashable],
    ) -> None:
        component_key = (context, component_id)
        with self._lock:
            old_dependencies = self._by_component.pop(component_key, set())
            for state_key in old_dependencies:
                contexts = self._by_state.get(state_key)
                if contexts is None:
                    continue
                component_ids = contexts.get(context)
                if component_ids is not None:
                    component_ids.discard(component_id)
                    if not component_ids:
                        contexts.pop(context, None)
                if not contexts:
                    self._by_state.pop(state_key, None)

            if dependencies:
                clean_dependencies = set(dependencies)
                self._by_component[component_key] = clean_dependencies
                for state_key in clean_dependencies:
                    self._by_state[state_key].setdefault(context, set()).add(component_id)

    def remap_component_id(
        self,
        context: ContextIdentity,
        old_id: str,
        new_id: str,
    ) -> None:
        """Remap tracked dependencies from old_id to new_id within context."""
        if old_id == new_id:
            return
        with self._lock:
            old_key = (context, old_id)
            deps = self._by_component.pop(old_key, None)
            if deps:
                for state_key in deps:
                    contexts = self._by_state.get(state_key)
                    if contexts and context in contexts:
                        contexts[context].discard(old_id)
                        contexts[context].add(new_id)
                new_key = (context, new_id)
                self._by_component.setdefault(new_key, set()).update(deps)

    def dependents(self, state_key: Hashable) -> dict[ContextIdentity, tuple[str, ...]]:
        with self._lock:
            all_keys = {state_key}
            queue = [state_key]
            while queue:
                curr = queue.pop(0)
                for dep in self._computed_by_state.get(curr, ()):
                    if dep not in all_keys:
                        all_keys.add(dep)
                        queue.append(dep)

            combined: dict[ContextIdentity, set[str]] = defaultdict(set)
            for k in all_keys:
                contexts = self._by_state.get(k, {})
                for context, component_ids in contexts.items():
                    combined[context].update(component_ids)

            return {
                context: tuple(sorted(component_ids))
                for context, component_ids in combined.items()
                if component_ids
            }


    def reconcile_context(
        self, context: ContextIdentity, retained_component_ids: set[str]
    ) -> None:
        """Remove dependency edges for components absent from the latest render.

        Conditional UI can unmount components without explicitly notifying the
        runtime. Reconciliation prevents those components from accumulating stale
        dependencies and receiving future invalidations.
        """
        with self._lock:
            stale = [
                component_id
                for candidate_context, component_id in self._by_component
                if candidate_context == context and component_id not in retained_component_ids
            ]
            for component_id in stale:
                self.replace_dependencies(context, component_id, set())

    def remove_component(self, context: ContextIdentity, component_id: str) -> None:
        self.replace_dependencies(context, component_id, set())

    def remove_context(self, context: ContextIdentity) -> None:
        with self._lock:
            component_keys = [
                key for key in self._by_component if key[0] == context
            ]
            for _, component_id in component_keys:
                # RLock permits reuse of the consistent reverse-index cleanup.
                self.replace_dependencies(context, component_id, set())

    def remove_session(self, app_id: str, session_id: str) -> None:
        with self._lock:
            contexts = {
                context
                for context, _ in self._by_component
                if context.app_id == app_id and context.session_id == session_id
            }
            for context in contexts:
                self.remove_context(context)

    def remove_user(self, app_id: str, user_id: str) -> None:
        with self._lock:
            contexts = {
                context
                for context, _ in self._by_component
                if context.app_id == app_id and context.user_id == user_id
            }
            for context in contexts:
                self.remove_context(context)

    def remove_view(self, app_id: str, session_id: str, view_id: str) -> None:
        with self._lock:
            contexts = {
                context
                for context, _ in self._by_component
                if context.app_id == app_id
                and context.session_id == session_id
                and context.view_id == view_id
            }
            for context in contexts:
                self.remove_context(context)

    def clear(self) -> None:
        with self._lock:
            self._by_state.clear()
            self._by_component.clear()
            self._computed_by_state.clear()
            self._state_by_computed.clear()
