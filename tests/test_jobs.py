from __future__ import annotations

import asyncio
import re
import time

import pytest
from starlette.testclient import TestClient

import radui as gx
from radui.jobs import JobCapacityError, JobNotFoundError, JobStatus, LocalJobBackend


_SECRET = "test-secret-that-is-long-enough-for-RADUI-jobs-123"


def _form(page_text: str, command: str):
    action = re.search(
        rf'<form[^>]*action="([^"]+)"[^>]*data-gx-command="{re.escape(command)}"[^>]*>',
        page_text,
    ).group(1)
    fields = {}
    block = re.search(
        rf'<form[^>]*data-gx-command="{re.escape(command)}"[^>]*>(.*?)</form>',
        page_text,
        re.S,
    ).group(1)
    for name, value in re.findall(
        r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', block
    ):
        fields[name] = value
    return action, fields


class ObservedApp(gx.App):
    observed_sessions: list[str] = []

    def _session(self, request):
        session_id, csrf = super()._session(request)
        self.observed_sessions.append(session_id)
        return session_id, csrf


def make_app(handler=None):
    app = ObservedApp(
        "RADUI Jobs",
        app_id="RADUI-jobs-tests",
        session_secret=_SECRET,
    )

    @app.job("reports.generate")
    async def generate(ctx, topic: str):
        await ctx.progress(15, "Collecting sources")
        await asyncio.sleep(0.01)
        await ctx.progress(65, "Writing report")
        await asyncio.sleep(0.01)
        if handler is not None:
            return await handler(ctx, topic)
        return f"Report for {topic}"

    @app.command("reports.start")
    async def start(ctx):
        await generate.submit(
            ctx,
            ctx.form_data["reports.topic"],
            idempotency_key=ctx.action_id,
        )

    @app.page("/", title="Job test")
    def home():
        topic = gx.state("reports.topic", "radui", scope="session")
        return gx.column(
            gx.form(
                "reports.start",
                gx.input("Topic", bind=topic),
                gx.button("Generate report"),
            ),
            gx.job_panel(generate, label="Report generation"),
        )

    return app, generate


def _latest(app: ObservedApp, session_id: str, name: str = "reports.generate"):
    snapshot = app.jobs.latest_snapshot(name, session_id)
    assert snapshot is not None
    return snapshot


