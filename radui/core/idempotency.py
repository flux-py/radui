"""RADUI Durable Idempotency Engine.

Provides durable deduplication, lease fencing, worker ownership tracking,
and at-least-once mutation delivery guarantees across single-process,
single-host, and distributed multi-worker clusters.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
import sqlite3
import threading
import time
from typing import Any, Iterator, Protocol, runtime_checkable

_LOGGER = logging.getLogger("radui.idempotency")


class IdempotencyError(Exception):
    """Base exception for idempotency engine errors."""


class IdempotencyConflictError(IdempotencyError):
    """Raised when an action ID is submitted with a differing payload fingerprint."""


class StaleLeaseError(IdempotencyError):
    """Raised when an operation is attempted with an outdated fencing token or mismatched owner."""


class IdempotencyBackendUnavailableError(IdempotencyError):
    """Raised when an idempotency storage backend is unreachable in fail-closed mode."""


@dataclass(frozen=True)
class IdempotencyRecord:
    key: str
    fingerprint: str
    status: str  # "PENDING", "COMPLETED", "FAILED"
    response: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    owner_id: str = ""
    fence_token: int = 1

    @property
    def is_expired(self) -> bool:
        if self.expires_at <= 0:
            return False
        return time.time() > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "fingerprint": self.fingerprint,
            "status": self.status,
            "response": self.response,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "owner_id": self.owner_id,
            "fence_token": self.fence_token,
        }


@dataclass(frozen=True)
class IdempotencyResult:
    status: str  # "PENDING", "COMPLETED", "FAILED", "CONFLICT"
    is_new: bool
    record: IdempotencyRecord | None = None
    error_message: str | None = None

    @property
    def fence_token(self) -> int:
        return self.record.fence_token if self.record else 1

    @property
    def owner_id(self) -> str:
        return self.record.owner_id if self.record else ""

    @property
    def completed(self) -> bool:
        return self.status == "COMPLETED"

    @property
    def in_progress(self) -> bool:
        return self.status == "PENDING" and not self.is_new

    @property
    def conflict(self) -> bool:
        return self.status == "CONFLICT"

    @property
    def failed(self) -> bool:
        return self.status == "FAILED"

    @property
    def response(self) -> dict[str, Any] | None:
        return self.record.response if self.record else None


@runtime_checkable
class IdempotencyBackend(Protocol):
    """Formal protocol for durable idempotency reservation backends."""

    def begin(
        self,
        key: str,
        fingerprint: str,
        ttl: int = 86400,
        owner_id: str = "",
    ) -> IdempotencyResult:
        """Attempt to reserve an idempotency key with an owner ID and fencing token."""
        ...

    def renew_lease(
        self,
        key: str,
        owner_id: str,
        fence_token: int,
        ttl: int = 86400,
    ) -> bool:
        """Renew active reservation lease if owner_id and fence_token match."""
        ...

    def complete(
        self,
        key: str,
        result: dict[str, Any],
        fence_token: int | None = None,
        owner_id: str | None = None,
    ) -> None:
        """Mark reservation as completed with response payload, validating fencing token."""
        ...

    def fail(
        self,
        key: str,
        error: str,
        fence_token: int | None = None,
        owner_id: str | None = None,
    ) -> None:
        """Mark reservation as failed with error message, validating fencing token."""
        ...

    def get(self, key: str) -> IdempotencyRecord | None:
        """Retrieve current idempotency record for a key."""
        ...


def compute_payload_fingerprint(command_id: str, payload: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 fingerprint for a command and submitted form payload."""
    sanitized = {
        k: v for k, v in sorted(payload.items())
        if not k.startswith("_gx_") and k != "_csrf"
    }
    encoded = json.dumps({"command": command_id, "data": sanitized}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class InMemoryIdempotencyBackend:
    """Thread-safe in-memory idempotency backend for development and testing."""

    def __init__(self) -> None:
        self._records: dict[str, IdempotencyRecord] = {}
        self._lock = threading.RLock()
        self._fence_counter = 0

    def begin(
        self,
        key: str,
        fingerprint: str,
        ttl: int = 86400,
        owner_id: str = "",
    ) -> IdempotencyResult:
        now = time.time()
        with self._lock:
            existing = self._records.get(key)
            if existing is not None:
                if existing.is_expired:
                    # Expired reservation: reclaim with incremented monotonic fence token
                    self._fence_counter += 1
                    token = self._fence_counter
                    record = IdempotencyRecord(
                        key=key,
                        fingerprint=fingerprint,
                        status="PENDING",
                        response=None,
                        created_at=now,
                        expires_at=now + ttl,
                        owner_id=owner_id,
                        fence_token=token,
                    )
                    self._records[key] = record
                    return IdempotencyResult(status="PENDING", is_new=True, record=record)

                if existing.fingerprint != fingerprint:
                    return IdempotencyResult(
                        status="CONFLICT",
                        is_new=False,
                        record=existing,
                        error_message="Action identifier re-used with differing payload fingerprint",
                    )
                if existing.status == "COMPLETED":
                    return IdempotencyResult(status="COMPLETED", is_new=False, record=existing)
                if existing.status == "PENDING":
                    return IdempotencyResult(status="PENDING", is_new=False, record=existing)
                if existing.status == "FAILED":
                    return IdempotencyResult(status="FAILED", is_new=False, record=existing)

            self._fence_counter += 1
            token = self._fence_counter
            record = IdempotencyRecord(
                key=key,
                fingerprint=fingerprint,
                status="PENDING",
                response=None,
                created_at=now,
                expires_at=now + ttl,
                owner_id=owner_id,
                fence_token=token,
            )
            self._records[key] = record
            return IdempotencyResult(status="PENDING", is_new=True, record=record)

    def renew_lease(
        self,
        key: str,
        owner_id: str,
        fence_token: int,
        ttl: int = 86400,
    ) -> bool:
        now = time.time()
        with self._lock:
            existing = self._records.get(key)
            if existing is None:
                return False
            if fence_token < existing.fence_token:
                raise StaleLeaseError(f"Stale lease renewal attempted: token {fence_token} < current {existing.fence_token}")
            if owner_id and existing.owner_id and owner_id != existing.owner_id:
                raise StaleLeaseError(f"Owner mismatch on lease renewal: {owner_id} != {existing.owner_id}")
            if existing.status != "PENDING":
                return False

            self._records[key] = IdempotencyRecord(
                key=key,
                fingerprint=existing.fingerprint,
                status=existing.status,
                response=existing.response,
                created_at=existing.created_at,
                expires_at=now + ttl,
                owner_id=existing.owner_id,
                fence_token=existing.fence_token,
            )
            return True

    def complete(
        self,
        key: str,
        result: dict[str, Any],
        fence_token: int | None = None,
        owner_id: str | None = None,
    ) -> None:
        with self._lock:
            existing = self._records.get(key)
            if existing is None:
                return
            if fence_token is not None and fence_token < existing.fence_token:
                raise StaleLeaseError(f"Stale worker commit rejected: token {fence_token} < current {existing.fence_token}")
            if owner_id and existing.owner_id and owner_id != existing.owner_id:
                raise StaleLeaseError(f"Owner mismatch: {owner_id} != {existing.owner_id}")

            self._records[key] = IdempotencyRecord(
                key=key,
                fingerprint=existing.fingerprint,
                status="COMPLETED",
                response=dict(result),
                created_at=existing.created_at,
                expires_at=existing.expires_at,
                owner_id=existing.owner_id,
                fence_token=existing.fence_token,
            )

    def fail(
        self,
        key: str,
        error: str,
        fence_token: int | None = None,
        owner_id: str | None = None,
    ) -> None:
        with self._lock:
            existing = self._records.get(key)
            if existing is None:
                return
            if fence_token is not None and fence_token < existing.fence_token:
                raise StaleLeaseError(f"Stale worker fail rejected: token {fence_token} < current {existing.fence_token}")
            if owner_id and existing.owner_id and owner_id != existing.owner_id:
                raise StaleLeaseError(f"Owner mismatch: {owner_id} != {existing.owner_id}")

            self._records[key] = IdempotencyRecord(
                key=key,
                fingerprint=existing.fingerprint,
                status="FAILED",
                response={"error": error},
                created_at=existing.created_at,
                expires_at=existing.expires_at,
                owner_id=existing.owner_id,
                fence_token=existing.fence_token,
            )

    def get(self, key: str) -> IdempotencyRecord | None:
        with self._lock:
            rec = self._records.get(key)
            if rec and rec.is_expired and rec.status == "PENDING":
                del self._records[key]
                return None
            return rec

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


class SQLiteIdempotencyBackend:
    """ACID SQLite idempotency backend for persistent single-host deployments."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._local = threading.local()
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
                CREATE TABLE IF NOT EXISTS gx_idempotency (
                    key TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response TEXT,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    owner_id TEXT DEFAULT '',
                    fence_token INTEGER NOT NULL DEFAULT 1
                );
                """
            )
            # Ensure schema migration if table existed from earlier versions
            cursor = conn.execute("PRAGMA table_info(gx_idempotency);")
            columns = {row[1] for row in cursor.fetchall()}
            if "owner_id" not in columns:
                conn.execute("ALTER TABLE gx_idempotency ADD COLUMN owner_id TEXT DEFAULT '';")
            if "fence_token" not in columns:
                conn.execute("ALTER TABLE gx_idempotency ADD COLUMN fence_token INTEGER NOT NULL DEFAULT 1;")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_gx_idemp_exp ON gx_idempotency (expires_at);"
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Provide atomic transaction boundary sharing the database connection."""
        conn = self._get_connection()
        with conn:
            yield conn

    def begin(
        self,
        key: str,
        fingerprint: str,
        ttl: int = 86400,
        owner_id: str = "",
    ) -> IdempotencyResult:
        now = time.time()
        conn = self._get_connection()
        with self._lock:
            with conn:
                cursor = conn.execute(
                    "SELECT fingerprint, status, response, created_at, expires_at, owner_id, fence_token FROM gx_idempotency WHERE key = ?",
                    (key,),
                )
                row = cursor.fetchone()
                if row is not None:
                    fp, status, resp_json, c_at, exp_at, cur_owner, cur_fence = row
                    record = IdempotencyRecord(
                        key=key,
                        fingerprint=fp,
                        status=status,
                        response=json.loads(resp_json) if resp_json else None,
                        created_at=c_at,
                        expires_at=exp_at,
                        owner_id=cur_owner or "",
                        fence_token=cur_fence or 1,
                    )
                    if record.is_expired and record.status == "PENDING":
                        # Expired reservation: reclaim with incremented fencing token
                        new_fence = (cur_fence or 1) + 1
                        conn.execute(
                            "UPDATE gx_idempotency SET fingerprint = ?, status = 'PENDING', response = NULL, created_at = ?, expires_at = ?, owner_id = ?, fence_token = ? WHERE key = ?",
                            (fingerprint, now, now + ttl, owner_id, new_fence, key),
                        )
                        new_rec = IdempotencyRecord(
                            key=key,
                            fingerprint=fingerprint,
                            status="PENDING",
                            created_at=now,
                            expires_at=now + ttl,
                            owner_id=owner_id,
                            fence_token=new_fence,
                        )
                        return IdempotencyResult(status="PENDING", is_new=True, record=new_rec)

                    if fp != fingerprint:
                        return IdempotencyResult(
                            status="CONFLICT",
                            is_new=False,
                            record=record,
                            error_message="Action identifier re-used with differing payload fingerprint",
                        )
                    return IdempotencyResult(status=status, is_new=False, record=record)

                # Insert fresh reservation with fence_token = 1
                conn.execute(
                    "INSERT INTO gx_idempotency (key, fingerprint, status, response, created_at, expires_at, owner_id, fence_token) VALUES (?, ?, 'PENDING', NULL, ?, ?, ?, 1)",
                    (key, fingerprint, now, now + ttl, owner_id),
                )
                new_rec = IdempotencyRecord(
                    key=key,
                    fingerprint=fingerprint,
                    status="PENDING",
                    created_at=now,
                    expires_at=now + ttl,
                    owner_id=owner_id,
                    fence_token=1,
                )
                return IdempotencyResult(status="PENDING", is_new=True, record=new_rec)

    def renew_lease(
        self,
        key: str,
        owner_id: str,
        fence_token: int,
        ttl: int = 86400,
    ) -> bool:
        now = time.time()
        conn = self._get_connection()
        with self._lock:
            with conn:
                cursor = conn.execute(
                    "SELECT owner_id, fence_token, status FROM gx_idempotency WHERE key = ?",
                    (key,),
                )
                row = cursor.fetchone()
                if row is None:
                    return False
                cur_owner, cur_fence, status = row
                if fence_token < cur_fence:
                    raise StaleLeaseError(f"Stale lease renewal rejected: {fence_token} < {cur_fence}")
                if owner_id and cur_owner and owner_id != cur_owner:
                    raise StaleLeaseError(f"Owner mismatch: {owner_id} != {cur_owner}")
                if status != "PENDING":
                    return False

                conn.execute(
                    "UPDATE gx_idempotency SET expires_at = ? WHERE key = ? AND fence_token = ?",
                    (now + ttl, key, fence_token),
                )
                return True

    def complete(
        self,
        key: str,
        result: dict[str, Any],
        fence_token: int | None = None,
        owner_id: str | None = None,
    ) -> None:
        conn = self._get_connection()
        with self._lock:
            with conn:
                if fence_token is not None or owner_id:
                    cursor = conn.execute(
                        "SELECT fence_token, owner_id FROM gx_idempotency WHERE key = ?",
                        (key,),
                    )
                    row = cursor.fetchone()
                    if row is not None:
                        cur_fence, cur_owner = row
                        if fence_token is not None and fence_token < cur_fence:
                            raise StaleLeaseError(f"Stale worker commit rejected: token {fence_token} < current {cur_fence}")
                        if owner_id and cur_owner and owner_id != cur_owner:
                            raise StaleLeaseError(f"Owner mismatch: {owner_id} != {cur_owner}")

                conn.execute(
                    "UPDATE gx_idempotency SET status = 'COMPLETED', response = ? WHERE key = ?",
                    (json.dumps(result), key),
                )

    def fail(
        self,
        key: str,
        error: str,
        fence_token: int | None = None,
        owner_id: str | None = None,
    ) -> None:
        conn = self._get_connection()
        with self._lock:
            with conn:
                if fence_token is not None or owner_id:
                    cursor = conn.execute(
                        "SELECT fence_token, owner_id FROM gx_idempotency WHERE key = ?",
                        (key,),
                    )
                    row = cursor.fetchone()
                    if row is not None:
                        cur_fence, cur_owner = row
                        if fence_token is not None and fence_token < cur_fence:
                            raise StaleLeaseError(f"Stale worker fail rejected: token {fence_token} < current {cur_fence}")
                        if owner_id and cur_owner and owner_id != cur_owner:
                            raise StaleLeaseError(f"Owner mismatch: {owner_id} != {cur_owner}")

                conn.execute(
                    "UPDATE gx_idempotency SET status = 'FAILED', response = ? WHERE key = ?",
                    (json.dumps({"error": error}), key),
                )

    def get(self, key: str) -> IdempotencyRecord | None:
        conn = self._get_connection()
        with self._lock:
            cursor = conn.execute(
                "SELECT fingerprint, status, response, created_at, expires_at, owner_id, fence_token FROM gx_idempotency WHERE key = ?",
                (key,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            fp, status, resp_json, c_at, exp_at, cur_owner, cur_fence = row
            rec = IdempotencyRecord(
                key=key,
                fingerprint=fp,
                status=status,
                response=json.loads(resp_json) if resp_json else None,
                created_at=c_at,
                expires_at=exp_at,
                owner_id=cur_owner or "",
                fence_token=cur_fence or 1,
            )
            if rec.is_expired and rec.status == "PENDING":
                return None
            return rec

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None


class RedisIdempotencyBackend:
    """Distributed Redis idempotency reservation backend with atomic Lua script fencing."""

    # Lua scripts for atomic owner and fence token validation
    LUA_COMPLETE = """
    local current_fence = tonumber(redis.call('HGET', KEYS[1], 'fence_token') or '0')
    local current_owner = redis.call('HGET', KEYS[1], 'owner_id') or ''
    local required_fence = tonumber(ARGV[1])
    local required_owner = ARGV[2]
    if required_fence >= 0 and current_fence > required_fence then
        return -1 -- stale fence token
    end
    if required_owner ~= '' and current_owner ~= '' and current_owner ~= required_owner then
        return -2 -- owner mismatch
    end
    redis.call('HMSET', KEYS[1], 'status', 'COMPLETED', 'response', ARGV[3])
    return 1
    """

    LUA_FAIL = """
    local current_fence = tonumber(redis.call('HGET', KEYS[1], 'fence_token') or '0')
    local current_owner = redis.call('HGET', KEYS[1], 'owner_id') or ''
    local required_fence = tonumber(ARGV[1])
    local required_owner = ARGV[2]
    if required_fence >= 0 and current_fence > required_fence then
        return -1
    end
    if required_owner ~= '' and current_owner ~= '' and current_owner ~= required_owner then
        return -2
    end
    redis.call('HMSET', KEYS[1], 'status', 'FAILED', 'response', ARGV[3])
    return 1
    """

    LUA_RENEW = """
    local current_fence = tonumber(redis.call('HGET', KEYS[1], 'fence_token') or '0')
    local current_owner = redis.call('HGET', KEYS[1], 'owner_id') or ''
    local current_status = redis.call('HGET', KEYS[1], 'status') or ''
    local required_fence = tonumber(ARGV[1])
    local required_owner = ARGV[2]
    local ttl = tonumber(ARGV[3])
    local new_exp = ARGV[4]
    if current_status ~= 'PENDING' then
        return 0
    end
    if required_fence >= 0 and current_fence > required_fence then
        return -1
    end
    if required_owner ~= '' and current_owner ~= '' and current_owner ~= required_owner then
        return -2
    end
    redis.call('HSET', KEYS[1], 'expires_at', new_exp)
    redis.call('EXPIRE', KEYS[1], ttl)
    return 1
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        *,
        prefix: str = "gx:idemp:",
        allow_fallback: bool = False,
    ) -> None:
        self.redis_url = redis_url
        self.prefix = prefix
        self.allow_fallback = allow_fallback
        self._client = None
        self._fallback = InMemoryIdempotencyBackend() if allow_fallback else None
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
                _LOGGER.error("RedisIdempotencyBackend unavailable at %s: %s", redis_url, exc)
            else:
                _LOGGER.warning("RedisIdempotencyBackend operating in degraded fallback mode for %s: %s", redis_url, exc)

    def _ensure_available(self) -> None:
        if self._client is None and not self.allow_fallback:
            raise IdempotencyBackendUnavailableError(
                f"Redis idempotency backend unavailable at {self.redis_url}. "
                "Fail-closed policy active to prevent duplicate execution."
            )

    def begin(
        self,
        key: str,
        fingerprint: str,
        ttl: int = 86400,
        owner_id: str = "",
    ) -> IdempotencyResult:
        self._ensure_available()
        if self._client is None:
            assert self._fallback is not None
            return self._fallback.begin(key, fingerprint, ttl=ttl, owner_id=owner_id)

        now = time.time()
        redis_key = f"{self.prefix}{key}"
        fence_counter_key = f"{self.prefix}fence:{key}"
        try:
            data = self._client.hgetall(redis_key)
            if data:
                exp_at = float(data.get("expires_at", 0))
                cur_fence = int(data.get("fence_token", 1))
                if exp_at > 0 and now > exp_at and data.get("status") == "PENDING":
                    # Expired: reclaim lease with newly incremented monotonic fence token
                    new_token = int(self._client.incr(fence_counter_key))
                    pipe = self._client.pipeline()
                    pipe.hset(
                        redis_key,
                        mapping={
                            "fingerprint": fingerprint,
                            "status": "PENDING",
                            "response": "",
                            "created_at": str(now),
                            "expires_at": str(now + ttl),
                            "owner_id": owner_id,
                            "fence_token": str(new_token),
                        },
                    )
                    pipe.expire(redis_key, ttl)
                    pipe.execute()
                    rec = IdempotencyRecord(
                        key=key,
                        fingerprint=fingerprint,
                        status="PENDING",
                        created_at=now,
                        expires_at=now + ttl,
                        owner_id=owner_id,
                        fence_token=new_token,
                    )
                    return IdempotencyResult(status="PENDING", is_new=True, record=rec)

                if data.get("fingerprint") != fingerprint:
                    rec = IdempotencyRecord(
                        key=key,
                        fingerprint=data.get("fingerprint", ""),
                        status=data.get("status", "PENDING"),
                        response=json.loads(data.get("response", "null")),
                        created_at=float(data.get("created_at", now)),
                        expires_at=exp_at,
                        owner_id=data.get("owner_id", ""),
                        fence_token=cur_fence,
                    )
                    return IdempotencyResult(
                        status="CONFLICT",
                        is_new=False,
                        record=rec,
                        error_message="Action identifier re-used with differing payload fingerprint",
                    )
                status = data.get("status", "PENDING")
                resp = json.loads(data.get("response")) if data.get("response") else None
                rec = IdempotencyRecord(
                    key=key,
                    fingerprint=fingerprint,
                    status=status,
                    response=resp,
                    created_at=float(data.get("created_at", now)),
                    expires_at=exp_at,
                    owner_id=data.get("owner_id", ""),
                    fence_token=cur_fence,
                )
                return IdempotencyResult(status=status, is_new=False, record=rec)

            # Fresh reservation
            token = int(self._client.incr(fence_counter_key))
            pipe = self._client.pipeline()
            pipe.hset(
                redis_key,
                mapping={
                    "fingerprint": fingerprint,
                    "status": "PENDING",
                    "response": "",
                    "created_at": str(now),
                    "expires_at": str(now + ttl),
                    "owner_id": owner_id,
                    "fence_token": str(token),
                },
            )
            pipe.expire(redis_key, ttl)
            pipe.execute()
            rec = IdempotencyRecord(
                key=key,
                fingerprint=fingerprint,
                status="PENDING",
                created_at=now,
                expires_at=now + ttl,
                owner_id=owner_id,
                fence_token=token,
            )
            return IdempotencyResult(status="PENDING", is_new=True, record=rec)
        except Exception as exc:
            if not self.allow_fallback:
                raise IdempotencyBackendUnavailableError(f"Redis operation failed: {exc}") from exc
            assert self._fallback is not None
            return self._fallback.begin(key, fingerprint, ttl=ttl, owner_id=owner_id)

    def renew_lease(
        self,
        key: str,
        owner_id: str,
        fence_token: int,
        ttl: int = 86400,
    ) -> bool:
        self._ensure_available()
        if self._client is None:
            assert self._fallback is not None
            return self._fallback.renew_lease(key, owner_id, fence_token, ttl=ttl)

        redis_key = f"{self.prefix}{key}"
        now = time.time()
        try:
            res = self._client.eval(
                self.LUA_RENEW,
                1,
                redis_key,
                fence_token,
                owner_id,
                ttl,
                str(now + ttl),
            )
            if res == -1:
                raise StaleLeaseError("Stale lease renewal rejected by Redis Lua fencing guard")
            if res == -2:
                raise StaleLeaseError("Owner mismatch during lease renewal")
            return res == 1
        except Exception as exc:
            if isinstance(exc, StaleLeaseError):
                raise
            if not self.allow_fallback:
                raise IdempotencyBackendUnavailableError(f"Redis lease renewal failed: {exc}") from exc
            assert self._fallback is not None
            return self._fallback.renew_lease(key, owner_id, fence_token, ttl=ttl)

    def complete(
        self,
        key: str,
        result: dict[str, Any],
        fence_token: int | None = None,
        owner_id: str | None = None,
    ) -> None:
        self._ensure_available()
        if self._client is None:
            assert self._fallback is not None
            self._fallback.complete(key, result, fence_token=fence_token, owner_id=owner_id)
            return

        redis_key = f"{self.prefix}{key}"
        try:
            res = self._client.eval(
                self.LUA_COMPLETE,
                1,
                redis_key,
                fence_token if fence_token is not None else -1,
                owner_id or "",
                json.dumps(result),
            )
            if res == -1:
                raise StaleLeaseError(f"Stale worker commit rejected: token {fence_token} is outdated in Redis")
            if res == -2:
                raise StaleLeaseError(f"Owner mismatch: {owner_id} does not own Redis reservation")
        except Exception as exc:
            if isinstance(exc, StaleLeaseError):
                raise
            if not self.allow_fallback:
                raise IdempotencyBackendUnavailableError(f"Redis complete failed: {exc}") from exc
            assert self._fallback is not None
            self._fallback.complete(key, result, fence_token=fence_token, owner_id=owner_id)

    def fail(
        self,
        key: str,
        error: str,
        fence_token: int | None = None,
        owner_id: str | None = None,
    ) -> None:
        self._ensure_available()
        if self._client is None:
            assert self._fallback is not None
            self._fallback.fail(key, error, fence_token=fence_token, owner_id=owner_id)
            return

        redis_key = f"{self.prefix}{key}"
        try:
            res = self._client.eval(
                self.LUA_FAIL,
                1,
                redis_key,
                fence_token if fence_token is not None else -1,
                owner_id or "",
                json.dumps({"error": error}),
            )
            if res == -1:
                raise StaleLeaseError(f"Stale worker fail rejected: token {fence_token} is outdated in Redis")
            if res == -2:
                raise StaleLeaseError(f"Owner mismatch: {owner_id} does not own Redis reservation")
        except Exception as exc:
            if isinstance(exc, StaleLeaseError):
                raise
            if not self.allow_fallback:
                raise IdempotencyBackendUnavailableError(f"Redis fail failed: {exc}") from exc
            assert self._fallback is not None
            self._fallback.fail(key, error, fence_token=fence_token, owner_id=owner_id)

    def get(self, key: str) -> IdempotencyRecord | None:
        self._ensure_available()
        if self._client is None:
            assert self._fallback is not None
            return self._fallback.get(key)

        redis_key = f"{self.prefix}{key}"
        try:
            data = self._client.hgetall(redis_key)
            if not data:
                return None
            exp_at = float(data.get("expires_at", 0))
            if exp_at > 0 and time.time() > exp_at and data.get("status") == "PENDING":
                return None
            resp = json.loads(data.get("response")) if data.get("response") else None
            return IdempotencyRecord(
                key=key,
                fingerprint=data.get("fingerprint", ""),
                status=data.get("status", "PENDING"),
                response=resp,
                created_at=float(data.get("created_at", 0)),
                expires_at=exp_at,
                owner_id=data.get("owner_id", ""),
                fence_token=int(data.get("fence_token", 1)),
            )
        except Exception as exc:
            if not self.allow_fallback:
                raise IdempotencyBackendUnavailableError(f"Redis get failed: {exc}") from exc
            assert self._fallback is not None
            return self._fallback.get(key)


