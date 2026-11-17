from __future__ import annotations

from collections import defaultdict, deque
import logging
import threading
import time
from typing import Any, Protocol
import uuid

from radui.observability import LatencyTracker

_LOGGER = logging.getLogger("radui.transport.governance")

# Atomic Lua scripts for distributed SSE governance using Redis server TIME.

_ADMIT_LUA = """
local sess_key = KEYS[1]
local ip_key = KEYS[2]
local rl_key = KEYS[3]
local worker_key = KEYS[4]

local conn_member = ARGV[1]
local lease_ttl_ms = tonumber(ARGV[2])
local max_per_session = tonumber(ARGV[3])
local max_per_ip = tonumber(ARGV[4])
local rate_limit = tonumber(ARGV[5])
local rate_window_ms = tonumber(ARGV[6])
local has_ip = ARGV[7]
local rl_member = ARGV[8]

local t = redis.call('TIME')
local now_ms = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local exp_ms = now_ms + lease_ttl_ms

if rate_limit > 0 and rate_window_ms > 0 then
    redis.call('ZREMRANGEBYSCORE', rl_key, '-inf', now_ms - rate_window_ms)
    local rl_count = redis.call('ZCARD', rl_key)
    if rl_count >= rate_limit then
        return {0, 'rate_limit'}
    end
    redis.call('ZADD', rl_key, now_ms, rl_member)
    redis.call('PEXPIRE', rl_key, rate_window_ms + 1000)
end

redis.call('ZREMRANGEBYSCORE', sess_key, '-inf', now_ms)
if max_per_session > 0 and redis.call('ZCARD', sess_key) >= max_per_session then
    return {0, 'session_limit'}
end

if has_ip == '1' then
    redis.call('ZREMRANGEBYSCORE', ip_key, '-inf', now_ms)
    if max_per_ip > 0 and redis.call('ZCARD', ip_key) >= max_per_ip then
        return {0, 'ip_limit'}
    end
end

redis.call('ZADD', sess_key, exp_ms, conn_member)
redis.call('PEXPIRE', sess_key, lease_ttl_ms + 5000)

if has_ip == '1' then
    redis.call('ZADD', ip_key, exp_ms, conn_member)
    redis.call('PEXPIRE', ip_key, lease_ttl_ms + 5000)
end

redis.call('ZADD', worker_key, exp_ms, conn_member)
redis.call('PEXPIRE', worker_key, lease_ttl_ms + 5000)

return {1, 'ok'}
"""

_RELEASE_LUA = """
local sess_key = KEYS[1]
local ip_key = KEYS[2]
local worker_key = KEYS[3]

local conn_member = ARGV[1]
local has_ip = ARGV[2]

local removed = redis.call('ZREM', sess_key, conn_member)
if has_ip == '1' then
    removed = removed + redis.call('ZREM', ip_key, conn_member)
end
redis.call('ZREM', worker_key, conn_member)
return removed
"""

_RENEW_BATCH_LUA = """
local worker_key = KEYS[1]
local lease_ttl_ms = tonumber(ARGV[1])

local t = redis.call('TIME')
local now_ms = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local exp_ms = now_ms + lease_ttl_ms

redis.call('ZREMRANGEBYSCORE', worker_key, '-inf', now_ms)

local renewed = 0
for i = 2, #ARGV, 3 do
    local member = ARGV[i]
    local sess_key = ARGV[i + 1]
    local ip_key = ARGV[i + 2]
    if redis.call('ZSCORE', worker_key, member) then
        redis.call('ZADD', worker_key, exp_ms, member)
        redis.call('ZADD', sess_key, exp_ms, member)
        redis.call('PEXPIRE', sess_key, lease_ttl_ms + 5000)
        if ip_key ~= '' then
            redis.call('ZADD', ip_key, exp_ms, member)
            redis.call('PEXPIRE', ip_key, lease_ttl_ms + 5000)
        end
        renewed = renewed + 1
    end
end

if redis.call('ZCARD', worker_key) > 0 then
    redis.call('PEXPIRE', worker_key, lease_ttl_ms + 5000)
end
return renewed
"""


class SSEGovernanceBackend(Protocol):
    """Protocol for process-local or distributed SSE admission, release, and lease renewal."""

    def try_acquire(
        self,
        session_id: str,
        client_ip: str | None = None,
        *,
        connection_id: str | None = None,
        max_per_session: int = 8,
        max_per_ip: int = 32,
        rate_limit: int = 30,
        rate_window_seconds: float = 60.0,
    ) -> tuple[bool, str | None, int, str | None]: ...

    def release(
        self,
        session_id: str,
        client_ip: str | None = None,
        *,
        connection_id: str | None = None,
    ) -> bool: ...

    def renew_leases(self, *, batch_size: int = 50) -> int: ...

    def release_all(self) -> int: ...

    def active_count(self) -> int: ...


