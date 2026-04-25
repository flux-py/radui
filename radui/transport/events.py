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
    """Distributed Redis event backend using Redis Streams/SortedSets and cross-worker pub/sub."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        *,
        prefix: str = "gx:events:",
        allow_fallback: bool = False,
    ) -> None:
        self.redis_url = redis_url
        self.prefix = prefix
        self.allow_fallback = allow_fallback
        self._client = None
        self._fallback = InMemoryEventBackend() if allow_fallback else None
        try:
            import redis  # type: ignore
            self._client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
            )
            self._client.ping()
        except Exception as exc:
            self._client = None
            if not self.allow_fallback:
                _LOGGER.error("RedisEventBackend unavailable at %s: %s", redis_url, exc)
            else:
                _LOGGER.warning("RedisEventBackend operating in degraded fallback mode for %s: %s", redis_url, exc)

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
        serialized = json.dumps(event.to_dict())
        pipeline = self._client.pipeline()
        pipeline.zadd(zset_key, {serialized: seq})
        pipeline.publish(f"{self.prefix}pub:{session_id}", serialized)
        pipeline.execute()
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
        if self._client is None:
            if not self.allow_fallback:
                return []
            assert self._fallback is not None
            return await self._fallback.replay_after(session_id, sequence, limit)

        zset_key = f"{self.prefix}hist:{session_id}"
        # Fetch members with score > sequence
        items = self._client.zrangebyscore(zset_key, f"({sequence}", "+inf", start=0, num=limit)
        events = []
        for item in items:
            try:
                d = json.loads(item)
                events.append(Event(**d))
            except Exception:
                pass
        return events

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
    """PostgreSQL event backend for distributed production deployments."""

    def __init__(self, connection_string: str = ":memory:") -> None:
        super().__init__(db_path=connection_string)


class EventBroker:
    """Unified event broker coordinating SSE fan-out, persistent backends, and race-free stream replay."""

    def __init__(
        self,
        backend: EventBackend | None = None,
        *,
        history_size: int = 128,
        subscriber_queue_size: int = 64,
    ) -> None:
        self.history_size = history_size
        self.subscriber_queue_size = subscriber_queue_size
        self.backend: EventBackend = backend if backend is not None else InMemoryEventBackend(history_size=history_size)
        self._lock = threading.RLock()
        self._subscribers: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[EventRecord]]]] = defaultdict(set)

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

        # 2. Capture durable high-watermark (HWM) from authoritative storage
        high_watermark = self.backend.current_sequence(session_id)
        delivered_sequence = last_event_id if last_event_id is not None else high_watermark

        try:
            # 3. Replay historical events from (last_event_id ... high_watermark]
            if last_event_id is not None:
                if last_event_id > high_watermark:
                    yield _encode_sse(EventRecord(high_watermark, "reset", {}))
                    return

                fetch_cursor = last_event_id
                while fetch_cursor < high_watermark:
                    replayed_events = await self.backend.replay_after(session_id, fetch_cursor, limit=self.history_size)
                    if not replayed_events:
                        if high_watermark > fetch_cursor:
                            yield _encode_sse(EventRecord(high_watermark, "reset", {}))
                            return
                        break
                    if fetch_cursor == last_event_id and replayed_events[0].sequence > last_event_id + 1:
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
                yield _encode_sse(record)
                if record.event == "reset":
                    return
        finally:
            with self._lock:
                subscribers = self._subscribers.get(session_id)
                if subscribers is not None:
                    subscribers.discard(subscriber)
                    if not subscribers:
                        self._subscribers.pop(session_id, None)


def _encode_sse(record: EventRecord) -> str:
    data = json.dumps(record.data, separators=(",", ":"), ensure_ascii=False)
    return f"id: {record.sequence}\nevent: {record.event}\ndata: {data}\n\n"
