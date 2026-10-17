"""Build the OSM-derived reference layers in public/reference/.

Every coordinate below comes out of a recorded Overpass response. Nothing is
entered by hand and no position is inferred: areas are reduced to the centroid
Overpass itself returns for them.

OpenStreetMap data is © OpenStreetMap contributors, licensed ODbL 1.0. The
attribution and licence travel with each file and are shown in the layer's
explanation panel and on every feature's hover card.
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.geo import country_at  # noqa: E402

MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
HEADERS = {"User-Agent": "signal-atlas-reference-registry/1.0"}
ATTRIBUTION = "© OpenStreetMap contributors"
LICENSE_URL = "https://www.openstreetmap.org/copyright"
LICENSE_FILE = Path("public/reference/REFERENCE_LICENSES.txt")
# Raw responses are cached so a long crawl can be resumed instead of restarted.
CACHE = Path("data/reference_cache")


# Each layer names the exact Overpass query used, so a re-run can be checked
# against what is recorded in the output file.
LAYERS = {
    "military-bases": {
        "file": "military-bases.geojson",
        "query": "[out:json][timeout:300];"
        'nwr["military"~"^(naval_base|air_base|aerodrome|airfield|base)$"]["name"];'
        "out center;",
        "type_tag": "military",
        "basis": "OpenStreetMap military feature with a published name, reduced to a point.",
        "summary": "OSM named military features",
        "note": (
            "A mapped facility is not activity, attribution or evidence that anything "
            "happened there, and OSM coverage is uneven between countries. Disused, "
            "abandoned and training features are tagged as such and are not filtered out."
        ),
    },
    "nuclear-facilities": {
        "file": "nuclear-facilities.geojson",
        # Deliberately facility-level. Querying generator:source alone returns
        # individual reactor units, which would present one plant as several
        # unrelated facilities.
        "query": "[out:json][timeout:300];"
        "("
        'nwr["power"="plant"]["plant:source"="nuclear"]["name"];'
        'nwr["power"="plant"]["generator:source"="nuclear"]["name"];'
        ");"
        "out center;",
        "type_tag": "plant:source",
        "basis": "OpenStreetMap power plant tagged as nuclear, reduced to a point.",
        "summary": "OSM nuclear power plants",
        "note": (
            "This is a crowd-mapped facility list, not a regulator inventory, and it "
            "covers nuclear power plants only. It is not a radiation measurement and must "
            "not be read as evidence of a release, a test or an accident. Plants tagged "
            "disused are included and labelled. Individual reactor units are not listed."
        ),
    },
    "spaceports": {
        "file": "spaceports.geojson",
        "query": '[out:json][timeout:300];nwr["aeroway"="spaceport"]["name"];out center;',
        "type_tag": "aeroway",
        "basis": "OpenStreetMap spaceport feature, reduced to a point.",
        "summary": "OSM spaceports",
        "note": (
            "A launch site is not a launch. No schedule, vehicle, payload, operator or "
            "readiness is implied, and the registry is crowd-sourced."
        ),
    },
}


def fetch(query: str, cache_key: str | None = None, attempts: int = 6):
    """Overpass mirrors throttle hard, so each query is retried across mirrors.

    When a cache key is given the raw response is stored and reused, so a crawl
    that is interrupted can continue instead of starting over.
    """
    cache_file = CACHE / f"{cache_key}.json" if cache_key else None
    if cache_file and cache_file.exists():
        return cache_file.read_bytes(), "cache"
    last = None
    for attempt in range(attempts):
        url = MIRRORS[attempt % len(MIRRORS)]
        try:
            response = httpx.post(url, data={"data": query}, headers=HEADERS, timeout=180)
            if response.status_code == 200:
                if cache_file:
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    cache_file.write_bytes(response.content)
                return response.content, url
            last = f"HTTP {response.status_code}"
        except Exception as error:  # network, TLS or mirror outage
            last = type(error).__name__
        time.sleep(5)
    raise RuntimeError(f"Overpass unavailable after {attempts} attempts ({last})")


def gather(spec: dict, cache_key: str):
    """Fetch the layer's single query.

    There is deliberately no partial path. A crawl that failed on some regions
    would silently produce a registry that looks complete and is not, which is
    worse than not shipping the layer at all.
    """
    return [fetch(spec["query"], cache_key)[0]]


def coordinates(element: dict):
    # Nodes carry lat/lon directly; ways and relations carry the centroid that
    # Overpass computed for them under `out center`.
    if element.get("type") == "node" and element.get("lat") is not None:
        return element["lat"], element["lon"]
    center = element.get("center") or {}
    if center.get("lat") is not None:
        return center["lat"], center["lon"]
    return None, None


def best_name(tags: dict):
    for key in ("name:en", "name", "official_name", "int_name"):
        value = (tags.get(key) or "").strip()
        if value:
            return value
    return ""


def build(name: str, spec: dict) -> dict:
    responses = gather(spec, name)
    if not responses:
        raise RuntimeError(f"{name}: no Overpass response could be retrieved")
    raw = b"".join(responses)
    digest = hashlib.sha256(raw).hexdigest()

    # Band responses overlap on shared boundaries, so features are keyed by the
    # OSM identity rather than appended blindly.
    features = []
    seen = set()
    placed = set()
    for response in responses:
        payload = json.loads(response)
        for element in payload.get("elements", []):
            tags = element.get("tags") or {}
            label = best_name(tags)
            if not label:
                # An unnamed feature would be a point with nothing to say.
                continue
            latitude, longitude = coordinates(element)
            if latitude is None or longitude is None:
                continue
            identity = (element.get("type"), element.get("id"))
            # One facility is often mapped as both a node and an area, so the OSM
            # identity alone is not enough to keep it from appearing twice.
            place_key = (label.casefold(), round(longitude, 3), round(latitude, 3))
            if identity in seen or place_key in placed:
                continue
            seen.add(identity)
            placed.add(place_key)
            properties = {
                "name": label,
                "facility_type": tags.get(spec["type_tag"], ""),
                "country": country_at(longitude, latitude) or "",
                "osm_id": f"{element.get('type')}/{element.get('id')}",
                "attribution": ATTRIBUTION,
            }
            if tags.get("disused") in {"yes", "abandoned", "ruins"}:
                properties["status"] = "Disused"
            if element.get("type") != "node":
                properties["geometry_basis"] = "area centroid as published by OpenStreetMap"
            features.append(
                {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                }
            )

    features.sort(key=lambda feature: (feature["properties"]["country"], feature["properties"]["name"]))

    collection = {
        "type": "FeatureCollection",
        "metadata": {
            "registry_version": "2026-10",
            "publisher": "OpenStreetMap contributors",
            "license": "ODbL 1.0",
            "license_url": LICENSE_URL,
            "attribution": ATTRIBUTION,
            "source": "Overpass API",
            "source_url": MIRRORS[0],
            "source_query": spec["query"],
            "source_sha256": digest,
            "source_responses": len(responses),
            "retrieved": "2026-10-17",
            "precision": "point",
            "feature_count": len(features),
            "basis": spec["basis"],
            "note": spec["note"],
            "extraction": (
                "Coordinates taken from the Overpass response; nodes as published and "
                "areas as the centroid OpenStreetMap publishes for them. No coordinate "
                "created or moved."
            ),
        },
        "features": features,
    }

    target = Path("public/reference") / spec["file"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(collection, separators=(",", ":")) + "\n", encoding="utf-8")

    unresolved = sum(1 for feature in features if not feature["properties"]["country"])
    return {
        "name": name,
        "file": str(target),
        "count": len(features),
        "country_unresolved": unresolved,
        "sha256": digest,
        "query": spec["query"],
    }


def licence_text(results: list[dict]) -> str:
    lines = [
        "Reference layer sources for public/reference/.",
        "",
        "ports.geojson",
        "  Natural Earth 10m ports, public domain.",
        "  https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_ports.geojson",
        "  Downloaded source SHA256: c5a5028f5187a5e1b9fe7f0fab99804a8be7482099a2365d404fb7e9dd6b5457",
        "  Port coordinates are taken exactly as published; no coordinate was",
        "  created, moved or inferred. Country is resolved with the repository's",
        "  own boundary test, which leaves coastal points unresolved rather than",
        "  guessing. Port presence is not throughput, condition or openness.",
        "",
        "OpenStreetMap-derived layers (ODbL 1.0, share-alike):",
    ]
    for result in results:
        lines += [
            f"  {result['file']} — {result['count']} features",
            f"    {ATTRIBUTION}, {LICENSE_URL}",
            f"    Downloaded response SHA256: {result['sha256']}",
            f"    Query: {result['query']}",
        ]
    lines += [
        "",
        "Terms: ODbL 1.0 requires attribution and share-alike for derived databases.",
        "If any of these layers is redistributed, that obligation applies to the",
        "distributed dataset. Re-check before offering this data commercially.",
        "",
        "Terminator geometry is computed at runtime from the solar ephemeris and",
        "carries no third-party data.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    results = []
    for name, spec in LAYERS.items():
        result = build(name, spec)
        results.append(result)
        print(
            f"{name}: {result['count']} features, "
            f"country unresolved {result['country_unresolved']}, "
            f"sha256 {result['sha256'][:16]}…"
        )
        time.sleep(5)
    LICENSE_FILE.write_text(licence_text(results), encoding="utf-8")
    print(f"licence file updated: {LICENSE_FILE}")
