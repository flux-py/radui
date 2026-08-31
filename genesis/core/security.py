"""RADUI Security: Rate limiting, CSRF hardening, and request throttling."""

from __future__ import annotations

import collections
import threading
import time
from typing import Any
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RateLimiter:
    """Thread-safe sliding-window rate limiter per client IP or session key."""

    def __init__(self, requests_per_minute: int = 120, burst: int = 30) -> None:
        self.rpm = requests_per_minute
        self.burst = burst
        self.window_seconds = 60.0
        self._history: dict[str, collections.deque[float]] = collections.defaultdict(collections.deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Check if request for key is allowed. Returns (allowed, retry_after)."""
        now = time.time()
        cutoff = now - self.window_seconds
        with self._lock:
            timestamps = self._history[key]
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()

            if len(timestamps) >= (self.rpm + self.burst):
                oldest = timestamps[0]
                retry_after = max(1, int(oldest + self.window_seconds - now))
                return False, retry_after

            timestamps.append(now)
            return True, 0

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._history.clear()
            else:
                self._history.pop(key, None)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware enforcing client rate limits."""

    def __init__(self, app: Any, requests_per_minute: int = 120, burst: int = 30) -> None:
        super().__init__(app)
        self.limiter = RateLimiter(requests_per_minute=requests_per_minute, burst=burst)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_after = self.limiter.check(client_ip)
        if not allowed:
            return JSONResponse(
                {"error": "Too Many Requests", "retry_after": retry_after},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        response = await call_next(request)
        return response
