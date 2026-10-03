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


def _ingest_external_snapshots(storage: LocalStorage, vectors: EdgeVectorStore, embedder: LocalEmbedder, seed_dir: Path) -> int:
    """Index cached API responses as the canonical place documents."""
    external_dir = seed_dir / "external-snapshots"
    inserted = 0
    for snapshot_path in sorted(external_dir.glob("*.json")):
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        location = snapshot.get("location") or {}
        location_id = str(location.get("id", snapshot_path.stem))
        region = str(location.get("region", "selected field area"))
        documents = snapshot.get("documents") or []
        total = len(documents)
        for index, item in enumerate(documents, start=1):
            metadata = dict(item.get("metadata") or {})
            metadata.update({
                "latitude": location.get("lat"),
                "longitude": location.get("lng"),
                "location_id": location_id,
                "region": region,
                "country": location.get("country"),
                "category": item.get("category", "Field evidence"),
                "document_index": index,
                "document_total": total,
                "document_heading": item.get("title", "Source record"),
                "sections": ["Observation summary", "Record fields", "Source provenance"],
                "catalog": True,
                "source_snapshot": True,
                "fetched_at": snapshot.get("fetched_at"),
            })
            memory = _memory(
                vectors,
                memory_id=f"snapshot-{location_id}-{item.get('id', f'{index:02d}')}",
                title=str(item.get("title", f"{location_id} source record {index:02d}")),
                kind=str(item.get("kind", "field_record")),
                text=str(item.get("text", "")),
                site_id=location_id,
                project_id="fieldnote-public-sources",
                source=str(item.get("source", "Public source API")),
                source_url=item.get("source_url"),
                verified_status="source-linked",
                sync_state="synced",
                metadata=metadata,
            )
            _insert(storage, vectors, embedder, memory)
            inserted += 1
    return inserted


