"""RADUI Collaborative Multi-User State & Real-Time Presence Subsystem."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class PresenceUser:
    """An active user occupant in a collaborative room."""

    user_id: str
    username: str
    avatar_url: str | None = None
    color: str = "#10b981"
    status: Literal["online", "idle", "busy", "away"] = "online"
    current_field: str | None = None
    cursor: tuple[float, float] | None = None
    last_heartbeat: float = field(default_factory=time.time)


class PresenceManager:
    """Thread-safe multi-user presence and collaborative field locking manager."""

    def __init__(self) -> None:
        self._rooms: dict[str, dict[str, PresenceUser]] = {}
        self._field_locks: dict[str, tuple[str, float]] = {}  # f"{room}:{field}" -> (user_id, expiry)
        self._lock = threading.RLock()

    def join(self, room: str, user: PresenceUser) -> list[PresenceUser]:
        """Register user presence in a specific collaborative room."""
        with self._lock:
            if room not in self._rooms:
                self._rooms[room] = {}
            user.last_heartbeat = time.time()
            self._rooms[room][user.user_id] = user
            return self.get_active_users(room)

    def heartbeat(
        self,
        room: str,
        user_id: str,
        current_field: str | None = None,
        cursor: tuple[float, float] | None = None,
    ) -> list[PresenceUser]:
        """Update last heartbeat, cursor coordinates, and active focused input field."""
        with self._lock:
            room_users = self._rooms.get(room, {})
            if user_id in room_users:
                user = room_users[user_id]
                user.last_heartbeat = time.time()
                if current_field is not None:
                    user.current_field = current_field
                if cursor is not None:
                    user.cursor = cursor
            return self.get_active_users(room)

    def leave(self, room: str, user_id: str) -> None:
        """Explicitly remove a user from an active presence room."""
        with self._lock:
            if room in self._rooms and user_id in self._rooms[room]:
                del self._rooms[room][user_id]
            # Release any active field locks owned by this user
            prefix = f"{room}:"
            expired_locks = [k for k, (u, _) in self._field_locks.items() if k.startswith(prefix) and u == user_id]
            for k in expired_locks:
                del self._field_locks[k]

    def get_active_users(self, room: str, timeout_seconds: float = 30.0) -> list[PresenceUser]:
        """Retrieve all currently active users in a room whose heartbeats are fresh."""
        now = time.time()
        with self._lock:
            room_users = self._rooms.get(room, {})
            active: list[PresenceUser] = []
            stale_keys = []
            for u_id, u in room_users.items():
                if now - u.last_heartbeat <= timeout_seconds:
                    active.append(u)
                else:
                    stale_keys.append(u_id)
            for k in stale_keys:
                del room_users[k]
            return active

    def lock_field(self, room: str, field_id: str, user_id: str, timeout_seconds: float = 15.0) -> bool:
        """Attempt to acquire a cooperative lock on a specific form input field."""
        lock_key = f"{room}:{field_id}"
        now = time.time()
        with self._lock:
            current = self._field_locks.get(lock_key)
            if current is not None:
                owner, expiry = current
                if owner != user_id and now < expiry:
                    return False  # Field locked by another user
            self._field_locks[lock_key] = (user_id, now + timeout_seconds)
            return True

    def unlock_field(self, room: str, field_id: str, user_id: str) -> bool:
        """Release a cooperative lock on a form input field."""
        lock_key = f"{room}:{field_id}"
        with self._lock:
            current = self._field_locks.get(lock_key)
            if current and current[0] == user_id:
                del self._field_locks[lock_key]
                return True
            return False

    def get_field_lock(self, room: str, field_id: str) -> str | None:
        """Return the user ID of the occupant holding an active lock, or None."""
        lock_key = f"{room}:{field_id}"
        now = time.time()
        with self._lock:
            current = self._field_locks.get(lock_key)
            if current and now < current[1]:
                return current[0]
            return None


_GLOBAL_PRESENCE = PresenceManager()


def get_global_presence_manager() -> PresenceManager:
    """Return the global process-wide PresenceManager instance."""
    return _GLOBAL_PRESENCE
