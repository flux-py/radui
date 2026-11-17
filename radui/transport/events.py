"""RADUI Distributed Event Broker and SSE Streaming Infrastructure.

Provides durable, monotonic event sequencing, distributed event backends,
and race-free reconnection/replay streaming for connected browser sessions.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import sqlite3
import threading
import time
from typing import Any, AsyncIterator, Protocol, runtime_checkable
import uuid

from radui.observability import LatencyTracker
from radui.transport.governance import (
    InMemorySSEGovernance,
    RedisSSEGovernance,
    SSEGovernanceBackend,
)

_LOGGER = logging.getLogger("radui.events")


@dataclass(frozen=True)
class Event:
    """Standardized event metadata structure."""

    event_id: str
    session_id: str
    sequence: int
    event_type: str
    payload: dict[str, Any]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tenant_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "payload": self.payload,
            "created_at": self.created_at,
            "tenant_id": self.tenant_id,
        }


@dataclass(frozen=True)
class EventRecord:
    """Backward-compatible event record representation."""

    sequence: int
    event: str
    data: dict[str, Any]
    event_id: str = ""
    session_id: str = ""
    created_at: str = ""
    tenant_id: str | None = None


@runtime_checkable
class EventBackend(Protocol):
    """Formal protocol for distributed SSE event persistence and fan-out backends."""

    def append_sync(
        self,
        session_id: str,
        payload: dict[str, Any],
        event_type: str = "state.patch",
    ) -> Event:
        """Synchronously append an event to the session stream with a monotonic sequence."""
        ...

    async def append(
        self,
        session_id: str,
        payload: dict[str, Any],
        event_type: str = "state.patch",
    ) -> Event:
        """Asynchronously append an event to the session stream with a monotonic sequence."""
        ...

    async def replay_after(
        self,
        session_id: str,
        sequence: int,
        limit: int = 128,
    ) -> list[Event]:
        """Fetch historical events with sequence > sequence in monotonic order."""
        ...

    async def wait_for_events(
        self,
        session_id: str,
        timeout: float = 15.0,
    ) -> list[Event]:
        """Wait for newly appended events for session_id up to timeout seconds."""
        ...

    def current_sequence(self, session_id: str) -> int:
        """Return the highest assigned sequence number for session_id."""
        ...

    def forget_session(self, session_id: str) -> None:
        """Purge retained event history for session_id on logout."""
        ...


class InMemoryEventBackend:
    """Thread-safe in-memory event backend with asyncio synchronization."""

    def __init__(self, history_size: int = 128) -> None:
        self.history_size = history_size
        self._lock = threading.RLock()
        self._sequences: dict[str, int] = defaultdict(int)
        self._history: dict[str, deque[Event]] = defaultdict(
            lambda: deque(maxlen=self.history_size)
        )
        self._subscribers: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[Event]]]] = defaultdict(set)

    def current_sequence(self, session_id: str) -> int:
        with self._lock:
            return self._sequences.get(session_id, 0)

    def append_sync(
        self,
        session_id: str,
        payload: dict[str, Any],
        event_type: str = "state.patch",
        tenant_id: str | None = None,
    ) -> Event:
        if not session_id:
            raise ValueError("session_id is required")
        resolved_tenant = tenant_id
        if resolved_tenant is None:
            try:
                from radui.state.runtime import get_active_context
                ctx = get_active_context()
                if ctx and ctx.tenant_id:
                    resolved_tenant = ctx.tenant_id
            except Exception:
                pass
        with self._lock:
            self._sequences[session_id] += 1
            seq = self._sequences[session_id]
            event = Event(
                event_id=str(uuid.uuid4()),
                session_id=session_id,
                sequence=seq,
                event_type=event_type,
                payload=dict(payload),
                created_at=datetime.now(timezone.utc).isoformat(),
                tenant_id=resolved_tenant,
            )
            self._history[session_id].append(event)
            for loop, queue in tuple(self._subscribers.get(session_id, ())):
                def enqueue(ev: Event = event, q: asyncio.Queue[Event] = queue) -> None:
                    try:
                        q.put_nowait(ev)
                    except asyncio.QueueFull:
                        pass
                try:
                    loop.call_soon_threadsafe(enqueue)
                except RuntimeError:
                    self._subscribers[session_id].discard((loop, queue))
            return event

    async def append(
        self,
        session_id: str,
        payload: dict[str, Any],
        event_type: str = "state.patch",
        tenant_id: str | None = None,
    ) -> Event:
        return self.append_sync(session_id, payload, event_type, tenant_id=tenant_id)

    async def replay_after(
        self,
        session_id: str,
        sequence: int,
        limit: int = 128,
        tenant_id: str | None = None,
    ) -> list[Event]:
        with self._lock:
            history = list(self._history.get(session_id, ()))
            matches = [
                e for e in history
                if e.sequence > sequence and (tenant_id is None or e.tenant_id is None or e.tenant_id == tenant_id)
            ]
            return matches[:limit]

    async def wait_for_events(
        self,
        session_id: str,
        timeout: float = 15.0,
        tenant_id: str | None = None,
    ) -> list[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=500)
        loop = asyncio.get_running_loop()
        sub = (loop, queue)
        with self._lock:
            self._subscribers[session_id].add(sub)
        try:
            ev = await asyncio.wait_for(queue.get(), timeout=timeout)
            events = [ev]
            while not queue.empty():
                try:
                    events.append(queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            if tenant_id is not None:
                events = [e for e in events if e.tenant_id is None or e.tenant_id == tenant_id]
            return events
            return events
        except asyncio.TimeoutError:
            return []
        finally:
            with self._lock:
                self._subscribers[session_id].discard(sub)

    def forget_session(self, session_id: str) -> None:
        with self._lock:
            self._history.pop(session_id, None)
            self._sequences.pop(session_id, None)
            self._subscribers.pop(session_id, None)


class SQLiteEventBackend:
    """ACID SQLite event backend providing durable multi-worker event persistence."""

    def __init__(self, db_path: str = ":memory:", history_size: int = 256) -> None:
        self.db_path = db_path
        self.history_size = history_size
        self._lock = threading.RLock()
        self._local = threading.local()
        self._subscribers: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[Event]]]] = defaultdict(set)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
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
                CREATE TABLE IF NOT EXISTS gx_events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_gx_events_session_seq ON gx_events (session_id, sequence);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_gx_events_session ON gx_events (session_id);"
            )

    def current_sequence(self, session_id: str) -> int:
        conn = self._get_connection()
        with self._lock:
            cursor = conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM gx_events WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def append_sync(
        self,
        session_id: str,
        payload: dict[str, Any],
        event_type: str = "state.patch",
    ) -> Event:
        conn = self._get_connection()
        with self._lock:
            with conn:
                cursor = conn.execute(
                    "SELECT COALESCE(MAX(sequence), 0) FROM gx_events WHERE session_id = ?",
                    (session_id,),
                )
                row = cursor.fetchone()
                seq = (int(row[0]) if row else 0) + 1
                ev_id = str(uuid.uuid4())
                created_at = datetime.now(timezone.utc).isoformat()
                payload_json = json.dumps(payload)
                conn.execute(
                    "INSERT INTO gx_events (event_id, session_id, sequence, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (ev_id, session_id, seq, event_type, payload_json, created_at),
                )
            event = Event(
                event_id=ev_id,
                session_id=session_id,
                sequence=seq,
                event_type=event_type,
                payload=dict(payload),
                created_at=created_at,
            )
            # Wake in-process subscribers
            for loop, queue in tuple(self._subscribers.get(session_id, ())):
                def enqueue(ev: Event = event, q: asyncio.Queue[Event] = queue) -> None:
                    try:
                        q.put_nowait(ev)
                    except asyncio.QueueFull:
                        pass
                try:
                    loop.call_soon_threadsafe(enqueue)
                except RuntimeError:
                    self._subscribers[session_id].discard((loop, queue))
            return event

    async def append(
        self,
        session_id: str,
        payload: dict[str, Any],
        event_type: str = "state.patch",
    ) -> Event:
        return self.append_sync(session_id, payload, event_type)

    async def replay_after(
        self,
        session_id: str,
        sequence: int,
        limit: int = 128,
    ) -> list[Event]:
        conn = self._get_connection()
        with self._lock:
            cursor = conn.execute(
                "SELECT event_id, sequence, event_type, payload, created_at FROM gx_events WHERE session_id = ? AND sequence > ? ORDER BY sequence ASC LIMIT ?",
                (session_id, sequence, limit),
            )
            rows = cursor.fetchall()
            return [
                Event(
                    event_id=r[0],
                    session_id=session_id,
                    sequence=r[1],
                    event_type=r[2],
                    payload=json.loads(r[3]),
                    created_at=r[4],
                )
                for r in rows
            ]

    async def wait_for_events(
        self,
        session_id: str,
        timeout: float = 15.0,
    ) -> list[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=128)
        loop = asyncio.get_running_loop()
        sub = (loop, queue)
        with self._lock:
            self._subscribers[session_id].add(sub)
        try:
            ev = await asyncio.wait_for(queue.get(), timeout=timeout)
            events = [ev]
            while not queue.empty():
                try:
                    events.append(queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            return events
        except asyncio.TimeoutError:
            return []
        finally:
            with self._lock:
                self._subscribers[session_id].discard(sub)

    def forget_session(self, session_id: str) -> None:
        conn = self._get_connection()
        with self._lock:
            with conn:
                conn.execute("DELETE FROM gx_events WHERE session_id = ?", (session_id,))
            self._subscribers.pop(session_id, None)

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None


class RedisEventBackend:
    """Distributed Redis event backend using bounded SortedSet history and Pub/Sub fan-out.

    Delivery semantics:
    - Live cross-worker Pub/Sub fan-out is at-most-once if a subscriber is disconnected.
    - Replay via Last-Event-ID is durable within `history_size` (bounded ZSET).
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        *,
        prefix: str = "gx:events:",
        history_size: int = 128,
        allow_fallback: bool = False,
        socket_timeout: float = 1.0,
        max_connections: int = 32,
        client: Any | None = None,
    ) -> None:
        self.redis_url = redis_url
        self.prefix = prefix
        self.history_size = history_size
        self.allow_fallback = allow_fallback
        self.socket_timeout = socket_timeout
        self.max_connections = max_connections
        self._pool: Any | None = None
        self._client: Any | None = client
        self._fallback = InMemoryEventBackend(history_size=history_size) if allow_fallback else None
        self._lock = threading.RLock()
        self._backend_errors = 0
        self._published = 0
        self._replayed = 0
        self._replay_calls = 0
        self._pubsub_delivered = 0
        self._lat_publish = LatencyTracker()
        self._lat_replay = LatencyTracker()
        if self._client is None:
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
            self._client = redis.Redis(connection_pool=self._pool)
            self._client.ping()
            return True
        except Exception as exc:
            self._client = None
            with self._lock:
                self._backend_errors += 1
            if not self.allow_fallback:
                _LOGGER.error("RedisEventBackend unavailable: %s", type(exc).__name__)
            else:
                _LOGGER.warning("RedisEventBackend operating in degraded fallback mode: %s", type(exc).__name__)
            return False

    def ping(self) -> bool:
        if self._client is None:
            return self.allow_fallback
        try:
            return bool(self._client.ping())
        except Exception:
            with self._lock:
                self._backend_errors += 1
            return False

    def close(self) -> None:
        if self._pool is not None:
            try:
                self._pool.disconnect()
            except Exception:
                pass
            self._pool = None
        self._client = None

    def metrics(self) -> dict[str, int]:
        with self._lock:
            return {
                "connected": 1 if self._client is not None else 0,
                "published": self._published,
                "replayed": self._replayed,
                "backend_errors": self._backend_errors,
            }

    def current_sequence(self, session_id: str) -> int:
        if self._client is None:
            return self._fallback.current_sequence(session_id) if self._fallback else 0
        try:
            val = self._client.get(f"{self.prefix}seq:{session_id}")
            return int(val) if val else 0
        except Exception:
            return 0

    def append_sync(
        self,
        session_id: str,
        payload: dict[str, Any],
        event_type: str = "state.patch",
    ) -> Event:
        if self._client is None:
            if not self.allow_fallback:
                raise RuntimeError("Redis event backend unavailable")
            assert self._fallback is not None
            return self._fallback.append_sync(session_id, payload, event_type)

        t0 = time.perf_counter()
        try:
            seq = int(self._client.incr(f"{self.prefix}seq:{session_id}"))
            ev_id = str(uuid.uuid4())
            created_at = datetime.now(timezone.utc).isoformat()
            event = Event(
                event_id=ev_id,
                session_id=session_id,
                sequence=seq,
                event_type=event_type,
                payload=dict(payload),
                created_at=created_at,
            )
            zset_key = f"{self.prefix}hist:{session_id}"
            serialized = json.dumps(event.to_dict(), allow_nan=False, separators=(",", ":"))
            pipeline = self._client.pipeline()
            pipeline.zadd(zset_key, {serialized: seq})
            if self.history_size > 0:
                pipeline.zremrangebyrank(zset_key, 0, -(self.history_size + 1))
            pipeline.publish(f"{self.prefix}pub:{session_id}", serialized)
            pipeline.execute()
            with self._lock:
                self._published += 1
            self._lat_publish.record((time.perf_counter() - t0) * 1000.0)
            return event
        except Exception:
            self._lat_publish.record((time.perf_counter() - t0) * 1000.0, error=True)
            with self._lock:
                self._backend_errors += 1
            raise

    def subscribe_remote(self, session_id: str, on_event: Any) -> Any:
        """Subscribe to cross-worker Redis Pub/Sub events for session_id."""
        if self._client is None:
            return lambda: None
        stop_flag = threading.Event()
        channel = f"{self.prefix}pub:{session_id}"
        pubsub = self._client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(channel)

        def _reader() -> None:
            try:
                while not stop_flag.is_set():
                    msg = pubsub.get_message(timeout=0.25)
                    if msg and msg.get("type") == "message":
                        try:
                            data = json.loads(msg["data"])
                            with self._lock:
                                self._pubsub_delivered += 1
                            on_event(Event(**data))
                        except Exception:
                            with self._lock:
                                self._backend_errors += 1
            except Exception:
                with self._lock:
                    self._backend_errors += 1
            finally:
                try:
                    pubsub.unsubscribe(channel)
                    pubsub.close()
                except Exception:
                    pass

        thread = threading.Thread(target=_reader, daemon=True, name=f"radui-redis-sub-{session_id[:8]}")
        thread.start()

        def unsubscribe() -> None:
            stop_flag.set()
            thread.join(timeout=1.0)

        return unsubscribe

    async def append(
        self,
        session_id: str,
        payload: dict[str, Any],
        event_type: str = "state.patch",
    ) -> Event:
        return self.append_sync(session_id, payload, event_type)

    async def replay_after(
        self,
        session_id: str,
        sequence: int,
        limit: int = 128,
    ) -> list[Event]:
        if self._client is None:
            if not self.allow_fallback:
                return []
            assert self._fallback is not None
            return await self._fallback.replay_after(session_id, sequence, limit)

        t0 = time.perf_counter()
        zset_key = f"{self.prefix}hist:{session_id}"
        # Fetch members with score > sequence
        try:
            items = self._client.zrangebyscore(zset_key, f"({sequence}", "+inf", start=0, num=limit)
            events = []
            for item in items:
                try:
                    d = json.loads(item)
                    events.append(Event(**d))
                except Exception:
                    pass
            with self._lock:
                self._replay_calls += 1
                self._replayed += len(events)
            self._lat_replay.record((time.perf_counter() - t0) * 1000.0)
            return events
        except Exception:
            self._lat_replay.record((time.perf_counter() - t0) * 1000.0, error=True)
            with self._lock:
                self._backend_errors += 1
            raise

    def observability_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "connected": self._client is not None,
                "operations": {
                    "published": self._published,
                    "replayed": self._replayed,
                    "replay_calls": self._replay_calls,
                    "pubsub_delivered": self._pubsub_delivered,
                    "backend_errors": self._backend_errors,
                },
                "latencies": {
                    "publish": self._lat_publish.snapshot(),
                    "replay": self._lat_replay.snapshot(),
                },
            }

    async def wait_for_events(
        self,
        session_id: str,
        timeout: float = 15.0,
    ) -> list[Event]:
        if self._client is None:
            if not self.allow_fallback:
                await asyncio.sleep(timeout)
                return []
            assert self._fallback is not None
            return await self._fallback.wait_for_events(session_id, timeout)

        # For Redis wait, poll sorted set or listen to pubsub
        start = time.time()
        initial_seq = self.current_sequence(session_id)
        while time.time() - start < timeout:
            await asyncio.sleep(0.1)
            current_seq = self.current_sequence(session_id)
            if current_seq > initial_seq:
                return await self.replay_after(session_id, initial_seq, limit=128)
        return []

    def forget_session(self, session_id: str) -> None:
        if self._client is not None:
            try:
                pipeline = self._client.pipeline()
                pipeline.delete(f"{self.prefix}seq:{session_id}")
                pipeline.delete(f"{self.prefix}hist:{session_id}")
                pipeline.execute()
            except Exception:
                pass
        if self._fallback is not None:
            self._fallback.forget_session(session_id)


