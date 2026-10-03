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


class ObservationCreate(BaseModel):
    """Create a new observation copy; the selected source record is immutable."""

    title: str = Field(default="Field observation", min_length=2, max_length=180)
    observation: str = Field(default="", max_length=5000)
    evidence: str = Field(default="", max_length=5000)
    refined_summary: str = Field(default="", max_length=6000)
    category: str = Field(default="Other field evidence", max_length=120)
    site_id: str = "manual-research-area"
    project_id: str = "clearwater-2026"
    location: dict[str, Any] = Field(default_factory=dict)
    source_memory_id: str | None = None
    source_title: str | None = None
    query: str = ""
    policy: SyncState = "ready-to-sync"


class ObservationRefine(BaseModel):
    observation: str = Field(default="", max_length=5000)
    evidence: str = Field(default="", max_length=5000)
    query: str = Field(default="", max_length=500)
    source_title: str = Field(default="Selected field evidence", max_length=180)
    source_text: str = Field(default="", max_length=6000)
    category: str = Field(default="Other field evidence", max_length=120)
    location: str = Field(default="selected area", max_length=180)
    network_allowed: bool = True


class ImageUpload(BaseModel):
    filename: str = Field(min_length=1, max_length=240)
    mime_type: str = Field(default="application/octet-stream", max_length=120)
    data_url: str = Field(min_length=20, max_length=15_000_000)


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