class InMemorySSEGovernance:
    """Process-local SSE admission, rate limiting, and connection tracking."""

    def __init__(self, *, worker_id: str = "worker-local") -> None:
        self.worker_id = worker_id
        self._lock = threading.RLock()
        self._active_by_session: dict[str, int] = defaultdict(int)
        self._active_by_ip: dict[str, int] = defaultdict(int)
        self._rate_buckets: dict[str, deque[float]] = {}
        self._owned: dict[str, tuple[str, str | None]] = {}
        self._anon_ids: dict[tuple[str, str | None], deque[str]] = defaultdict(deque)

    def try_acquire(
        self,
        session_id: str,
        client_ip: str | None = None,
        *,
        connection_id: str | None = None,
        max_per_session: int = 8,
        max_per_ip: int = 32,
        rate_limit: int = 30,
        rate_window_seconds: float = 60.0,
    ) -> tuple[bool, str | None, int, str | None]:
        now = time.monotonic()
        rate_key = f"ip:{client_ip}" if client_ip else f"session:{session_id}"
        with self._lock:
            if rate_limit > 0 and rate_window_seconds > 0:
                bucket = self._rate_buckets.get(rate_key)
                if bucket is None:
                    bucket = deque()
                    self._rate_buckets[rate_key] = bucket
                cutoff = now - rate_window_seconds
                while bucket and bucket[0] <= cutoff:
                    bucket.popleft()
                if len(bucket) >= rate_limit:
                    return False, "SSE connection rate limit exceeded", 429, "rate_limit"
                bucket.append(now)

            if max_per_session > 0 and self._active_by_session[session_id] >= max_per_session:
                return False, "Too many concurrent SSE connections for session", 429, "session_limit"

            if client_ip and max_per_ip > 0 and self._active_by_ip[client_ip] >= max_per_ip:
                return False, "Too many concurrent SSE connections for IP", 429, "ip_limit"

            conn_id = connection_id or uuid.uuid4().hex
            self._active_by_session[session_id] += 1
            if client_ip:
                self._active_by_ip[client_ip] += 1
            self._owned[conn_id] = (session_id, client_ip)
            if connection_id is None:
                self._anon_ids[(session_id, client_ip)].append(conn_id)
            return True, None, 200, conn_id

    def release(
        self,
        session_id: str,
        client_ip: str | None = None,
        *,
        connection_id: str | None = None,
    ) -> bool:
        with self._lock:
            cid = connection_id
            if cid is None:
                q = self._anon_ids.get((session_id, client_ip))
                if q:
                    cid = q.popleft()
                    if not q:
                        self._anon_ids.pop((session_id, client_ip), None)
            if cid is not None and cid in self._owned:
                self._owned.pop(cid, None)

            cur_s = self._active_by_session.get(session_id, 0)
            if cur_s <= 1:
                self._active_by_session.pop(session_id, None)
            else:
                self._active_by_session[session_id] = cur_s - 1

            if client_ip:
                cur_ip = self._active_by_ip.get(client_ip, 0)
                if cur_ip <= 1:
                    self._active_by_ip.pop(client_ip, None)
                else:
                    self._active_by_ip[client_ip] = cur_ip - 1
            return True

    def renew_leases(self, *, batch_size: int = 50) -> int:
        return 0

    def release_all(self) -> int:
        with self._lock:
            count = len(self._owned)
            self._owned.clear()
            self._anon_ids.clear()
            self._active_by_session.clear()
            self._active_by_ip.clear()
            return count

    def active_count(self) -> int:
        with self._lock:
            return sum(self._active_by_session.values())


