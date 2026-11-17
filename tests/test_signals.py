from __future__ import annotations

import asyncio
import gc
from concurrent.futures import ThreadPoolExecutor

import pytest

import radui as gx
from radui.state import get_active_render_context, render_context


def test_state_signal_factory_and_stateref_compatibility():
    runtime = gx.StateRuntime("app")
    count = gx.state.signal(0)
    named = gx.state.signal("Ada", key="profile.name")
    assert isinstance(count, gx.StateRef)
    assert count.key.startswith("signal.")
    assert named.key == "profile.name"

    doubled = gx.computed(lambda: count.value * 2, key="doubled")
    ctx = runtime.context(session_id="s1")

    with ctx.activate():
        assert count.value == 0
        assert doubled.value == 0
        count.set(5)
        assert count.value == 5
        assert doubled.value == 10
        count.update(lambda v: v + 3)
        assert count.value == 8
        assert doubled.value == 16


def test_signal_peek_does_not_register_dependency():
    runtime = gx.StateRuntime("app")
    tracked = gx.state.signal(1)
    untracked = gx.state.signal(10)
    ctx = runtime.context(session_id="s1")

    with ctx.track_component("comp-a"):
        _ = tracked.value
        _ = untracked.peek()

    assert ctx.write(untracked, 20).invalidations == ()
    inv = ctx.write(tracked, 2).invalidations
    assert len(inv) == 1
    assert inv[0].component_ids == ("comp-a",)


def test_render_context_and_dependency_cleanup_are_exception_safe():
    runtime = gx.StateRuntime("app")
    a = gx.state.signal(1)
    b = gx.state.signal(2)
    ctx = runtime.context(session_id="s1")

    assert get_active_render_context() is None

    with ctx.track_component("panel"):
        rctx = get_active_render_context()
        assert rctx is not None
        assert rctx.component_id == "panel"
        _ = a.value

    assert get_active_render_context() is None

    # Conditional re-render switches from `a` to `b`
    with ctx.track_component("panel"):
        _ = b.value

    assert ctx.write(a, 10).invalidations == ()
    assert ctx.write(b, 20).invalidations[0].component_ids == ("panel",)

    # Failed render keeps previous dependency (`b`) and resets RenderContext
    with pytest.raises(RuntimeError, match="boom"):
        with ctx.track_component("panel"):
            _ = a.value
            raise RuntimeError("boom")

    assert get_active_render_context() is None
    assert ctx.write(a, 99).invalidations == ()
    assert ctx.write(b, 30).invalidations[0].component_ids == ("panel",)


def test_subscriber_lifecycle_and_weakref_gc_cleanup():
    runtime = gx.StateRuntime("app")
    sig = gx.state.signal(0)
    ctx = runtime.context(session_id="s1")
    seen: list[tuple[int, int]] = []

    unsub = sig.subscribe(lambda new, old: seen.append((old, new)), context=ctx)
    with ctx.activate():
        sig.set(1)
        sig.set(2)
        unsub()
        sig.set(3)

    assert seen == [(0, 1), (1, 2)]
    assert sig.subscriber_count() == 0

    class Observer:
        def __init__(self) -> None:
            self.events: list[int] = []

        def on_change(self, new: int, old: int) -> None:
            self.events.append(new)

    obs = Observer()
    sig.subscribe(obs.on_change, context=ctx, weak=True)
    assert sig.subscriber_count() == 1

    with ctx.activate():
        sig.set(4)
    assert obs.events == [4]

    del obs
    gc.collect()
    assert sig.subscriber_count() == 0


def test_nested_render_context_and_component_disposal():
    runtime = gx.StateRuntime("app")
    a = gx.state.signal(1)
    b = gx.state.signal(2)
    ctx = runtime.context(session_id="s1")

    with render_context(ctx, "outer") as outer:
        assert get_active_render_context() is outer
        with pytest.raises(RuntimeError, match="inner-err"):
            with render_context(ctx, "inner") as inner:
                assert get_active_render_context() is inner
                assert inner.parent is outer
                raise RuntimeError("inner-err")
        assert get_active_render_context() is outer
    assert get_active_render_context() is None

    with ctx.track_component("disposable"):
        _ = a.value
        _ = b.value
    ctx.unregister_component("disposable")
    assert ctx.write(a, 10).invalidations == ()
    assert ctx.write(b, 20).invalidations == ()


