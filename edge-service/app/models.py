from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


SyncState = Literal["local-only", "needs-verification", "ready-to-sync", "synced", "conflict"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    site_id: str | None = None
    kind: str | None = None
    limit: int = Field(default=8, ge=1, le=25)
    source: Literal["edge", "cloud"] = "edge"
    area: dict[str, Any] | None = None


class NoteCreate(BaseModel):
    text: str = Field(min_length=3, max_length=5000)
    title: str = Field(default="Field observation", min_length=2, max_length=180)
    site_id: str = "river-zone-3"
    project_id: str = "clearwater-2026"
    policy: SyncState = "needs-verification"
    source: str = "Researcher field note"


class PolicyUpdate(BaseModel):
    policy: SyncState


class ConnectivityUpdate(BaseModel):
    online: bool


class ConflictResolve(BaseModel):
    choice: Literal["local", "remote", "merged"]
    merged_text: str | None = None


class Memory(BaseModel):
    id: str
    title: str
    kind: str
    text: str
    site_id: str
    project_id: str
    source: str
    source_url: str | None = None
    verified_status: str
    privacy_level: str
    sync_state: SyncState
    version: int
    vector_id: str
    created_at: str
    updated_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Activity(BaseModel):
    id: int
    at: str
    title: str
    detail: str
    type: str
