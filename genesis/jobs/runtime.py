from __future__ import annotations

import asyncio
import hashlib
import logging
import json
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Protocol
from weakref import WeakKeyDictionary

from radui.jobs.contracts import (
    JobCancelledError,
    JobCapacityError,
    JobNotFoundError,
    JobSnapshot,
    JobStatus,
)
from radui.state.runtime import StateChange, StateContext

_LOGGER = logging.getLogger("radui.jobs")
_RESULT_TEXT_LIMIT = 2_000
_MESSAGE_LIMIT = 240
_MAX_RESULT_BYTES = 64 * 1024
_MAX_PAYLOAD_BYTES = 256 * 1024


def _bounded_result(value: Any) -> tuple[Any, bool]:
    """Retain only detached JSON-compatible results under a small memory limit."""
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError, OverflowError):
        return None, False
    if len(encoded.encode("utf-8")) > _MAX_RESULT_BYTES:
        return None, False
    return json.loads(encoded), True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_result_text(value: Any) -> str:
    try:
        text = str(value)
    except Exception:
        text = f"<{type(value).__name__} result>"
    if len(text) > _RESULT_TEXT_LIMIT:
        return text[:_RESULT_TEXT_LIMIT] + "…"
    return text


class JobContext:
    """Execution context supplied to an asynchronous job handler."""

    def __init__(
        self,
        *,
        job_id: str,
        state: StateContext,
        backend: JobBackend,
        cancelled: asyncio.Event,
    ) -> None:
        self.job_id = job_id
        self.state = state
        self.session_id = state.session_id
        self.user_id = state.user_id
        self.tenant_id = state.tenant_id
        self._backend = backend
        self._cancelled = cancelled

    async def progress(self, percent: int, message: str = "") -> None:
        """Publish monotonic integer progress in the range 0–100."""
        if isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= 100:
            raise ValueError("progress percent must be an integer from 0 to 100")
        self.raise_if_cancelled()
        await self._backend.update_progress(self.job_id, percent, message)

    def raise_if_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise JobCancelledError("job cancellation requested")

    async def checkpoint(self) -> None:
        """Cooperative cancellation checkpoint for long-running handlers."""
        self.raise_if_cancelled()
        await asyncio.sleep(0)
        self.raise_if_cancelled()