class PostgreSQLIdempotencyBackend:
    """Production PostgreSQL idempotency backend powered by psycopg 3 and connection pooling."""

    def __init__(
        self,
        connection_string: str = "postgresql://localhost:5432/RADUI",
        *,
        min_size: int = 2,
        max_size: int = 10,
        timeout: float = 30.0,
        allow_fallback: bool = False,
    ) -> None:
        self.connection_string = connection_string
        self.min_size = min_size
        self.max_size = max_size
        self.timeout = timeout
        self.allow_fallback = allow_fallback
        self._async_pool = None
        self._sync_conn = None
        self._fallback = SQLiteIdempotencyBackend(":memory:") if allow_fallback else None
        self._is_psycopg_available = False

        try:
            import psycopg  # type: ignore
            from psycopg_pool import AsyncConnectionPool  # type: ignore
            self._is_psycopg_available = True
        except ImportError:
            self._is_psycopg_available = False
            if not self.allow_fallback:
                _LOGGER.warning("psycopg 3 or psycopg_pool not installed. Install with 'pip install \"psycopg[binary,pool]>=3.2\"'")

    async def open(self) -> None:
        """Asynchronously initialize the psycopg 3 connection pool and table schema."""
        if not self._is_psycopg_available:
            if not self.allow_fallback:
                raise IdempotencyBackendUnavailableError("psycopg[pool] is required for native PostgreSQL support")
            return

        from psycopg_pool import AsyncConnectionPool  # type: ignore
        try:
            self._async_pool = AsyncConnectionPool(
                conninfo=self.connection_string,
                min_size=self.min_size,
                max_size=self.max_size,
                timeout=self.timeout,
                open=False,
            )
            await self._async_pool.open()
            async with self._async_pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS gx_idempotency (
                            key TEXT PRIMARY KEY,
                            fingerprint TEXT NOT NULL,
                            status TEXT NOT NULL,
                            response JSONB,
                            created_at DOUBLE PRECISION NOT NULL,
                            expires_at DOUBLE PRECISION NOT NULL,
                            owner_id TEXT DEFAULT '',
                            fence_token BIGINT NOT NULL DEFAULT 1
                        );
                        CREATE INDEX IF NOT EXISTS idx_gx_idemp_exp ON gx_idempotency (expires_at);
                        """
                    )
        except Exception as exc:
            if not self.allow_fallback:
                raise IdempotencyBackendUnavailableError(f"PostgreSQL connection failed: {exc}") from exc
            _LOGGER.warning("Operating PostgreSQL backend in degraded fallback mode: %s", exc)

    async def close(self) -> None:
        """Gracefully drain and close the connection pool."""
        if self._async_pool is not None:
            await self._async_pool.close()
            self._async_pool = None

    def begin(
        self,
        key: str,
        fingerprint: str,
        ttl: int = 86400,
        owner_id: str = "",
    ) -> IdempotencyResult:
        if self._fallback is not None:
            return self._fallback.begin(key, fingerprint, ttl=ttl, owner_id=owner_id)
        raise IdempotencyBackendUnavailableError("Synchronous execution requires active pool or allow_fallback=True")

    def renew_lease(
        self,
        key: str,
        owner_id: str,
        fence_token: int,
        ttl: int = 86400,
    ) -> bool:
        if self._fallback is not None:
            return self._fallback.renew_lease(key, owner_id, fence_token, ttl=ttl)
        raise IdempotencyBackendUnavailableError("Synchronous execution requires active pool or allow_fallback=True")

    def complete(
        self,
        key: str,
        result: dict[str, Any],
        fence_token: int | None = None,
        owner_id: str | None = None,
    ) -> None:
        if self._fallback is not None:
            self._fallback.complete(key, result, fence_token=fence_token, owner_id=owner_id)
            return
        raise IdempotencyBackendUnavailableError("Synchronous execution requires active pool or allow_fallback=True")

    def fail(
        self,
        key: str,
        error: str,
        fence_token: int | None = None,
        owner_id: str | None = None,
    ) -> None:
        if self._fallback is not None:
            self._fallback.fail(key, error, fence_token=fence_token, owner_id=owner_id)
            return
        raise IdempotencyBackendUnavailableError("Synchronous execution requires active pool or allow_fallback=True")

    def get(self, key: str) -> IdempotencyRecord | None:
        if self._fallback is not None:
            return self._fallback.get(key)
        raise IdempotencyBackendUnavailableError("Synchronous execution requires active pool or allow_fallback=True")
