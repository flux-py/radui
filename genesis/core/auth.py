from __future__ import annotations

from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable


@dataclass(frozen=True)
class User:
    """Represents an authenticated user within radui."""

    id: str
    username: str = ""
    roles: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_role(self, role: str) -> bool:
        return role in self.roles or "admin" in self.roles

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions or "admin" in self.roles


class AuthenticationError(Exception):
    """Raised when authentication is required but missing."""


class AuthorizationError(Exception):
    """Raised when a user lacks required roles or permissions."""


class RBACPolicy:
    """Manages role-to-permission mappings and evaluation."""

    def __init__(self) -> None:
        self._role_permissions: dict[str, set[str]] = {
            "admin": {"*"},
            "editor": {"read", "write", "update"},
            "viewer": {"read"},
        }

    def register_role(self, role: str, permissions: set[str] | list[str]) -> None:
        self._role_permissions[role] = set(permissions)

    def check_permission(self, roles: set[str] | frozenset[str], permission: str) -> bool:
        if "admin" in roles:
            return True
        for role in roles:
            perms = self._role_permissions.get(role, set())
            if "*" in perms or permission in perms:
                return True
        return False
