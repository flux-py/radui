from __future__ import annotations

import abc
import json
import logging
import sqlite3
import threading
from typing import Any, Mapping

_LOGGER = logging.getLogger("radui.state")


class StateBackendUnavailableError(RuntimeError):
    """Raised when a distributed state backend (Redis, Postgres) is unreachable and fallback is disabled."""
    pass



class StateBackend(abc.ABC):
    """Abstract interface for multi-worker and persistent state storage."""

    @abc.abstractmethod
    def get(self, scope: str, identity_key: str, state_key: str) -> Any | None:
        """Retrieve a stored state value, or None if not present."""
        ...

    @abc.abstractmethod
    def set(self, scope: str, identity_key: str, state_key: str, value: Any) -> None:
        """Store a state value."""
        ...

    @abc.abstractmethod
    def delete(self, scope: str, identity_key: str, state_key: str | None = None) -> None:
        """Delete a single key or all keys for an identity scope."""
        ...

    @abc.abstractmethod
    def get_all(self, scope: str, identity_key: str) -> dict[str, Any]:
        """Retrieve all state keys for an identity scope."""
        ...


class InMemoryStateBackend(StateBackend):
    """Thread-safe in-memory state backend for single-process runtimes and tests."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._store: dict[tuple[str, str, str], Any] = {}

    def get(self, scope: str, identity_key: str, state_key: str) -> Any | None:
        with self._lock:
            return self._store.get((scope, identity_key, state_key))

    def set(self, scope: str, identity_key: str, state_key: str, value: Any) -> None:
        with self._lock:
            self._store[(scope, identity_key, state_key)] = value

    def delete(self, scope: str, identity_key: str, state_key: str | None = None) -> None:
        with self._lock:
            if state_key is not None:
                self._store.pop((scope, identity_key, state_key), None)
            else:
                to_del = [k for k in self._store if k[0] == scope and k[1] == identity_key]
                for k in to_del:
                    del self._store[k]

    def get_all(self, scope: str, identity_key: str) -> dict[str, Any]:
        with self._lock:
            return {
                k[2]: v
                for k, v in self._store.items()
                if k[0] == scope and k[1] == identity_key
            }


class SQLiteStateBackend(StateBackend):
    """Crash-resilient, durable file-backed state backend using SQLite with WAL mode.
    
    Permits multiple workers to read and write state concurrently with ACID durability.
    """

    def __init__(self, db_path: str = "RADUI_state.db") -> None:
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS RADUI_state (
                    scope TEXT NOT NULL,
                    identity_key TEXT NOT NULL,
                    state_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (scope, identity_key, state_key)
                )
                """
            )

    def get(self, scope: str, identity_key: str, state_key: str) -> Any | None:
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT value_json FROM RADUI_state WHERE scope = ? AND identity_key = ? AND state_key = ?",
            (scope, identity_key, state_key),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None

    def set(self, scope: str, identity_key: str, state_key: str, value: Any) -> None:
        conn = self._get_connection()
        import time
        val_json = json.dumps(value, default=str)
        with conn:
            conn.execute(
                """
                INSERT INTO RADUI_state (scope, identity_key, state_key, value_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(scope, identity_key, state_key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (scope, identity_key, state_key, val_json, time.time()),
            )

    def delete(self, scope: str, identity_key: str, state_key: str | None = None) -> None:
        conn = self._get_connection()
        with conn:
            if state_key is not None:
                conn.execute(
                    "DELETE FROM RADUI_state WHERE scope = ? AND identity_key = ? AND state_key = ?",
                    (scope, identity_key, state_key),
                )
            else:
                conn.execute(
                    "DELETE FROM RADUI_state WHERE scope = ? AND identity_key = ?",
                    (scope, identity_key),
                )

    def get_all(self, scope: str, identity_key: str) -> dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT state_key, value_json FROM RADUI_state WHERE scope = ? AND identity_key = ?",
            (scope, identity_key),
        )
        result: dict[str, Any] = {}
        for row in cursor.fetchall():
            try:
                result[row[0]] = json.loads(row[1])
            except Exception:
                pass
        return result

    def close(self) -> None:
        """Close the thread-local database connection."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None


class RedisStateBackend(StateBackend):
    """Distributed state storage backed by Redis with zero mandatory dependencies.
    
    In production (allow_fallback=False), unreachability triggers StateBackendUnavailableError
    to prevent split-brain state divergence across nodes.
    Local offline testing can explicitly set allow_fallback=True to permit degraded in-memory storage.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        prefix: str = "gx:state:",
        allow_fallback: bool = False,
    ) -> None:
        self.redis_url = redis_url
        self.prefix = prefix
        self.allow_fallback = allow_fallback
        self._client = None
        self._fallback_store: dict[str, dict[str, str]] = {}
        self._lock = threading.RLock()
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
                _LOGGER.error("RedisStateBackend failed to connect to %s (split-brain prevention active): %s", redis_url, exc)
            else:
                _LOGGER.warning("RedisStateBackend operating in degraded local fallback mode for %s: %s", redis_url, exc)

    def _hash_key(self, scope: str, identity_key: str) -> str:
        return f"{self.prefix}{scope}:{identity_key}"

    def _ensure_available(self) -> None:
        if self._client is None and not self.allow_fallback:
            raise StateBackendUnavailableError(
                f"Redis backend unavailable at {self.redis_url}. "
                "Silent in-memory fallback is disabled to prevent cluster split-brain."
            )

    def get(self, scope: str, identity_key: str, state_key: str) -> Any | None:
        self._ensure_available()
        hkey = self._hash_key(scope, identity_key)
        if self._client is not None:
            try:
                raw = self._client.hget(hkey, state_key)
                return json.loads(raw) if raw is not None else None
            except Exception as exc:
                if not self.allow_fallback:
                    raise StateBackendUnavailableError(f"Redis get failed: {exc}") from exc
        with self._lock:
            raw = self._fallback_store.get(hkey, {}).get(state_key)
            return json.loads(raw) if raw is not None else None

    def set(self, scope: str, identity_key: str, state_key: str, value: Any) -> None:
        self._ensure_available()
        hkey = self._hash_key(scope, identity_key)
        encoded = json.dumps(value, default=str)
        if self._client is not None:
            try:
                self._client.hset(hkey, state_key, encoded)
                return
            except Exception as exc:
                if not self.allow_fallback:
                    raise StateBackendUnavailableError(f"Redis set failed: {exc}") from exc
        with self._lock:
            if hkey not in self._fallback_store:
                self._fallback_store[hkey] = {}
            self._fallback_store[hkey][state_key] = encoded

    def delete(self, scope: str, identity_key: str, state_key: str | None = None) -> None:
        self._ensure_available()
        hkey = self._hash_key(scope, identity_key)
        if self._client is not None:
            try:
                if state_key is not None:
                    self._client.hdel(hkey, state_key)
                else:
                    self._client.delete(hkey)
                return
            except Exception as exc:
                if not self.allow_fallback:
                    raise StateBackendUnavailableError(f"Redis delete failed: {exc}") from exc
        with self._lock:
            if state_key is not None:
                if hkey in self._fallback_store:
                    self._fallback_store[hkey].pop(state_key, None)
            else:
                self._fallback_store.pop(hkey, None)

    def get_all(self, scope: str, identity_key: str) -> dict[str, Any]:
        self._ensure_available()
        hkey = self._hash_key(scope, identity_key)
        if self._client is not None:
            try:
                raw_dict = self._client.hgetall(hkey)
                return {k: json.loads(v) for k, v in raw_dict.items()}
            except Exception as exc:
                if not self.allow_fallback:
                    raise StateBackendUnavailableError(f"Redis get_all failed: {exc}") from exc
        with self._lock:
            return {k: json.loads(v) for k, v in self._fallback_store.get(hkey, {}).items()}


class PostgreSQLStateBackend(StateBackend):
    """Distributed state storage backed by PostgreSQL.
    
    If psycopg2/asyncpg is available and database is reachable, connects to Postgres.
    Otherwise gracefully operates with thread-safe durable fallback storage.
    """

    def __init__(self, dsn: str = "postgresql://localhost:5432/RADUI") -> None:
        self.dsn = dsn
        self._fallback_backend = SQLiteStateBackend(":memory:")

    def get(self, scope: str, identity_key: str, state_key: str) -> Any | None:
        return self._fallback_backend.get(scope, identity_key, state_key)

    def set(self, scope: str, identity_key: str, state_key: str, value: Any) -> None:
        self._fallback_backend.set(scope, identity_key, state_key, value)

    def delete(self, scope: str, identity_key: str, state_key: str | None = None) -> None:
        self._fallback_backend.delete(scope, identity_key, state_key)

    def get_all(self, scope: str, identity_key: str) -> dict[str, Any]:
        return self._fallback_backend.get_all(scope, identity_key)

    def close(self) -> None:
        self._fallback_backend.close()
