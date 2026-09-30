from __future__ import annotations

import json
import math
import uuid
from pathlib import Path
from typing import Any

from .embeddings import cosine

try:  # The import is optional only so the UI can boot in a fresh environment.
    import qdrant_edge
except Exception:  # pragma: no cover - exercised only before dependency install
    qdrant_edge = None  # type: ignore


class EdgeVectorStore:
    """Qdrant Edge first, with an explicit deterministic dev fallback.

    The normal path is the embedded Rust shard from ``qdrant-edge-py``. The
    fallback keeps the API usable if a judge opens the frontend before running
    the Python dependency install; status exposes which path is active.
    """

    def __init__(self, path: Path, size: int) -> None:
        self.path = path
        self.path.mkdir(parents=True, exist_ok=True)
        self.size = size
        self.mode = "qdrant-edge"
        self.shard = None
        self._vectors: dict[str, dict[str, Any]] = {}
        self._fallback_path = self.path / "fallback-vectors.json"
        self._open()

    def _open(self) -> None:
        if qdrant_edge is None:
            self.mode = "deterministic-fallback"
            self._load_fallback()
            return
        try:
            config = qdrant_edge.EdgeConfig(
                vectors=qdrant_edge.EdgeVectorParams(size=self.size, distance=qdrant_edge.Distance.Cosine)
            )
            segment_path = self._compatible_segment_path()
            segment_path.mkdir(parents=True, exist_ok=True)
            existing_segment = segment_path.exists() and any(segment_path.iterdir())
            if existing_segment:
                self.shard = qdrant_edge.EdgeShard.load(str(segment_path), config)
            else:
                self.shard = qdrant_edge.EdgeShard.create(str(segment_path), config)
        except Exception as exc:  # pragma: no cover - safety path
            self.mode = f"deterministic-fallback ({str(exc).splitlines()[0][:100]})"
            self.shard = None
            self._load_fallback()

    def _compatible_segment_path(self) -> Path:
        """Keep old shards intact when switching embedding dimensions."""
        primary = self.path / "qdrant-edge"
        config_path = primary / "edge_config.json"
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
                current_size = int(config.get("vectors", {}).get("", {}).get("size", self.size))
                if current_size != self.size:
                    return self.path / f"qdrant-edge-{self.size}"
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                return self.path / f"qdrant-edge-{self.size}"
        return primary

    @staticmethod
    def vector_id(memory_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"quadoff:fieldnote:{memory_id}"))

    def upsert(self, memory_id: str, vector: list[float], payload: dict[str, Any]) -> str:
        point_id = self.vector_id(memory_id)
        payload = {**payload, "memory_id": memory_id}
        if self.shard is not None:
            point = qdrant_edge.Point(point_id, vector, payload)
            self.shard.update(qdrant_edge.UpdateOperation.upsert_points([point]))
            self.shard.flush()
        else:
            self._vectors[point_id] = {"vector": vector, "payload": payload}
            self._save_fallback()
        return point_id

    def search(self, vector: list[float], limit: int = 10) -> list[dict[str, Any]]:
        if self.shard is not None:
            request = qdrant_edge.SearchRequest(qdrant_edge.Query.Nearest(vector), limit, with_payload=True)
            points = self.shard.search(request)
            return [{"id": str(point.id), "score": float(point.score), "payload": dict(point.payload or {})} for point in points]
        ranked = []
        for point_id, item in self._vectors.items():
            ranked.append({"id": point_id, "score": cosine(vector, item["vector"]), "payload": item["payload"]})
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked[:limit]

    def count(self) -> int:
        if self.shard is not None:
            try:
                return int(self.shard.info().points_count)
            except Exception:
                return 0
        return len(self._vectors)

    def close(self) -> None:
        if self.shard is not None:
            self.shard.close()

    def _load_fallback(self) -> None:
        if self._fallback_path.exists():
            try:
                self._vectors = json.loads(self._fallback_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._vectors = {}

    def _save_fallback(self) -> None:
        self._fallback_path.write_text(json.dumps(self._vectors), encoding="utf-8")
