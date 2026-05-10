import asyncio
import os
import tempfile
import pytest
from radui.jobs.contracts import JobStatus, JobNotFoundError, JobCapacityError
from radui.jobs.runtime import JobDefinition
from radui.jobs.sqlite import SQLiteJobBackend
from radui.state.dependencies import ContextIdentity
from radui.state.runtime import StateContext, StateRuntime


@pytest.mark.anyio
async def test_sqlite_job_backend_basic_lifecycle():
    backend = SQLiteJobBackend(":memory:")

    async def sample_task(ctx, x, y):
        await ctx.progress(50, "Halfway there")
        return {"sum": x + y}

    job_def = JobDefinition("add_numbers", sample_task, backend)

    state_runtime = StateRuntime("test-app")
    state_ctx = StateContext(
        runtime=state_runtime,
        identity=ContextIdentity(app_id="test-app", session_id="sess-1", user_id="user-1", view_id="/"),
    )

    snapshot = await backend.submit(job_def, state_ctx, (10, 20), {})
    assert snapshot.status in {JobStatus.QUEUED, JobStatus.RUNNING}
    assert snapshot.name == "add_numbers"

    # Wait for completion
    latest = None
    for _ in range(30):
        await asyncio.sleep(0.05)
        latest = backend.latest_snapshot("add_numbers", "sess-1")
        if latest and latest.status == JobStatus.SUCCEEDED:
            break

    assert latest is not None
    assert latest.status == JobStatus.SUCCEEDED
    assert latest.progress == 100
    assert latest.result_available is True

    res = backend.get_result(latest.id, "sess-1")
    assert res == {"sum": 30}

    await backend.shutdown()


@pytest.mark.anyio
async def test_sqlite_job_backend_idempotency():
    backend = SQLiteJobBackend(":memory:")

    async def sample_task(ctx):
        return "done"

    job_def = JobDefinition("task", sample_task, backend)
    state_runtime = StateRuntime("test-app")
    state_ctx = StateContext(
        runtime=state_runtime,
        identity=ContextIdentity(app_id="test-app", session_id="sess-1", user_id="u1", view_id="/"),
    )

    snap1 = await backend.submit(job_def, state_ctx, (), {}, idempotency_key="key-123")
    snap2 = await backend.submit(job_def, state_ctx, (), {}, idempotency_key="key-123")

    assert snap1.id == snap2.id
    await backend.shutdown()


@pytest.mark.anyio
async def test_sqlite_job_cancellation():
    backend = SQLiteJobBackend(":memory:")

    async def long_task(ctx):
        for _ in range(10):
            await ctx.checkpoint()
            await asyncio.sleep(0.05)
        return "finished"

    job_def = JobDefinition("long_task", long_task, backend)
    state_runtime = StateRuntime("test-app")
    state_ctx = StateContext(
        runtime=state_runtime,
        identity=ContextIdentity(app_id="test-app", session_id="sess-1", user_id="u1", view_id="/"),
    )

    snap = await backend.submit(job_def, state_ctx, (), {})
    cancelled = await backend.cancel(snap.id, "sess-1")
    assert cancelled is True

    snap_after = backend.get_snapshot(snap.id, "sess-1")
    assert snap_after.status == JobStatus.CANCELLED

    await backend.shutdown()


@pytest.mark.anyio
async def test_sqlite_job_recovery_on_startup():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "crash_test.db")
        b1 = SQLiteJobBackend(db_path=db_path)

        async def stuck_task(ctx):
            await asyncio.sleep(100)

        job_def = JobDefinition("stuck", stuck_task, b1)
        state_runtime = StateRuntime("test-app")
        state_ctx = StateContext(
            runtime=state_runtime,
            identity=ContextIdentity(app_id="test-app", session_id="sess-1", user_id="u1", view_id="/"),
        )

        snap = await b1.submit(job_def, state_ctx, (), {})
        # Cancel in-memory task to simulate sudden restart
        task = b1._tasks.get(snap.id)
        if task:
            task.cancel()
        b1._conn.close()

        # New process boots up with same db
        b2 = SQLiteJobBackend(db_path=db_path)
        await b2.startup()

        recovered_snap = b2.get_snapshot(snap.id, "sess-1")
        assert recovered_snap.status == JobStatus.FAILED
        assert recovered_snap.error_type == "ProcessRestartError"

        await b2.shutdown()
