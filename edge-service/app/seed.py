from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .embeddings import LocalEmbedder
from .models import Memory, utc_now
from .storage import LocalStorage
from .vector_store import EdgeVectorStore


def _frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    _, raw, body = text.split("---", 2)
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields, body.strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _memory(
    vectors: EdgeVectorStore,
    *,
    memory_id: str,
    title: str,
    kind: str,
    text: str,
    site_id: str,
    project_id: str,
    source: str,
    source_url: str | None,
    verified_status: str,
    sync_state: str,
    metadata: dict[str, Any] | None = None,
    version: int = 1,
    created_at: str | None = None,
) -> Memory:
    created = created_at or utc_now()
    return Memory(
        id=memory_id,
        title=title,
        kind=kind,
        text=text,
        site_id=site_id,
        project_id=project_id,
        source=source,
        source_url=source_url,
        verified_status=verified_status,
        privacy_level="public",
        sync_state=sync_state,  # type: ignore[arg-type]
        version=version,
        vector_id=vectors.vector_id(memory_id),
        created_at=created,
        updated_at=created,
        metadata=metadata or {},
    )


def _insert(storage: LocalStorage, vectors: EdgeVectorStore, embedder: LocalEmbedder, memory: Memory) -> None:
    storage.insert_memory(memory)
    vectors.upsert(memory.id, embedder.encode(f"{memory.title}\n{memory.text}"), memory.model_dump())


def seed_once(storage: LocalStorage, vectors: EdgeVectorStore, embedder: LocalEmbedder, seed_dir: Path) -> None:
    if storage.get_meta("seed_version") == "fieldnote-v1" and storage.memory_count() > 0:
        # A shard can be moved or upgraded independently of SQLite. Rebuild
        # the embedded index from canonical local memory when needed.
        if vectors.count() < storage.memory_count():
            for existing in storage.list_memory():
                vectors.upsert(existing.id, embedder.encode(f"{existing.title}\n{existing.text}"), existing.model_dump())
        return

    reports_dir = seed_dir / "reports"
    for report_path in sorted(reports_dir.glob("*.md")):
        fields, body = _frontmatter(report_path)
        memory = _memory(
            vectors,
            memory_id=f"report-{report_path.stem}",
            title=fields.get("title", report_path.stem.replace("-", " ").title()),
            kind=fields.get("kind", "report_chunk"),
            text=body,
            site_id=fields.get("site_id", "all"),
            project_id=fields.get("project_id", "clearwater-2026"),
            source=fields.get("source", "Curated project pack"),
            source_url=fields.get("source_url"),
            verified_status=fields.get("verified_status", "verified"),
            sync_state="synced",
            metadata={"file": str(report_path.relative_to(seed_dir)), "chunk_index": 0},
        )
        _insert(storage, vectors, embedder, memory)

    observation_path = seed_dir / "observations" / "water-observations.csv"
    with observation_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    facets = ("reading", "trend context", "comparison cue", "review cue")
    for row_index, row in enumerate(rows):
        base = (
            f"On {row['date']}, {row['site_id'].replace('-', ' ').title()} recorded pH {row['pH']}, "
            f"turbidity {row['turbidity_ntu']} NTU, dissolved oxygen {row['dissolved_oxygen_mg_l']} mg/L, "
            f"and temperature {row['temperature_c']}°C."
        )
        for facet_index, facet in enumerate(facets):
            cue = {
                "reading": "This is the original measurement row.",
                "trend context": "Compare this value with adjacent dates and the upstream reference site.",
                "comparison cue": "Use the project review bands: dissolved oxygen below 6.0 mg/L or turbidity above 10 NTU needs review.",
                "review cue": "Preserve calibration and weather metadata before interpreting this observation.",
            }[facet]
            memory_id = f"obs-{row_index:03d}-{facet_index}"
            memory = _memory(
                vectors,
                memory_id=memory_id,
                title=f"{row['site_id'].replace('-', ' ').title()} · {row['date']} · {facet}",
                kind="observation",
                text=f"{base} {cue}",
                site_id=row["site_id"],
                project_id="clearwater-2026",
                source=row.get("source", "USGS/EPA curated demo pack"),
                source_url="https://waterdata.usgs.gov/",
                verified_status=row.get("verified_status", "verified"),
                sync_state="synced",
                metadata={"date": row["date"], "facet": facet, "parameters": row},
            )
            _insert(storage, vectors, embedder, memory)

    findings = json.loads((seed_dir / "verified-findings" / "baseline-findings.json").read_text(encoding="utf-8"))
    for item in findings:
        memory = _memory(
            vectors,
            memory_id=item["id"],
            title=item["title"],
            kind="verified_finding",
            text=item["text"],
            site_id=item.get("site_id", "all"),
            project_id="clearwater-2026",
            source=item["source"],
            source_url="https://api.waterdata.usgs.gov/docs/",
            verified_status=item.get("verified_status", "verified"),
            sync_state=item.get("sync_state", "synced"),
            version=item.get("version", 1),
            metadata={"fixture": "verified-findings/baseline-findings.json"},
        )
        _insert(storage, vectors, embedder, memory)
        if memory.sync_state == "conflict":
            remote = {**memory.model_dump(), "text": "The shared team record says Zone 3 was last reviewed on 12 August."}
            storage.add_conflict(f"conflict-{memory.id}", memory, remote, base_version=max(1, memory.version - 1))

    cloud_item = json.loads((seed_dir / "cloud-updates" / "cloud-verified-finding.json").read_text(encoding="utf-8"))
    cloud_memory = _memory(
        vectors,
        memory_id=cloud_item["id"],
        title=cloud_item["title"],
        kind="verified_finding",
        text=cloud_item["text"],
        site_id=cloud_item["site_id"],
        project_id="clearwater-2026",
        source=cloud_item["source"],
        source_url="https://qdrant.tech/documentation/",
        verified_status="verified",
        sync_state="synced",
        metadata={"fixture": "cloud-updates/cloud-verified-finding.json", "remote_revision": 7},
    )
    _insert(storage, vectors, embedder, cloud_memory)

    storage.set_meta("seed_version", "fieldnote-v1")
    storage.set_meta("connectivity", "online")
    storage.record_activity("Knowledge pack installed", "108 local evidence vectors are ready on this device", "sync")
    storage.record_activity("Conflict fixture detected", "One shared finding needs an explicit local/remote decision", "conflict")