class JobBackend(Protocol):
    def bind_callbacks(
        self,
        *,
        on_update: Callable[[JobSnapshot], None],
        on_state_changes: Callable[[list[StateChange], StateContext], None],
    ) -> None: ...

    def reconcile_watchers(
        self, session_id: str, view_id: str, job_components: dict[str, set[str]]
    ) -> None: ...

    def observers(self, session_id: str, job_name: str) -> list[tuple[str, tuple[str, ...]]]: ...

    def drop_session(self, session_id: str) -> None: ...

    async def startup(self) -> None: ...

    async def shutdown(self) -> None: ...

    async def submit(
        self,
        definition: JobDefinition,
        state: StateContext,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> JobSnapshot: ...

    def latest_snapshot(self, job_name: str, session_id: str) -> JobSnapshot | None: ...

    def get_snapshot(self, job_id: str, session_id: str) -> JobSnapshot: ...

    def get_result(self, job_id: str, session_id: str) -> Any: ...

    async def cancel(self, job_id: str, session_id: str) -> bool: ...

    async def update_progress(self, job_id: str, percent: int, message: str = "") -> None: ...


class JobDefinition:
    """Registered job handler exposed to application code and JobPanel."""

    def __init__(
        self,
        name: str,
        handler: Callable[..., Awaitable[Any]],
        backend: JobBackend,
    ) -> None:
        self.name = name
        self.handler = handler
        self.backend = backend

    async def submit(
        self,
        context: Any,
        *args: Any,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> JobSnapshot:
        state = getattr(context, "state", context)
        if not isinstance(state, StateContext):
            raise TypeError("job.submit requires a RADUI CommandContext or StateContext")
        try:
            encoded = json.dumps(
                {"args": args, "kwargs": kwargs},
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
        except (TypeError, ValueError, OverflowError) as exc:
            raise TypeError("job arguments must be JSON-serializable values") from exc
        if len(encoded.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
            raise ValueError("job arguments exceed the 256 KiB payload limit")
        detached = json.loads(encoded)
        return await self.backend.submit(
            self,
            state,
            tuple(detached["args"]),
            dict(detached["kwargs"]),
            idempotency_key=idempotency_key,
        )

    def latest_snapshot(self, session_id: str) -> JobSnapshot | None:
        return self.backend.latest_snapshot(self.name, session_id)

    def get(self, context: Any, job_id: str) -> JobSnapshot:
        state = getattr(context, "state", context)
        if not isinstance(state, StateContext):
            raise TypeError("job.get requires a RADUI CommandContext or StateContext")
        return self.backend.get_snapshot(job_id, state.session_id)

    def get_result(self, context: Any, job_id: str) -> Any:
        state = getattr(context, "state", context)
        if not isinstance(state, StateContext):
            raise TypeError("job.get_result requires a RADUI CommandContext or StateContext")
        getter = getattr(self.backend, "get_result", None)
        if getter is None:
            raise NotImplementedError("this job backend does not expose synchronous result retrieval")
        return getter(job_id, state.session_id)

    async def cancel(self, context: Any, job_id: str) -> bool:
        state = getattr(context, "state", context)
        if not isinstance(state, StateContext):
            raise TypeError("job.cancel requires a RADUI CommandContext or StateContext")
        return await self.backend.cancel(job_id, state.session_id)


class LocalJobBackend:
    """Process-local async job executor for development and single-worker use.

    It deliberately provides no persistence, cross-process coordination or
    restart recovery. Applications needing those properties should supply a
    different JobBackend implementation.
    """

    def __init__(
        self,
        *,
        on_update: Callable[[JobSnapshot], None] | None = None,
        on_state_changes: Callable[[list[StateChange], StateContext], None] | None = None,
        max_concurrent: int = 4,
        max_active: int = 64,
        max_records: int = 512,
    ) -> None:
        if min(max_concurrent, max_active, max_records) < 1:
            raise ValueError("job backend limits must be positive")
        self._on_update = on_update or (lambda _snapshot: None)
        self._on_state_changes = on_state_changes or (lambda _changes, _context: None)
        self.max_concurrent = max_concurrent
        self.max_active = max_active
        self.max_records = max_records
        self._lock = threading.RLock()
        self._records: OrderedDict[str, _JobRecord] = OrderedDict()
        self._latest: dict[tuple[str, str], str] = {}
        self._idempotency: dict[tuple[str, str, str], str] = {}
        self._watchers: dict[tuple[str, str], dict[str, set[str]]] = {}
        self._semaphores: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = WeakKeyDictionary()
        self._closed = False

    def bind_callbacks(
        self,
        *,
        on_update: Callable[[JobSnapshot], None],
        on_state_changes: Callable[[list[StateChange], StateContext], None],
    ) -> None:
        self._on_update = on_update
        self._on_state_changes = on_state_changes

    async def submit(
        self,
        definition: JobDefinition,
        state: StateContext,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> JobSnapshot:
        if self._closed:
            raise RuntimeError("job backend is shut down")
        if idempotency_key is not None:
            if not idempotency_key or len(idempotency_key) > 128:
                raise ValueError("idempotency_key must contain 1–128 characters")
            dedupe_key = (state.session_id, definition.name, idempotency_key)
        else:
            dedupe_key = None
        payload_hash = hashlib.sha256(
            json.dumps([args, kwargs], ensure_ascii=False, allow_nan=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

        with self._lock:
            if dedupe_key is not None:
                existing_id = self._idempotency.get(dedupe_key)
                if existing_id is not None and existing_id in self._records:
                    existing = self._records[existing_id]
                    if existing.payload_hash != payload_hash:
                        raise ValueError("idempotency key was already used with a different job payload")
                    return existing.snapshot
            active = sum(
                1 for record in self._records.values() if not record.snapshot.status.terminal
            )
            if active >= self.max_active:
                raise JobCapacityError("local job capacity has been reached")
            now = _now()
            job_id = uuid.uuid4().hex
            snapshot = JobSnapshot(
                id=job_id,
                name=definition.name,
                status=JobStatus.QUEUED,
                session_id=state.session_id,
                user_id=state.user_id,
                progress=None,
                message="Queued",
                result_text=None,
                result_available=False,
                error_type=None,
                created_at=now,
                updated_at=now,
                tenant_id=state.tenant_id,
            )
            record = _JobRecord(snapshot=snapshot, result=None, task=None, cancelled=None, payload_hash=payload_hash)
            self._records[job_id] = record
            self._latest[(state.session_id, definition.name)] = job_id
            if dedupe_key is not None:
                self._idempotency[dedupe_key] = job_id
            self._prune_locked()
            self._notify(snapshot)

            task = asyncio.create_task(
                self._run(job_id, definition, state, args, kwargs),
                name=f"RADUI-job-{definition.name}-{job_id[:8]}",
            )
            record.task = task
            return snapshot

    async def _run(
        self,
        job_id: str,
        definition: JobDefinition,
        state: StateContext,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        loop = asyncio.get_running_loop()
        with self._lock:
            semaphore = self._semaphores.get(loop)
            if semaphore is None:
                semaphore = asyncio.Semaphore(self.max_concurrent)
                self._semaphores[loop] = semaphore
            record = self._records.get(job_id)
            if record is None or record.snapshot.status.terminal:
                return
            record.started = True
            cancelled = asyncio.Event()
            record.cancelled = cancelled

        acquired = False
        changes: list[StateChange] = []
        try:
            await semaphore.acquire()
            acquired = True
            self._transition(
                job_id,
                status=JobStatus.RUNNING,
                progress=0,
                message="Running",
            )
            context = JobContext(
                job_id=job_id,
                state=state,
                backend=self,
                cancelled=cancelled,
            )
            with state.activate(), state.capture_changes() as changes:
                result = await definition.handler(context, *args, **kwargs)
            if cancelled.is_set():
                raise JobCancelledError("job cancellation requested")
            stored_result, result_available = _bounded_result(result)
            self._transition(
                job_id,
                status=JobStatus.SUCCEEDED,
                progress=100,
                message="Completed",
                result=stored_result,
                result_available=result_available,
                result_text=_safe_result_text(result) if result is not None else None,
            )
        except (asyncio.CancelledError, JobCancelledError):
            cancelled.set()
            self._transition(
                job_id,
                status=JobStatus.CANCELLED,
                message="Cancelled",
            )
        except Exception as exc:
            _LOGGER.exception("RADUI job %s (%s) failed", job_id, definition.name)
            self._transition(
                job_id,
                status=JobStatus.FAILED,
                message="Failed",
                error_type=type(exc).__name__,
            )
        finally:
            if changes:
                try:
                    self._on_state_changes(list(changes), state)
                except Exception:
                    _LOGGER.exception("Job state-change notification failed")
            if acquired:
                semaphore.release()

    async def update_progress(self, job_id: str, percent: int, message: str = "") -> None:
        cleaned = str(message).strip()[:_MESSAGE_LIMIT]
        self._transition(
            job_id,
            status=JobStatus.RUNNING,
            progress=percent,
            message=cleaned or "Working",
        )

    def _transition(
        self,
        job_id: str,
        *,
        status: JobStatus,
        progress: int | None = None,
        message: str | None = None,
        result: Any = None,
        result_text: str | None = None,
        result_available: bool = False,
        error_type: str | None = None,
    ) -> JobSnapshot | None:
        with self._lock:
            record = self._records.get(job_id)
            if record is None or record.snapshot.status.terminal:
                return None
            previous = record.snapshot
            if status == JobStatus.RUNNING and previous.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
                raise RuntimeError("invalid job state transition")
            if progress is not None and previous.progress is not None and progress < previous.progress:
                raise ValueError("job progress cannot move backwards")
            snapshot = replace(
                previous,
                status=status,
                progress=progress if progress is not None else previous.progress,
                message=message if message is not None else previous.message,
                result_text=result_text if result_text is not None else previous.result_text,
                result_available=result_available if status == JobStatus.SUCCEEDED else previous.result_available,
                error_type=error_type,
                updated_at=_now(),
            )
            record.snapshot = snapshot
            if status == JobStatus.SUCCEEDED:
                record.result = result
            self._records.move_to_end(job_id)
            self._notify(snapshot)
            self._prune_locked()
            return snapshot

    def _notify(self, snapshot: JobSnapshot) -> None:
        # Callbacks must be fast and non-blocking; App publishes a bounded event.
        try:
            self._on_update(snapshot)
        except Exception:
            _LOGGER.exception("Job update notification failed")

    def latest_snapshot(self, job_name: str, session_id: str) -> JobSnapshot | None:
        with self._lock:
            job_id = self._latest.get((session_id, job_name))
            record = self._records.get(job_id) if job_id else None
            return record.snapshot if record else None

    def get_snapshot(self, job_id: str, session_id: str, tenant_id: str | None = None) -> JobSnapshot:
        with self._lock:
            record = self._records.get(job_id)
            if record is None or record.snapshot.session_id != session_id:
                raise JobNotFoundError("job not found")
            if tenant_id is not None and record.snapshot.tenant_id is not None and record.snapshot.tenant_id != tenant_id:
                raise JobNotFoundError("job not found")
            return record.snapshot

    def get_result(self, job_id: str, session_id: str, tenant_id: str | None = None) -> Any:
        with self._lock:
            record = self._records.get(job_id)
            if record is None or record.snapshot.session_id != session_id:
                raise JobNotFoundError("job not found")
            if tenant_id is not None and record.snapshot.tenant_id is not None and record.snapshot.tenant_id != tenant_id:
                raise JobNotFoundError("job not found")
            if record.snapshot.status != JobStatus.SUCCEEDED:
                raise RuntimeError("job has not completed successfully")
            if not record.snapshot.result_available:
                raise RuntimeError(
                    "job result is not retained by this backend; persist large or custom results externally"
                )
            return record.result

    async def cancel(self, job_id: str, session_id: str, tenant_id: str | None = None) -> bool:
        with self._lock:
            record = self._records.get(job_id)
            if record is None or record.snapshot.session_id != session_id:
                raise JobNotFoundError("job not found")
            if tenant_id is not None and record.snapshot.tenant_id is not None and record.snapshot.tenant_id != tenant_id:
                raise JobNotFoundError("job not found")
            if record.snapshot.status.terminal:
                return False
            task = record.task
            started = record.started
            if record.cancelled is not None:
                record.cancelled.set()
            # A task cancelled before its first event-loop turn may never enter
            # _run(); mark that queued record terminal here. Running jobs become
            # cancelled only when the handler actually exits its task.
            if not started:
                self._transition(job_id, status=JobStatus.CANCELLED, message="Cancelled")
        if task is not None and not task.done():
            task.cancel()
        return True

    def reconcile_watchers(
        self,
        session_id: str,
        view_id: str,
        job_components: dict[str, set[str]],
    ) -> None:
        key = (session_id, view_id)
        normalized = {name: set(ids) for name, ids in job_components.items() if ids}
        with self._lock:
            if normalized:
                self._watchers[key] = normalized
            else:
                self._watchers.pop(key, None)

    def observers(self, session_id: str, job_name: str) -> list[tuple[str, tuple[str, ...]]]:
        with self._lock:
            return [
                (view_id, tuple(sorted(components[job_name])))
                for (owner_session, view_id), components in self._watchers.items()
                if owner_session == session_id and job_name in components
            ]

    def drop_session(self, session_id: str) -> None:
        with self._lock:
            jobs = [
                (job_id, record.task)
                for job_id, record in self._records.items()
                if record.snapshot.session_id == session_id
            ]
            for job_id, _ in jobs:
                record = self._records.get(job_id)
                if record is not None and record.cancelled is not None:
                    record.cancelled.set()
                self._records.pop(job_id, None)
            for key in [key for key in self._latest if key[0] == session_id]:
                self._latest.pop(key, None)
            for key in [key for key in self._idempotency if key[0] == session_id]:
                self._idempotency.pop(key, None)
            for key in [key for key in self._watchers if key[0] == session_id]:
                self._watchers.pop(key, None)
        for _, task in jobs:
            if task is not None and not task.done():
                try:
                    task.get_loop().call_soon_threadsafe(task.cancel)
                except RuntimeError:
                    pass

    def _prune_locked(self) -> None:
        while len(self._records) > self.max_records:
            removable = next(
                (job_id for job_id, record in self._records.items() if record.snapshot.status.terminal),
                None,
            )
            if removable is None:
                break
            self._records.pop(removable, None)
            for key, value in tuple(self._latest.items()):
                if value == removable:
                    self._latest.pop(key, None)
            for key, value in tuple(self._idempotency.items()):
                if value == removable:
                    self._idempotency.pop(key, None)

    async def shutdown(self) -> None:
        self._closed = True
        with self._lock:
            active = [
                (job_id, record.task)
                for job_id, record in self._records.items()
                if not record.snapshot.status.terminal
            ]
            for job_id, _task in active:
                record = self._records.get(job_id)
                if record is not None and record.cancelled is not None:
                    record.cancelled.set()
                self._transition(job_id, status=JobStatus.CANCELLED, message="Application shutdown")
        tasks = [task for _job_id, task in active if task is not None and not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def startup(self) -> None:
        self._closed = False


@dataclass
class _JobRecord:
    snapshot: JobSnapshot
    result: Any
    task: asyncio.Task[None] | None
    cancelled: asyncio.Event | None
    payload_hash: str
    started: bool = False
