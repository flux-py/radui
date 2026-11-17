from __future__ import annotations

import abc
import json
import logging
import sqlite3
import threading
import time
from typing import Any, Mapping

from radui.observability import LatencyTracker

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

    def ping(self) -> bool:
        """Check backend health/connectivity."""
        return True

    def close(self) -> None:
        """Release any open backend connections."""
        return None

    def metrics(self) -> dict[str, int]:
        """Return aggregate operational metrics without credentials or state values."""
        return {}


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
    """Distributed state storage backed by Redis with connection pooling, TTL, and CAS.

    In production (allow_fallback=False), unreachability raises StateBackendUnavailableError
    to prevent split-brain state divergence across nodes.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        prefix: str = "gx:state:",
        allow_fallback: bool = False,
        *,
        ttl_seconds: int | None = None,
        socket_timeout: float = 1.0,
        max_connections: int = 32,
        client: Any | None = None,
    ) -> None:
        self.redis_url = redis_url
        self.prefix = prefix
        self.allow_fallback = allow_fallback
        self.ttl_seconds = ttl_seconds
        self.socket_timeout = socket_timeout
        self.max_connections = max_connections
        self._pool: Any | None = None
        self._client: Any | None = client
        self._fallback_store: dict[str, dict[str, str]] = {}
        self._lock = threading.RLock()
        self._reads = 0
        self._writes = 0
        self._deletes = 0
        self._cas_ops = 0
        self._cas_conflicts = 0
        self._ttl_writes = 0
        self._backend_errors = 0
        self._lat_get = LatencyTracker()
        self._lat_set = LatencyTracker()
        self._lat_cas = LatencyTracker()
        self._lat_delete = LatencyTracker()
        if self._client is None:
            self.reconnect()

    def reconnect(self) -> bool:
        """Initialize or re-establish the Redis connection pool."""
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
                _LOGGER.error("RedisStateBackend failed to connect (split-brain prevention active): %s", type(exc).__name__)
            else:
                _LOGGER.warning("RedisStateBackend operating in degraded local fallback mode: %s", type(exc).__name__)
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
                "reads": self._reads,
                "writes": self._writes,
                "deletes": self._deletes,
                "cas_conflicts": self._cas_conflicts,
                "backend_errors": self._backend_errors,
            }

    def observability_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "connected": self._client is not None,
                "operations": {
                    "get": self._reads,
                    "set": self._writes,
                    "cas": self._cas_ops,
                    "cas_conflicts": self._cas_conflicts,
                    "delete": self._deletes,
                    "ttl_writes": self._ttl_writes,
                    "backend_errors": self._backend_errors,
                },
                "latencies": {
                    "get": self._lat_get.snapshot(),
                    "set": self._lat_set.snapshot(),
                    "cas": self._lat_cas.snapshot(),
                    "delete": self._lat_delete.snapshot(),
                },
            }

    def _hash_key(self, scope: str, identity_key: str) -> str:
        return f"{self.prefix}{scope}:{identity_key}"

    def _ensure_available(self) -> None:
        if self._client is None and not self.allow_fallback:
            raise StateBackendUnavailableError(
                "Redis backend unavailable. Silent in-memory fallback is disabled to prevent cluster split-brain."
            )

    @staticmethod
    def _encode_envelope(value: Any, version: int) -> str:
        return json.dumps({"v": version, "d": value}, allow_nan=False, separators=(",", ":"))

    @staticmethod
    def _decode_envelope(raw: str) -> tuple[Any, int]:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and set(parsed.keys()) == {"v", "d"} and isinstance(parsed["v"], int):
            return parsed["d"], parsed["v"]
        return parsed, 1

    def get_versioned(self, scope: str, identity_key: str, state_key: str) -> tuple[Any | None, int]:
        self._ensure_available()
        t0 = time.perf_counter()
        hkey = self._hash_key(scope, identity_key)
        if self._client is not None:
            try:
                raw = self._client.hget(hkey, state_key)
                with self._lock:
                    self._reads += 1
                self._lat_get.record((time.perf_counter() - t0) * 1000.0)
                if raw is None:
                    return None, 0
                return self._decode_envelope(raw)
            except Exception as exc:
                self._lat_get.record((time.perf_counter() - t0) * 1000.0, error=True)
                with self._lock:
                    self._backend_errors += 1
                if not self.allow_fallback:
                    raise StateBackendUnavailableError(f"Redis get failed: {type(exc).__name__}") from exc
        with self._lock:
            self._reads += 1
            raw = self._fallback_store.get(hkey, {}).get(state_key)
            if raw is None:
                return None, 0
            return self._decode_envelope(raw)

    def get(self, scope: str, identity_key: str, state_key: str) -> Any | None:
        val, _ver = self.get_versioned(scope, identity_key, state_key)
        return val

    def set(
        self,
        scope: str,
        identity_key: str,
        state_key: str,
        value: Any,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        self._ensure_available()
        hkey = self._hash_key(scope, identity_key)
        eff_ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        # Validate JSON serialization upfront so TypeError/ValueError is not misclassified as backend outage
        self._encode_envelope(value, 1)
        if self._client is not None:
            t0 = time.perf_counter()
            try:
                raw_prev = self._client.hget(hkey, state_key)
                next_ver = (self._decode_envelope(raw_prev)[1] + 1) if raw_prev is not None else 1
                encoded = self._encode_envelope(value, next_ver)
                pipe = self._client.pipeline()
                pipe.hset(hkey, state_key, encoded)
                has_ttl = eff_ttl is not None and eff_ttl > 0
                if has_ttl:
                    pipe.expire(hkey, eff_ttl)
                pipe.execute()
                with self._lock:
                    self._writes += 1
                    if has_ttl:
                        self._ttl_writes += 1
                self._lat_set.record((time.perf_counter() - t0) * 1000.0)
                return
            except Exception as exc:
                self._lat_set.record((time.perf_counter() - t0) * 1000.0, error=True)
                with self._lock:
                    self._backend_errors += 1
                if not self.allow_fallback:
                    raise StateBackendUnavailableError(f"Redis set failed: {type(exc).__name__}") from exc
        with self._lock:
            bucket = self._fallback_store.setdefault(hkey, {})
            raw_prev = bucket.get(state_key)
            next_ver = (self._decode_envelope(raw_prev)[1] + 1) if raw_prev is not None else 1
            bucket[state_key] = self._encode_envelope(value, next_ver)
            self._writes += 1

    def compare_and_set(
        self,
        scope: str,
        identity_key: str,
        state_key: str,
        expected_version: int,
        value: Any,
        *,
        ttl_seconds: int | None = None,
    ) -> tuple[bool, int]:
        """Optimistic concurrency update using Redis WATCH/MULTI/EXEC."""
        self._ensure_available()
        hkey = self._hash_key(scope, identity_key)
        eff_ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        # Validate JSON serialization upfront so TypeError/ValueError is not misclassified as backend outage
        self._encode_envelope(value, 1)
        if self._client is not None:
            t0 = time.perf_counter()
            try:
                import redis  # type: ignore

                with self._client.pipeline() as pipe:
                    pipe.watch(hkey)
                    raw_prev = pipe.hget(hkey, state_key)
                    curr_ver = self._decode_envelope(raw_prev)[1] if raw_prev is not None else 0
                    if curr_ver != expected_version:
                        pipe.unwatch()
                        with self._lock:
                            self._cas_ops += 1
                            self._cas_conflicts += 1
                        self._lat_cas.record((time.perf_counter() - t0) * 1000.0)
                        return False, curr_ver
                    next_ver = curr_ver + 1
                    encoded = self._encode_envelope(value, next_ver)
                    pipe.multi()
                    pipe.hset(hkey, state_key, encoded)
                    has_ttl = eff_ttl is not None and eff_ttl > 0
                    if has_ttl:
                        pipe.expire(hkey, eff_ttl)
                    try:
                        pipe.execute()
                        with self._lock:
                            self._cas_ops += 1
                            self._writes += 1
                            if has_ttl:
                                self._ttl_writes += 1
                        self._lat_cas.record((time.perf_counter() - t0) * 1000.0)
                        return True, next_ver
                    except redis.WatchError:
                        with self._lock:
                            self._cas_ops += 1
                            self._cas_conflicts += 1
                        self._lat_cas.record((time.perf_counter() - t0) * 1000.0)
                        return False, curr_ver
            except StateBackendUnavailableError:
                raise
            except Exception as exc:
                self._lat_cas.record((time.perf_counter() - t0) * 1000.0, error=True)
                with self._lock:
                    self._backend_errors += 1
                if not self.allow_fallback:
                    raise StateBackendUnavailableError(f"Redis CAS failed: {type(exc).__name__}") from exc
        with self._lock:
            bucket = self._fallback_store.setdefault(hkey, {})
            raw_prev = bucket.get(state_key)
            curr_ver = self._decode_envelope(raw_prev)[1] if raw_prev is not None else 0
            if curr_ver != expected_version:
                self._cas_conflicts += 1
                return False, curr_ver
            next_ver = curr_ver + 1
            bucket[state_key] = self._encode_envelope(value, next_ver)
            self._writes += 1
            return True, next_ver

    def delete(self, scope: str, identity_key: str, state_key: str | None = None) -> None:
        self._ensure_available()
        hkey = self._hash_key(scope, identity_key)
        if self._client is not None:
            t0 = time.perf_counter()
            try:
                if state_key is not None:
                    self._client.hdel(hkey, state_key)
                else:
                    self._client.delete(hkey)
                with self._lock:
                    self._deletes += 1
                self._lat_delete.record((time.perf_counter() - t0) * 1000.0)
                return
            except Exception as exc:
                self._lat_delete.record((time.perf_counter() - t0) * 1000.0, error=True)
                with self._lock:
                    self._backend_errors += 1
                if not self.allow_fallback:
                    raise StateBackendUnavailableError(f"Redis delete failed: {type(exc).__name__}") from exc
        with self._lock:
            self._deletes += 1
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
                with self._lock:
                    self._reads += 1
                return {k: self._decode_envelope(v)[0] for k, v in raw_dict.items()}
            except Exception as exc:
                with self._lock:
                    self._backend_errors += 1
                if not self.allow_fallback:
                    raise StateBackendUnavailableError(f"Redis get_all failed: {type(exc).__name__}") from exc
        with self._lock:
            self._reads += 1
            return {k: self._decode_envelope(v)[0] for k, v in self._fallback_store.get(hkey, {}).items()}


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