class RedisSSEGovernance:
    """Distributed Redis-backed SSE governance using atomic Lua scripts and server TIME leases."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        backend: Any | None = None,
        prefix: str = "gx:gov:sse:",
        worker_id: str | None = None,
        lease_ttl_seconds: float = 30.0,
        fail_open: bool = False,
        max_owned_connections: int = 10000,
    ) -> None:
        self._client = client
        self._backend = backend
        self.prefix = prefix
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.lease_ttl_seconds = max(3.0, float(lease_ttl_seconds))
        self.fail_open = bool(fail_open)
        self.max_owned_connections = max(1, int(max_owned_connections))
        self._lock = threading.RLock()
        self._owned: dict[str, tuple[str, str | None]] = {}
        self._anon_ids: dict[tuple[str, str | None], deque[str]] = defaultdict(deque)
        self._local_fallback = InMemorySSEGovernance(worker_id=self.worker_id)
        self.leases_renewed: int = 0
        self.renewal_failures: int = 0
        self.expired_leases: int = 0
        self.admitted_connections: int = 0
        self.rejected_by_reason: dict[str, int] = defaultdict(int)
        self.backend_errors: int = 0
        self._lat_admit = LatencyTracker()

    def _get_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        if self._backend is not None:
            cli = getattr(self._backend, "_client", None)
            if cli is not None:
                return cli
            reconnect = getattr(self._backend, "reconnect", None)
            if callable(reconnect) and reconnect():
                return getattr(self._backend, "_client", None)
        return None

    def _session_key(self, session_id: str) -> str:
        return f"{self.prefix}session:{session_id}"

    def _ip_key(self, client_ip: str | None) -> str:
        return f"{self.prefix}ip:{client_ip}" if client_ip else f"{self.prefix}ip:_none_"

    def _rate_key(self, session_id: str, client_ip: str | None) -> str:
        ident = f"ip:{client_ip}" if client_ip else f"session:{session_id}"
        return f"{self.prefix}rl:{ident}"

    def _worker_key(self) -> str:
        return f"{self.prefix}worker:{self.worker_id}"

    def _member(self, conn_id: str) -> str:
        return f"{self.worker_id}:{conn_id}"

    def try_acquire(
        self,
        session_id: str,
        client_ip: str | None = None,
        *,
        connection_id: str | None = None,
        max_per_session: int = 8,
        max_per_ip: int = 32,
        rate_limit: int = 30,
        rate_window_seconds: float = 60.0,
    ) -> tuple[bool, str | None, int, str | None]:
        with self._lock:
            if len(self._owned) >= self.max_owned_connections:
                self.rejected_by_reason["worker_capacity"] += 1
                return False, "Worker SSE connection capacity reached", 503, "worker_capacity"

        t0 = time.perf_counter()
        conn_id = connection_id or uuid.uuid4().hex
        member = self._member(conn_id)
        client = self._get_client()
        if client is None:
            res = self._handle_backend_unavailable(
                session_id,
                client_ip,
                conn_id=conn_id,
                connection_id=connection_id,
                max_per_session=max_per_session,
                max_per_ip=max_per_ip,
                rate_limit=rate_limit,
                rate_window_seconds=rate_window_seconds,
            )
            self._lat_admit.record((time.perf_counter() - t0) * 1000.0, error=not res[0])
            if not res[0] and res[3]:
                with self._lock:
                    self.rejected_by_reason[res[3]] += 1
            return res

        has_ip = "1" if client_ip else "0"
        lease_ttl_ms = int(self.lease_ttl_seconds * 1000)
        rate_window_ms = int(max(0.0, rate_window_seconds) * 1000)
        rl_member = f"{time.monotonic_ns()}:{conn_id}"

        try:
            res = client.eval(
                _ADMIT_LUA,
                4,
                self._session_key(session_id),
                self._ip_key(client_ip),
                self._rate_key(session_id, client_ip),
                self._worker_key(),
                member,
                str(lease_ttl_ms),
                str(int(max_per_session)),
                str(int(max_per_ip)),
                str(int(rate_limit)),
                str(rate_window_ms),
                has_ip,
                rl_member,
            )
        except Exception as exc:
            self._lat_admit.record((time.perf_counter() - t0) * 1000.0, error=True)
            with self._lock:
                self.backend_errors += 1
            if self._backend is not None and hasattr(self._backend, "_client"):
                self._backend._client = None
            _LOGGER.warning("RedisSSEGovernance admit failed: %s", type(exc).__name__)
            res = self._handle_backend_unavailable(
                session_id,
                client_ip,
                conn_id=conn_id,
                connection_id=connection_id,
                max_per_session=max_per_session,
                max_per_ip=max_per_ip,
                rate_limit=rate_limit,
                rate_window_seconds=rate_window_seconds,
            )
            if not res[0] and res[3]:
                with self._lock:
                    self.rejected_by_reason[res[3]] += 1
            return res

        admitted = bool(res and int(res[0]) == 1)
        reason_code = str(res[1]) if res and len(res) > 1 else "unknown"
        self._lat_admit.record((time.perf_counter() - t0) * 1000.0)
        if not admitted:
            with self._lock:
                self.rejected_by_reason[reason_code] += 1
            if reason_code == "rate_limit":
                return False, "SSE connection rate limit exceeded", 429, "rate_limit"
            if reason_code == "session_limit":
                return False, "Too many concurrent SSE connections for session", 429, "session_limit"
            if reason_code == "ip_limit":
                return False, "Too many concurrent SSE connections for IP", 429, "ip_limit"
            return False, "SSE connection rejected", 429, reason_code

        with self._lock:
            self.admitted_connections += 1
            self._owned[conn_id] = (session_id, client_ip)
            if connection_id is None:
                self._anon_ids[(session_id, client_ip)].append(conn_id)
        return True, None, 200, conn_id

    def _handle_backend_unavailable(
        self,
        session_id: str,
        client_ip: str | None,
        *,
        conn_id: str,
        connection_id: str | None,
        max_per_session: int,
        max_per_ip: int,
        rate_limit: int,
        rate_window_seconds: float,
    ) -> tuple[bool, str | None, int, str | None]:
        with self._lock:
            self.backend_errors += 1
        if not self.fail_open:
            return False, "SSE governance backend unavailable", 503, "backend_unavailable"
        return self._local_fallback.try_acquire(
            session_id,
            client_ip,
            connection_id=connection_id or conn_id,
            max_per_session=max_per_session,
            max_per_ip=max_per_ip,
            rate_limit=rate_limit,
            rate_window_seconds=rate_window_seconds,
        )

    def release(
        self,
        session_id: str,
        client_ip: str | None = None,
        *,
        connection_id: str | None = None,
    ) -> bool:
        with self._lock:
            cid = connection_id
            if cid is None:
                q = self._anon_ids.get((session_id, client_ip))
                if q:
                    cid = q.popleft()
                    if not q:
                        self._anon_ids.pop((session_id, client_ip), None)
            if cid is not None:
                self._owned.pop(cid, None)

        if self.fail_open and cid in self._local_fallback._owned:
            self._local_fallback.release(session_id, client_ip, connection_id=cid)

        if cid is None:
            return False

        client = self._get_client()
        if client is None:
            return False
        has_ip = "1" if client_ip else "0"
        try:
            client.eval(
                _RELEASE_LUA,
                3,
                self._session_key(session_id),
                self._ip_key(client_ip),
                self._worker_key(),
                self._member(cid),
                has_ip,
            )
            return True
        except Exception as exc:
            with self._lock:
                self.backend_errors += 1
            _LOGGER.warning("RedisSSEGovernance release failed: %s", type(exc).__name__)
            return False

    def renew_leases(self, *, batch_size: int = 50) -> int:
        with self._lock:
            items = list(self._owned.items())
        if not items:
            return 0
        client = self._get_client()
        if client is None:
            return 0

        lease_ttl_ms = int(self.lease_ttl_seconds * 1000)
        total_renewed = 0
        step = max(1, int(batch_size))
        for idx in range(0, len(items), step):
            chunk = items[idx : idx + step]
            argv: list[str] = [str(lease_ttl_ms)]
            for cid, (sess_id, cip) in chunk:
                argv.append(self._member(cid))
                argv.append(self._session_key(sess_id))
                argv.append(self._ip_key(cip) if cip else "")
            try:
                renewed = int(client.eval(_RENEW_BATCH_LUA, 1, self._worker_key(), *argv) or 0)
                total_renewed += renewed
                if renewed < len(chunk):
                    with self._lock:
                        self.expired_leases += (len(chunk) - renewed)
            except Exception as exc:
                with self._lock:
                    self.backend_errors += 1
                    self.renewal_failures += 1
                _LOGGER.warning("RedisSSEGovernance renew_leases failed: %s", type(exc).__name__)
                break
        if total_renewed:
            with self._lock:
                self.leases_renewed += total_renewed
        return total_renewed

    def release_all(self) -> int:
        with self._lock:
            items = list(self._owned.items())
            self._owned.clear()
            self._anon_ids.clear()
        released = 0
        for cid, (sess_id, cip) in items:
            if self.release(sess_id, cip, connection_id=cid):
                released += 1
        client = self._get_client()
        if client is not None:
            try:
                client.delete(self._worker_key())
            except Exception:
                pass
        self._local_fallback.release_all()
        return released

    def active_count(self) -> int:
        with self._lock:
            return len(self._owned)

    def observability_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "mode": "redis",
                "active_connections": len(self._owned),
                "operations": {
                    "admitted": self.admitted_connections,
                    "rejected_rate_limit": self.rejected_by_reason.get("rate_limit", 0),
                    "rejected_session_limit": self.rejected_by_reason.get("session_limit", 0),
                    "rejected_ip_limit": self.rejected_by_reason.get("ip_limit", 0),
                    "rejected_worker_capacity": self.rejected_by_reason.get("worker_capacity", 0),
                    "rejected_backend_unavailable": self.rejected_by_reason.get("backend_unavailable", 0),
                    "leases_renewed": self.leases_renewed,
                    "expired_leases": self.expired_leases,
                    "renewal_failures": self.renewal_failures,
                    "backend_errors": self.backend_errors,
                },
                "latencies": {
                    "admit": self._lat_admit.snapshot(),
                },
            }
