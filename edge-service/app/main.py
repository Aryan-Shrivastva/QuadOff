from __future__ import annotations

import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .embeddings import LocalEmbedder, lexical_score
from .models import ConnectivityUpdate, ConflictResolve, Memory, NoteCreate, PolicyUpdate, SearchRequest
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
edge_dir = runtime_dir / "edge-shard"
vector_size = int(os.getenv("EDGE_VECTOR_SIZE", "384"))
storage = LocalStorage(runtime_dir / "fieldnote.sqlite3")
embedder = LocalEmbedder(vector_size)
vectors = EdgeVectorStore(edge_dir, embedder.size)
reasoner = LocalReasoner()
syncer = SyncCoordinator(runtime_dir)


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


@app.post("/api/search")
def search(request: SearchRequest) -> dict[str, Any]:
    started = time.perf_counter()
    query_vector = embedder.encode(request.query, role="query")
    retrieval_origin = "Qdrant Edge"
    if request.source == "cloud":
        try:
            candidates = syncer.search_remote(query_vector, max(request.limit * 5, 20))
        except Exception:
            candidates = []
        if candidates:
            retrieval_origin = "Qdrant Server"
        else:
            # A local demo remains useful before CENTRAL_QDRANT_URL is configured.
            candidates = vectors.search(query_vector, max(request.limit * 5, 20))
            retrieval_origin = "Central demo · Edge fallback"
    else:
        candidates = vectors.search(query_vector, max(request.limit * 5, 20))
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
    answer = reasoner.answer(request.query, matches)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    storage.record_activity("Area search completed" if request.area else "Local search completed", f"{request.source} · {request.query[:60]} · {elapsed_ms} ms · {len(matches)} evidence matches", "search")
    return {
        "query": request.query,
        "matches": matches,
        "answer": answer,
        "retrieval": {"origin": retrieval_origin, "offline": storage.get_meta("connectivity", "online") == "offline", "latency_ms": elapsed_ms, "mode": vectors.mode, "source": request.source, "area": request.area},
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
    return {"connectivity": next_state, "offline_search_available": True}


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
