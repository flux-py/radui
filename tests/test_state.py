from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

import radui as gx


def test_state_ref_requires_active_context_for_value_property():
    count = gx.state("counter.value", 0)
    with pytest.raises(RuntimeError, match="active StateContext"):
        _ = count.value
    with pytest.raises(RuntimeError, match="active StateContext"):
        count.value = 2


def test_typed_state_read_write_and_change_revision():
    runtime = gx.StateRuntime("app")
    context = runtime.context(session_id="s1")
    count = gx.state("counter.value", 0)

    with context.activate():
        assert count.value == 0
        count.value = 3
        assert count.value == 3

    change = context.write(count, 4)
    assert change.changed is True
    assert change.previous == 3
    assert change.value == 4
    assert change.revision == 2

    unchanged = context.write(count, 4)
    assert unchanged.changed is False
    assert unchanged.revision == 2
    assert unchanged.invalidations == ()


def test_strict_type_validation_rejects_implicit_coercion():
    runtime = gx.StateRuntime("app")
    context = runtime.context(session_id="s1")
    count = gx.state("counter.value", 0)

    with pytest.raises(ValidationError):
        context.write(count, "42")


def test_session_scope_isolated_between_sessions():
    runtime = gx.StateRuntime("app")
    count = gx.state("counter.value", 0, scope="session")
    first = runtime.context(session_id="session-a")
    second = runtime.context(session_id="session-b")

    first.write(count, 10)

    assert first.read(count) == 10
    assert second.read(count) == 0


def test_user_scope_shared_across_sessions_but_isolated_between_users():
    runtime = gx.StateRuntime("app")
    preference = gx.state("preferences.page_size", 20, scope="user")
    first_session = runtime.context(session_id="s1", user_id="alice")
    another_session = runtime.context(session_id="s2", user_id="alice")
    other_user = runtime.context(session_id="s3", user_id="bob")

    first_session.write(preference, 50)

    assert another_session.read(preference) == 50
    assert other_user.read(preference) == 20


def test_app_scope_shared_across_users_and_sessions():
    runtime = gx.StateRuntime("app")
    feature = gx.state("feature.enabled", False, scope="app")
    first = runtime.context(session_id="s1", user_id="alice")
    second = runtime.context(session_id="s2", user_id="bob")

    first.write(feature, True)

    assert second.read(feature) is True


def test_view_scope_isolated_between_views_in_same_session():
    runtime = gx.StateRuntime("app")
    draft = gx.state("editor.draft", "", scope="view")
    first_view = runtime.context(session_id="s1", view_id="tab-a")
    second_view = runtime.context(session_id="s1", view_id="tab-b")

    first_view.write(draft, "draft A")

    assert first_view.read(draft) == "draft A"
    assert second_view.read(draft) == ""


def test_scope_requirements_are_enforced():
    runtime = gx.StateRuntime("app")
    user_state = gx.state("user.name", "unknown", scope="user")
    context = runtime.context(session_id="s1")

    with pytest.raises(RuntimeError, match="authenticated user_id"):
        context.read(user_state)


def test_dependency_tracking_invalidates_only_dependent_component():
    runtime = gx.StateRuntime("app")
    count = gx.state("counter.value", 0)
    context = runtime.context(session_id="s1")

    with context.track_component("counter-label"):
        assert context.read(count) == 0
    with context.track_component("static-footer"):
        _ = "always the same"

    change = context.write(count, 1)

    assert len(change.invalidations) == 1
    assert change.invalidations[0].context == context.identity
    assert change.invalidations[0].component_ids == ("counter-label",)


def test_dependencies_are_partitioned_by_session_context():
    runtime = gx.StateRuntime("app")
    count = gx.state("counter.value", 0)
    first = runtime.context(session_id="s1", view_id="main")
    second = runtime.context(session_id="s2", view_id="main")

    with first.track_component("counter-label"):
        first.read(count)
    with second.track_component("counter-label"):
        second.read(count)

    change = first.write(count, 1)

    assert len(change.invalidations) == 1
    assert change.invalidations[0].context == first.identity


