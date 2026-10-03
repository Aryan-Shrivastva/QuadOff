from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .embeddings import LocalEmbedder
from .models import Memory
from .storage import LocalStorage
from .vector_store import EdgeVectorStore


class SyncCoordinator:
    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = runtime_dir
        self.central_url = os.getenv("CENTRAL_QDRANT_URL", "").strip()
        self.collection = os.getenv("CENTRAL_QDRANT_COLLECTION", "fieldnote_shared")
        self.api_key = os.getenv("CENTRAL_QDRANT_API_KEY", "").strip() or None
        self.demo_allowed = os.getenv("ALLOW_DEMO_CENTRAL", "true").lower() == "true"

    @property
    def mode(self) -> str:
        return "qdrant-server" if self.central_url else "demo-central"

    def sync(self, storage: LocalStorage, vectors: EdgeVectorStore, embedder: LocalEmbedder) -> dict[str, Any]:
        queue = storage.pending_outbox()
        if not queue:
            return {"delivered": 0, "remote_applied": 0, "mode": self.mode, "message": "Outbox is already clear."}
        if self.central_url:
            delivered, remote_applied = self._sync_qdrant(queue, storage, vectors, embedder)
        elif self.demo_allowed:
            delivered = self._sync_demo(queue, storage)
            remote_applied = 0
        else:
            raise RuntimeError("CENTRAL_QDRANT_URL is not configured and demo central mode is disabled")
        storage.record_activity("Outbox delivered", f"{delivered} approved update(s) acknowledged by {self.mode}", "sync")
        storage.record_activity("Shared knowledge refreshed", "Central revision checked; local shard remains available offline", "sync")
        return {"delivered": delivered, "remote_applied": remote_applied, "mode": self.mode, "message": "Delivery acknowledged."}

    def search_remote(self, vector: list[float], limit: int = 20) -> list[dict[str, Any]]:
        """Query the configured central Qdrant collection when cloud search is requested."""
        if not self.central_url:
            return []
        from qdrant_client import QdrantClient  # type: ignore

        client = QdrantClient(url=self.central_url, api_key=self.api_key)
        try:
            result = client.query_points(
                collection_name=self.collection,
                query=vector,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            points = result.points
        except AttributeError:
            points = client.search(
                collection_name=self.collection,
                query_vector=vector,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
        return [
            {"id": str(point.id), "score": float(point.score), "payload": dict(point.payload or {})}
            for point in points
        ]

    def _sync_demo(self, queue: list[dict[str, Any]], storage: LocalStorage) -> int:
        central_path = self.runtime_dir / "central-state.json"
        state: list[dict[str, Any]] = []
        if central_path.exists():
            try:
                state = json.loads(central_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                state = []
        for item in queue:
            state.append({"outbox_id": item["id"], "received_at": item["created_at"], "payload": item["payload"]})
            storage.complete_outbox(int(item["id"]))
            storage.update_memory(item["memory_id"], sync_state="synced")
        central_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return len(queue)

    def _sync_qdrant(self, queue: list[dict[str, Any]], storage: LocalStorage, vectors: EdgeVectorStore, embedder: LocalEmbedder) -> tuple[int, int]:
        from qdrant_client import QdrantClient, models  # type: ignore

        client = QdrantClient(url=self.central_url, api_key=self.api_key)
        size = embedder.size
        collections = {item.name for item in client.get_collections().collections}
        if self.collection not in collections:
            client.create_collection(self.collection, vectors_config=models.VectorParams(size=size, distance=models.Distance.COSINE))

        remote_applied = self._pull_remote(client, storage, vectors, embedder)
        open_conflict_memory_ids = {item["memory_id"] for item in storage.conflicts()}
        points = []
        for item in queue:
            if item["memory_id"] in open_conflict_memory_ids:
                continue
            # The point is acknowledged as synced only after the remote
            # upsert succeeds, so keep the cloud payload truthful as well.
            payload = {**item["payload"], "sync_state": "synced"}
            points.append(models.PointStruct(id=vectors.vector_id(payload["id"]), vector=embedder.encode(f"{payload['title']}\n{payload['text']}"), payload=payload))
        if points:
            client.upsert(self.collection, points=points, wait=True)
        for item in queue:
            if item["memory_id"] in open_conflict_memory_ids:
                continue
            storage.complete_outbox(int(item["id"]))
            storage.update_memory(item["memory_id"], sync_state="synced")
        remote_applied += self._pull_remote(client, storage, vectors, embedder)
        return len(points), remote_applied

    def _pull_remote(self, client: Any, storage: LocalStorage, vectors: EdgeVectorStore, embedder: LocalEmbedder) -> int:
        """Merge shared records into the device without overwriting local work."""
        applied = 0
        offset = None
        while True:
            records, offset = client.scroll(
                collection_name=self.collection,
                offset=offset,
                limit=100,
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                payload = dict(record.payload or {})
                try:
                    remote = Memory.model_validate(payload)
                except Exception:
                    continue
                local = storage.get_memory(remote.id)
                if local is None:
                    storage.insert_memory(remote)
                    vectors.upsert(remote.id, embedder.encode(f"{remote.title}\n{remote.text}"), remote.model_dump())
                    applied += 1
                    continue
                if local.version == remote.version and local.text == remote.text:
                    continue
                if local.sync_state in {"local-only", "needs-verification", "ready-to-sync"}:
                    storage.add_conflict(
                        f"conflict-{remote.id}-{remote.version}",
                        local,
                        remote.model_dump(),
                        base_version=min(local.version, remote.version),
                    )
                    continue
                if remote.version > local.version:
                    storage.insert_memory(remote)
                    vectors.upsert(remote.id, embedder.encode(f"{remote.title}\n{remote.text}"), remote.model_dump())
                    applied += 1
            if offset is None:
                break
        return applied