class PostgreSQLEventBackend(SQLiteEventBackend):
    """Deprecated alias: real PostgreSQL event streaming is not implemented."""

    def __init__(self, connection_string: str = ":memory:") -> None:
        if isinstance(connection_string, str) and connection_string.startswith(("postgres://", "postgresql://")):
            raise NotImplementedError(
                "PostgreSQLEventBackend is not implemented; use RedisEventBackend or SQLiteEventBackend"
            )
        super().__init__(db_path=connection_string)


class EventBroker:
    """Unified event broker coordinating SSE fan-out, persistent backends, and race-free stream replay."""

    def __init__(
        self,
        backend: EventBackend | None = None,
        *,
        history_size: int = 128,
        subscriber_queue_size: int = 64,
        max_connections_per_session: int = 8,
        max_connections_per_ip: int = 32,
        connect_rate_limit: int = 30,
        connect_rate_window_seconds: float = 60.0,
        governance: SSEGovernanceBackend | None = None,
        worker_id: str | None = None,
        sse_lease_ttl_seconds: float = 30.0,
        sse_governance_fail_open: bool = False,
    ) -> None:
        self.history_size = history_size
        self.subscriber_queue_size = subscriber_queue_size
        self.max_connections_per_session = max_connections_per_session
        self.max_connections_per_ip = max_connections_per_ip
        self.connect_rate_limit = connect_rate_limit
        self.connect_rate_window_seconds = connect_rate_window_seconds
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.backend: EventBackend = backend if backend is not None else InMemoryEventBackend(history_size=history_size)
        if governance is not None:
            self.governance: SSEGovernanceBackend = governance
        elif isinstance(self.backend, RedisEventBackend) and (not self.backend.allow_fallback or self.backend._client is not None):
            self.governance = RedisSSEGovernance(
                backend=self.backend,
                worker_id=self.worker_id,
                lease_ttl_seconds=sse_lease_ttl_seconds,
                fail_open=sse_governance_fail_open,
            )
        else:
            self.governance = InMemorySSEGovernance(worker_id=self.worker_id)
        self._lock = threading.RLock()
        self._subscribers: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[EventRecord]]]] = defaultdict(set)
        self._rejected_connections: int = 0
        self._connection_limit_violations: int = 0
        self._rate_limit_violations: int = 0
        self._disconnects: int = 0
        self._queue_overflows: int = 0
        self._reconnection_attempts: int = 0
        self._events_published: int = 0
        self._events_delivered: int = 0
        self._replay_gaps: int = 0
        self._resets_sent: int = 0
        self._backend_errors: int = 0

    def try_acquire_connection(
        self,
        session_id: str,
        client_ip: str | None = None,
        *,
        is_reconnect: bool = False,
        connection_id: str | None = None,
    ) -> tuple[bool, str | None, int]:
        """Atomically enforce rate limits and per-session/per-IP connection caps."""
        admitted, reason, status_code, detail_code = self.governance.try_acquire(
            session_id,
            client_ip,
            connection_id=connection_id,
            max_per_session=self.max_connections_per_session,
            max_per_ip=self.max_connections_per_ip,
            rate_limit=self.connect_rate_limit,
            rate_window_seconds=self.connect_rate_window_seconds,
        )
        with self._lock:
            if not admitted:
                self._rejected_connections += 1
                if detail_code == "rate_limit":
                    self._rate_limit_violations += 1
                elif detail_code in {"session_limit", "ip_limit"}:
                    self._connection_limit_violations += 1
                elif detail_code == "backend_unavailable":
                    self._backend_errors += 1
                return False, reason, status_code
            if is_reconnect:
                self._reconnection_attempts += 1
            return True, None, 200

    def release_connection(
        self,
        session_id: str,
        client_ip: str | None = None,
        *,
        connection_id: str | None = None,
    ) -> None:
        """Release a previously acquired SSE connection slot."""
        self.governance.release(session_id, client_ip, connection_id=connection_id)
        with self._lock:
            self._disconnects += 1

    def record_rejection(self) -> None:
        """Increment rejected connections counter (e.g. auth/origin failures)."""
        with self._lock:
            self._rejected_connections += 1

    async def run_governance_renewal_loop(self, interval: float = 10.0) -> None:
        """Periodically renew distributed SSE connection leases until cancelled."""
        sleep_s = max(0.5, float(interval))
        while True:
            await asyncio.sleep(sleep_s)
            try:
                await asyncio.to_thread(self.governance.renew_leases)
            except asyncio.CancelledError:
                raise
            except Exception:
                with self._lock:
                    self._backend_errors += 1

    def metrics(self) -> dict[str, int]:
        """Return process-local SSE transport metrics without sensitive identifiers."""
        with self._lock:
            gov_errors = int(getattr(self.governance, "backend_errors", 0))
            return {
                "active_connections": self.governance.active_count(),
                "active_subscribers": sum(len(subs) for subs in self._subscribers.values()),
                "rejected_connections": self._rejected_connections,
                "connection_limit_violations": self._connection_limit_violations,
                "rate_limit_violations": self._rate_limit_violations,
                "disconnects": self._disconnects,
                "queue_overflows": self._queue_overflows,
                "reconnection_attempts": self._reconnection_attempts,
                "events_published": self._events_published,
                "events_delivered": self._events_delivered,
                "backend_errors": self._backend_errors + gov_errors,
            }

    def governance_metrics(self) -> dict[str, Any]:
        """Return SSE governance metrics for local or distributed governance."""
        with self._lock:
            return {
                "worker_id": self.worker_id,
                "mode": "redis" if isinstance(self.governance, RedisSSEGovernance) else "memory",
                "active_connections": self.governance.active_count(),
                "leases_renewed": int(getattr(self.governance, "leases_renewed", 0)),
                "backend_errors": int(getattr(self.governance, "backend_errors", 0)),
                "fail_open": bool(getattr(self.governance, "fail_open", False)),
            }

    def observability_snapshot(self) -> dict[str, Any]:
        """Return structured event + SSE governance observability snapshot."""
        backend_snap = (
            self.backend.observability_snapshot()
            if hasattr(self.backend, "observability_snapshot")
            else {
                "connected": True,
                "operations": {
                    "published": self._events_published,
                    "replayed": 0,
                    "replay_calls": 0,
                    "pubsub_delivered": 0,
                    "backend_errors": self._backend_errors,
                },
                "latencies": {},
            }
        )
        ops = dict(backend_snap.get("operations", {}))
        with self._lock:
            ops["replay_gaps"] = self._replay_gaps
            ops["resets_sent"] = self._resets_sent
            ops["queue_overflows"] = self._queue_overflows
            ops["events_delivered"] = self._events_delivered
        events_snap = {
            "connected": backend_snap.get("connected", True),
            "operations": ops,
            "latencies": backend_snap.get("latencies", {}),
        }
        sse_snap = (
            self.governance.observability_snapshot()
            if hasattr(self.governance, "observability_snapshot")
            else self.governance_metrics()
        )
        return {"events": events_snap, "sse": sse_snap}

    def current_sequence(self, session_id: str) -> int:
        return self.backend.current_sequence(session_id)

    @property
    def _sequences(self) -> dict[str, int]:
        return getattr(self.backend, "_sequences", {})

    def history_snapshot(self, session_id: str) -> tuple[EventRecord, ...]:
        """Return a read-only snapshot of recent events for diagnostics/tests."""
        # Synchronous inspection of recent history
        if isinstance(self.backend, InMemoryEventBackend):
            with self.backend._lock:
                return tuple(
                    EventRecord(e.sequence, e.event_type, e.payload, e.event_id, e.session_id, e.created_at)
                    for e in self.backend._history.get(session_id, ())
                )
        return ()

    def publish(self, session_id: str, event: str, data: dict[str, Any]) -> EventRecord:
        """Publish an event to the session stream via the configured EventBackend."""
        if not session_id:
            raise ValueError("session_id is required")
        ev = self.backend.append_sync(session_id, data, event_type=event)
        with self._lock:
            self._events_published += 1
        record = EventRecord(
            sequence=ev.sequence,
            event=ev.event_type,
            data=ev.payload,
            event_id=ev.event_id,
            session_id=ev.session_id,
            created_at=ev.created_at,
        )
        # Notify process-local streaming subscribers
        with self._lock:
            for loop, queue in tuple(self._subscribers.get(session_id, ())):
                def enqueue(target: asyncio.Queue[EventRecord] = queue, rec: EventRecord = record) -> None:
                    if target.full():
                        with self._lock:
                            self._queue_overflows += 1
                        while not target.empty():
                            try:
                                target.get_nowait()
                            except asyncio.QueueEmpty:
                                break
                        try:
                            target.put_nowait(EventRecord(rec.sequence, "reset", {}))
                        except asyncio.QueueFull:
                            pass
                    else:
                        target.put_nowait(rec)
                try:
                    loop.call_soon_threadsafe(enqueue)
                except RuntimeError:
                    self._subscribers[session_id].discard((loop, queue))
        return record

    def close_all(self) -> None:
        """Terminate all active SSE subscriber streams for graceful shutdown."""
        with self._lock:
            all_sessions = list(self._subscribers.items())
            for session_id, subs in all_sessions:
                for loop, queue in tuple(subs):
                    def terminate(target: asyncio.Queue[EventRecord] = queue) -> None:
                        while not target.empty():
                            try:
                                target.get_nowait()
                            except asyncio.QueueEmpty:
                                break
                        try:
                            target.put_nowait(EventRecord(0, "reset", {}))
                        except asyncio.QueueFull:
                            pass
                    try:
                        loop.call_soon_threadsafe(terminate)
                    except RuntimeError:
                        subs.discard((loop, queue))
            self._subscribers.clear()
        self.governance.release_all()

    def forget_session(self, session_id: str) -> None:
        """Forget retained event history for a session."""
        self.backend.forget_session(session_id)
        with self._lock:
            subscribers = tuple(self._subscribers.get(session_id, ()))
            for loop, queue in subscribers:
                def terminate(target: asyncio.Queue[EventRecord] = queue) -> None:
                    while not target.empty():
                        try:
                            target.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    try:
                        target.put_nowait(EventRecord(0, "reset", {}))
                    except asyncio.QueueFull:
                        pass
                try:
                    loop.call_soon_threadsafe(terminate)
                except RuntimeError:
                    self._subscribers[session_id].discard((loop, queue))
            self._subscribers.pop(session_id, None)

    async def stream(
        self,
        session_id: str,
        *,
        last_event_id: int | None = None,
        keepalive_seconds: float = 15.0,
    ) -> AsyncIterator[str]:
        """Stream events to client with high-watermark replay and sequence deduplication."""
        queue: asyncio.Queue[EventRecord] = asyncio.Queue(self.subscriber_queue_size)
        loop = asyncio.get_running_loop()
        subscriber = (loop, queue)

        # 1. Register subscriber FIRST before querying replay to prevent race conditions
        with self._lock:
            self._subscribers[session_id].add(subscriber)

        remote_unsub = None
        if hasattr(self.backend, "subscribe_remote"):
            def _on_remote(ev: Event) -> None:
                rec = EventRecord(
                    sequence=ev.sequence,
                    event=ev.event_type,
                    data=ev.payload,
                    event_id=ev.event_id,
                    session_id=ev.session_id,
                    created_at=ev.created_at,
                )

                def _enqueue_remote() -> None:
                    if queue.full():
                        with self._lock:
                            self._queue_overflows += 1
                        while not queue.empty():
                            try:
                                queue.get_nowait()
                            except asyncio.QueueEmpty:
                                break
                        try:
                            queue.put_nowait(EventRecord(rec.sequence, "reset", {}))
                        except asyncio.QueueFull:
                            pass
                    else:
                        queue.put_nowait(rec)

                try:
                    loop.call_soon_threadsafe(_enqueue_remote)
                except RuntimeError:
                    pass

            try:
                remote_unsub = self.backend.subscribe_remote(session_id, _on_remote)
            except Exception:
                with self._lock:
                    self._backend_errors += 1

        # 2. Capture durable high-watermark (HWM) from authoritative storage
        high_watermark = self.backend.current_sequence(session_id)
        delivered_sequence = last_event_id if last_event_id is not None else high_watermark

        try:
            # 3. Replay historical events from (last_event_id ... high_watermark]
            if last_event_id is not None:
                if last_event_id > high_watermark:
                    with self._lock:
                        self._resets_sent += 1
                    yield _encode_sse(EventRecord(high_watermark, "reset", {}))
                    return

                fetch_cursor = last_event_id
                while fetch_cursor < high_watermark:
                    replayed_events = await self.backend.replay_after(session_id, fetch_cursor, limit=self.history_size)
                    if not replayed_events:
                        if high_watermark > fetch_cursor:
                            with self._lock:
                                self._replay_gaps += 1
                                self._resets_sent += 1
                            yield _encode_sse(EventRecord(high_watermark, "reset", {}))
                            return
                        break
                    if fetch_cursor == last_event_id and replayed_events[0].sequence > last_event_id + 1:
                        with self._lock:
                            self._replay_gaps += 1
                            self._resets_sent += 1
                        yield _encode_sse(EventRecord(high_watermark, "reset", {}))
                        return

                    for ev in replayed_events:
                        if ev.sequence > high_watermark:
                            break
                        rec = EventRecord(ev.sequence, ev.event_type, ev.payload, ev.event_id, ev.session_id, ev.created_at)
                        yield _encode_sse(rec)
                        delivered_sequence = max(delivered_sequence, ev.sequence)
                        fetch_cursor = ev.sequence
                    if not replayed_events or fetch_cursor >= high_watermark:
                        break

            # 4. Drain live queue with strict deduplication against delivered_sequence
            while True:
                try:
                    record = await asyncio.wait_for(queue.get(), timeout=keepalive_seconds)
                except asyncio.TimeoutError:
                    # Reconcile against durable storage to protect against dropped pub/sub notifications
                    cur_seq = self.backend.current_sequence(session_id)
                    if cur_seq > delivered_sequence:
                        missed = await self.backend.replay_after(session_id, delivered_sequence, limit=64)
                        for ev in missed:
                            rec = EventRecord(ev.sequence, ev.event_type, ev.payload, ev.event_id, ev.session_id, ev.created_at)
                            yield _encode_sse(rec)
                            delivered_sequence = max(delivered_sequence, ev.sequence)
                    else:
                        yield ": keep-alive\n\n"
                    continue

                if record.sequence <= delivered_sequence and record.event != "reset":
                    # Deduplicate: event was delivered in replay phase or previously drained
                    continue

                delivered_sequence = max(delivered_sequence, record.sequence)
                with self._lock:
                    self._events_delivered += 1
                yield _encode_sse(record)
                if record.event == "reset":
                    return
        finally:
            if remote_unsub is not None:
                try:
                    remote_unsub()
                except Exception:
                    pass
            with self._lock:
                subscribers = self._subscribers.get(session_id)
                if subscribers is not None:
                    subscribers.discard(subscriber)
                    if not subscribers:
                        self._subscribers.pop(session_id, None)


def _encode_sse(record: EventRecord) -> str:
    data = json.dumps(record.data, separators=(",", ":"), ensure_ascii=False)
    return f"id: {record.sequence}\nevent: {record.event}\ndata: {data}\n\n"
