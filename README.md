# QuadOff FieldNote

Offline-first environmental research memory for a field researcher working around River Zone 3. FieldNote keeps a curated evidence pack on the device, searches it with an embedded Qdrant Edge shard, records observations locally, and synchronizes only approved findings when connectivity returns.

The app is intentionally a field-intelligence workflow, not a generic chatbot:

- Ask: “Has low dissolved oxygen or high turbidity been reported near River Zone 3 before?”
- Retrieve source-preserving evidence from Qdrant Edge while offline.
- See a citation-first local briefing and inspect the underlying observations.
- Capture a new observation; choose local-only, needs-verification, or ready-to-sync.
- Toggle the device offline, continue searching and capturing, then reconnect.
- Resolve a seeded local/remote conflict before synchronizing.

## Run locally

### 1. Start the edge service

From the repository root, install the Python dependencies once:

```powershell
python -m pip install -r edge-service/requirements.txt
```

Then run the API:

```powershell
$env:PYTHONPATH = "$PWD/edge-service"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The first start creates `runtime/fieldnote.sqlite3` and a persistent Qdrant Edge shard at `runtime/edge-shard`. The app also keeps the source snapshot catalog under `seed-data/external-snapshots` so document reading still works when the network is unavailable.

### Ingest real public source records

The place catalog is populated from public API responses rather than invented document text. From the repository root, run:

```powershell
python scripts/ingest_public_sources.py
```

The script fetches source responses from GBIF, iNaturalist, Open-Meteo, and OpenStreetMap Overpass, then writes one immutable JSON snapshot per place. It creates 30–40 source-derived records for each of the 39 low-connectivity places in `public/field-locations.json`; each record keeps the raw response payload, the complete upstream response, source URL, timestamp, coordinates, and provenance. No API key is required for these public endpoints. The UI's document reader presents readable source sections and detailed record context; implementation-level response payloads stay in the local snapshot for offline indexing rather than cluttering the researcher-facing page. If a public endpoint is temporarily unavailable, the last cached snapshot is retained for offline use.

### Area search

The Device Overview map supports click-to-select search areas, browser location detection, radius adjustment, and a **Search Qdrant Cloud** action. The action sends the selected center and bounds to `POST /api/search` with `source: "cloud"`. Configure `CENTRAL_QDRANT_URL`, `CENTRAL_QDRANT_API_KEY`, and `CENTRAL_QDRANT_COLLECTION` in `edge-service/.env` to query a real Qdrant Server collection. Without those settings, the UI uses the local Edge shard as an explicit demo fallback so the workflow still works offline.

To inspect or enable the optional local models:

```powershell
$env:PYTHONPATH = "$PWD/edge-service"
python -m pip install -r edge-service/requirements-models.txt
python -m app.model_setup check
python -m app.model_setup download --kind all
```

After the model weights are cached, copy the commented model profile from
`edge-service/.env.example` into a local `.env`. The service will then use
EmbeddingGemma for document/query vectors and Gemma 4 E2B for the cited local
briefing. Without the weights, it remains fully runnable using its deterministic
offline encoder and evidence-first fallback; the Observation page labels that
result as a local draft rather than pretending Gemma 4 ran. Gemma 4 E2B is
loaded through Transformers' `AutoProcessor` + `AutoModelForMultimodalLM`
adapter when the model is present locally; the model download is about 10.3 GB,
so it is intentionally never triggered by a normal app start.

### Optional online summarizer

For an online presentation, the same evidence-first flow can use Gemini as an
optional summarizer while Qdrant Edge still performs the local retrieval. Set
`REASONING_BACKEND=gemini-api`, add `GEMINI_API_KEY` and `GEMINI_MODEL` to the
backend `.env`, and restart the service. The key stays server-side. When the
app is switched offline, the API call is skipped and the deterministic local
draft remains available.

### 2. Start the React UI

In another terminal:

```powershell
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). The frontend gracefully shows its seeded visual shell if the API is not running, but the judge-facing workflow is complete when both processes are running.

## Demo path

1. Open **Knowledge search** and run the prefilled River Zone 3 question.
2. Open **Overview** to show local vector count and the Qdrant Edge origin.
3. Click the connection control to switch to **Offline**.
4. Search again; the response remains local and displays offline retrieval latency.
5. Create a field observation. Keep it **Needs verification** to demonstrate local-only memory, or select **Ready to sync** to put it in the outbox.
6. Return online and open **Sync center**. Deliver the approved update to the demo central Qdrant adapter (or a configured Qdrant Server).
7. Use the API or the conflict panel implementation to show that local and remote edits are preserved until a researcher chooses local, remote, or merged content.

## Architecture

```text
React/Vite UI
    │ localhost HTTP
FastAPI edge service
    ├── Qdrant Edge embedded shard (vectors/search)
    ├── SQLite (canonical memory metadata, notes, policy, outbox, activity)
    ├── local embedding interface (deterministic offline encoder by default;
    │   cached EmbeddingGemma adapter can be enabled)
    ├── evidence-first local reasoning (cached Gemma 4 adapter can be enabled)
    └── sync coordinator → Qdrant Server/Cloud or explicit demo central
```

See [Needs.md](./Needs.md), [docs/architecture.md](./docs/architecture.md), and [docs/demo-script.md](./docs/demo-script.md) for the product contract, API map, dataset attribution, and judge walkthrough.

No Git push is performed by the local run instructions.