def test_app_scope_change_invalidates_all_dependent_contexts():
    runtime = gx.StateRuntime("app")
    feature = gx.state("feature.enabled", False, scope="app")
    first = runtime.context(session_id="s1", view_id="main")
    second = runtime.context(session_id="s2", view_id="main")

    with first.track_component("feature-banner"):
        first.read(feature)
    with second.track_component("feature-banner"):
        second.read(feature)

    change = first.write(feature, True)

    assert {item.context.session_id for item in change.invalidations} == {"s1", "s2"}


def test_dependency_replacement_removes_stale_state_edges():
    runtime = gx.StateRuntime("app")
    first_state = gx.state("filters.first", False)
    second_state = gx.state("filters.second", False)
    context = runtime.context(session_id="s1")

    with context.track_component("filter-summary"):
        context.read(first_state)
    with context.track_component("filter-summary"):
        context.read(second_state)

    first_change = context.write(first_state, True)
    second_change = context.write(second_state, True)

    assert first_change.invalidations == ()
    assert second_change.invalidations[0].component_ids == ("filter-summary",)


def test_component_can_unregister_dependencies():
    runtime = gx.StateRuntime("app")
    count = gx.state("counter.value", 0)
    context = runtime.context(session_id="s1")

    with context.track_component("counter-label"):
        context.read(count)
    context.unregister_component("counter-label")

    assert context.write(count, 1).invalidations == ()


def test_failed_component_render_keeps_previous_dependencies():
    runtime = gx.StateRuntime("app")
    count = gx.state("counter.value", 0)
    context = runtime.context(session_id="s1")

    with context.track_component("counter-label"):
        context.read(count)

    with pytest.raises(RuntimeError):
        with context.track_component("counter-label"):
            raise RuntimeError("render failed")

    change = context.write(count, 1)
    assert change.invalidations[0].component_ids == ("counter-label",)


def test_mutable_values_are_defensively_copied():
    runtime = gx.StateRuntime("app")
    tags = gx.state("filters.tags", ["python"], value_type=list[str])
    context = runtime.context(session_id="s1")

    returned = context.read(tags)
    returned.append("mutated-outside-store")

    assert context.read(tags) == ["python"]


def test_conflicting_state_declarations_are_rejected():
    runtime = gx.StateRuntime("app")
    first = gx.state("shared.value", 0)
    conflicting = gx.state("shared.value", "zero")
    context = runtime.context(session_id="s1")

    context.read(first)
    with pytest.raises(TypeError, match="conflicting declarations"):
        context.read(conflicting)


def test_drop_session_cleans_session_and_view_state_but_not_user_state():
    runtime = gx.StateRuntime("app")
    session_value = gx.state("session.value", 1, scope="session")
    view_value = gx.state("view.value", 2, scope="view")
    user_value = gx.state("user.value", 3, scope="user")
    context = runtime.context(session_id="s1", user_id="alice", view_id="main")

    context.write(session_value, 10)
    context.write(view_value, 20)
    context.write(user_value, 30)
    with context.track_component("user-profile"):
        context.read(user_value)

    runtime.drop_session("s1")
    new_context = runtime.context(session_id="s2", user_id="alice", view_id="main")

    assert new_context.read(session_value) == 1
    assert new_context.read(view_value) == 2
    assert new_context.read(user_value) == 30


def test_active_context_is_isolated_between_async_tasks():
    runtime = gx.StateRuntime("app")
    count = gx.state("counter.value", 0)
    first = runtime.context(session_id="s1")
    second = runtime.context(session_id="s2")

    async def read_in_context(context, value):
        with context.activate():
            count.value = value
            await asyncio.sleep(0)
            return count.value

    async def run():
        return await asyncio.gather(
            read_in_context(first, 11),
            read_in_context(second, 22),
        )

    assert asyncio.run(run()) == [11, 22]


