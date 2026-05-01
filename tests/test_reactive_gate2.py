from __future__ import annotations

import asyncio
from typing import Any
import pytest
from starlette.requests import Request
from starlette.testclient import TestClient

import radui as gx


def test_computed_basic_derivation_and_memoization():
    runtime = gx.StateRuntime("app")
    context = runtime.context(session_id="s1")

    s_price = gx.state("price", 100.0, scope="session")
    s_tax = gx.state("tax", 0.20, scope="session")

    eval_count = 0

    @gx.computed
    def s_total() -> float:
        nonlocal eval_count
        eval_count += 1
        return s_price.value * (1.0 + s_tax.value)

    assert eval_count == 0  # Lazy: not evaluated until read

    with context.activate():
        # First read
        val1 = s_total.value
        assert val1 == pytest.approx(120.0)
        assert eval_count == 1

        # Second read: cached
        val2 = s_total.value
        assert val2 == pytest.approx(120.0)
        assert eval_count == 1

        # Mutate upstream state
        s_price.value = 200.0

        # Third read: cache invalidated, recomputes
        val3 = s_total.value
        assert val3 == pytest.approx(240.0)
        assert eval_count == 2


def test_computed_transitive_cascading_and_invalidation():
    runtime = gx.StateRuntime("app")
    context = runtime.context(session_id="s1")

    s_base = gx.state("base", 10, scope="session")

    @gx.computed
    def s_doubled() -> int:
        return s_base.value * 2

    @gx.computed
    def s_quadrupled() -> int:
        return s_doubled.value * 2

    with context.activate():
        # Track a component depending on the transitive computed value
        with context.track_component("display-card"):
            assert s_quadrupled.value == 40

        # Upstream base mutation should cascade and invalidate display-card
        change = context.write(s_base, 20)
        assert s_quadrupled.value == 80
        assert len(change.invalidations) == 1
        assert change.invalidations[0].component_ids == ("display-card",)


def test_computed_cyclic_dependency_detection():
    runtime = gx.StateRuntime("app")
    context = runtime.context(session_id="s1")

    @gx.computed(key="node_a")
    def node_a() -> int:
        return node_b.value + 1

    @gx.computed(key="node_b")
    def node_b() -> int:
        return node_c.value + 1

    @gx.computed(key="node_c")
    def node_c() -> int:
        return node_a.value + 1

    with context.activate():
        with pytest.raises(gx.CyclicDependencyError, match="Cyclic dependency detected"):
            _ = node_a.value


def test_computed_read_only_enforcement():
    runtime = gx.StateRuntime("app")
    context = runtime.context(session_id="s1")

    s_val = gx.state("val", 5)

    @gx.computed
    def s_derived() -> int:
        return s_val.value * 2

    with context.activate():
        with pytest.raises(TypeError, match="read-only"):
            s_derived.value = 50

        with pytest.raises(TypeError, match="read-only"):
            context.write(s_derived, 50)


def test_batched_mutations_consolidate_invalidations():
    runtime = gx.StateRuntime("app")
    context = runtime.context(session_id="s1")

    s_a = gx.state("state_a", 1)
    s_b = gx.state("state_b", 2)
    s_c = gx.state("state_c", 3)

    with context.track_component("comp_1"):
        context.read(s_a)
        context.read(s_b)

    with context.track_component("comp_2"):
        context.read(s_b)
        context.read(s_c)

    # Perform batched writes
    with context.batch() as batch:
        context.write(s_a, 10)
        context.write(s_b, 20)
        context.write(s_c, 30)

        # Reads inside the batch see the updated values
        assert context.read(s_a) == 10
        assert context.read(s_b) == 20
        assert context.read(s_c) == 30

    # Consolidated invalidation contains exactly one merged context entry with sorted deduplicated components
    assert len(batch.consolidated_invalidations) == 1
    assert batch.consolidated_invalidations[0].context == context.identity
    assert batch.consolidated_invalidations[0].component_ids == ("comp_1", "comp_2")


