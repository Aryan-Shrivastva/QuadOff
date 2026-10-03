from __future__ import annotations

import os
import time
import uuid
import base64
import binascii
import re
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .embeddings import LocalEmbedder, lexical_score
from .models import ConnectivityUpdate, ConflictResolve, ImageUpload, Memory, NoteCreate, ObservationCreate, ObservationRefine, PolicyUpdate, SearchRequest
from .reasoning import LocalReasoner
from .seed import seed_once
from .storage import LocalStorage
from .sync import SyncCoordinator
from .vector_store import EdgeVectorStore

load_dotenv()
ROOT = Path(__file__).resolve().parents[2]


def resolve_path(value: str, default: Path) -> Path:
    path = Path(value) if value else default
    return path if path.is_absolute() else (ROOT / path).resolve()


runtime_dir = resolve_path(os.getenv("FIELDNOTE_DATA_DIR", "runtime"), ROOT / "runtime")
seed_dir = resolve_path(os.getenv("FIELDNOTE_SEED_DIR", "seed-data"), ROOT / "seed-data")
attachment_dir = runtime_dir / "observation-attachments"
edge_dir = runtime_dir / "edge-shard"
vector_size = int(os.getenv("EDGE_VECTOR_SIZE", "384"))
storage = LocalStorage(runtime_dir / "fieldnote.sqlite3")
embedder = LocalEmbedder(vector_size)
vectors = EdgeVectorStore(edge_dir, embedder.size)
reasoner = LocalReasoner()
syncer = SyncCoordinator(runtime_dir)


def location_catalog() -> list[dict[str, Any]]:
    path = ROOT / "public" / "field-locations.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
    except (OSError, json.JSONDecodeError):
        return []


@asynccontextmanager
async def lifespan(_: FastAPI):
    seed_once(storage, vectors, embedder, seed_dir)
    yield
    vectors.close()
    storage.close()


