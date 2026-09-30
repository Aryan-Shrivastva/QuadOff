# FieldNote implementation notes

## Why this aligns with the brief

The device has a durable local memory and a distinct central memory. Qdrant
Edge is the first retrieval path; the service never requires a network for
search. SQLite is the source of truth for memory policy and outbox state, so a
note can be local-only, awaiting verification, ready-to-sync, synced, or in a
conflict without relying on a remote service.

## API surface

| Endpoint | Purpose |
| --- | --- |
| `GET /api/status` | Edge mode, vector count, connectivity, model adapters, queue and conflict counts |
| `POST /api/search` | Hybrid local vector + lexical retrieval and evidence-first briefing |
| `GET /api/memory` | Inspect local records and policy states |
| `POST /api/notes` | Embed and index a new field observation locally |
| `POST /api/notes/{id}/policy` | Explicitly keep local, request verification, or approve sync |
| `POST /api/connectivity` | Set the device's demonstrable connectivity state |
| `GET /api/sync/queue` | Inspect the SQLite outbox |
| `POST /api/sync/run` | Deliver approved records and acknowledge them |
| `GET /api/activity` | Inspect searchable local system activity |
| `GET /api/conflicts` | Inspect preserved local/remote edits |
| `POST /api/conflicts/{id}/resolve` | Choose local, remote, or merged content |

## Model adapters

The default install is intentionally zero-download at runtime: a deterministic
hashing embedder and citation-preserving local briefing keep the demo working
on a disconnected laptop. `LocalEmbedder` accepts a locally cached
EmbeddingGemma/SentenceTransformer model, and `LocalReasoner` accepts a
locally cached Gemma 4 text-generation model. Set the corresponding backend
environment variables only after the weights are present on the device.

## Central sync modes

Set `CENTRAL_QDRANT_URL` (and optionally `CENTRAL_QDRANT_API_KEY`) to use a
real Qdrant Server or Cloud collection. The sync coordinator pulls remote
records into the Edge shard, uploads approved outbox records, and creates a
conflict instead of overwriting local work when versions diverge. With no URL,
`ALLOW_DEMO_CENTRAL=true` uses an explicit local `runtime/central-state.json`
adapter so the complete outbox and acknowledgement workflow can still be
demonstrated without pretending that a cloud connection exists.