def test_app_exposes_state_runtime_and_context_factory():
    app = gx.App("Test", app_id="test")
    context = app.state_context(session_id="s1", user_id="u1")

    assert isinstance(app.state_runtime, gx.StateRuntime)
    assert isinstance(context, gx.StateContext)
    assert context.identity.app_id == "test"


def test_state_reference_is_immutable():
    count = gx.state("counter.value", 0)
    with pytest.raises(AttributeError, match="immutable"):
        count.key = "other.key"
    with pytest.raises(AttributeError, match="immutable"):
        count.scope = "app"


def test_empty_successful_render_clears_old_dependencies():
    runtime = gx.StateRuntime("app")
    count = gx.state("counter.value", 0)
    context = runtime.context(session_id="s1")

    with context.track_component("counter-label"):
        context.read(count)
    with context.track_component("counter-label"):
        pass

    assert context.write(count, 1).invalidations == ()


def test_drop_view_removes_dependencies_only_for_that_view():
    runtime = gx.StateRuntime("app")
    count = gx.state("counter.value", 0, scope="app")
    first = runtime.context(session_id="s1", user_id="alice", view_id="one")
    second = runtime.context(session_id="s1", user_id="alice", view_id="two")

    with first.track_component("count-one"):
        first.read(count)
    with second.track_component("count-two"):
        second.read(count)

    runtime.drop_view("s1", "one")
    change = second.write(count, 1)

    assert len(change.invalidations) == 1
    assert change.invalidations[0].context == second.identity
    assert change.invalidations[0].component_ids == ("count-two",)


def test_mutable_default_is_not_shared_across_sessions():
    runtime = gx.StateRuntime("app")
    tags = gx.state("filters.tags", ["python"], value_type=list[str])
    first = runtime.context(session_id="s1")
    second = runtime.context(session_id="s2")

    first_value = first.read(tags)
    first_value.append("changed")

    assert second.read(tags) == ["python"]


def test_session_state_invalidates_all_views_in_the_same_session():
    runtime = gx.StateRuntime("app")
    current_project = gx.state("project.current", "alpha", scope="session")
    first_view = runtime.context(session_id="s1", view_id="dashboard")
    second_view = runtime.context(session_id="s1", view_id="editor")

    with first_view.track_component("dashboard-project"):
        first_view.read(current_project)
    with second_view.track_component("editor-project"):
        second_view.read(current_project)

    change = first_view.write(current_project, "beta")

    assert {item.context.view_id for item in change.invalidations} == {
        "dashboard", "editor"
    }


def test_user_state_invalidates_only_sessions_for_that_user():
    runtime = gx.StateRuntime("app")
    theme = gx.state("preferences.theme", "system", scope="user")
    alice_one = runtime.context(session_id="a1", user_id="alice")
    alice_two = runtime.context(session_id="a2", user_id="alice")
    bob = runtime.context(session_id="b1", user_id="bob")

    with alice_one.track_component("theme-one"):
        alice_one.read(theme)
    with alice_two.track_component("theme-two"):
        alice_two.read(theme)
    with bob.track_component("theme-bob"):
        bob.read(theme)

    change = alice_one.write(theme, "dark")

    assert {item.context.session_id for item in change.invalidations} == {"a1", "a2"}


def test_drop_view_resets_only_that_views_state():
    runtime = gx.StateRuntime("app")
    draft = gx.state("editor.draft", "", scope="view")
    first = runtime.context(session_id="s1", view_id="one")
    second = runtime.context(session_id="s1", view_id="two")
    first.write(draft, "first draft")
    second.write(draft, "second draft")

    runtime.drop_view("s1", "one")
    reopened = runtime.context(session_id="s1", view_id="one")

    assert reopened.read(draft) == ""
    assert second.read(draft) == "second draft"
