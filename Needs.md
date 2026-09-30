# QuadOff FieldNote - Build Needs and Execution Plan

> **Product statement:** QuadOff FieldNote is an offline-first environmental research notebook. It keeps a verified research pack on a laptop or tablet, searches it with Qdrant Edge without internet, records new observations locally, and synchronizes only approved findings when a connection returns.
>
> **Tagline:** *Where the signal ends, intelligence begins.*

This is a field-intelligence product, not a generic notes app or a cloud RAG chatbot.

~~~
Approved cloud knowledge pack
  -> selected local Qdrant Edge memory
  -> offline hybrid search plus local Gemma 4 reasoning
  -> new local field observation
  -> local-only / needs-verification / ready-to-sync policy
  -> reconnection
  -> approved finding synchronizes to Qdrant Server
~~~

## 1. Problem-statement requirements

| Requirement | FieldNote proof |
| --- | --- |
| Local semantic memory | A persistent Qdrant Edge shard on the laptop/tablet holds reports, observations, guidance, and verified findings. |
| Offline low-latency search | Disable cloud access, then search reports and measurements successfully. Show local origin and retrieval latency. |
| Evolving local memory | A new field note is embedded, indexed, and searchable immediately. |
| Local-versus-cloud decision | Notes use local-only, needs-verification, ready-to-sync, synced, or conflict state. |
| Edge-to-cloud workflow | An approved note enters an outbox, synchronizes after reconnection, then the device refreshes shared knowledge. |
| Conflict handling | Cloud and local edits from the same base record are preserved and explicitly merged or chosen. |
| Inspectable UI | Device memory, evidence sources, filters, sync queue, versions, and activity are visible. |

## 2. Product scenario

A researcher travels to a river-monitoring location with unreliable connectivity. Before leaving, their device receives a small project-specific knowledge pack: prior studies, public water-quality measurements, sampling procedures, regulations, and verified field findings.

At the site, the researcher asks:

> Has low dissolved oxygen or high turbidity been reported near River Zone 3 before?

Qdrant Edge searches local evidence, Gemma 4 summarizes only that evidence with citations, and the researcher records a new observation. The note stays local until the researcher explicitly approves it for team sharing.

### Scope boundary

This is a research-support tool. It must not diagnose contamination, publish official alerts, or make environmental decisions automatically. Gemma 4 identifies evidence and gaps; the researcher verifies conclusions.

## 3. Dataset strategy

### Small, reproducible knowledge pack

Do not download a national dataset or call public APIs during the presentation. Download and curate a compact source pack once; local Qdrant Edge must power the entire offline demo.

| Data item | Demo target |
| --- | ---: |
| Monitoring locations | 3-5 |
| Water-quality observations | 100-300 |
| Short research/regulation documents | 8-15 |
| Verified historic findings | 5-10 |
| Notes created live | 1-2 |
| Seeded conflict | 1 |

### Source material

