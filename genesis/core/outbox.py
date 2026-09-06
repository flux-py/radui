"""RADUI Transactional Outbox Engine.

Ensures at-least-once external operation dispatch with durable deduplication,
crash recovery, worker fencing, exponential backoff retries, and compensation workflows.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
import inspect
import json
import logging
import random
import sqlite3
import threading
import time
from typing import Any, Callable, Iterator, Literal
import uuid

_LOGGER = logging.getLogger("radui.outbox")

OutboxStatus = Literal["PENDING", "DISPATCHED", "COMPLETED", "FAILED", "COMPENSATING", "COMPENSATED"]


class OutboxError(Exception):
    """Base exception for outbox engine operations."""


class StaleOutboxLeaseError(OutboxError):
    """Raised when an outbox transition is attempted with an outdated fencing token."""


@dataclass(frozen=True)
class OutboxRecord:
    id: str
    event_type: str
    payload: dict[str, Any]
    status: OutboxStatus
    idempotency_key: str
    owner_id: str = ""
    fence_token: int = 1
    retry_count: int = 0
    max_retries: int = 5
    next_attempt_at: float = 0.0
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    last_error: str | None = None
    tenant_id: str = "_default"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "payload": self.payload,
            "status": self.status,
            "idempotency_key": self.idempotency_key,
            "owner_id": self.owner_id,
            "fence_token": self.fence_token,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "next_attempt_at": self.next_attempt_at,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "last_error": self.last_error,
            "tenant_id": self.tenant_id,
        }


class TransactionalOutbox:
    """ACID transactional outbox coordinating local database mutations with external side effects."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._local = threading.local()
        self._shared_conn: sqlite3.Connection | None = None
        if db_path == ":memory:":
            self._shared_conn = sqlite3.connect(":memory:", check_same_thread=False, timeout=30.0)
        self._handlers: dict[str, Callable[[OutboxRecord], Any]] = {}
        self._compensators: dict[str, Callable[[OutboxRecord], Any]] = {}
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._shared_conn is not None:
            return self._shared_conn
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=30000;")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gx_outbox (
                    id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    owner_id TEXT DEFAULT '',
                    fence_token INTEGER NOT NULL DEFAULT 1,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 5,
                    next_attempt_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    completed_at REAL,
                    last_error TEXT,
                    tenant_id TEXT NOT NULL DEFAULT '_default'
                );
                """
            )
            try:
                conn.execute("ALTER TABLE gx_outbox ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '_default';")
            except Exception:
                pass
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gx_outbox_sched ON gx_outbox (status, next_attempt_at);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gx_outbox_idemp ON gx_outbox (idempotency_key);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gx_outbox_tenant ON gx_outbox (tenant_id);")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Provide an atomic transaction context sharing the active connection."""
        conn = self._get_connection()
        with conn:
            yield conn

    def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        conn: sqlite3.Connection | None = None,
        idempotency_key: str | None = None,
        max_retries: int = 5,
        tenant_id: str | None = None,
    ) -> OutboxRecord:
        """Atomically insert an outbox event into the active transaction."""
        record_id = str(uuid.uuid4())
        downstream_key = idempotency_key or f"outbox-{record_id}"
        now = time.time()
        t_id = tenant_id
        if t_id is None:
            try:
                from radui.state.runtime import get_active_context
                ctx = get_active_context()
                if ctx and ctx.tenant_id:
                    t_id = ctx.tenant_id
            except Exception:
                pass
        resolved_tenant = t_id or "_default"

        record = OutboxRecord(
            id=record_id,
            event_type=event_type,
            payload=dict(payload),
            status="PENDING",
            idempotency_key=downstream_key,
            owner_id="",
            fence_token=1,
            retry_count=0,
            max_retries=max_retries,
            next_attempt_at=now,
            created_at=now,
            completed_at=None,
            last_error=None,
            tenant_id=resolved_tenant,
        )

        active_conn = conn if conn is not None else self._get_connection()
        with self._lock:
            # If no external transaction was supplied, manage local transaction context
            ctx = active_conn if conn is None else nullcontext()
            with ctx:
                active_conn.execute(
                    """
                    INSERT INTO gx_outbox (
                        id, event_type, payload, status, idempotency_key, owner_id,
                        fence_token, retry_count, max_retries, next_attempt_at,
                        created_at, completed_at, last_error, tenant_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)
                    """,
                    (
                        record.id,
                        record.event_type,
                        json.dumps(record.payload),
                        record.status,
                        record.idempotency_key,
                        record.owner_id,
                        record.fence_token,
                        record.retry_count,
                        record.max_retries,
                        record.next_attempt_at,
                        record.created_at,
                        record.tenant_id,
                    ),
                )
        return record

    def claim_batch(
        self,
        limit: int = 10,
        lease_seconds: int = 30,
        worker_id: str = "worker-1",
    ) -> list[OutboxRecord]:
        """Claim a batch of pending or expired outbox records, incrementing fencing tokens."""
        now = time.time()
        conn = self._get_connection()
        claimed: list[OutboxRecord] = []
        with self._lock:
            with conn:
                cursor = conn.execute(
                    """
                    SELECT id, event_type, payload, status, idempotency_key, owner_id,
                           fence_token, retry_count, max_retries, next_attempt_at, created_at,
                           completed_at, last_error, tenant_id
                    FROM gx_outbox
                    WHERE (status = 'PENDING' AND next_attempt_at <= ?)
                       OR (status = 'DISPATCHED' AND next_attempt_at <= ?)
                    ORDER BY next_attempt_at ASC
                    LIMIT ?
                    """,
                    (now, now, limit),
                )
                rows = cursor.fetchall()
                for row in rows:
                    rec_id = row[0]
                    cur_fence = row[6] or 1
                    new_fence = cur_fence + 1
                    new_exp = now + lease_seconds
                    conn.execute(
                        """
                        UPDATE gx_outbox
                        SET status = 'DISPATCHED', owner_id = ?, fence_token = ?, next_attempt_at = ?
                        WHERE id = ? AND fence_token = ?
                        """,
                        (worker_id, new_fence, new_exp, rec_id, cur_fence),
                    )
                    row_tenant = row[13] if len(row) > 13 else "_default"
                    claimed.append(
                        OutboxRecord(
                            id=rec_id,
                            event_type=row[1],
                            payload=json.loads(row[2]),
                            status="DISPATCHED",
                            idempotency_key=row[4],
                            owner_id=worker_id,
                            fence_token=new_fence,
                            retry_count=row[7],
                            max_retries=row[8],
                            next_attempt_at=new_exp,
                            created_at=row[10],
                            completed_at=row[11],
                            last_error=row[12],
                            tenant_id=row_tenant,
                        )
                    )
        return claimed

    def mark_completed(self, record_id: str, fence_token: int) -> bool:
        """Mark outbox record as completed, validating that the worker's fencing token is current."""
        now = time.time()
        conn = self._get_connection()
        with self._lock:
            with conn:
                cursor = conn.execute(
                    "SELECT fence_token FROM gx_outbox WHERE id = ?",
                    (record_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return False
                if fence_token < row[0]:
                    raise StaleOutboxLeaseError(f"Stale outbox completion rejected: token {fence_token} < current {row[0]}")

                conn.execute(
                    "UPDATE gx_outbox SET status = 'COMPLETED', completed_at = ? WHERE id = ? AND fence_token = ?",
                    (now, record_id, fence_token),
                )
                return True

    def mark_failed(
        self,
        record_id: str,
        error: str,
        fence_token: int,
        can_retry: bool = True,
    ) -> bool:
        """Record dispatch failure, scheduling exponential retry or initiating compensation."""
        now = time.time()
        conn = self._get_connection()
        with self._lock:
            with conn:
                cursor = conn.execute(
                    "SELECT fence_token, retry_count, max_retries, event_type FROM gx_outbox WHERE id = ?",
                    (record_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return False
                cur_fence, retries, max_retries, ev_type = row
                if fence_token < cur_fence:
                    raise StaleOutboxLeaseError(f"Stale outbox failure rejected: token {fence_token} < current {cur_fence}")

                new_retries = retries + 1
                if can_retry and new_retries < max_retries:
                    # Exponential backoff with jitter: 2^retries + [0.1, 0.5] seconds
                    delay = (2 ** min(new_retries, 6)) + random.uniform(0.1, 0.5)
                    next_attempt = now + delay
                    conn.execute(
                        """
                        UPDATE gx_outbox
                        SET status = 'PENDING', retry_count = ?, next_attempt_at = ?, last_error = ?
                        WHERE id = ? AND fence_token = ?
                        """,
                        (new_retries, next_attempt, error, record_id, fence_token),
                    )
                else:
                    # Retries exhausted: transition to COMPENSATING if compensator registered, else FAILED
                    new_status = "COMPENSATING" if ev_type in self._compensators else "FAILED"
                    conn.execute(
                        """
                        UPDATE gx_outbox
                        SET status = ?, retry_count = ?, last_error = ?
                        WHERE id = ? AND fence_token = ?
                        """,
                        (new_status, new_retries, error, record_id, fence_token),
                    )
                return True

    def mark_compensated(self, record_id: str, fence_token: int) -> bool:
        """Mark outbox record as successfully compensated."""
        now = time.time()
        conn = self._get_connection()
        with self._lock:
            with conn:
                conn.execute(
                    "UPDATE gx_outbox SET status = 'COMPENSATED', completed_at = ? WHERE id = ? AND fence_token = ?",
                    (now, record_id, fence_token),
                )
                return True

    def register_handler(self, event_type: str, handler: Callable[[OutboxRecord], Any]) -> None:
        """Register dispatcher for an outbox event type."""
        self._handlers[event_type] = handler

    def register_compensator(self, event_type: str, compensator: Callable[[OutboxRecord], Any]) -> None:
        """Register compensation logic for an outbox event type when retries fail."""
        self._compensators[event_type] = compensator

    def process_pending_once(self, worker_id: str = "worker-1", limit: int = 10) -> int:
        """Process one batch of claimable outbox records. Returns count of completed operations."""
        claimed = self.claim_batch(limit=limit, worker_id=worker_id)
        completed_count = 0
        for rec in claimed:
            handler = self._handlers.get(rec.event_type)
            if handler is None:
                self.mark_failed(rec.id, f"No handler registered for event type {rec.event_type}", rec.fence_token, can_retry=False)
                continue

            try:
                res = handler(rec)
                if inspect.isawaitable(res):
                    asyncio.run(res)
                self.mark_completed(rec.id, rec.fence_token)
                completed_count += 1
            except Exception as exc:
                _LOGGER.exception("Outbox handler failed for %s (%s)", rec.id, rec.event_type)
                self.mark_failed(rec.id, str(exc), rec.fence_token, can_retry=True)

        # Process compensating records if any
        self._process_compensations_once(worker_id=worker_id, limit=limit)
        return completed_count

    def _process_compensations_once(self, worker_id: str = "worker-1", limit: int = 10) -> int:
        now = time.time()
        conn = self._get_connection()
        compensating: list[OutboxRecord] = []
        with self._lock:
            with conn:
                cursor = conn.execute(
                    """
                    SELECT id, event_type, payload, status, idempotency_key, owner_id,
                           fence_token, retry_count, max_retries, next_attempt_at, created_at,
                           completed_at, last_error
                    FROM gx_outbox
                    WHERE status = 'COMPENSATING'
                    LIMIT ?
                    """,
                    (limit,),
                )
                for row in cursor.fetchall():
                    compensating.append(
                        OutboxRecord(
                            id=row[0],
                            event_type=row[1],
                            payload=json.loads(row[2]),
                            status="COMPENSATING",
                            idempotency_key=row[4],
                            owner_id=row[5],
                            fence_token=row[6],
                            retry_count=row[7],
                            max_retries=row[8],
                            next_attempt_at=row[9],
                            created_at=row[10],
                            completed_at=row[11],
                            last_error=row[12],
                        )
                    )

        compensated_count = 0
        for rec in compensating:
            compensator = self._compensators.get(rec.event_type)
            if compensator:
                try:
                    res = compensator(rec)
                    if inspect.isawaitable(res):
                        asyncio.run(res)
                    self.mark_compensated(rec.id, rec.fence_token)
                    compensated_count += 1
                except Exception as exc:
                    _LOGGER.exception("Compensation failed for %s", rec.id)
        return compensated_count

    def get(self, record_id: str) -> OutboxRecord | None:
        conn = self._get_connection()
        with self._lock:
            cursor = conn.execute(
                """
                SELECT id, event_type, payload, status, idempotency_key, owner_id,
                       fence_token, retry_count, max_retries, next_attempt_at, created_at,
                       completed_at, last_error
                FROM gx_outbox WHERE id = ?
                """,
                (record_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return OutboxRecord(
                id=row[0],
                event_type=row[1],
                payload=json.loads(row[2]),
                status=row[3],
                idempotency_key=row[4],
                owner_id=row[5],
                fence_token=row[6],
                retry_count=row[7],
                max_retries=row[8],
                next_attempt_at=row[9],
                created_at=row[10],
                completed_at=row[11],
                last_error=row[12],
            )

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None


class nullcontext:
    """Standard context manager dummy for optional transaction boundaries."""
    def __enter__(self):
        return None
    def __exit__(self, exc_type, exc_val, exc_tb):
        return False
