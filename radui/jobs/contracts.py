from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED, self.CANCELLED}


@dataclass(frozen=True)
class JobSnapshot:
    """Public, immutable view of one job execution."""

    id: str
    name: str
    status: JobStatus
    session_id: str
    user_id: str | None
    progress: int | None
    message: str
    result_text: str | None
    result_available: bool
    error_type: str | None
    created_at: str
    updated_at: str
    tenant_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "result_text": self.result_text,
            "result_available": self.result_available,
            "error_type": self.error_type,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tenant_id": self.tenant_id,
        }


class JobError(RuntimeError):
    """Base exception for RADUI job operations."""


class JobNotFoundError(JobError):
    """Raised when a job is unknown or belongs to another session."""


class JobCapacityError(JobError):
    """Raised when the local executor has reached its configured capacity."""


class JobCancelledError(JobError):
    """Raised when a job checks its cancellation token after cancellation."""
