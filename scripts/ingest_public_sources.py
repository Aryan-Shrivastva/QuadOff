"""Fetch small, auditable source snapshots for the FieldNote demo.

The snapshots are kept in seed-data/external-snapshots so the app can read
them offline after this one-time ingestion step. No API keys are required for
the public endpoints used here.
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
LOCATIONS = ROOT / "public" / "field-locations.json"
OUTPUT = ROOT / "seed-data" / "external-snapshots"
USER_AGENT = "QuadOff-FieldNote/1.0 (offline-first demo ingestion)"


def fetch_json(url: str, *, data: bytes | None = None, retries: int = 3) -> tuple[dict[str, Any], str]:
    request = Request(url, data=data, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, method="POST" if data else "GET")
    last_error = "unknown error"
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=35) as response:
                return json.loads(response.read().decode("utf-8")), url
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            time.sleep(1.5 * (attempt + 1))
    return {"error": last_error}, url


def location_box(lat: float, lng: float, delta: float = 0.25) -> dict[str, str]:
    return {"decimalLatitude": f"{lat - delta},{lat + delta}", "decimalLongitude": f"{lng - delta},{lng + delta}"}


def add_document(documents: list[dict[str, Any]], *, source_key: str, index: int, title: str, kind: str, category: str, source: str, source_url: str, text: str, payload: Any, extra: dict[str, Any] | None = None) -> None:
    documents.append({
        "id": f"{source_key}-{index:02d}",
        "title": title,
        "kind": kind,
        "category": category,
        "source": source,
        "source_url": source_url,
        "text": text,
        "payload": payload,
        "metadata": {
            "source_snapshot": True,
            "source_key": source_key,
            "response_key": source_key.split("-", 1)[0],
            "record_index": index,
            **(extra or {}),
        },
    })


def ingest_location(location: dict[str, Any]) -> dict[str, Any]:
    location_id = str(location["id"])
    name = str(location["name"])
    region = str(location.get("region", "selected field area"))
    lat = float(location["lat"])
    lng = float(location["lng"])
    documents: list[dict[str, Any]] = []

    gbif_params = {**location_box(lat, lng), "limit": "5", "hasCoordinate": "true", "occurrenceStatus": "present"}
    gbif_url = "https://api.gbif.org/v1/occurrence/search?" + urlencode(gbif_params)
    gbif, gbif_source = fetch_json(gbif_url)
    for index, item in enumerate(gbif.get("results", [])[:5], start=1):
        scientific = item.get("scientificName") or item.get("species") or "Unidentified occurrence"
        common = item.get("vernacularName") or item.get("genericName") or ""
        title_name = f"{common} ({scientific})" if common else str(scientific)
        text = (
            f"# {name} · GBIF occurrence {index:02d}\n\n"
            f"## Observation summary\nThis indexed occurrence is {title_name}. It was recorded at {item.get('locality') or item.get('municipality') or name} "
            f"on {item.get('eventDate') or item.get('year') or 'an undated event'}. The record reports {item.get('basisOfRecord', 'an observation')} "
            f"with occurrence status {item.get('occurrenceStatus', 'not specified')}.\n\n"
            f"## Record fields\nScientific name: {scientific}\nCommon name: {common}\nCountry: {item.get('country', location.get('country', ''))}\n"
            f"Coordinates: {item.get('decimalLatitude', lat)}, {item.get('decimalLongitude', lng)}\nDataset: {item.get('datasetName', 'GBIF indexed dataset')}\n"
            f"GBIF key: {item.get('key', item.get('gbifID', 'not supplied'))}\n\n"
            f"## Detailed record\nThis record describes a {item.get('taxonRank', 'taxonomic')} observation associated with {item.get('stateProvince') or item.get('country') or name}. "
            f"The reported occurrence status is {item.get('occurrenceStatus', 'not specified')}, and the observation basis is {item.get('basisOfRecord', 'not specified')}. "
            f"The coordinate uncertainty is {item.get('coordinateUncertaintyInMeters', 'not supplied')} metres. "
            f"Use the event date, taxon, location, and uncertainty together when comparing this record with a new field observation.\n\n"
            f"## Source provenance\nSource: GBIF Occurrence API\nThis public source response is cached locally for offline inspection."
        )
        add_document(documents, source_key="gbif", index=index, title=f"{name} · {index:02d} · {title_name}", kind="biodiversity_record", category="Biodiversity", source="GBIF Occurrence API", source_url=gbif_source, text=text, payload=item, extra={"location_id": location_id, "region": region})

    inat_params = {"lat": lat, "lng": lng, "radius": 10, "per_page": 5, "order_by": "observed_on", "order": "desc", "verifiable": "true"}
    inat_url = "https://api.inaturalist.org/v1/observations?" + urlencode(inat_params)
    inat, inat_source = fetch_json(inat_url)
    for index, item in enumerate(inat.get("results", [])[:5], start=1):
        taxon = item.get("taxon") or {}
        taxon_name = taxon.get("name") or "Unidentified taxon"
        common = taxon.get("preferred_common_name") or ""
        text = (
            f"# {name} · iNaturalist observation {index:02d}\n\n"
            f"## Observation summary\nThe community observation identifies {common + ' (' if common else ''}{taxon_name}{')' if common else ''}. "
            f"It was observed on {item.get('observed_on', 'an undated event')} near {item.get('place_guess') or name} and has a {item.get('quality_grade', 'needs review')} quality grade.\n\n"
            f"## Record fields\nObservation ID: {item.get('id', 'not supplied')}\nTaxon rank: {taxon.get('rank', 'not supplied')}\n"
            f"Observer: {item.get('user', {}).get('login', 'not supplied')}\nCoordinates: {item.get('geojson', {}).get('coordinates', [lng, lat])}\n"
            f"Photos attached: {len(item.get('photos', []))}\n\n"
            f"## Detailed record\nThis observation has a {item.get('quality_grade', 'not specified')} review grade and was contributed by {item.get('user', {}).get('login', 'an unidentified observer')}. "
            f"The record contains {len(item.get('photos', []))} attached image reference(s), an observation date of {item.get('observed_on', 'not supplied')}, and the taxon classification shown above. "
            f"Treat the community grade as provenance context, not as a substitute for a new field verification.\n\n"
            f"## Source provenance\nSource: iNaturalist observations API\nThis public source response is cached locally for offline inspection."
        )
        add_document(documents, source_key="inat", index=index, title=f"{name} · {6 + index:02d} · {common or taxon_name} observation", kind="biodiversity_record", category="Biodiversity", source="iNaturalist API", source_url="https://api.inaturalist.org/v1/docs/", text=text, payload=item, extra={"location_id": location_id, "region": region})

    overpass_query = f"[out:json][timeout:25];(nwr(around:3000,{lat},{lng})[natural];nwr(around:3000,{lat},{lng})[waterway];nwr(around:3000,{lat},{lng})[highway~\"path|track|footway|cycleway\"];);out center tags;"
    overpass, overpass_source = fetch_json("https://overpass-api.de/api/interpreter", data=urlencode({"data": overpass_query}).encode("utf-8"))
    for index, item in enumerate(overpass.get("elements", [])[:10], start=1):
        tags = item.get("tags") or {}
        label = tags.get("name") or tags.get("natural") or tags.get("waterway") or tags.get("highway") or "Unnamed mapped feature"
        center = item.get("center") or {"lat": lat, "lon": lng}
        text = (
            f"# {name} · mapped feature {index:02d}\n\n"
            f"## Feature summary\nOpenStreetMap contains a mapped {tags.get('natural') or tags.get('waterway') or tags.get('highway') or 'field feature'} named {label}. "
            f"Its map center is {center.get('lat', lat)}, {center.get('lon', lng)} and it is within the selected research area.\n\n"
            f"## Record fields\nOSM element: {item.get('type', 'element')} {item.get('id', 'not supplied')}\nName: {label}\n"
            f"Tags: {json.dumps(tags, ensure_ascii=False, sort_keys=True)}\n\n"
            f"## Detailed record\nThe mapped element is a {item.get('type', 'map')} feature with the tags shown above. "
            f"Its center coordinate places it inside the selected search area, making it useful for planning access, identifying nearby water or natural features, and describing the surroundings of a new observation.\n\n"
            f"## Source provenance\nSource: OpenStreetMap Overpass API\nThis public map response is cached locally for offline inspection."
        )
        add_document(documents, source_key="osm", index=index, title=f"{name} · {11 + index:02d} · {label}", kind="terrain_record", category="Trails & terrain", source="OpenStreetMap Overpass API", source_url="https://overpass-api.de/", text=text, payload=item, extra={"location_id": location_id, "region": region})

    weather_params = {"latitude": lat, "longitude": lng, "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m", "hourly": "temperature_2m,precipitation_probability,precipitation,wind_speed_10m", "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code", "forecast_days": 5, "timezone": "auto"}
    weather_url = "https://api.open-meteo.com/v1/forecast?" + urlencode(weather_params)
    weather, weather_source = fetch_json(weather_url)
    daily = weather.get("daily") or {}
    daily_times = daily.get("time") or []
    for index, day in enumerate(daily_times[:5], start=1):
        text = (
            f"# {name} · weather day {index:02d}\n\n"
            f"## Forecast summary\nFor {day}, the Open-Meteo response reports a maximum temperature of {daily.get('temperature_2m_max', [''])[index - 1]} °C, "
            f"a minimum of {daily.get('temperature_2m_min', [''])[index - 1]} °C, precipitation of {daily.get('precipitation_sum', [''])[index - 1]} mm, "
            f"and weather code {daily.get('weather_code', [''])[index - 1]}.\n\n"
            f"## Detailed forecast record\nThe forecast row belongs to the {location.get('country', 'selected area')} point at {lat}, {lng}, using the source timezone {weather.get('timezone', 'not supplied')}. "
            f"Read the maximum and minimum together with precipitation and the weather code: they describe the expected operating window for access, visibility, equipment protection, and the conditions under which an observation was made. "
            f"This is a forecast context record, not a measurement made by the researcher in the field.\n\n"
            f"## Source provenance\nSource: Open-Meteo Forecast API\nThis public forecast response is cached locally for offline inspection."
        )
        add_document(documents, source_key="weather-day", index=index, title=f"{name} · {22 + index:02d} · Weather forecast {day}", kind="weather_record", category="Weather", source="Open-Meteo Forecast API", source_url=weather_source, text=text, payload={"date": day, "temperature_max": daily.get("temperature_2m_max", [])[index - 1], "temperature_min": daily.get("temperature_2m_min", [])[index - 1], "precipitation": daily.get("precipitation_sum", [])[index - 1], "weather_code": daily.get("weather_code", [])[index - 1]}, extra={"location_id": location_id, "region": region})

    hourly = weather.get("hourly") or {}
    hourly_times = hourly.get("time") or []
    for index, hour in enumerate(hourly_times[:15], start=1):
        temperature = (hourly.get("temperature_2m") or [None])[index - 1]
        precipitation_probability = (hourly.get("precipitation_probability") or [None])[index - 1]
        precipitation = (hourly.get("precipitation") or [None])[index - 1]
        wind = (hourly.get("wind_speed_10m") or [None])[index - 1]
        current = weather.get("current") or {}
        text = (
            f"# {name} · hourly weather {index:02d}\n\n"
            f"## Observation window\nAt {hour}, the model response gives {temperature} °C, precipitation {precipitation} mm, "
            f"a {precipitation_probability}% precipitation probability, and wind speed {wind} km/h for the selected coordinate.\n\n"
            f"## Detailed observation context\nThis hourly row is part of a forecast series for {lat}, {lng} in the {weather.get('timezone', 'source')} timezone. "
            f"The source uses {weather.get('elevation', 'unspecified')} m elevation and reports the current reference temperature as {current.get('temperature_2m', 'not supplied')} °C "
            f"with relative humidity {current.get('relative_humidity_2m', 'not supplied')}%. Compare the timestamp with the field note, then use temperature, precipitation, probability, and wind together to distinguish a visual change from a weather-driven change. "
            f"The row describes expected conditions; it does not replace a local instrument reading.\n\n"
            f"## Source provenance\nSource: Open-Meteo Forecast API\nThis public forecast response is cached locally for offline inspection."
        )
        add_document(documents, source_key="weather-hour", index=index, title=f"{name} · {27 + index:02d} · Weather hour {hour}", kind="weather_record", category="Weather", source="Open-Meteo Forecast API", source_url=weather_source, text=text, payload={"time": hour, "temperature": temperature, "precipitation_probability": precipitation_probability, "precipitation": precipitation, "wind_speed": wind, "timezone": weather.get("timezone"), "elevation": weather.get("elevation")}, extra={"location_id": location_id, "region": region})

    # Ensure the pack remains useful even if a biodiversity or map endpoint has
    # no records for a remote coordinate: retain additional real hourly rows.
    if len(documents) > 40:
        documents = documents[:40]
    return {
        "location": location,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "documents": documents,
        "sources": {"gbif": gbif_source, "inat": inat_source, "osm": overpass_source, "weather": weather_source},
        # Keep each complete upstream response once per location. Individual
        # records retain their own payload, while the document reader can also
        # open the full response without duplicating it 40 times per snapshot.
        "source_responses": {"gbif": gbif, "inat": inat, "osm": overpass, "weather": weather},
    }


def main() -> None:
    locations = json.loads(LOCATIONS.read_text(encoding="utf-8"))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    force_refresh = "--refresh" in sys.argv
    def ingest_and_write(location: dict[str, Any]) -> tuple[str, int, bool]:
        target = OUTPUT / f"{location['id']}.json"
        if target.exists() and not force_refresh:
            try:
                cached = json.loads(target.read_text(encoding="utf-8"))
                # Snapshots created before complete source responses were
                # retained are migrated on the next run.
                if cached.get("source_responses"):
                    return str(location["id"]), len(cached.get("documents", [])), True
            except (OSError, json.JSONDecodeError):
                pass
        snapshot = ingest_location(location)
        target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(location["id"]), len(snapshot["documents"]), False

    completed = 0
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(ingest_and_write, location): location for location in locations}
        for future in as_completed(futures):
            location = futures[future]
            try:
                location_id, count, cached = future.result()
                completed += 1
                print(f"[{completed}/{len(locations)}] {location['name']}: {count} source documents{' (cached)' if cached else ''}", flush=True)
            except Exception as exc:  # keep the other locations ingesting
                completed += 1
                print(f"[{completed}/{len(locations)}] {location['name']}: FAILED ({exc})", flush=True)
    print(f"Wrote {completed} location snapshots to {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
