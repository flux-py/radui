"""RADUI AI Chat History Persistence and Thread Repository."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import sqlite3
import threading
import uuid
from typing import Any


def _resolve_tenant(explicit_tenant: str | None = None) -> str:
    if explicit_tenant:
        return explicit_tenant
    try:
        from radui.state.runtime import get_active_context
        ctx = get_active_context()
        if ctx and ctx.tenant_id:
            return ctx.tenant_id
    except Exception:
        pass
    return "_default"


@dataclass
class ChatMessageRecord:
    id: str
    thread_id: str
    role: str
    content: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)
    tenant_id: str = "_default"


class SQLiteChatRepository:
    """Persistent, thread-safe SQLite repository for conversational threads with tenant isolation."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS RADUI_chat_messages (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT '_default',
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            try:
                conn.execute("ALTER TABLE RADUI_chat_messages ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '_default'")
            except Exception:
                pass
            conn.execute("CREATE INDEX IF NOT EXISTS idx_thread_tenant ON RADUI_chat_messages(thread_id, tenant_id)")

    def add_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        tenant_id: str | None = None,
    ) -> ChatMessageRecord:
        msg_id = f"msg-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {})
        t_id = _resolve_tenant(tenant_id)
        conn = self._get_conn()
        with conn:
            conn.execute(
                """
                INSERT INTO RADUI_chat_messages (id, thread_id, tenant_id, role, content, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (msg_id, thread_id, t_id, role, content, meta_json, now),
            )
        return ChatMessageRecord(
            id=msg_id,
            thread_id=thread_id,
            role=role,
            content=content,
            created_at=now,
            metadata=metadata or {},
            tenant_id=t_id,
        )

    def get_messages(self, thread_id: str, limit: int = 50, tenant_id: str | None = None) -> list[ChatMessageRecord]:
        t_id = _resolve_tenant(tenant_id)
        conn = self._get_conn()
        cursor = conn.execute(
            """
            SELECT id, thread_id, tenant_id, role, content, metadata_json, created_at
            FROM RADUI_chat_messages
            WHERE thread_id = ? AND tenant_id = ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (thread_id, t_id, limit),
        )
        records = []
        for row in cursor.fetchall():
            meta = {}
            try:
                meta = json.loads(row["metadata_json"])
            except Exception:
                pass
            records.append(
                ChatMessageRecord(
                    id=row["id"],
                    thread_id=row["thread_id"],
                    role=row["role"],
                    content=row["content"],
                    created_at=row["created_at"],
                    metadata=meta,
                    tenant_id=row["tenant_id"],
                )
            )
        return records

    def delete_thread(self, thread_id: str, tenant_id: str | None = None) -> None:
        t_id = _resolve_tenant(tenant_id)
        conn = self._get_conn()
        with conn:
            conn.execute("DELETE FROM RADUI_chat_messages WHERE thread_id = ? AND tenant_id = ?", (thread_id, t_id))

    def list_threads(self, tenant_id: str | None = None) -> list[str]:
        t_id = _resolve_tenant(tenant_id)
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT DISTINCT thread_id FROM RADUI_chat_messages WHERE tenant_id = ? ORDER BY created_at DESC",
            (t_id,),
        )
        return [row[0] for row in cursor.fetchall()]

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None
