from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any, Callable
import uuid

from radui.observability import LatencyTracker
from radui.jobs.runtime import (
    JobContext,
    JobDefinition,
    JobSnapshot,
    JobStatus,
)
from radui.state.runtime import StateChange, StateContext

_LOGGER = logging.getLogger("radui.jobs.redis")


class JobBackendUnavailableError(RuntimeError):
    """Raised when the distributed Redis job backend is unreachable and fallback is disabled."""


class RedisJobBackend:
    """Genuine distributed Redis job queue, worker coordinator, and lease manager.

    Uses:
    - Shared FIFO list `{prefix}queue` for pending job IDs.
    - Persistent job state hashes `{prefix}job:{job_id}`.
    - Atomic worker claim locks `{prefix}lock:{job_id}` (`SET NX EX`) to prevent duplicate execution.
    - Idempotency keys `{prefix}idem:{key}` (`SET NX EX`).
    - Dead-letter queue `{prefix}dlq` for exhausted retries.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        *,
        prefix: str = "gx:jobs:",
        allow_fallback: bool | None = None,
        max_retries: int = 2,
        default_timeout_seconds: float = 60.0,
        lease_ttl_seconds: int = 30,
        socket_timeout: float = 1.0,
        max_connections: int = 32,
        on_update: Callable[[JobSnapshot], None] | None = None,
        on_state_changes: Callable[[list[StateChange], StateContext], None] | None = None,
        client: Any | None = None,
        worker_id: str | None = None,
    ) -> None:
        self.redis_url = redis_url or "redis://localhost:6379/0"
        self.prefix = prefix
        # Backward compatibility: parameterless RedisJobBackend() in dev/tests permits local lease fallback
        self.allow_fallback = (redis_url is None) if allow_fallback is None else allow_fallback
        self.max_retries = max_retries
        self.default_timeout_seconds = default_timeout_seconds
        self.lease_ttl_seconds = lease_ttl_seconds
        self.socket_timeout = socket_timeout
        self.max_connections = max_connections
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"

        self._on_update = on_update
        self._on_state_changes = on_state_changes
        self._lock = threading.RLock()
        self._pool: Any | None = None
        self._redis_client: Any | None = client
        self._watchers: dict[tuple[str, str], dict[str, set[str]]] = {}
        self._local_leases: dict[str, int] = {}
        self._local_fence_counter = 0
        self._local_jobs: dict[str, dict[str, Any]] = {}
        self._local_queue: list[str] = []
        self._local_dlq: list[str] = []
        self._local_idem: dict[str, str] = {}
        self._stop_event = asyncio.Event()

        # Metrics
        self._enqueued = 0
        self._claimed = 0
        self._executed = 0
        self._failed = 0
        self._retried = 0
        self._dead_lettered = 0
        self._stale_recovered = 0
        self._backend_errors = 0
        self._lat_enqueue = LatencyTracker()
        self._lat_claim = LatencyTracker()
        self._lat_exec = LatencyTracker()

        if self._redis_client is None:
            self.reconnect()

    def reconnect(self) -> bool:
        try:
            import redis  # type: ignore

            if self._pool is not None:
                try:
                    self._pool.disconnect()
                except Exception:
                    pass
            self._pool = redis.ConnectionPool.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=self.socket_timeout,
                socket_timeout=self.socket_timeout,
                health_check_interval=30,
                max_connections=self.max_connections,
            )
            self._redis_client = redis.Redis(connection_pool=self._pool)
            self._redis_client.ping()
            return True
        except Exception as exc:
            self._redis_client = None
            with self._lock:
                self._backend_errors += 1
            if not self.allow_fallback:
                _LOGGER.error("RedisJobBackend unavailable: %s", type(exc).__name__)
            else:
                _LOGGER.warning("RedisJobBackend operating in degraded local fallback mode: %s", type(exc).__name__)
            return False

    def ping(self) -> bool:
        if self._redis_client is None:
            return self.allow_fallback
        try:
            return bool(self._redis_client.ping())
        except Exception:
            with self._lock:
                self._backend_errors += 1
            return False

    def _ensure_available(self) -> None:
        if self._redis_client is None and not self.allow_fallback:
            raise JobBackendUnavailableError(
                "Redis job backend unavailable. Silent local fallback is disabled."
            )

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
            if job_components:
                self._watchers[key] = {k: set(v) for k, v in job_components.items()}
            else:
                self._watchers.pop(key, None)

    def observers(self, session_id: str, job_name: str) -> list[tuple[str, tuple[str, ...]]]:
        with self._lock:
            out: list[tuple[str, tuple[str, ...]]] = []
            for (sid, vid), jobs_map in self._watchers.items():
                if sid == session_id and job_name in jobs_map:
                    out.append((vid, tuple(sorted(jobs_map[job_name]))))
            return out

    def drop_session(self, session_id: str) -> None:
        with self._lock:
            for key in [k for k in self._watchers if k[0] == session_id]:
                self._watchers.pop(key, None)

    async def startup(self) -> None:
        self._stop_event.clear()
        self._ensure_available()

    async def shutdown(self) -> None:
        self._stop_event.set()
        if self._pool is not None:
            try:
                self._pool.disconnect()
            except Exception:
                pass
            self._pool = None
        self._redis_client = None

    def metrics(self) -> dict[str, int]:
        queue_depth = 0
        dlq_depth = 0
        if self._redis_client is not None:
            try:
                queue_depth = int(self._redis_client.llen(f"{self.prefix}queue"))
                dlq_depth = int(self._redis_client.llen(f"{self.prefix}dlq"))
            except Exception:
                pass
        else:
            with self._lock:
                queue_depth = len(self._local_queue)
                dlq_depth = len(self._local_dlq)
        with self._lock:
            return {
                "connected": 1 if self._redis_client is not None else 0,
                "enqueued": self._enqueued,
                "executed": self._executed,
                "failed": self._failed,
                "retried": self._retried,
                "dead_lettered": self._dead_lettered,
                "backend_errors": self._backend_errors,
                "queue_depth": queue_depth,
                "dlq_depth": dlq_depth,
            }

    def observability_snapshot(self) -> dict[str, Any]:
        queue_depth = 0
        active_count = 0
        dlq_depth = 0
        if self._redis_client is not None:
            try:
                queue_depth = int(self._redis_client.llen(f"{self.prefix}queue"))
                active_count = int(self._redis_client.scard(f"{self.prefix}active"))
                dlq_depth = int(self._redis_client.llen(f"{self.prefix}dlq"))
            except Exception:
                pass
        else:
            with self._lock:
                queue_depth = len(self._local_queue)
                dlq_depth = len(self._local_dlq)
        with self._lock:
            return {
                "connected": self._redis_client is not None,
                "queue_depth": queue_depth,
                "active_count": active_count,
                "dlq_depth": dlq_depth,
                "operations": {
                    "enqueue": self._enqueued,
                    "claim": self._claimed,
                    "complete": self._executed,
                    "fail": self._failed,
                    "retry": self._retried,
                    "dlq": self._dead_lettered,
                    "stale_recovered": self._stale_recovered,
                    "backend_errors": self._backend_errors,
                },
                "latencies": {
                    "enqueue": self._lat_enqueue.snapshot(),
                    "claim": self._lat_claim.snapshot(),
                    "execution": self._lat_exec.snapshot(),
                },
            }

    # --- Distributed Fencing / Leases ---

    def acquire_lease(self, job_id: str, ttl_seconds: int = 30) -> int | None:
        if self._redis_client is not None:
            try:
                token = int(self._redis_client.incr(f"{self.prefix}fence:{job_id}"))
                self._redis_client.set(f"{self.prefix}lease:{job_id}", str(token), ex=ttl_seconds)
                return token
            except Exception as exc:
                with self._lock:
                    self._backend_errors += 1
                if not self.allow_fallback:
                    raise JobBackendUnavailableError(f"Redis acquire_lease failed: {type(exc).__name__}") from exc
        with self._lock:
            self._local_fence_counter += 1
            self._local_leases[job_id] = self._local_fence_counter
            return self._local_fence_counter

    def validate_fence(self, job_id: str, fence_token: int) -> bool:
        if self._redis_client is not None:
            try:
                val = self._redis_client.get(f"{self.prefix}lease:{job_id}")
                return val is not None and int(val) == fence_token
            except Exception:
                return False
        with self._lock:
            return self._local_leases.get(job_id) == fence_token

    def release_lease(self, job_id: str) -> None:
        if self._redis_client is not None:
            try:
                self._redis_client.delete(f"{self.prefix}lease:{job_id}")
                return
            except Exception:
                pass
        with self._lock:
            self._local_leases.pop(job_id, None)

    # --- Shared Queue & Status Persistence ---

    def _to_snapshot(self, rec: dict[str, Any]) -> JobSnapshot:
        return JobSnapshot(
            id=rec["job_id"],
            name=rec["name"],
            status=JobStatus(rec["status"]),
            session_id=rec["session_id"],
            user_id=rec.get("user_id"),
            progress=int(rec.get("progress_percent", 0)),
            message=rec.get("progress_message", ""),
            result_text=str(rec["result"]) if rec.get("result") is not None else None,
            result_available=rec.get("status") == JobStatus.SUCCEEDED.value,
            error_type=rec.get("error_type"),
            created_at=str(rec.get("created_at", "")),
            updated_at=str(rec.get("updated_at", "")),
            tenant_id=rec.get("tenant_id"),
        )

    def _save_job(self, rec: dict[str, Any]) -> None:
        if self._redis_client is not None:
            encoded = json.dumps(rec, allow_nan=False, separators=(",", ":"))
            self._redis_client.set(f"{self.prefix}job:{rec['job_id']}", encoded)
            self._redis_client.set(f"{self.prefix}latest:{rec['session_id']}:{rec['name']}", rec["job_id"])
            return
        with self._lock:
            self._local_jobs[rec["job_id"]] = dict(rec)

    def _load_job(self, job_id: str) -> dict[str, Any] | None:
        if self._redis_client is not None:
            raw = self._redis_client.get(f"{self.prefix}job:{job_id}")
            return json.loads(raw) if raw is not None else None
        with self._lock:
            rec = self._local_jobs.get(job_id)
            return dict(rec) if rec is not None else None

    async def submit(
        self,
        definition: JobDefinition,
        state: StateContext,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> JobSnapshot:
        self._ensure_available()
        if idempotency_key:
            idem_redis_key = f"{self.prefix}idem:{state.session_id}:{idempotency_key}"
            if self._redis_client is not None:
                existing_id = self._redis_client.get(idem_redis_key)
                if existing_id:
                    existing_rec = self._load_job(existing_id)
                    if existing_rec is not None:
                        return self._to_snapshot(existing_rec)
            else:
                with self._lock:
                    existing_id = self._local_idem.get(idem_redis_key)
                    if existing_id and existing_id in self._local_jobs:
                        return self._to_snapshot(self._local_jobs[existing_id])

        from datetime import datetime, timezone
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        rec: dict[str, Any] = {
            "job_id": job_id,
            "name": definition.name,
            "session_id": state.session_id,
            "user_id": state.user_id,
            "view_id": state.view_id,
            "tenant_id": state.tenant_id,
            "args": list(args),
            "kwargs": dict(kwargs),
            "status": JobStatus.QUEUED.value,
            "attempt": 0,
            "max_retries": self.max_retries,
            "timeout_seconds": getattr(definition, "timeout_seconds", None) or self.default_timeout_seconds,
            "progress_percent": 0,
            "progress_message": "",
            "error": None,
            "error_type": None,
            "result": None,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        # Validate JSON safety of payload before enqueueing
        json.dumps(rec, allow_nan=False)

        t0 = time.perf_counter()
        if self._redis_client is not None:
            if idempotency_key:
                claimed = self._redis_client.set(
                    f"{self.prefix}idem:{state.session_id}:{idempotency_key}",
                    job_id,
                    nx=True,
                    ex=86400,
                )
                if not claimed:
                    existing_id = self._redis_client.get(f"{self.prefix}idem:{state.session_id}:{idempotency_key}")
                    if existing_id:
                        existing_rec = self._load_job(existing_id)
                        if existing_rec is not None:
                            self._lat_enqueue.record((time.perf_counter() - t0) * 1000.0)
                            return self._to_snapshot(existing_rec)
            self._save_job(rec)
            self._redis_client.lpush(f"{self.prefix}queue", job_id)
        else:
            with self._lock:
                if idempotency_key:
                    self._local_idem[f"{self.prefix}idem:{state.session_id}:{idempotency_key}"] = job_id
                self._save_job(rec)
                self._local_queue.insert(0, job_id)

        with self._lock:
            self._enqueued += 1
        self._lat_enqueue.record((time.perf_counter() - t0) * 1000.0)
        snap = self._to_snapshot(rec)
        if self._on_update is not None:
            self._on_update(snap)
        return snap

    def recover_stale_jobs(self) -> int:
        """Re-enqueue or dead-letter running jobs whose worker lease has expired."""
        if self._redis_client is None:
            return 0
        recovered = 0
        active_key = f"{self.prefix}active"
        for jid in list(self._redis_client.smembers(active_key)):
            if self._redis_client.exists(f"{self.prefix}lock:{jid}"):
                continue
            rec = self._load_job(jid)
            if rec is None or rec.get("status") != JobStatus.RUNNING.value:
                self._redis_client.srem(active_key, jid)
                continue
            # Claim short recovery lock so only one worker recovers this orphaned job
            if not self._redis_client.set(f"{self.prefix}rec:{jid}", self.worker_id, nx=True, ex=5):
                continue
            try:
                self._redis_client.srem(active_key, jid)
                if int(rec.get("attempt", 0)) <= int(rec.get("max_retries", self.max_retries)):
                    rec["status"] = JobStatus.QUEUED.value
                    rec["error"] = "Recovered after worker lease expiration"
                    self._save_job(rec)
                    self._redis_client.lpush(f"{self.prefix}queue", jid)
                    with self._lock:
                        self._retried += 1
                        self._stale_recovered += 1
                else:
                    rec["status"] = JobStatus.FAILED.value
                    rec["error"] = "Worker lease expired and max retries exhausted"
                    self._save_job(rec)
                    with self._lock:
                        self._stale_recovered += 1
                    self._redis_client.rpush(f"{self.prefix}dlq", jid)
                    with self._lock:
                        self._dead_lettered += 1
                recovered += 1
            finally:
                self._redis_client.delete(f"{self.prefix}rec:{jid}")
        return recovered

    def _owns_lease(self, job_id: str) -> bool:
        if self._redis_client is None:
            return True
        return self._redis_client.get(f"{self.prefix}lock:{job_id}") == self.worker_id

    async def process_once(
        self,
        definitions: dict[str, JobDefinition],
        state_runtime: Any,
    ) -> bool:
        """Pop and execute one job atomically using a distributed claim lock."""
        self._ensure_available()
        if self._redis_client is not None:
            self.recover_stale_jobs()
        job_id: str | None = None
        if self._redis_client is not None:
            job_id = self._redis_client.rpop(f"{self.prefix}queue")
        else:
            with self._lock:
                if self._local_queue:
                    job_id = self._local_queue.pop()
        if not job_id:
            return False

        # Atomic claim lock prevents duplicate concurrent execution across workers
        t_claim = time.perf_counter()
        if self._redis_client is not None:
            claimed = self._redis_client.set(
                f"{self.prefix}lock:{job_id}",
                self.worker_id,
                nx=True,
                ex=self.lease_ttl_seconds,
            )
            if not claimed:
                return False
            self._redis_client.sadd(f"{self.prefix}active", job_id)
        with self._lock:
            self._claimed += 1
        self._lat_claim.record((time.perf_counter() - t_claim) * 1000.0)

        try:
            rec = self._load_job(job_id)
            if rec is None:
                return False
            if rec["status"] == JobStatus.CANCELLED.value:
                return True
            defn = definitions.get(rec["name"])
            if defn is None:
                rec["status"] = JobStatus.FAILED.value
                rec["error"] = f"Unknown job definition: {rec['name']}"
                rec["finished_at"] = time.time()
                self._save_job(rec)
                return True

            from datetime import datetime, timezone
            rec["status"] = JobStatus.RUNNING.value
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            rec["attempt"] = int(rec.get("attempt", 0)) + 1
            self._save_job(rec)

            ctx = state_runtime.context(
                session_id=rec["session_id"],
                user_id=rec.get("user_id"),
                view_id=rec.get("view_id") or "default",
                tenant_id=rec.get("tenant_id"),
            )
            cancel_ev = asyncio.Event()
            job_ctx = JobContext(job_id=job_id, state=ctx, backend=self, cancelled=cancel_ev)
            t_exec = time.perf_counter()
            try:
                with ctx.capture_changes() as changes:
                    with ctx.activate():
                        res = await asyncio.wait_for(
                            defn.handler(job_ctx, *rec.get("args", ()), **rec.get("kwargs", {})),
                            timeout=float(rec.get("timeout_seconds") or self.default_timeout_seconds),
                        )
                if not self._owns_lease(job_id):
                    # Stale worker lost lease; do not overwrite newer worker's state
                    self._lat_exec.record((time.perf_counter() - t_exec) * 1000.0, error=True)
                    return False
                rec["status"] = JobStatus.SUCCEEDED.value
                rec["result"] = res
                rec["progress_percent"] = 100
                rec["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save_job(rec)
                with self._lock:
                    self._executed += 1
                self._lat_exec.record((time.perf_counter() - t_exec) * 1000.0)
                if changes and self._on_state_changes is not None:
                    self._on_state_changes(changes, ctx)
            except Exception as exc:
                self._lat_exec.record((time.perf_counter() - t_exec) * 1000.0, error=True)
                with self._lock:
                    self._failed += 1
                rec["updated_at"] = datetime.now(timezone.utc).isoformat()
                rec["error_type"] = type(exc).__name__
                if int(rec["attempt"]) <= int(rec.get("max_retries", self.max_retries)):
                    rec["status"] = JobStatus.QUEUED.value
                    rec["error"] = f"{type(exc).__name__}: {exc}"
                    self._save_job(rec)
                    if self._redis_client is not None:
                        self._redis_client.lpush(f"{self.prefix}queue", job_id)
                    else:
                        with self._lock:
                            self._local_queue.insert(0, job_id)
                    with self._lock:
                        self._retried += 1
                else:
                    rec["status"] = JobStatus.FAILED.value
                    rec["error"] = f"{type(exc).__name__}: {exc}"
                    self._save_job(rec)
                    if self._redis_client is not None:
                        self._redis_client.rpush(f"{self.prefix}dlq", job_id)
                    else:
                        with self._lock:
                            self._local_dlq.append(job_id)
                    with self._lock:
                        self._dead_lettered += 1
            if self._on_update is not None:
                self._on_update(self._to_snapshot(rec))
            return True
        finally:
            if self._redis_client is not None:
                try:
                    # Atomic compare-and-delete Lua script so a worker never releases another worker's lease
                    lua = (
                        "if redis.call('get', KEYS[1]) == ARGV[1] then "
                        "redis.call('del', KEYS[1]); return 1 else return 0 end"
                    )
                    if self._redis_client.eval(lua, 1, f"{self.prefix}lock:{job_id}", self.worker_id) == 1:
                        self._redis_client.srem(f"{self.prefix}active", job_id)
                except Exception:
                    pass

    def latest_snapshot(self, job_name: str, session_id: str) -> JobSnapshot | None:
        if self._redis_client is not None:
            jid = self._redis_client.get(f"{self.prefix}latest:{session_id}:{job_name}")
            if not jid:
                return None
            rec = self._load_job(jid)
            return self._to_snapshot(rec) if rec is not None else None
        with self._lock:
            matches = [
                rec for rec in self._local_jobs.values()
                if rec["session_id"] == session_id and rec["name"] == job_name
            ]
            if not matches:
                return None
            matches.sort(key=lambda r: float(r["created_at"]))
            return self._to_snapshot(matches[-1])

    def get_snapshot(self, job_id: str, session_id: str) -> JobSnapshot:
        rec = self._load_job(job_id)
        if rec is None or rec["session_id"] != session_id:
            raise KeyError(f"Unknown job {job_id!r} for session")
        return self._to_snapshot(rec)

    def get_result(self, job_id: str, session_id: str) -> Any:
        rec = self._load_job(job_id)
        if rec is None or rec["session_id"] != session_id:
            raise KeyError(f"Unknown job {job_id!r} for session")
        if rec["status"] != JobStatus.SUCCEEDED.value:
            raise RuntimeError(f"Job {job_id!r} has not succeeded (status={rec['status']})")
        return rec.get("result")

    async def cancel(self, job_id: str, session_id: str) -> bool:
        rec = self._load_job(job_id)
        if rec is None or rec["session_id"] != session_id:
            return False
        if rec["status"] in {JobStatus.SUCCEEDED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value}:
            return False
        rec["status"] = JobStatus.CANCELLED.value
        rec["finished_at"] = time.time()
        self._save_job(rec)
        if self._on_update is not None:
            self._on_update(self._to_snapshot(rec))
        return True

    async def update_progress(self, job_id: str, percent: int, message: str = "") -> None:
        rec = self._load_job(job_id)
        if rec is None:
            return
        rec["progress_percent"] = max(0, min(100, int(percent)))
        rec["progress_message"] = message
        self._save_job(rec)
        if self._on_update is not None:
            self._on_update(self._to_snapshot(rec))