- [USGS Water Data APIs](https://api.waterdata.usgs.gov/docs/) provide monitoring locations, measurements, time series, and water-quality access.
- [EPA Water Quality Portal](https://www.epa.gov/waterdata/water-quality-data-download) provides public water-quality records from USGS, EPA, and participating agencies.

Use a single region/basin, 3-5 monitoring sites, a fixed date period, and 3-5 parameters such as pH, turbidity, dissolved oxygen, nitrate, and temperature. Keep attribution, source URL, publication date, and usage note in a manifest.

### Repository data layout

~~~
seed-data/
  reports/
    river-zone-3-baseline-report.md
    watershed-risk-summary.md
    sampling-protocol.md
    regulation-thresholds.md
  observations/
    water-observations.csv
  verified-findings/
    baseline-findings.json
  cloud-updates/
    cloud-verified-finding.json
  manifest.json
~~~

### Convert rows into searchable memories

Raw tabular data needs readable text plus metadata:

~~~
Raw row:
Site: River-Zone-3
Date: 2026-08-14
pH: 6.1
Turbidity: 15 NTU
Dissolved oxygen: 4.2 mg/L

Searchable text:
On 14 August 2026, River Zone 3 recorded pH 6.1,
turbidity 15 NTU, and dissolved oxygen 4.2 mg/L.
The reading has lower dissolved oxygen than the project baseline.
~~~

Store each source/observation with metadata:

~~~
point_id, kind, site_id, project_id, parameter, date,
source, source_url, verified_status, privacy_level,
sync_state, version, updated_at
~~~

Label any hand-written seeded note as demo-created; never present it as public data.

## 4. Architecture

~~~
React/Vite UI on laptop or tablet
        |
        | localhost HTTP / WebSocket
        v
Python edge service (FastAPI)
  |-- ingestion: normalize -> chunk -> embed -> upsert
  |-- local search: dense, BM25, filters, ranking, sources
  |-- Qdrant Edge: persistent in-process semantic memory
  |-- local Gemma 4 runtime: source-grounded summaries
  |-- SQLite: note versions, sync outbox, activity log
  |-- policy engine: privacy and sharing state
  |-- sync worker: controlled push/pull when online
        |
        v
Central Qdrant Server or Qdrant Cloud
  |-- approved shared research collection
  '-- versioned research-pack updates
~~~

| Component | Purpose |
| --- | --- |
| Qdrant Edge Python bindings | Mandatory local embedded vector search; this is the on-device semantic-memory engine, not a Dockerized local server. |
| Local embedding model | Creates document, observation, and query embeddings offline. Evaluate EmbeddingGemma first. |
| Local Gemma 4 runtime | Reasons only over retrieved local evidence and produces cited summaries offline. |
| SQLite | Owns canonical notes, sharing policy, versions, outbox events, and activity history. |
| Central Qdrant Server/Cloud | Holds approved shared knowledge and proves the edge-to-cloud sync workflow. |
| React/Vite + FastAPI | Provides the visible product experience and local API. |

## 5. Technical resources

- [Qdrant Edge Quickstart](https://qdrant.tech/documentation/edge/edge-quickstart/) - create/load EdgeShard, filter, optimize, and close safely.
- [Qdrant Edge Python package](https://pypi.org/project/qdrant-edge-py/) - local embedded Python bindings; pin the version used.
- [Qdrant Edge synchronization patterns](https://qdrant.tech/documentation/edge/edge-data-synchronization-patterns/) and [server synchronization guide](https://qdrant.tech/documentation/edge/edge-synchronization-guide/).
- [Qdrant Edge BM25 guide](https://qdrant.tech/documentation/edge/edge-bm25/) - exact-term retrieval for site IDs, dates, and terms.
- [Gemma local-running guidance](https://ai.google.dev/gemma/docs/run).

## 6. Qdrant Edge data design

### Local memory kinds

~~~
report_chunk       paragraph from a source report
observation        normalized measurement/observation
verified_finding   approved research conclusion
field_note         researcher-created observation
procedure          sampling or safety procedure
~~~

Create payload indexes for:

~~~
kind, site_id, project_id, parameter, source,
verified_status, privacy_level, sync_state, date, updated_at
~~~

The live demo must show an actual filtered query:

> Show verified high-turbidity observations for River Zone 3 during August.

### Sharing and verification policy

| State | Meaning |
| --- | --- |
| local-only | Raw photos, private interview notes, and preliminary observations. Searchable only on this device; never added to the outbox. |
| needs-verification | New field note or tentative conclusion. Stored locally and visible in the verification queue. |
| ready-to-sync | Researcher-approved finding. Placed in the outbox when online. |
| synced | Approved baseline evidence available on device and central server. |
| conflict | Local and cloud edits derive from the same base version; preserve both and require resolution. |

## 7. Implementation flows

### A. Initial research-pack ingestion

~~~
USGS/EPA-derived CSV plus curated reports
  -> preserve attribution and source URL
  -> convert observations to readable text
  -> split reports into source-preserving chunks
  -> create dense embeddings locally
  -> optionally create BM25 sparse vectors
  -> upsert vectors plus payload into Qdrant Edge
  -> save canonical records and versions in SQLite
  -> run Edge optimize after batch import
  -> display Local research pack ready
~~~

Use batch imports. Qdrant Edge does not run a background optimizer; call optimize after the seed import. Close the shard cleanly on shutdown and load the existing shard on restart.

### B. Offline research query

~~~
Research question plus filters
  -> create local query embedding
  -> Qdrant Edge dense search with payload filters
  -> optional BM25 search for exact names, IDs, and dates
  -> combine/rerank locally
  -> pass only retrieved source content to Gemma 4
  -> return answer, citations, filter chips, local origin, and latency
~~~

Gemma 4 system instruction:

~~~
Answer only from retrieved sources.
State clearly when evidence is insufficient or unverified.
Do not make environmental or health conclusions beyond evidence.
Cite source title and date for each claim.
~~~

### C. Create a note offline

~~~
Researcher enters observation
  -> SQLite saves note, timestamp, policy, and version
  -> local embedding is created
  -> note is upserted to Qdrant Edge
  -> note becomes searchable immediately
  -> only ready-to-sync notes are added to SQLite outbox
  -> activity timeline records the event
~~~

Demo note:

~~~
At River Zone 3, water had a strong chemical odour near the east bank.
Photo/reference attached. Requires laboratory verification.

State: needs-verification
~~~

### D. Reconnect and synchronize

~~~
Connection restored
  -> cloud health check succeeds
  -> user selects Sync now
  -> push approved outbox events to central Qdrant Server
  -> mark acknowledged events synced
  -> pull new approved cloud baseline or partial snapshot
  -> refresh local shared memory
  -> retain local-only material on device
~~~

Qdrant Edge does not provide a one-call bidirectional sync. The application owns its outbox, retry state, sharing policy, and conflict rules.

### E. Conflict resolution

Seed one conflict:

~~~
Cloud: River Zone 3 sample verified as high turbidity after laboratory review.
Local: Strong odour observed near east bank; laboratory verification pending.
~~~

When they derive from the same base record:

~~~
mark conflict
-> show local and cloud evidence side by side
-> researcher chooses keep local, keep cloud, or merge
-> merged record receives new version
-> resolved record may enter shared sync queue
~~~

## 8. MVP API contract

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | /api/status | Online/offline state, Edge count, queue count, last sync, storage summary. |
| POST | /api/search | Local dense/hybrid search with question and filters. |
| GET | /api/memory | Lists local records and state for Memory Inspector. |
| POST | /api/notes | Creates/indexes a local field note and applies policy. |
| PATCH | /api/notes/{id}/policy | Updates local-only, needs-verification, or ready-to-sync state. |
| GET | /api/sync/queue | Shows pending, retrying, synced, and failed events. |
| POST | /api/sync/run | Performs one controlled sync pass. |
| POST | /api/connectivity | Demo-only network control; it must block remote requests, not only recolor UI. |
| GET | /api/activity | Returns the event timeline. |
| POST | /api/conflicts/{id}/resolve | Saves chosen or merged result as a new local version. |

## 9. User-facing screens

1. **Research Device Overview** - state, local memory count, pending sync, last sync, and activity timeline.
2. **Evidence Search** - natural-language query, filters, citations, local origin, and latency.
3. **Local Memory Inspector** - reports, observations, notes, findings, privacy state, version, and source.
4. **Field Note Composer** - add observation, optional local attachment, and sharing state.
5. **Sync and Verification Center** - review queue, outbox, sync history, and Sync now control.
6. **Conflict Resolution** - cloud/local evidence side by side with Keep Local, Keep Cloud, and Merge actions.

## 10. Build order

### Phase 0 - reproducible repository

- [ ] Create frontend, edge-service, seed-data, docs, and runtime folders.
- [ ] Ignore node_modules, environment secrets, Python virtual environments, runtime Edge storage, SQLite, logs, and model cache.
- [ ] Commit source manifest, seed data, and an environment example.
- [ ] Pin Python, Node, Qdrant Edge, and model-runtime versions.

### Phase 1 - prove Edge first

- [ ] Create an EdgeShard in runtime/edge-shard from Python.
- [ ] Ingest reports and normalized observations.
- [ ] Create payload indexes and prove filtered retrieval.
- [ ] Search local River Zone 3 evidence.
- [ ] Restart and prove local-shard persistence.
- [ ] Repeat the search after network access is disabled.

**Do not move on until this works.** A polished UI without a real local Edge shard does not meet the core requirement.

### Phase 2 - useful local experience

- [ ] Build search, citations, filters, local-origin badge, and latency display.
- [ ] Add local Gemma 4 reasoning over retrieved context only.
- [ ] Add offline field-note creation and immediate re-search.
- [ ] Add sharing state and Local Memory Inspector.

### Phase 3 - edge-to-cloud proof

- [ ] Run central Qdrant Server/Cloud with approved shared knowledge.
- [ ] Implement SQLite outbox and approved-event push after reconnection.
- [ ] Implement scoped baseline refresh/snapshot pull.
- [ ] Add timeline, retry state, and one scripted conflict.

### Phase 4 - harden the demo

- [ ] Reset known initial state with a script.
- [ ] Preload seed data and models before presenting.
- [ ] Test every scripted query in real offline mode.
- [ ] Record a backup video.
- [ ] Finish README: setup, architecture, data attribution, privacy policy, and demo steps.

## 11. Live demo procedure

| Step | Show | Proof |
| --- | --- | --- |
| 1 | Online dashboard, local memory count, policy version, zero queued changes | Device contains a versioned knowledge pack. |
| 2 | Search for low oxygen/high turbidity near River Zone 3 | Qdrant Edge retrieves cited local reports and observations. |
| 3 | Apply site/date/parameter/verification filters | Structured filtering is real. |
| 4 | Turn offline mode on and show cloud access blocked | Cloud is no longer a dependency. |
| 5 | Repeat the search successfully | Local semantic/hybrid retrieval works offline. |
| 6 | Create a River Zone 3 observation | Local memory evolves and is immediately searchable. |
| 7 | Move state from needs-verification to ready-to-sync | Researcher controls sharing. |
| 8 | Reconnect and select Sync now | Approved note leaves outbox and reaches cloud. |
| 9 | Show and merge cloud/local conflict | Conflicting information is explicitly handled. |
| 10 | Show final activity timeline | Complete edge-to-cloud workflow is visible. |

### Presentation statement

> QuadOff FieldNote keeps critical research evidence searchable on the device even when the cloud is unavailable. Qdrant Edge is its local semantic memory; researchers can create observations offline, decide what remains private, and synchronize only approved findings when connectivity returns.

## 12. Do not do these things

- Do not replace Qdrant Edge with a local Docker Qdrant Server.
- Do not use a fake offline toggle; remote calls must fail/block while local search continues.
- Do not use a hosted LLM during offline demo. Reasoning must be local to claim full offline operation.
- Do not make Qdrant the transactional source of truth; SQLite owns notes, versions, and outbox events.
- Do not automatically sync every note.
- Do not present unverified observations as factual environmental conclusions.
- Do not rely on a live public-data API during the demo.

## 13. Final judging checklist

- [ ] Qdrant Edge runs in-process and persists local data.
- [ ] Local retrieval works after network access is disabled.
- [ ] Answer shows source, filter, local origin, and latency.
- [ ] A new offline note is immediately searchable.
- [ ] Local-only notes never enter sync queue.
- [ ] Approved notes sync after reconnection.
- [ ] UI exposes device memory, sync status, verification state, and activity.
- [ ] One cloud/device conflict is preserved and explicitly resolved.
- [ ] Demo resets and runs without live external data.
- [ ] README explains setup, data attribution, architecture, and demo flow.

## 14. Proposed repository layout

~~~
quadoff-fieldnote/
  README.md
  Needs.md
  .gitignore
  .env.example
  seed-data/
  frontend/
  edge-service/
    app/
      main.py
      edge_store.py
      ingestion.py
      search.py
      reasoning.py
      local_state.py
      sync.py
      policy.py
  docs/
    architecture.md
    demo-script.md
    data-attribution.md
  runtime/  # ignored: Edge shard, SQLite DB, logs, model cache
~~~

## 15. Immediate first actions

1. Download/curate the small water-research pack and complete its source manifest.
2. Build a Python EdgeShard prototype and prove one local filtered search with internet disabled.
3. Test a local embedding model; add local Gemma 4 reasoning only after retrieval is stable.
4. Implement local-only, needs-verification, and ready-to-sync state transitions.
5. Add central sync and a single scripted conflict last.