def test_nested_property_tracking_dict_list_and_model():
    from pydantic import BaseModel

    class Profile(BaseModel):
        name: str
        items: list[str]

    runtime = gx.StateRuntime("app")
    user = gx.state.signal(
        {"name": "Ada", "prefs": {"theme": "dark"}, "tags": ["a", "b"]},
        value_type=dict,
    )
    model_sig = gx.state.signal(Profile(name="Ada", items=["x", "y"]), value_type=Profile)
    ctx = runtime.context(session_id="s1")

    with ctx.track_component("theme-badge"):
        assert user.get_path("prefs.theme") == "dark"
    with ctx.track_component("tag-0"):
        assert user.get_path("tags.0") == "a"
    with ctx.track_component("profile-name"):
        assert model_sig.get_path("name") == "Ada"

    theme_events: list[tuple[str, str]] = []
    user.subscribe(
        lambda new, old: theme_events.append((old, new)),
        context=ctx,
        path="prefs.theme",
    )

    with ctx.activate():
        # Unrelated sibling change must NOT invalidate theme-badge or theme_events
        ch1 = user.set_path("name", "Grace")
        assert ch1.invalidations == ()
        assert theme_events == []

        # Changing tags.0 invalidates tag-0 only
        ch_list = user.set_path("tags.0", "z")
        assert ch_list.invalidations[0].component_ids == ("tag-0",)

        # Changing prefs.theme invalidates theme-badge and notifies theme_events
        ch2 = user.set_path("prefs.theme", "light")
        assert ch2.invalidations[0].component_ids == ("theme-badge",)
        assert theme_events == [("dark", "light")]

        # Model attribute path tracking
        assert model_sig.get_path("items.1") == "y"
        ch_model = model_sig.set(Profile(name="Grace", items=["x", "y"]))
        assert ch_model.invalidations[0].component_ids == ("profile-name",)


def test_signal_batch_coalescing_and_transaction_suppression():
    runtime = gx.StateRuntime("app")
    sig = gx.state.signal(0)
    ctx = runtime.context(session_id="s1")
    events: list[tuple[int, int]] = []
    sig.subscribe(lambda new, old: events.append((old, new)), context=ctx)

    with ctx.activate():
        with ctx.batch():
            sig.set(1)
            sig.set(2)
            assert events == []
        # Coalesced to single (initial, final) notification
        assert events == [(0, 2)]

        events.clear()
        with ctx.batch():
            sig.set(5)
            sig.set(2)
        # Net no-op across batch emits nothing
        assert events == []

        events.clear()
        with pytest.raises(ValueError, match="abort"):
            with ctx.transaction():
                sig.set(99)
                raise ValueError("abort")

        # Rolled-back write must restore value and emit NO subscriber notifications
        assert sig.value == 2
        assert events == []

        with ctx.transaction():
            sig.set(10)
            assert events == []
        assert sig.value == 10
        assert events == [(2, 10)]


def test_signal_thread_safe_updates_and_async_context_isolation():
    runtime = gx.StateRuntime("app")
    counter = gx.state.signal(0)
    ctx = runtime.context(session_id="s1")
    lock_acquired_in_cb: list[bool] = []

    # Verify update() executes callbacks outside runtime._lock (non-blocking from another check)
    unsub_cb = counter.subscribe(
        lambda _n, _o: lock_acquired_in_cb.append(runtime._lock._is_owned()),  # noqa: SLF001
        context=ctx,
    )

    def writer() -> None:
        for _ in range(25):
            counter.update(lambda v: v + 1, context=ctx)

    def reader() -> int:
        last = 0
        for _ in range(25):
            val = counter.peek(context=ctx)
            assert val >= last
            last = val
        return last

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(writer) for _ in range(4)] + [pool.submit(reader) for _ in range(2)]
        for f in futures:
            f.result()

    unsub_cb()
    assert counter.peek(context=ctx) == 100
    assert lock_acquired_in_cb and all(owned is False for owned in lock_acquired_in_cb)

    # Async ContextVar isolation + loop-scheduled subscriber notification
    ctx1 = runtime.context(session_id="async-1")
    ctx2 = runtime.context(session_id="async-2")

    async def run_async() -> tuple[list[int], list[int]]:
        loop = asyncio.get_running_loop()
        loop_events: list[int] = []
        unsub = counter.subscribe(lambda new, _old: loop_events.append(new), context=ctx1, loop=loop)

        async def task(target_ctx: gx.StateContext, val: int) -> int:
            with target_ctx.activate():
                with render_context(target_ctx, f"comp-{target_ctx.session_id}"):
                    counter.set(val)
                    await asyncio.sleep(0)
                    return counter.value

        results = await asyncio.gather(task(ctx1, 111), task(ctx2, 222))
        await asyncio.sleep(0)
        unsub()
        return results, loop_events

    res, loop_events = asyncio.run(run_async())
    assert res == [111, 222]
    assert loop_events == [111]