app = FastAPI(title="QuadOff FieldNote Edge Service", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:5174", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _memory_result(memory: Memory, score: float, lexical: float) -> dict[str, Any]:
    return {
        "id": memory.id,
        "title": memory.title,
        "kind": memory.kind,
        "text": memory.text,
        "site_id": memory.site_id,
        "source": memory.source,
        "source_url": memory.source_url,
        "score": round(max(0.0, min(0.999, score)), 4),
        "lexical_score": round(lexical, 4),
        "sync_state": memory.sync_state,
        "verified_status": memory.verified_status,
        "version": memory.version,
        "metadata": memory.metadata,
        "citation": f"{memory.title} · {memory.source}",
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "fieldnote-edge"}


@app.get("/api/status")
def status() -> dict[str, Any]:
    states = storage.state_counts()
    return {
        "service": "fieldnote-edge",
        "project_id": "clearwater-2026",
        "connectivity": storage.get_meta("connectivity", "online"),
        "local_memory": storage.memory_count(),
        "edge_vectors": vectors.count(),
        "pending_sync": storage.pending_count(),
        "open_conflicts": len(storage.conflicts()),
        "state_counts": states,
        "qdrant_edge": {"mode": vectors.mode, "collection": os.getenv("EDGE_COLLECTION", "fieldnote_memory"), "path": str(edge_dir)},
        "embedding": embedder.description,
        "reasoning": reasoner.description,
        "central": {"mode": syncer.mode, "configured": bool(syncer.central_url), "collection": syncer.collection},
        "offline_capable": True,
    }


@app.get("/api/catalog")
def catalog() -> dict[str, Any]:
    """Return the curated public-source catalog used by the presentation flow."""
    return {
        "locations": location_catalog(),
        "sources": [
            {"category": "Biodiversity", "source": "GBIF Occurrence API", "url": "https://techdocs.gbif.org/en/openapi/v1/occurrence"},
            {"category": "Water", "source": "USGS Water Data APIs", "url": "https://api.waterdata.usgs.gov/"},
            {"category": "Weather", "source": "NOAA NCEI Climate Data Online", "url": "https://www.ncei.noaa.gov/cdo-web/webservices/v2"},
            {"category": "Trails", "source": "National Park Service APIs", "url": "https://www.nps.gov/subjects/developer/api-documentation.htm"},
            {"category": "Protected areas", "source": "Protected Planet WDPA", "url": "https://www.protectedplanet.net/en/thematic-areas/wdpa"},
            {"category": "Terrain", "source": "USGS 3DEP", "url": "https://www.usgs.gov/3d-elevation-program/about-3dep-products-services"},
        ],
    }


@app.get("/api/documents")
def documents(site_id: str = Query(..., min_length=1), kind: str | None = None, limit: int = Query(default=40, ge=1, le=100)) -> dict[str, Any]:
    """Return the exact source-linked documents for one selectable place."""
    items = storage.list_memory(site_id=site_id, kind=kind)
    external_items = [memory for memory in items if memory.metadata.get("source_snapshot")]
    if external_items:
        items = external_items
    source_documents: dict[str, dict[str, Any]] = {}
    snapshot_path = seed_dir / "external-snapshots" / f"{site_id}.json"
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        source_documents = {
            f"snapshot-{site_id}-{item.get('id', '')}": item
            for item in snapshot.get("documents", [])
            if item.get("id")
        }
    except (OSError, json.JSONDecodeError):
        source_documents = {}
    documents = []
    for memory in items:
        if not memory.metadata.get("catalog"):
            continue
        metadata = {**memory.metadata}
        source_document = source_documents.get(memory.id) or {}
        item = memory.model_dump()
        # The snapshot is the canonical readable copy. This lets refreshed
        # source text appear immediately without a costly Edge re-embedding
        # pass on every ingestion refresh.
        if source_document:
            item.update({
                "title": source_document.get("title", item["title"]),
                "text": source_document.get("text", item["text"]),
                "source": source_document.get("source", item["source"]),
                "source_url": source_document.get("source_url", item.get("source_url")),
            })
            metadata["sections"] = re.findall(r"^##\s+(.+)$", str(item["text"]), flags=re.MULTILINE)
        documents.append({
            **item,
            "metadata": metadata,
            "citation": f"{item['title']} · {item['source']}",
        })
        if len(documents) >= limit:
            break
    return {"documents": documents, "count": len(documents), "site_id": site_id}


@app.get("/api/documents/{document_id}")
def document_detail(document_id: str) -> dict[str, Any]:
    """Return one source record plus its complete upstream API response.

    The catalog endpoint intentionally stays light for the Home page. This
    detail endpoint is fetched only after a researcher opens a record, so the
    reader can show the full response without duplicating large payloads in
    every catalog card.
    """
    memory = storage.get_memory(document_id)
    if memory is None or not memory.metadata.get("source_snapshot"):
        raise HTTPException(status_code=404, detail="Source document not found")

    metadata = {**memory.metadata}
    snapshot_path = seed_dir / "external-snapshots" / f"{memory.site_id}.json"
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        snapshot = {}

    source_document = next(
        (item for item in snapshot.get("documents", []) if f"snapshot-{memory.site_id}-{item.get('id', '')}" == memory.id),
        None,
    )
    if source_document:
        item = memory.model_dump()
        item.update({
            "title": source_document.get("title", item["title"]),
            "text": source_document.get("text", item["text"]),
            "source": source_document.get("source", item["source"]),
            "source_url": source_document.get("source_url", item.get("source_url")),
        })
        metadata["sections"] = re.findall(r"^##\s+(.+)$", str(item["text"]), flags=re.MULTILINE)
        response_key = str((source_document.get("metadata") or {}).get("response_key") or metadata.get("response_key") or "")
        metadata["source_fetched_at"] = snapshot.get("fetched_at")
        metadata["source_family"] = response_key or metadata.get("source_key") or "public-source"
    else:
        item = memory.model_dump()

    return {
        **item,
        "metadata": metadata,
        "citation": f"{item['title']} · {item['source']}",
    }


@app.post("/api/search")
def search(request: SearchRequest) -> dict[str, Any]:
    started = time.perf_counter()
    query_vector = embedder.encode(request.query, role="query")
    online = storage.get_meta("connectivity", "online") == "online"
    # A cloud source is only eligible while the device is connected. This is
    # a server-side guard as well as a UI choice, so an offline map search can
    # never accidentally make a remote request.
    effective_source = "cloud" if request.source == "cloud" and online else "edge"
    # Use a wider retrieval window when filtering by selected region or map
    # bounds, so globally similar records do not crowd out local documents.
    candidate_limit = max(request.limit * 20, 100) if request.site_id or request.area else max(request.limit * 5, 20)
    retrieval_origin = "Qdrant Edge"
    if effective_source == "cloud":
        try:
            candidates = syncer.search_remote(query_vector, candidate_limit)
        except Exception:
            candidates = []
        if candidates:
            retrieval_origin = "Qdrant Server"
        else:
            # A local demo remains useful before CENTRAL_QDRANT_URL is configured.
            candidates = vectors.search(query_vector, candidate_limit)
            retrieval_origin = "Central demo · Edge fallback"
    else:
        candidates = vectors.search(query_vector, candidate_limit)
    combined: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        memory_id = str(candidate.get("payload", {}).get("memory_id", ""))
        if not memory_id or memory_id in seen:
            continue
        memory = storage.get_memory(memory_id)
        if memory is None:
            try:
                memory = Memory.model_validate(candidate.get("payload", {}))
            except Exception:
                continue
        coords = memory.metadata or {}
        if request.area and {"latitude", "longitude"}.issubset(coords):
            latitude = float(coords["latitude"])
            longitude = float(coords["longitude"])
            if not (request.area.get("south", -90) <= latitude <= request.area.get("north", 90) and request.area.get("west", -180) <= longitude <= request.area.get("east", 180)):
                continue
        if (request.site_id and memory.site_id != request.site_id) or (request.kind and memory.kind != request.kind):
            continue
        seen.add(memory_id)
        lexical = lexical_score(request.query, f"{memory.title} {memory.text}")
        semantic = (float(candidate.get("score", 0.0)) + 1) / 2 if float(candidate.get("score", 0.0)) < 0 else float(candidate.get("score", 0.0))
        combined.append(_memory_result(memory, semantic * 0.72 + lexical * 0.28, lexical))

    if not combined:
        # This also keeps search useful if an old shard was opened before a
        # dependency upgrade; it still operates entirely on the local DB.
        for memory in storage.list_memory(site_id=request.site_id, kind=request.kind):
            coords = memory.metadata or {}
            if request.area and {"latitude", "longitude"}.issubset(coords):
                latitude = float(coords["latitude"])
                longitude = float(coords["longitude"])
                if not (request.area.get("south", -90) <= latitude <= request.area.get("north", 90) and request.area.get("west", -180) <= longitude <= request.area.get("east", 180)):
                    continue
            lexical = lexical_score(request.query, f"{memory.title} {memory.text}")
            if lexical > 0:
                combined.append(_memory_result(memory, lexical, lexical))
    combined.sort(key=lambda item: item["score"], reverse=True)
    matches = combined[: request.limit]
    answer = reasoner.answer(request.query, matches, network_allowed=storage.get_meta("connectivity", "online") == "online")
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    storage.record_activity("Area search completed" if request.area else "Local search completed", f"{effective_source} · {request.query[:60]} · {elapsed_ms} ms · {len(matches)} evidence matches", "search")
    return {
        "query": request.query,
        "matches": matches,
        "answer": answer,
        "retrieval": {"origin": retrieval_origin, "offline": not online, "latency_ms": elapsed_ms, "mode": vectors.mode, "source": effective_source, "area": request.area},
    }


@app.get("/api/memory")
def memory(site_id: str | None = None, kind: str | None = None, state: str | None = None, limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    items = storage.list_memory(site_id=site_id, kind=kind, state=state)[:limit]
    return {"items": [item.model_dump() for item in items], "count": len(items), "total": storage.memory_count(), "edge_vectors": vectors.count()}


@app.get("/api/memory/{memory_id}")
def memory_detail(memory_id: str) -> dict[str, Any]:
    item = storage.get_memory(memory_id)
    if not item:
        raise HTTPException(status_code=404, detail="Memory record not found")
    return item.model_dump()


@app.post("/api/notes")
def create_note(note: NoteCreate) -> dict[str, Any]:
    memory_id = f"note-{uuid.uuid4().hex[:12]}"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    item = Memory(
        id=memory_id,
        title=note.title,
        kind="field_note",
        text=note.text,
        site_id=note.site_id,
        project_id=note.project_id,
        source=note.source,
        source_url=None,
        verified_status="needs-review",
        privacy_level="project-private",
        sync_state=note.policy,
        version=1,
        vector_id=vectors.vector_id(memory_id),
        created_at=now,
        updated_at=now,
        metadata={"captured_offline": storage.get_meta("connectivity", "online") == "offline", "created_by": "researcher"},
    )
    storage.insert_memory(item)
    vectors.upsert(item.id, embedder.encode(f"{item.title}\n{item.text}"), item.model_dump())
    if item.sync_state == "ready-to-sync":
        storage.enqueue(item)
    storage.record_activity("Field note indexed locally", f"{item.title} · policy: {item.sync_state}", "queued" if item.sync_state == "ready-to-sync" else "note")
    return {"item": item.model_dump(), "queued": item.sync_state == "ready-to-sync"}


@app.post("/api/observations/refine")
def refine_observation(request: ObservationRefine) -> dict[str, Any]:
    result = reasoner.refine_observation(
        observation=request.observation,
        evidence=request.evidence,
        query=request.query,
        source_title=request.source_title,
        source_text=request.source_text,
        category=request.category,
        location=request.location,
        network_allowed=request.network_allowed and storage.get_meta("connectivity", "online") == "online",
    )
    return result


@app.post("/api/observations")
def create_observation(observation: ObservationCreate) -> dict[str, Any]:
    """Create an immutable new copy rather than editing the selected source."""
    memory_id = f"observation-{uuid.uuid4().hex[:12]}"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    combined = "\n\n".join(part for part in (observation.refined_summary.strip(), observation.observation.strip(), observation.evidence.strip()) if part)
    if not combined:
        raise HTTPException(status_code=422, detail="Observation or qualitative evidence is required")
    metadata = {
        "captured_offline": storage.get_meta("connectivity", "online") == "offline",
        "created_by": "researcher",
        "category": observation.category,
        "query": observation.query,
        "location": observation.location,
        "latitude": observation.location.get("latitude"),
        "longitude": observation.location.get("longitude"),
        "source_memory_id": observation.source_memory_id,
        "source_title": observation.source_title,
        "images": [],
        "record_kind": "observation_copy",
    }
    item = Memory(
        id=memory_id,
        title=observation.title,
        kind="field_observation",
        text=combined,
        site_id=observation.site_id,
        project_id=observation.project_id,
        source="Researcher observation · new copy",
        source_url=None,
        verified_status="needs-review",
        privacy_level="project-private",
        sync_state=observation.policy,
        version=1,
        vector_id=vectors.vector_id(memory_id),
        created_at=now,
        updated_at=now,
        metadata=metadata,
    )
    storage.insert_memory(item)
    vectors.upsert(item.id, embedder.encode(f"{item.title}\n{item.text}"), item.model_dump())
    if item.sync_state == "ready-to-sync":
        storage.enqueue(item)
    storage.record_activity("New observation copy indexed", f"{item.title} · source remains immutable · {item.id}", "queued")
    return {"item": item.model_dump(), "queued": item.sync_state == "ready-to-sync", "source_unchanged": True}


@app.post("/api/observations/{memory_id}/images")
def upload_observation_image(memory_id: str, upload: ImageUpload) -> dict[str, Any]:
    memory = storage.get_memory(memory_id)
    if not memory or memory.kind != "field_observation":
        raise HTTPException(status_code=404, detail="Observation copy not found")
    match = re.match(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$", upload.data_url, re.DOTALL)
    if not match:
        raise HTTPException(status_code=422, detail="Image must be a base64 data URL")
    try:
        raw = base64.b64decode(match.group("data"), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Image data could not be decoded") from exc
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", upload.filename)[:180] or "field-image"
    destination = attachment_dir / memory_id
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / safe_name
    path.write_bytes(raw)
    image_meta = {"filename": safe_name, "mime_type": upload.mime_type, "path": str(path.relative_to(ROOT)), "bytes": len(raw)}
    metadata = dict(memory.metadata)
    metadata["images"] = [*metadata.get("images", []), image_meta]
    updated = memory.model_copy(update={"metadata": metadata, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    storage.insert_memory(updated)
    vectors.upsert(updated.id, embedder.encode(f"{updated.title}\n{updated.text}"), updated.model_dump())
    storage.refresh_pending_outbox(updated)
    storage.record_activity("Offline-capable image attached", f"{safe_name} · {memory_id}", "note")
    return {"item": updated.model_dump(), "image": image_meta, "stored_locally": True}


@app.post("/api/observations/{memory_id}/upload")
def upload_observation(memory_id: str) -> dict[str, Any]:
    memory = storage.get_memory(memory_id)
    if not memory or memory.kind != "field_observation":
        raise HTTPException(status_code=404, detail="Observation copy not found")
    if memory.sync_state != "ready-to-sync":
        memory = storage.update_memory(memory_id, sync_state="ready-to-sync", version=memory.version + 1) or memory
        vectors.upsert(memory.id, embedder.encode(f"{memory.title}\n{memory.text}"), memory.model_dump())
    if not any(entry["memory_id"] == memory_id for entry in storage.pending_outbox()):
        storage.enqueue(memory)
    else:
        # The note may have received images or other local metadata after it
        # was first queued. Upload the current immutable copy, not the stale
        # payload captured before those attachments were added.
        storage.refresh_pending_outbox(memory)
    if storage.get_meta("connectivity", "online") != "online":
        return {"item": memory.model_dump(), "queued": True, "uploaded": False, "message": "New record queued locally; upload will resume when connectivity returns."}
    try:
        result = syncer.sync(storage, vectors, embedder)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Qdrant upload failed: {exc}") from exc
    latest = storage.get_memory(memory_id) or memory
    return {"item": latest.model_dump(), "queued": storage.pending_count() > 0, "uploaded": latest.sync_state == "synced", "message": f"New record uploaded through {result.get('mode', syncer.mode)}; source record was not modified."}


@app.post("/api/notes/{memory_id}/policy")
def update_policy(memory_id: str, policy: PolicyUpdate) -> dict[str, Any]:
    item = storage.get_memory(memory_id)
    if not item or item.kind != "field_note":
        raise HTTPException(status_code=404, detail="Field note not found")
    updated = storage.update_memory(memory_id, sync_state=policy.policy, version=item.version + 1)
    queued = False
    if updated and policy.policy == "ready-to-sync" and not any(entry["memory_id"] == memory_id for entry in storage.pending_outbox()):
        storage.enqueue(updated)
        queued = True
    storage.record_activity("Note policy changed", f"{updated.title if updated else memory_id} → {policy.policy}", "queued" if queued else "note")
    return {"item": updated.model_dump() if updated else None, "queued": queued}


@app.post("/api/connectivity")
def connectivity(update: ConnectivityUpdate) -> dict[str, Any]:
    next_state = "online" if update.online else "offline"
    storage.set_meta("connectivity", next_state)
    storage.record_activity("Connection restored" if update.online else "Offline mode enabled", "Central traffic is allowed" if update.online else "Qdrant Edge and SQLite remain active", "online" if update.online else "offline")
    # Reconnecting is also the synchronization trigger. The local outbox is
    # durable, so a failed cloud request leaves every item queued for the next
    # reconnect instead of making the researcher press a second sync button.
    sync_result: dict[str, Any] | None = None
    sync_error: str | None = None
    if update.online and storage.pending_count() > 0:
        try:
            sync_result = syncer.sync(storage, vectors, embedder)
        except Exception as exc:  # keep offline-first capture usable on failure
            sync_error = str(exc)
            storage.record_activity("Reconnect sync deferred", f"Central Qdrant unavailable: {sync_error[:160]}", "queued")
    return {
        "connectivity": next_state,
        "offline_search_available": True,
        "sync": sync_result,
        "sync_error": sync_error,
        "pending_sync": storage.pending_count(),
    }


@app.get("/api/sync/queue")
def sync_queue() -> dict[str, Any]:
    return {"items": storage.pending_outbox(), "pending": storage.pending_count(), "central": {"mode": syncer.mode, "configured": bool(syncer.central_url)}}


@app.post("/api/sync/run")
def run_sync() -> dict[str, Any]:
    if storage.get_meta("connectivity", "online") != "online":
        raise HTTPException(status_code=409, detail="Device is offline; local updates remain safely queued")
    try:
        result = syncer.sync(storage, vectors, embedder)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Central sync failed: {exc}") from exc
    return {**result, "pending": storage.pending_count()}


@app.get("/api/activity")
def activity(limit: int = Query(30, ge=1, le=100)) -> dict[str, Any]:
    return {"items": [item.model_dump() for item in storage.activities(limit)]}


@app.get("/api/conflicts")
def conflicts() -> dict[str, Any]:
    return {"items": storage.conflicts(), "open": len(storage.conflicts())}


@app.post("/api/conflicts/{conflict_id}/resolve")
def resolve_conflict(conflict_id: str, resolution: ConflictResolve) -> dict[str, Any]:
    conflict = storage.get_conflict(conflict_id)
    if not conflict or conflict["status"] != "open":
        raise HTTPException(status_code=404, detail="Open conflict not found")
    memory_id = conflict["memory_id"]
    local = conflict["local"]
    remote = conflict["remote"]
    if resolution.choice == "remote":
        text = remote.get("text", local.get("text", ""))
        state = "synced"
        version = int(remote.get("version", local.get("version", 1)))
    elif resolution.choice == "merged":
        text = resolution.merged_text or f"{local.get('text', '')}\n\nTeam context: {remote.get('text', '')}"
        state = "ready-to-sync"
        version = max(int(local.get("version", 1)), int(remote.get("version", 1))) + 1
    else:
        text = local.get("text", "")
        state = "ready-to-sync"
        version = int(local.get("version", 1)) + 1
    updated = storage.update_memory(memory_id, text=text, sync_state=state, version=version)
    if updated:
        vectors.upsert(updated.id, embedder.encode(f"{updated.title}\n{updated.text}"), updated.model_dump())
        if state == "ready-to-sync":
            storage.enqueue(updated)
    storage.resolve_conflict(conflict_id)
    storage.record_activity("Conflict resolved", f"{memory_id} · chose {resolution.choice}", "conflict")
    return {"item": updated.model_dump() if updated else None, "choice": resolution.choice, "queued": state == "ready-to-sync"}
