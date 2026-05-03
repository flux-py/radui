from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sqlite3
import threading
import uuid
from collections import OrderedDict
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable
from weakref import WeakKeyDictionary

from radui.jobs.contracts import (
    JobCancelledError,
    JobCapacityError,
    JobNotFoundError,
    JobSnapshot,
    JobStatus,
)
from radui.jobs.runtime import (
    JobBackend,
    JobContext,
    JobDefinition,
    _bounded_result,
    _MESSAGE_LIMIT,
    _now,
    _safe_result_text,
)
from radui.state.runtime import StateChange, StateContext

_LOGGER = logging.getLogger("radui.jobs.sqlite")


class SQLiteJobBackend:
    """Persistent, WAL-mode SQLite job execution backend for radui.

    Guarantees job durability, crash recovery, and multi-process query capability
    while maintaining zero external dependencies.
    """

    def __init__(
        self,
        db_path: str = ":memory:",
        *,
        wal: bool = True,
        max_concurrent: int = 4,
        max_active: int = 64,
        max_records: int = 512,
        on_update: Callable[[JobSnapshot], None] | None = None,
        on_state_changes: Callable[[list[StateChange], StateContext], None] | None = None,
    ) -> None:
        if min(max_concurrent, max_active, max_records) < 1:
            raise ValueError("job backend limits must be positive")
        self.db_path = db_path
        self.wal = wal
        self.max_concurrent = max_concurrent
        self.max_active = max_active
        self.max_records = max_records
        self._on_update = on_update or (lambda _snapshot: None)
        self._on_state_changes = on_state_changes or (lambda _changes, _context: None)
        self._lock = threading.RLock()
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._cancellation_events: dict[str, asyncio.Event] = {}
        self._watchers: dict[tuple[str, str], dict[str, set[str]]] = {}
        self._semaphores: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = WeakKeyDictionary()
        self._closed = False

        # Initialize SQLite database
        self._conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            isolation_level=None,  # Autocommit mode
        )
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            if self.wal and self.db_path != ":memory:":
                try:
                    cur.execute("PRAGMA journal_mode=WAL;")
                    cur.execute("PRAGMA synchronous=NORMAL;")
                except Exception as ex:
                    _LOGGER.warning("Could not enable WAL mode: %s", ex)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS RADUI_jobs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    user_id TEXT,
                    progress INTEGER,
                    message TEXT,
                    result_text TEXT,
                    result_json TEXT,
                    result_available INTEGER,
                    error_type TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    idempotency_key TEXT,
                    tenant_id TEXT DEFAULT '_default'
                );
            """)
            try:
                cur.execute("ALTER TABLE RADUI_jobs ADD COLUMN tenant_id TEXT DEFAULT '_default';")
            except Exception:
                pass
            cur.execute("CREATE INDEX IF NOT EXISTS idx_gx_jobs_sess ON RADUI_jobs (session_id, name);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_gx_jobs_idem ON RADUI_jobs (session_id, name, idempotency_key);")
            cur.close()

    def bind_callbacks(
        self,
        *,
        on_update: Callable[[JobSnapshot], None],
        on_state_changes: Callable[[list[StateChange], StateContext], None],
    ) -> None:
        self._on_update = on_update
        self._on_state_changes = on_state_changes

    def reconcile_watchers(
        self, session_id: str, view_id: str, job_components: dict[str, set[str]]
    ) -> None:
        with self._lock:
            key = (session_id, view_id)
            if not job_components:
                self._watchers.pop(key, None)
                return
            self._watchers[key] = {k: set(v) for k, v in job_components.items()}

    def observers(self, session_id: str, job_name: str) -> list[tuple[str, tuple[str, ...]]]:
        with self._lock:
            results: list[tuple[str, tuple[str, ...]]] = []
            for (sid, view_id), job_map in self._watchers.items():
                if sid == session_id and job_name in job_map:
                    results.append((view_id, tuple(sorted(job_map[job_name]))))
            return sorted(results)

    def drop_session(self, session_id: str) -> None:
        with self._lock:
            keys = [k for k in self._watchers if k[0] == session_id]
            for k in keys:
                self._watchers.pop(k, None)

    async def startup(self) -> None:
        """Mark any leftover un-terminated jobs from previous processes as failed on startup."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "UPDATE RADUI_jobs SET status = ?, error_type = ?, message = ?, updated_at = ? WHERE status IN (?, ?)",
                (
                    JobStatus.FAILED.value,
                    "ProcessRestartError",
                    "Interrupted by server restart",
                    _now(),
                    JobStatus.QUEUED.value,
                    JobStatus.RUNNING.value,
                ),
            )
            cur.close()

    async def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    def _row_to_snapshot(self, row: sqlite3.Row) -> JobSnapshot:
        tenant_id = row["tenant_id"] if "tenant_id" in row.keys() else None
        return JobSnapshot(
            id=row["id"],
            name=row["name"],
            status=JobStatus(row["status"]),
            session_id=row["session_id"],
            user_id=row["user_id"],
            progress=row["progress"],
            message=row["message"] or "",
            result_text=row["result_text"],
            result_available=bool(row["result_available"]),
            error_type=row["error_type"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            tenant_id=tenant_id,
        )

    def _active_count(self) -> int:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM RADUI_jobs WHERE status IN (?, ?)",
            (JobStatus.QUEUED.value, JobStatus.RUNNING.value),
        )
        count = cur.fetchone()[0]
        cur.close()
        return count

    async def submit(
        self,
        definition: JobDefinition,
        state: StateContext,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> JobSnapshot:
        with self._lock:
            if self._closed:
                raise RuntimeError("Job backend is closed")

            # Check idempotency
            if idempotency_key is not None:
                cur = self._conn.cursor()
                cur.execute(
                    "SELECT * FROM RADUI_jobs WHERE session_id = ? AND name = ? AND idempotency_key = ? ORDER BY created_at DESC LIMIT 1",
                    (state.session_id, definition.name, idempotency_key),
                )
                row = cur.fetchone()
                cur.close()
                if row is not None:
                    return self._row_to_snapshot(row)

            # Capacity check
            if self._active_count() >= self.max_active:
                raise JobCapacityError(f"active job capacity exceeded ({self.max_active})")

            # Enforce max records
            cur = self._conn.cursor()
            cur.execute("SELECT COUNT(*) FROM RADUI_jobs")
            total = cur.fetchone()[0]
            if total >= self.max_records:
                cur.execute(
                    "DELETE FROM RADUI_jobs WHERE id IN (SELECT id FROM RADUI_jobs WHERE status NOT IN (?, ?) ORDER BY created_at ASC LIMIT ?)",
                    (JobStatus.QUEUED.value, JobStatus.RUNNING.value, (total - self.max_records + 1)),
                )
            cur.close()

            job_id = f"job-{uuid.uuid4().hex[:12]}"
            now = _now()
            initial = JobSnapshot(
                id=job_id,
                name=definition.name,
                status=JobStatus.QUEUED,
                session_id=state.session_id,
                user_id=state.user_id,
                progress=0,
                message="Queued",
                result_text=None,
                result_available=False,
                error_type=None,
                created_at=now,
                updated_at=now,
                tenant_id=state.tenant_id,
            )

            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO RADUI_jobs (
                    id, name, status, session_id, user_id, progress, message,
                    result_text, result_json, result_available, error_type,
                    created_at, updated_at, idempotency_key, tenant_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    initial.id,
                    initial.name,
                    initial.status.value,
                    initial.session_id,
                    initial.user_id,
                    initial.progress,
                    initial.message,
                    initial.result_text,
                    None,
                    1 if initial.result_available else 0,
                    initial.error_type,
                    initial.created_at,
                    initial.updated_at,
                    idempotency_key,
                    state.tenant_id or "_default",
                ),
            )
            cur.close()

            cancel_event = asyncio.Event()
            self._cancellation_events[job_id] = cancel_event

        self._on_update(initial)

        loop = asyncio.get_running_loop()
        sem = self._semaphores.get(loop)
        if sem is None:
            sem = asyncio.Semaphore(self.max_concurrent)
            self._semaphores[loop] = sem

        task = asyncio.create_task(
            self._run_job(definition, job_id, state, args, kwargs, cancel_event, sem)
        )
        with self._lock:
            self._tasks[job_id] = task

        return initial

    async def _run_job(
        self,
        definition: JobDefinition,
        job_id: str,
        state: StateContext,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        cancel_event: asyncio.Event,
        semaphore: asyncio.Semaphore,
    ) -> None:
        job_ctx = JobContext(job_id=job_id, state=state, backend=self, cancelled=cancel_event)
        try:
            async with semaphore:
                with self._lock:
                    if cancel_event.is_set():
                        await self._transition(job_id, JobStatus.CANCELLED, message="Cancelled before execution")
                        return
                    await self._transition(job_id, JobStatus.RUNNING, message="Running")

                result = await definition.handler(job_ctx, *args, **kwargs)
                bounded, is_avail = _bounded_result(result)
                await self._transition(
                    job_id,
                    JobStatus.SUCCEEDED,
                    progress=100,
                    message="Completed",
                    result_text=_safe_result_text(result),
                    result_json=json.dumps(bounded) if is_avail else None,
                    result_available=is_avail,
                )
        except JobCancelledError:
            await self._transition(job_id, JobStatus.CANCELLED, message="Cancelled")
        except asyncio.CancelledError:
            await self._transition(job_id, JobStatus.CANCELLED, message="Cancelled")
            raise
        except sqlite3.ProgrammingError:
            # Database connection was closed externally (e.g. process termination)
            return
        except Exception as exc:
            _LOGGER.exception("Error executing job %s (%s)", job_id, definition.name)
            await self._transition(
                job_id,
                JobStatus.FAILED,
                message=str(exc)[:_MESSAGE_LIMIT] or "Job failed",
                error_type=type(exc).__name__,
            )
        finally:
            with self._lock:
                self._tasks.pop(job_id, None)
                self._cancellation_events.pop(job_id, None)

    async def _transition(
        self,
        job_id: str,
        status: JobStatus,
        *,
        progress: int | None = None,
        message: str = "",
        result_text: str | None = None,
        result_json: str | None = None,
        result_available: bool = False,
        error_type: str | None = None,
    ) -> JobSnapshot:
        with self._lock:
            now = _now()
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM RADUI_jobs WHERE id = ?", (job_id,))
            row = cur.fetchone()
            if row is None:
                cur.close()
                raise JobNotFoundError(f"Job {job_id} not found")

            new_progress = progress if progress is not None else row["progress"]
            new_msg = message or row["message"] or ""
            new_r_text = result_text if result_text is not None else row["result_text"]
            new_r_json = result_json if result_json is not None else row["result_json"]
            new_r_avail = result_available if result_available else bool(row["result_available"])
            new_err = error_type if error_type is not None else row["error_type"]

            cur.execute(
                """
                UPDATE RADUI_jobs SET
                    status = ?, progress = ?, message = ?, result_text = ?,
                    result_json = ?, result_available = ?, error_type = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status.value,
                    new_progress,
                    new_msg,
                    new_r_text,
                    new_r_json,
                    1 if new_r_avail else 0,
                    new_err,
                    now,
                    job_id,
                ),
            )
            cur.execute("SELECT * FROM RADUI_jobs WHERE id = ?", (job_id,))
            updated_row = cur.fetchone()
            cur.close()
            snapshot = self._row_to_snapshot(updated_row)

        self._on_update(snapshot)
        return snapshot

    async def update_progress(self, job_id: str, percent: int, message: str = "") -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM RADUI_jobs WHERE id = ?", (job_id,))
            row = cur.fetchone()
            if row is None:
                cur.close()
                raise JobNotFoundError(f"Job {job_id} not found")
            now = _now()
            msg = message or row["message"] or ""
            cur.execute(
                "UPDATE RADUI_jobs SET progress = ?, message = ?, updated_at = ? WHERE id = ?",
                (percent, msg, now, job_id),
            )
            cur.execute("SELECT * FROM RADUI_jobs WHERE id = ?", (job_id,))
            updated = cur.fetchone()
            cur.close()
            snapshot = self._row_to_snapshot(updated)

        self._on_update(snapshot)

    def latest_snapshot(self, job_name: str, session_id: str) -> JobSnapshot | None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM RADUI_jobs WHERE name = ? AND session_id = ? ORDER BY created_at DESC LIMIT 1",
                (job_name, session_id),
            )
            row = cur.fetchone()
            cur.close()
            if row is None:
                return None
            return self._row_to_snapshot(row)

    def get_snapshot(self, job_id: str, session_id: str, tenant_id: str | None = None) -> JobSnapshot:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM RADUI_jobs WHERE id = ? AND session_id = ?",
                (job_id, session_id),
            )
            row = cur.fetchone()
            cur.close()
            if row is None:
                raise JobNotFoundError(f"Job {job_id} not found for session {session_id}")
            snapshot = self._row_to_snapshot(row)
            if tenant_id is not None and snapshot.tenant_id is not None and snapshot.tenant_id != tenant_id:
                raise JobNotFoundError(f"Job {job_id} not found for session {session_id}")
            return snapshot

    def get_result(self, job_id: str, session_id: str, tenant_id: str | None = None) -> Any:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT result_json, result_available, tenant_id FROM RADUI_jobs WHERE id = ? AND session_id = ?",
                (job_id, session_id),
            )
            row = cur.fetchone()
            cur.close()
            if row is None:
                raise JobNotFoundError(f"Job {job_id} not found")
            row_tenant = row["tenant_id"] if "tenant_id" in row.keys() else None
            if tenant_id is not None and row_tenant is not None and row_tenant != tenant_id:
                raise JobNotFoundError(f"Job {job_id} not found")
            if not row["result_available"] or not row["result_json"]:
                return None
            return json.loads(row["result_json"])

    async def cancel(self, job_id: str, session_id: str, tenant_id: str | None = None) -> bool:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT status, tenant_id FROM RADUI_jobs WHERE id = ? AND session_id = ?",
                (job_id, session_id),
            )
            row = cur.fetchone()
            cur.close()
            if row is None:
                raise JobNotFoundError(f"Job {job_id} not found")
            row_tenant = row["tenant_id"] if "tenant_id" in row.keys() else None
            if tenant_id is not None and row_tenant is not None and row_tenant != tenant_id:
                raise JobNotFoundError(f"Job {job_id} not found")
            status = JobStatus(row["status"])
            if status.terminal:
                return False

            event = self._cancellation_events.get(job_id)
            if event is not None:
                event.set()

            task = self._tasks.get(job_id)
            if task is not None:
                task.cancel()

        await self._transition(job_id, JobStatus.CANCELLED, message="Cancellation requested")
        return True
