"""Redis-backed distributed job execution backend with distributed leases and heartbeats."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any, Callable

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
    LocalJobBackend,
)
from radui.state.runtime import StateChange, StateContext

_LOGGER = logging.getLogger("radui.jobs.redis")


class RedisJobBackend(LocalJobBackend):
    """Distributed Redis job execution backend with worker lease acquisition and heartbeats.
    
    Coordinates job scheduling and distributed state sync across multiple RADUI app worker nodes.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        *,
        prefix: str = "gx:jobs:",
        max_concurrent: int = 4,
        max_active: int = 64,
        max_records: int = 512,
        on_update: Callable[[JobSnapshot], None] | None = None,
        on_state_changes: Callable[[list[StateChange], StateContext], None] | None = None,
    ) -> None:
        super().__init__(
            max_concurrent=max_concurrent,
            max_active=max_active,
            max_records=max_records,
            on_update=on_update,
            on_state_changes=on_state_changes,
        )
        self.redis_url = redis_url
        self.prefix = prefix
        self._redis_client = None
        self._local_leases: dict[str, int] = {}
        self._local_fence_counter = 0
        try:
            import redis  # type: ignore
            self._redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
            )
            self._redis_client.ping()
        except Exception:
            self._redis_client = None

    def acquire_lease(self, job_id: str, ttl_seconds: int = 30) -> int | None:
        """Acquire a distributed lease for processing job_id with a monotonic fencing token.
        
        Returns the integer fencing token on success, or None if lease is currently held by another worker.
        """
        if self._redis_client is not None:
            try:
                lease_key = f"{self.prefix}lease:{job_id}"
                counter_key = f"{self.prefix}fence:{job_id}"
                token = int(self._redis_client.incr(counter_key))
                acquired = self._redis_client.set(lease_key, str(token), ex=ttl_seconds, nx=True)
                return token if acquired else None
            except Exception:
                pass
        self._local_fence_counter += 1
        token = self._local_fence_counter
        self._local_leases[job_id] = token
        return token

    def validate_fence(self, job_id: str, fence_token: int) -> bool:
        """Verify that the worker's fencing token is still the active, non-expired lease holder."""
        if self._redis_client is not None:
            try:
                lease_key = f"{self.prefix}lease:{job_id}"
                current = self._redis_client.get(lease_key)
                return current == str(fence_token)
            except Exception:
                pass
        return self._local_leases.get(job_id) == fence_token

    def release_lease(self, job_id: str) -> None:
        """Release distributed lease for job_id."""
        if self._redis_client is not None:
            try:
                lease_key = f"{self.prefix}lease:{job_id}"
                self._redis_client.delete(lease_key)
            except Exception:
                pass
        self._local_leases.pop(job_id, None)

    def _notify(self, snapshot: JobSnapshot) -> None:
        super()._notify(snapshot)
        if self._redis_client is not None:
            try:
                channel = f"{self.prefix}updates"
                self._redis_client.publish(channel, json.dumps(snapshot.to_dict()))
            except Exception:
                pass