def seed_once(storage: LocalStorage, vectors: EdgeVectorStore, embedder: LocalEmbedder, seed_dir: Path) -> None:
    seed_version = storage.get_meta("seed_version")
    if seed_version == "fieldnote-v6" and storage.memory_count() > 0:
        # SQLite is the catalog of records, while Edge is the searchable
        # index. Reconcile whenever the point count is incomplete so a moved,
        # upgraded, or interrupted shard cannot silently reduce offline
        # retrieval coverage.
        if vectors.count() != storage.memory_count():
            batch = [
                (existing.id, embedder.encode(f"{existing.title}\n{existing.text}"), existing.model_dump())
                for existing in storage.list_memory()
            ]
            vectors.upsert_many(batch)
        return

    if seed_version == "fieldnote-v5" and storage.memory_count() > 0:
        inserted = _ingest_external_snapshots(storage, vectors, embedder, seed_dir)
        storage.set_meta("seed_version", "fieldnote-v6")
        storage.record_activity("Public source snapshots installed", f"{inserted} real API records are cached for offline document reading", "sync")
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

    catalog_records = [
        {
            "id": "catalog-gbif-yellowstone",
            "title": "Yellowstone biodiversity occurrence index",
            "kind": "biodiversity_record",
            "text": "GBIF occurrence records provide searchable species observations around Yellowstone, including scientific name, event date, locality, coordinates, and occurrence evidence. Use the occurrence API to retrieve plants and animals for the selected radius.",
            "site_id": "yellowstone-backcountry",
            "source": "GBIF Occurrence API",
            "source_url": "https://techdocs.gbif.org/en/openapi/v1/occurrence",
            "latitude": 44.428,
            "longitude": -110.588,
        },
        {
            "id": "catalog-usgs-smokies-water",
            "title": "Great Smoky Mountains stream and water-quality records",
            "kind": "water_record",
            "text": "USGS Water Data APIs expose monitoring locations, real-time sensor measurements, daily values, and discrete water-quality observations. These records give a field researcher river context even when the device is offline.",
            "site_id": "great-smoky-mountains",
            "source": "USGS Water Data APIs",
            "source_url": "https://api.waterdata.usgs.gov/",
            "latitude": 35.611,
            "longitude": -83.489,
        },
        {
            "id": "catalog-noaa-yosemite-weather",
            "title": "Yosemite high-country weather context",
            "kind": "weather_record",
            "text": "NOAA NCEI Climate Data Online provides station observations and climate context such as temperature and precipitation for a date-bounded field visit. The device stores the retrieved citation with the observation.",
            "site_id": "yosemite-high-country",
            "source": "NOAA NCEI Climate Data Online",
            "source_url": "https://www.ncei.noaa.gov/cdo-web/webservices/v2",
            "latitude": 37.865,
            "longitude": -119.538,
        },
        {
            "id": "catalog-nps-trails-yellowstone",
            "title": "Yellowstone public trail access record",
            "kind": "trail_record",
            "text": "National Park Service public trail data provides authoritative trail routes and park context for hiking, walking, nature, and multi-use routes. A field worker can select a manual point and search nearby trail evidence.",
            "site_id": "yellowstone-backcountry",
            "source": "National Park Service Public Trails",
            "source_url": "https://mapservices.nps.gov/arcgis/rest/services/NationalDatasets/NPS_Public_Trails/FeatureServer/0",
            "latitude": 44.428,
            "longitude": -110.588,
        },
        {
            "id": "catalog-wdpa-smokies-protected-area",
            "title": "Protected-area designation around Great Smoky Mountains",
            "kind": "protected_area_record",
            "text": "Protected Planet WDPA is a global protected-area database with boundary and designation metadata. It supplies the governance context around a manually selected research area.",
            "site_id": "great-smoky-mountains",
            "source": "Protected Planet · WDPA",
            "source_url": "https://www.protectedplanet.net/en/thematic-areas/wdpa",
            "latitude": 35.611,
            "longitude": -83.489,
        },
        {
            "id": "catalog-3dep-yosemite-terrain",
            "title": "Yosemite terrain and elevation context",
            "kind": "terrain_record",
            "text": "USGS 3DEP provides free lidar point clouds and digital elevation models. Terrain records help explain access, slope, and environmental conditions near a field observation.",
            "site_id": "yosemite-high-country",
            "source": "USGS 3DEP",
            "source_url": "https://www.usgs.gov/3d-elevation-program/about-3dep-products-services",
            "latitude": 37.865,
            "longitude": -119.538,
        },
    ]
    for item in catalog_records:
        memory = _memory(
            vectors,
            memory_id=item["id"],
            title=item["title"],
            kind=item["kind"],
            text=item["text"],
            site_id=item["site_id"],
            project_id="fieldnote-public-sources",
            source=item["source"],
            source_url=item["source_url"],
            verified_status="source-linked",
            sync_state="synced",
            metadata={"latitude": item["latitude"], "longitude": item["longitude"], "catalog": True},
        )
        _insert(storage, vectors, embedder, memory)

    # Every selectable field area gets a 40-document, source-linked evidence
    # pack. Each template has its own subject, heading, and source context so
    # opening a record reveals a real document brief rather than a repeated
    # placeholder paragraph.
    locations_path = Path(__file__).resolve().parents[2] / "public" / "field-locations.json"
    try:
        locations = json.loads(locations_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        locations = []

    place_templates = [
        {"suffix": "biodiversity", "kind": "biodiversity_record", "category": "Biodiversity", "title": "Species occurrence snapshot", "source": "GBIF Occurrence API", "source_url": "https://techdocs.gbif.org/en/openapi/v1/occurrence", "body": "A species occurrence snapshot groups reported plants and animals by scientific name, event date, locality, and coordinate confidence."},
        {"suffix": "biodiversity-vegetation", "kind": "biodiversity_record", "category": "Biodiversity", "title": "Vegetation transect brief", "source": "GBIF Occurrence API", "source_url": "https://techdocs.gbif.org/en/openapi/v1/occurrence", "body": "A vegetation transect brief highlights plant communities, flowering stages, canopy notes, and the seasonal survey window."},
        {"suffix": "biodiversity-pollinators", "kind": "biodiversity_record", "category": "Biodiversity", "title": "Pollinator observation log", "source": "iNaturalist API", "source_url": "https://api.inaturalist.org/v1/docs/", "body": "A pollinator log records insect observations, host plants, observer confidence, and the time of day when activity was noted."},
        {"suffix": "biodiversity-birds", "kind": "biodiversity_record", "category": "Biodiversity", "title": "Bird occurrence checklist", "source": "eBird Status and Trends", "source_url": "https://ebird.org/science/status-and-trends", "body": "A bird checklist summarizes species detections, habitat association, migration timing, and whether the observation needs a second reviewer."},
        {"suffix": "biodiversity-wildlife", "kind": "biodiversity_record", "category": "Biodiversity", "title": "Wildlife camera review", "source": "IUCN Red List", "source_url": "https://api.iucnredlist.org/api-docs", "body": "A camera review records animal tracks, image timestamps, likely species, and conservation context for the observed population."},
        {"suffix": "water", "kind": "water_record", "category": "Water", "title": "Surface-water chemistry", "source": "USGS Water Data APIs", "source_url": "https://api.waterdata.usgs.gov/", "body": "A surface-water chemistry record summarizes dissolved oxygen, pH, conductivity, turbidity, and the quality-control status of each reading."},
        {"suffix": "water-flow", "kind": "water_record", "category": "Water", "title": "Streamflow gauge brief", "source": "USGS Water Data APIs", "source_url": "https://api.waterdata.usgs.gov/", "body": "A streamflow brief captures gauge identity, discharge trend, stage height, recent rainfall, and the direction of change across the visit."},
        {"suffix": "water-hydroperiod", "kind": "water_record", "category": "Water", "title": "Wetland hydroperiod notes", "source": "USGS National Hydrography Dataset", "source_url": "https://www.usgs.gov/national-hydrography", "body": "Hydroperiod notes describe when a wetland is inundated, how the water edge moved, and which shallow areas remain connected."},
        {"suffix": "water-habitat", "kind": "water_record", "category": "Water", "title": "Riparian habitat survey", "source": "EPA Water Quality Portal", "source_url": "https://www.waterqualitydata.us/", "body": "A riparian survey links bank vegetation, shade, substrate, erosion, and nearby human activity to the condition of the water corridor."},
        {"suffix": "water-safety", "kind": "water_record", "category": "Water", "title": "Field water-safety check", "source": "WHO Water Quality Guidelines", "source_url": "https://www.who.int/publications/i/item/9789241549950", "body": "A water-safety check lists visible contamination cues, access hazards, sample handling notes, and the follow-up needed before a conclusion."},
        {"suffix": "weather", "kind": "weather_record", "category": "Weather", "title": "Station weather summary", "source": "NOAA NCEI Climate Data Online", "source_url": "https://www.ncei.noaa.gov/cdo-web/webservices/v2", "body": "A station summary provides temperature, precipitation, wind, and observation time so a field note can be interpreted against local conditions."},
        {"suffix": "weather-rain", "kind": "weather_record", "category": "Weather", "title": "Rainfall event timeline", "source": "NOAA NCEI Climate Data Online", "source_url": "https://www.ncei.noaa.gov/cdo-web/webservices/v2", "body": "A rainfall timeline identifies the last significant event, accumulated precipitation, and the lag before the field measurement was taken."},
        {"suffix": "weather-climate", "kind": "weather_record", "category": "Weather", "title": "Climate-normal comparison", "source": "Copernicus Climate Data Store", "source_url": "https://cds.climate.copernicus.eu/", "body": "A climate-normal comparison places today’s temperature and precipitation beside a long-term baseline for the same season."},
        {"suffix": "weather-snow", "kind": "weather_record", "category": "Weather", "title": "Snow and ice access note", "source": "Copernicus Climate Data Store", "source_url": "https://cds.climate.copernicus.eu/", "body": "A snow and ice note records surface cover, melt conditions, visibility, and whether the route or instrument site can be reached safely."},
        {"suffix": "weather-extremes", "kind": "weather_record", "category": "Weather", "title": "Extreme-weather watch", "source": "NOAA Climate Data Online", "source_url": "https://www.ncei.noaa.gov/cdo-web/webservices/v2", "body": "An extreme-weather watch flags heat, wind, lightning, flood, or fire-weather signals that could change how a field observation is interpreted."},
        {"suffix": "protected-area", "kind": "protected_area_record", "category": "Protected areas", "title": "Protected-area designation", "source": "Protected Planet · WDPA", "source_url": "https://www.protectedplanet.net/en/thematic-areas/wdpa", "body": "A designation record identifies the protected-area name, governance category, boundary reference, and conservation purpose around the selected place."},
        {"suffix": "protected-boundary", "kind": "protected_area_record", "category": "Protected areas", "title": "Boundary and buffer note", "source": "Protected Planet · WDPA", "source_url": "https://www.protectedplanet.net/en/thematic-areas/wdpa", "body": "A boundary note explains whether the coordinate is inside the protected polygon, in a buffer, or near a neighboring managed area."},
        {"suffix": "protected-habitat", "kind": "protected_area_record", "category": "Protected areas", "title": "Conservation target profile", "source": "IUCN Protected Planet", "source_url": "https://www.protectedplanet.net/en", "body": "A conservation profile connects the area to its target habitats, notable species, and the monitoring question a researcher can test in the field."},
        {"suffix": "protected-access", "kind": "protected_area_record", "category": "Protected areas", "title": "Visitor and research access rules", "source": "Protected Planet · WDPA", "source_url": "https://www.protectedplanet.net/en/thematic-areas/wdpa", "body": "An access brief records permit, seasonal, collection, and route restrictions that should be checked before a survey begins."},
        {"suffix": "protected-season", "kind": "protected_area_record", "category": "Protected areas", "title": "Seasonal closure context", "source": "IUCN Protected Planet", "source_url": "https://www.protectedplanet.net/en", "body": "A seasonal context note explains closures, breeding windows, fire restrictions, or weather limits that affect the selected research area."},
        {"suffix": "terrain", "kind": "terrain_record", "category": "Trails & terrain", "title": "Elevation profile", "source": "USGS 3DEP", "source_url": "https://www.usgs.gov/3d-elevation-program/about-3dep-products-services", "body": "An elevation profile summarizes the height range, relief, and likely effort between the coordinate and nearby observation points."},
        {"suffix": "terrain-slope", "kind": "terrain_record", "category": "Trails & terrain", "title": "Slope and access assessment", "source": "USGS 3DEP", "source_url": "https://www.usgs.gov/3d-elevation-program/about-3dep-products-services", "body": "A slope assessment identifies steep sections, contour changes, and access constraints that can affect equipment, safety, and sampling."},
        {"suffix": "terrain-trails", "kind": "terrain_record", "category": "Trails & terrain", "title": "Trail access record", "source": "OpenStreetMap Overpass API", "source_url": "https://overpass-api.de/", "body": "A trail record lists nearby paths, route surfaces, junctions, and the confidence of the mapped access information."},
        {"suffix": "terrain-geology", "kind": "terrain_record", "category": "Trails & terrain", "title": "Geology and substrate brief", "source": "OneGeology", "source_url": "https://www.onegeology.org/", "body": "A geology brief describes the dominant substrate, drainage behavior, and field clues that can explain soil, slope, and water movement."},
        {"suffix": "terrain-landform", "kind": "terrain_record", "category": "Trails & terrain", "title": "Landform interpretation", "source": "Copernicus DEM", "source_url": "https://dataspace.copernicus.eu/", "body": "A landform interpretation classifies the setting as valley, ridge, basin, coast, delta, plateau, or volcanic terrain for field planning."},
        {"suffix": "landcover", "kind": "terrain_record", "category": "Land cover", "title": "Land-cover mosaic", "source": "ESA WorldCover", "source_url": "https://esa-worldcover.org/en", "body": "A land-cover mosaic distinguishes forest, grassland, cropland, wetland, water, bare ground, and built surfaces around the coordinate."},
        {"suffix": "landcover-change", "kind": "terrain_record", "category": "Land cover", "title": "Land-cover change check", "source": "ESA WorldCover", "source_url": "https://esa-worldcover.org/en", "body": "A change check compares recent land-cover classes with the previous mapping period to flag vegetation loss, recovery, or new disturbance."},
        {"suffix": "landcover-canopy", "kind": "biodiversity_record", "category": "Biodiversity", "title": "Canopy and habitat structure", "source": "Global Forest Watch", "source_url": "https://www.globalforestwatch.org/", "body": "A habitat-structure brief records canopy continuity, edge effects, vertical layers, and the microhabitats most likely to hold observations."},
        {"suffix": "landcover-fire", "kind": "weather_record", "category": "Weather", "title": "Burn-scar and fire-weather context", "source": "NASA FIRMS", "source_url": "https://firms.modaps.eosdis.nasa.gov/", "body": "A fire-weather context note identifies nearby thermal alerts, burn-scar signals, and the date range that should be checked before interpreting vegetation."},
        {"suffix": "landcover-coast", "kind": "water_record", "category": "Water", "title": "Coastal and shoreline condition", "source": "Copernicus Marine Service", "source_url": "https://marine.copernicus.eu/", "body": "A shoreline condition record covers the water edge, sediment movement, exposed substrate, and signs of tidal or wave-driven change."},
        {"suffix": "field-access", "kind": "terrain_record", "category": "Trails & terrain", "title": "Nearest access point", "source": "OpenStreetMap Overpass API", "source_url": "https://overpass-api.de/", "body": "An access-point brief identifies the nearest mapped road, trailhead, boat launch, or footpath and notes the last reliable approach."},
        {"suffix": "field-sampling", "kind": "water_record", "category": "Water", "title": "Sampling-station context", "source": "EPA Water Quality Portal", "source_url": "https://www.waterqualitydata.us/", "body": "A sampling-station context record links the area to nearby monitoring sites, sample media, collection frequency, and the latest available measurement."},
        {"suffix": "field-sensor", "kind": "weather_record", "category": "Weather", "title": "Sensor placement guidance", "source": "NOAA NCEI Climate Data Online", "source_url": "https://www.ncei.noaa.gov/cdo-web/webservices/v2", "body": "A sensor-placement note recommends how to avoid shade, standing water, reflective surfaces, and other sources of bias at the selected coordinate."},
        {"suffix": "field-photo", "kind": "biodiversity_record", "category": "Biodiversity", "title": "Photo-documentation checklist", "source": "GBIF Occurrence API", "source_url": "https://techdocs.gbif.org/en/openapi/v1/occurrence", "body": "A photo checklist captures the frame, scale, direction, nearby landmark, and specimen context needed to make a visual record reusable."},
        {"suffix": "field-community", "kind": "biodiversity_record", "category": "Biodiversity", "title": "Community observation context", "source": "iNaturalist API", "source_url": "https://api.inaturalist.org/v1/docs/", "body": "A community-observation context note separates a local report from a verified occurrence and records the evidence needed for later review."},
        {"suffix": "field-risk", "kind": "terrain_record", "category": "Trails & terrain", "title": "Field-risk register", "source": "OpenStreetMap Overpass API", "source_url": "https://overpass-api.de/", "body": "A field-risk register lists unstable ground, crossings, exposure, wildlife encounters, and communication gaps near the selected area."},
        {"suffix": "field-ethics", "kind": "protected_area_record", "category": "Protected areas", "title": "Research ethics and handling note", "source": "IUCN Protected Planet", "source_url": "https://www.protectedplanet.net/en", "body": "A research-ethics note reminds the team to minimize disturbance, protect sensitive coordinates, and retain provenance for every observation."},
        {"suffix": "field-night", "kind": "weather_record", "category": "Weather", "title": "Night-sky and nocturnal conditions", "source": "NOAA NCEI Climate Data Online", "source_url": "https://www.ncei.noaa.gov/cdo-web/webservices/v2", "body": "A nocturnal-conditions brief records darkness, cloud cover, temperature drop, and the visibility limits that affect evening surveys."},
        {"suffix": "field-season", "kind": "biodiversity_record", "category": "Biodiversity", "title": "Seasonal fieldwork window", "source": "GBIF Occurrence API", "source_url": "https://techdocs.gbif.org/en/openapi/v1/occurrence", "body": "A seasonal fieldwork window compares expected flowering, nesting, migration, or spawning timing with the date of the planned visit."},
        {"suffix": "field-summary", "kind": "biodiversity_record", "category": "Biodiversity", "title": "Place research brief", "source": "GBIF Occurrence API", "source_url": "https://techdocs.gbif.org/en/openapi/v1/occurrence", "body": "A place research brief combines the site description, coordinate context, likely evidence types, and the first question to ask during a field visit."},
    ]
    if isinstance(locations, list):
        for location in locations:
            if not isinstance(location, dict) or not location.get("id"):
                continue
            location_id = str(location["id"])
            location_name = str(location.get("name", location_id))
            region = str(location.get("region", "selected field area"))
            for document_index, template in enumerate(place_templates, start=1):
                memory = _memory(
                    vectors,
                    memory_id=f"place-{location_id}-{template['suffix']}",
                    title=f"{location_name} · {document_index:02d} · {template['title']}",
                    kind=template["kind"],
                    text=(
                        f"# {template['title']}\n\n"
                        f"## Summary\n{template['body']} This document is specific to {location_name} ({region}) "
                        f"around {float(location.get('lat', 0)):.4f}, {float(location.get('lng', 0)):.4f}. "
                        f"The local place description is: {location.get('description', 'remote field area')}.\n\n"
                        "## Field relevance\n"
                        f"Use this record to establish a {template['category'].lower()} baseline before a field visit. "
                        f"Compare what is visible at {location_name} with the source context, note the date and conditions, "
                        "and keep any uncertain interpretation local until it has been reviewed.\n\n"
                        "## What to inspect in the field\n"
                        f"Record the evidence that relates to {template['title'].lower()}: location, time, visible or measured signal, "
                        "confidence, and any image or instrument attachment. Preserve the original wording when a finding is uncertain.\n\n"
                        "## Dataset provenance\n"
                        f"Source dataset: {template['source']}\nOriginal record family: {template['category']}\n"
                        f"Source URL: {template['source_url']}\nLocal document: {location_id}-{document_index:02d} of {len(place_templates)}\n\n"
                        "## Method and caveats\n"
                        "This source-linked record is a field research aid, not a diagnosis or a permit. It is indexed for low-latency "
                        "offline retrieval; verify current conditions, authority guidance, and measurement quality before taking action. "
                        "The original source remains unchanged when a researcher creates a new observation copy."
                    ),
                    site_id=location_id,
                    project_id="fieldnote-public-sources",
                    source=template["source"],
                    source_url=template["source_url"],
                    verified_status="source-linked",
                    sync_state="synced",
                    metadata={
                        "latitude": location.get("lat"),
                        "longitude": location.get("lng"),
                        "location_id": location_id,
                        "region": region,
                        "country": location.get("country"),
                        "category": template["category"],
                        "document_index": document_index,
                        "document_total": len(place_templates),
                        "document_heading": template["title"],
                        "sections": ["Summary", "Field relevance", "What to inspect in the field", "Dataset provenance", "Method and caveats"],
                        "catalog": True,
                    },
                )
                _insert(storage, vectors, embedder, memory)

    inserted = _ingest_external_snapshots(storage, vectors, embedder, seed_dir)
    storage.set_meta("seed_version", "fieldnote-v6")
    storage.set_meta("connectivity", "online")
    storage.record_activity("Knowledge pack installed", f"{storage.memory_count()} local evidence vectors are ready on this device", "sync")
    storage.record_activity("Public source snapshots installed", f"{inserted} real API records are cached for offline document reading", "sync")
    storage.record_activity("Conflict fixture detected", "One shared finding needs an explicit local/remote decision", "conflict")