def _wait_terminal(app: ObservedApp, session_id: str, timeout: float = 2.0, name: str = "reports.generate"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = app.jobs.latest_snapshot(name, session_id)
        if snapshot is not None and snapshot.status.terminal:
            return snapshot
        time.sleep(0.01)
    raise AssertionError("job did not reach a terminal state")


def test_job_submission_progress_result_and_job_panel_refresh():
    app, generate = make_app()
    with TestClient(app.asgi()) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "No task has been submitted" in page.text
        action, fields = _form(page.text, "reports.start")
        response = client.post(action, data=fields)
        assert response.status_code == 200
        session_id = app.observed_sessions[-1]
        snapshot = _wait_terminal(app, session_id)
        assert snapshot.status == JobStatus.SUCCEEDED
        assert snapshot.progress == 100
        assert snapshot.result_text == "Report for radui"
        rendered = client.get("/").text
        assert "Succeeded" in rendered
        assert "Report for radui" in rendered
        assert "reports.generate" in app.to_ir().model_dump_json()
        assert any(
            record.event == "invalidate"
            and "gx-job-reports.generate" in record.data.get("component_ids", [])
            for record in app.events.history_snapshot(session_id)
        )


def test_job_submit_requires_RADUI_context():
    app, generate = make_app()

    async def run():
        with pytest.raises(TypeError, match="CommandContext or StateContext"):
            await generate.submit("not-a-context", "topic")

    asyncio.run(run())


def test_job_idempotency_key_returns_existing_job():
    app, generate = make_app()
    context = app.state_context(session_id="session-job-dedupe", view_id="/")

    async def run():
        first = await generate.submit(context, "same topic", idempotency_key="same-action")
        second = await generate.submit(context, "same topic", idempotency_key="same-action")
        assert first.id == second.id
        deadline = asyncio.get_running_loop().time() + 2
        while asyncio.get_running_loop().time() < deadline:
            snapshot = generate.get(context, first.id)
            if snapshot.status.terminal:
                break
            await asyncio.sleep(0.01)
        assert generate.get(context, first.id).status == JobStatus.SUCCEEDED

    asyncio.run(run())


def test_job_result_can_only_be_retrieved_by_owning_session():
    app, generate = make_app()
    context = app.state_context(session_id="job-owner", view_id="/")

    async def run():
        submitted = await generate.submit(context, "private topic")
        deadline = asyncio.get_running_loop().time() + 2
        while asyncio.get_running_loop().time() < deadline:
            current = generate.get(context, submitted.id)
            if current.status.terminal:
                break
            await asyncio.sleep(0.01)
        assert generate.get_result(context, submitted.id) == "Report for private topic"
        other = app.state_context(session_id="other-session", view_id="/")
        with pytest.raises(JobNotFoundError):
            generate.get(other, submitted.id)

    asyncio.run(run())


def test_failed_job_does_not_expose_exception_message_to_browser():
    async def failure(ctx, topic):
        raise ValueError("database password must not leak")

    app, _ = make_app(failure)
    with TestClient(app.asgi()) as client:
        page = client.get("/")
        action, fields = _form(page.text, "reports.start")
        client.post(action, data=fields)
        session_id = app.observed_sessions[-1]
        snapshot = _wait_terminal(app, session_id)
        assert snapshot.status == JobStatus.FAILED
        assert snapshot.error_type == "ValueError"
        rendered = client.get("/").text
        assert "ValueError" in rendered
        assert "database password" not in rendered


def test_job_cancel_endpoint_requires_csrf_and_updates_panel():
    app, generate = make_app()

    async def slow(ctx, topic):
        await ctx.progress(5, "Waiting for cancellation")
        await asyncio.sleep(30)
        return topic

    generate.handler = slow
    with TestClient(app.asgi()) as client:
        page = client.get("/")
        action, fields = _form(page.text, "reports.start")
        client.post(action, data=fields)
        session_id = app.observed_sessions[-1]
        snapshot = _latest(app, session_id)
        running_page = client.get("/")
        assert "data-gx-job-cancel" in running_page.text
        assert f"/_gx/jobs/{snapshot.id}/cancel" in running_page.text

        rejected = client.post(f"/_gx/jobs/{snapshot.id}/cancel")
        assert rejected.status_code == 403

        accepted = client.post(
            f"/_gx/jobs/{snapshot.id}/cancel",
            headers={"X-GX-CSRF": fields["_csrf"]},
        )
        assert accepted.status_code == 200
        assert accepted.json()["ok"] is True
        final = _wait_terminal(app, session_id)
        assert final.status == JobStatus.CANCELLED


def test_job_cancel_cannot_cross_session_boundary():
    app, _ = make_app()
    client_a = TestClient(app.asgi())
    client_b = TestClient(app.asgi())
    try:
        page_a = client_a.get("/")
        session_a = app.observed_sessions[-1]
        page_b = client_b.get("/")
        action, fields = _form(page_a.text, "reports.start")
        client_a.post(action, data=fields)
        snapshot = _latest(app, session_a)
        csrf_b = re.search(r'name="_csrf" value="([^"]+)"', page_b.text).group(1)
        response = client_b.post(
            f"/_gx/jobs/{snapshot.id}/cancel",
            headers={"X-GX-CSRF": csrf_b},
        )
        assert response.status_code == 404
    finally:
        client_a.close()
        client_b.close()


def test_job_panel_handle_is_excluded_from_serialized_ir():
    app, _ = make_app()
    dumped = app.to_ir().model_dump(mode="json")
    assert dumped["version"] == "0.4"
    assert dumped["jobs"] == [{"id": "reports.generate"}]
    assert "job_handle" not in str(dumped)


def test_local_job_backend_enforces_active_capacity():
    # The limit is tested without starting a handler by occupying the only slot
    # with a coroutine that waits until the test releases it.
    app = gx.App("Capacity", app_id="capacity-test", session_secret=_SECRET)
    app.jobs.max_active = 1

    @app.job("waiter")
    async def waiter(ctx):
        await asyncio.sleep(10)

    context_a = app.state_context(session_id="capacity-a", view_id="/")
    context_b = app.state_context(session_id="capacity-b", view_id="/")

    async def run():
        first = await waiter.submit(context_a)
        await asyncio.sleep(0)
        with pytest.raises(JobCapacityError):
            await waiter.submit(context_b)
        await app.jobs.cancel(first.id, "capacity-a")
        await asyncio.sleep(0)
        await app.jobs.shutdown()

    asyncio.run(run())


def test_job_panel_rejects_unregistered_job_handle():
    with pytest.raises((TypeError, ValueError)):
        gx.job_panel(object())


def test_job_handler_must_be_async():
    app = gx.App("Invalid job", app_id="invalid-job", session_secret=_SECRET)
    with pytest.raises(TypeError, match="async functions"):
        @app.job("not.async")
        def sync_job(ctx):
            return None


def test_job_result_storage_is_bounded_and_reports_unavailable_results():
    app, generate = make_app()
    context = app.state_context(session_id="large-result", view_id="/")

    async def run():
        submitted = await generate.submit(context, "large")
        deadline = asyncio.get_running_loop().time() + 2
        while asyncio.get_running_loop().time() < deadline:
            current = generate.get(context, submitted.id)
            if current.status.terminal:
                break
            await asyncio.sleep(0.01)
        return generate.get(context, submitted.id)

    # Replace the handler with a result larger than the local result retention cap.
    async def large_result(ctx, topic):
        return {"report": "x" * 70_000}

    generate.handler = large_result
    snapshot = asyncio.run(run())
    assert snapshot.status == JobStatus.SUCCEEDED
    assert snapshot.result_available is False
    assert snapshot.result_text is not None and len(snapshot.result_text) <= 2_001
    with pytest.raises(RuntimeError, match="not retained"):
        generate.get_result(context, snapshot.id)


def test_job_handler_state_writes_publish_dependency_invalidations():
    app = ObservedApp("Job state", app_id="job-state", session_secret=_SECRET)
    progress_text = gx.state("job.progress", "Waiting", scope="session")

    @app.job("progress.run")
    async def run_job(ctx):
        progress_text.value = "Started"
        await ctx.progress(50, "Halfway")
        progress_text.value = "Finished"
        return "ok"

    @app.command("progress.submit")
    async def submit(ctx):
        await run_job.submit(ctx, idempotency_key=ctx.action_id)

    @app.page("/")
    def home():
        return gx.column(
            gx.text(bind=progress_text, id="progress-label"),
            gx.form("progress.submit", gx.button("Run")),
            gx.job_panel(run_job),
        )

    with TestClient(app.asgi()) as client:
        page = client.get("/")
        action, fields = _form(page.text, "progress.submit")
        response = client.post(action, data=fields)
        assert response.status_code == 200
        session_id = app.observed_sessions[-1]
        snapshot = _wait_terminal(app, session_id, name="progress.run")
        assert snapshot.status == JobStatus.SUCCEEDED
        invalidations = [
            record for record in app.events.history_snapshot(session_id)
            if record.event == "invalidate"
        ]
        assert any("progress-label" in record.data.get("component_ids", []) for record in invalidations)
        refreshed = client.get("/")
        assert "Finished" in refreshed.text


def test_app_shutdown_marks_unfinished_jobs_cancelled():
    app, generate = make_app()

    async def slow(ctx, topic):
        await ctx.progress(1, "Starting")
        await asyncio.sleep(30)
        return topic

    generate.handler = slow
    client = TestClient(app.asgi())
    with client:
        page = client.get("/")
        action, fields = _form(page.text, "reports.start")
        client.post(action, data=fields)
        session_id = app.observed_sessions[-1]
        snapshot = _latest(app, session_id)
        assert snapshot.status in {JobStatus.QUEUED, JobStatus.RUNNING}
    assert app.jobs.get_snapshot(snapshot.id, session_id).status == JobStatus.CANCELLED


def test_app_accepts_a_pluggable_job_backend():
    backend = LocalJobBackend(max_concurrent=1)
    app = gx.App(
        "Injected backend",
        app_id="injected-backend",
        session_secret=_SECRET,
        job_backend=backend,
    )

    @app.job("injected.run")
    async def injected(ctx):
        await ctx.progress(100, "Done")
        return "injected-result"

    context = app.state_context(session_id="injected-owner", view_id="/")

    async def run():
        submitted = await injected.submit(context)
        deadline = asyncio.get_running_loop().time() + 2
        while asyncio.get_running_loop().time() < deadline:
            snapshot = injected.get(context, submitted.id)
            if snapshot.status.terminal:
                break
            await asyncio.sleep(0.01)
        assert injected.get(context, submitted.id).status == JobStatus.SUCCEEDED

    asyncio.run(run())


def test_same_idempotency_key_with_different_payload_is_rejected():
    app, generate = make_app()
    context = app.state_context(session_id="conflicting-idempotency", view_id="/")

    async def run():
        await generate.submit(context, "first", idempotency_key="action-1")
        with pytest.raises(ValueError, match="different job payload"):
            await generate.submit(context, "second", idempotency_key="action-1")
        await app.jobs.shutdown()

    asyncio.run(run())


def test_job_arguments_must_be_json_serializable_and_bounded():
    app, generate = make_app()
    context = app.state_context(session_id="invalid-payload", view_id="/")

    async def run():
        with pytest.raises(TypeError, match="JSON-serializable"):
            await generate.submit(context, object())
        with pytest.raises(ValueError, match="256 KiB"):
            await generate.submit(context, "x" * (300 * 1024))

    asyncio.run(run())


def test_job_state_changes_are_published_even_when_handler_fails():
    app = ObservedApp("Failed job state", app_id="failed-job-state", session_secret=_SECRET)
    status = gx.state("pipeline.status", "waiting", scope="session")

    @app.job("pipeline.run")
    async def run_pipeline(ctx):
        status.value = "started"
        await ctx.progress(10, "Started")
        raise RuntimeError("synthetic failure")

    @app.command("pipeline.submit")
    async def submit(ctx):
        await run_pipeline.submit(ctx, idempotency_key=ctx.action_id)

    @app.page("/")
    def home():
        return gx.column(
            gx.text(bind=status, id="pipeline-status"),
            gx.form("pipeline.submit", gx.button("Run pipeline")),
            gx.job_panel(run_pipeline),
        )

    with TestClient(app.asgi()) as client:
        page = client.get("/")
        action, fields = _form(page.text, "pipeline.submit")
        client.post(action, data=fields)
        session_id = app.observed_sessions[-1]
        snapshot = _wait_terminal(app, session_id, name="pipeline.run")
        assert snapshot.status == JobStatus.FAILED
        records = app.events.history_snapshot(session_id)
        assert any(
            record.event == "invalidate"
            and "pipeline-status" in record.data.get("component_ids", [])
            for record in records
        )
        assert "started" in client.get("/").text


def test_handler_that_suppresses_task_cancel_still_ends_as_cancelled():
    app, generate = make_app()

    async def suppress_cancel(ctx, topic):
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            # A handler may catch cancellation, but RADUI must not report success.
            return {"topic": topic, "ignored": True}

    generate.handler = suppress_cancel
    context = app.state_context(session_id="suppress-cancel", view_id="/")

    async def run():
        submitted = await generate.submit(context, "cancel me")
        await asyncio.sleep(0.01)
        assert await generate.cancel(context, submitted.id) is True
        deadline = asyncio.get_running_loop().time() + 2
        while asyncio.get_running_loop().time() < deadline:
            snapshot = generate.get(context, submitted.id)
            if snapshot.status.terminal:
                break
            await asyncio.sleep(0.01)
        assert generate.get(context, submitted.id).status == JobStatus.CANCELLED

    asyncio.run(run())


def test_job_result_preview_is_html_escaped():
    app, generate = make_app()

    async def html_result(ctx, topic):
        return "<script>alert('xss')</script>"

    generate.handler = html_result
    with TestClient(app.asgi()) as client:
        page = client.get("/")
        action, fields = _form(page.text, "reports.start")
        client.post(action, data=fields)
        session_id = app.observed_sessions[-1]
        snapshot = _wait_terminal(app, session_id)
        assert snapshot.status == JobStatus.SUCCEEDED
        rendered = client.get("/").text
        assert "&lt;script&gt;" in rendered
        assert "<script>alert('xss')</script>" not in rendered