def test_transactional_state_rollback_on_unhandled_exception():
    runtime = gx.StateRuntime("app")
    context = runtime.context(session_id="s1")

    s_balance_sender = gx.state("balance.sender", 100)
    s_balance_recipient = gx.state("balance.recipient", 20)

    # Failed transaction
    with pytest.raises(RuntimeError, match="Network timeout connecting to bank API"):
        with context.transaction():
            context.write(s_balance_sender, 50)
            assert context.read(s_balance_sender) == 50
            # Crash simulation
            raise RuntimeError("Network timeout connecting to bank API")

    # Values must be rolled back to their pre-transaction values
    assert context.read(s_balance_sender) == 100
    assert context.read(s_balance_recipient) == 20

    # Successful transaction commits
    with context.transaction():
        context.write(s_balance_sender, 50)
        context.write(s_balance_recipient, 70)

    assert context.read(s_balance_sender) == 50
    assert context.read(s_balance_recipient) == 70


def test_state_middleware_pipeline():
    runtime = gx.StateRuntime("app")

    audit_log: list[str] = []

    class AuditMiddleware(gx.StateMiddleware):
        def before_read(self, ref: Any, context: Any) -> None:
            audit_log.append(f"before_read:{ref.key}")

        def after_read(self, ref: Any, context: Any, value: Any) -> Any:
            audit_log.append(f"after_read:{ref.key}")
            return value

        def before_write(self, ref: Any, context: Any, value: Any, previous: Any) -> Any:
            audit_log.append(f"before_write:{ref.key}:{previous}->{value}")
            # Middleware can transform/sanitize value
            if isinstance(value, str):
                return value.strip().upper()
            return value

        def after_write(self, ref: Any, context: Any, change: Any) -> None:
            audit_log.append(f"after_write:{ref.key}:{change.value}")

    runtime.add_middleware(AuditMiddleware())
    context = runtime.context(session_id="s1")
    s_name = gx.state("user.name", "john")

    val = context.read(s_name)
    assert val == "john"
    assert "before_read:user.name" in audit_log
    assert "after_read:user.name" in audit_log

    context.write(s_name, "  alice  ")
    assert context.read(s_name) == "ALICE"
    assert "before_write:user.name:john->  alice  " in audit_log
    assert "after_write:user.name:ALICE" in audit_log


def test_command_context_batch_and_transaction():
    app = gx.App("Test App")
    s_stock = gx.state("stock", 10)

    @app.command("order.batch_buy")
    def batch_buy(ctx: gx.CommandContext):
        with ctx.batch():
            ctx.write(s_stock, ctx.read(s_stock) - 2)
            ctx.write(s_stock, ctx.read(s_stock) - 3)

    @app.command("order.failing_buy")
    def failing_buy(ctx: gx.CommandContext):
        with ctx.transaction():
            ctx.write(s_stock, 0)
            raise ValueError("Insufficient payment funds")

    ctx = app.state_context(session_id="s1")
    assert ctx.read(s_stock) == 10


def test_worker_lifecycle_hooks_and_graceful_draining():
    app = gx.App("Lifecycle App")

    events: list[str] = []

    @app.on_startup
    def startup_one():
        events.append("startup_sync")

    @app.on_startup
    async def startup_two():
        events.append("startup_async")

    @app.on_shutdown
    def shutdown_one():
        events.append("shutdown_sync")

    @app.on_shutdown
    async def shutdown_two():
        events.append("shutdown_async")

    asgi = app.asgi()
    with TestClient(asgi) as client:
        # On startup hooks should have executed
        assert events == ["startup_sync", "startup_async"]

    # On shutdown hooks execute in reverse order after client exits context
    assert "shutdown_async" in events
    assert "shutdown_sync" in events
    assert app._shutting_down is True
