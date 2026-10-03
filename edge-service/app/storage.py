from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .models import Activity, Memory, SyncState, utc_now


class LocalStorage:
    """SQLite owns notes, policy state, activity, and the sync outbox."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self._create_schema()

    def _create_schema(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memory (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                site_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                source TEXT NOT NULL,
                source_url TEXT,
                verified_status TEXT NOT NULL,
                privacy_level TEXT NOT NULL,
                sync_state TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                vector_id TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_memory_kind ON memory(kind);
            CREATE INDEX IF NOT EXISTS idx_memory_site ON memory(site_id);
            CREATE INDEX IF NOT EXISTS idx_memory_state ON memory(sync_state);
            CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                delivered_at TEXT,
                error TEXT,
                FOREIGN KEY(memory_id) REFERENCES memory(id)
            );
            CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox(status);
            CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                at TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT NOT NULL,
                type TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS conflicts (
                id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL,
                base_version INTEGER NOT NULL,
                local_json TEXT NOT NULL,
                remote_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                FOREIGN KEY(memory_id) REFERENCES memory(id)
            );
            """
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.db.commit()

    @staticmethod
    def _memory_from_row(row: sqlite3.Row) -> Memory:
        return Memory(
            id=row["id"], title=row["title"], kind=row["kind"], text=row["text"],
            site_id=row["site_id"], project_id=row["project_id"], source=row["source"],
            source_url=row["source_url"], verified_status=row["verified_status"],
            privacy_level=row["privacy_level"], sync_state=row["sync_state"],
            version=row["version"], vector_id=row["vector_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    def insert_memory(self, memory: Memory) -> Memory:
        self.db.execute(
            """INSERT OR REPLACE INTO memory
            (id,title,kind,text,site_id,project_id,source,source_url,verified_status,privacy_level,sync_state,version,vector_id,metadata_json,created_at,updated_at)
            VALUES (:id,:title,:kind,:text,:site_id,:project_id,:source,:source_url,:verified_status,:privacy_level,:sync_state,:version,:vector_id,:metadata_json,:created_at,:updated_at)""",
            {**memory.model_dump(exclude={"metadata"}), "metadata_json": json.dumps(memory.metadata)},
        )
        self.db.commit()
        return memory

    def get_memory(self, memory_id: str) -> Memory | None:
        row = self.db.execute("SELECT * FROM memory WHERE id = ?", (memory_id,)).fetchone()
        return self._memory_from_row(row) if row else None

    def list_memory(self, site_id: str | None = None, kind: str | None = None, state: str | None = None) -> list[Memory]:
        clauses: list[str] = []
        params: list[str] = []
        if site_id:
            clauses.append("site_id = ?")
            params.append(site_id)
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if state:
            clauses.append("sync_state = ?")
            params.append(state)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.db.execute(f"SELECT * FROM memory{where} ORDER BY updated_at DESC", params).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def update_memory(self, memory_id: str, *, text: str | None = None, title: str | None = None,
                      sync_state: SyncState | None = None, version: int | None = None,
                      verified_status: str | None = None) -> Memory | None:
        memory = self.get_memory(memory_id)
        if not memory:
            return None
        updated = memory.model_copy(update={
            "text": text if text is not None else memory.text,
            "title": title if title is not None else memory.title,
            "sync_state": sync_state if sync_state is not None else memory.sync_state,
            "version": version if version is not None else memory.version,
            "verified_status": verified_status if verified_status is not None else memory.verified_status,
            "updated_at": utc_now(),
        })
        return self.insert_memory(updated)

    def enqueue(self, memory: Memory, action: str = "upsert") -> int:
        cursor = self.db.execute(
            "INSERT INTO outbox(memory_id,action,status,payload_json,created_at) VALUES(?,?,?,?,?)",
            (memory.id, action, "queued", json.dumps(memory.model_dump()), utc_now()),
        )
        self.db.commit()
        return int(cursor.lastrowid)

    def refresh_pending_outbox(self, memory: Memory) -> int:
        """Keep a queued payload aligned with local edits made before sync."""
        cursor = self.db.execute(
            "UPDATE outbox SET payload_json=? WHERE memory_id=? AND status='queued'",
            (json.dumps(memory.model_dump()), memory.id),
        )
        self.db.commit()
        return int(cursor.rowcount)

    def pending_outbox(self) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM outbox WHERE status = 'queued' ORDER BY id").fetchall()
        return [dict(row) | {"payload": json.loads(row["payload_json"])} for row in rows]

    def complete_outbox(self, outbox_id: int) -> None:
        self.db.execute("UPDATE outbox SET status='delivered', delivered_at=?, error=NULL WHERE id=?", (utc_now(), outbox_id))
        self.db.commit()

    def fail_outbox(self, outbox_id: int, error: str) -> None:
        self.db.execute("UPDATE outbox SET status='failed', error=? WHERE id=?", (error, outbox_id))
        self.db.commit()

    def pending_count(self) -> int:
        row = self.db.execute("SELECT COUNT(*) AS count FROM outbox WHERE status='queued'").fetchone()
        return int(row["count"])

    def record_activity(self, title: str, detail: str, activity_type: str) -> None:
        self.db.execute("INSERT INTO activity(at,title,detail,type) VALUES(?,?,?,?)", (utc_now(), title, detail, activity_type))
        self.db.commit()

    def activities(self, limit: int = 30) -> list[Activity]:
        rows = self.db.execute("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [Activity(id=row["id"], at=row["at"], title=row["title"], detail=row["detail"], type=row["type"]) for row in rows]

    def add_conflict(self, conflict_id: str, memory: Memory, remote: dict[str, Any], base_version: int) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO conflicts(id,memory_id,base_version,local_json,remote_json,status,created_at) VALUES(?,?,?,?,?,?,?)",
            (conflict_id, memory.id, base_version, json.dumps(memory.model_dump()), json.dumps(remote), "open", utc_now()),
        )
        self.db.commit()

    def conflicts(self, status: str = "open") -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM conflicts WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
        return [dict(row) | {"local": json.loads(row["local_json"]), "remote": json.loads(row["remote_json"])} for row in rows]

    def get_conflict(self, conflict_id: str) -> dict[str, Any] | None:
        rows = self.db.execute("SELECT * FROM conflicts WHERE id=?", (conflict_id,)).fetchone()
        return (dict(rows) | {"local": json.loads(rows["local_json"]), "remote": json.loads(rows["remote_json"])}) if rows else None

    def resolve_conflict(self, conflict_id: str) -> None:
        self.db.execute("UPDATE conflicts SET status='resolved', resolved_at=? WHERE id=?", (utc_now(), conflict_id))
        self.db.commit()

    def memory_count(self) -> int:
        row = self.db.execute("SELECT COUNT(*) AS count FROM memory").fetchone()
        return int(row["count"])

    def state_counts(self) -> dict[str, int]:
        rows = self.db.execute("SELECT sync_state, COUNT(*) AS count FROM memory GROUP BY sync_state").fetchall()
        return {str(row["sync_state"]): int(row["count"]) for row in rows}
