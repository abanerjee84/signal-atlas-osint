"""Build the public/reference/ports.geojson reference layer from Natural Earth.

Reference geometry is published data, not a collected observation, so this script
records the exact upstream bytes it derived from. Nothing is typed in by hand:
every coordinate below came out of the downloaded file.
"""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.geo import country_at  # noqa: E402

SOURCE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_ports.geojson"
TARGET = Path("public/reference/ports.geojson")
LICENSE = Path("public/reference/REFERENCE_LICENSES.txt")

with urllib.request.urlopen(SOURCE, timeout=60) as response:
    raw = response.read()
digest = hashlib.sha256(raw).hexdigest()
payload = json.loads(raw)

features = []
for feature in payload.get("features", []):
    properties = feature.get("properties", {})
    name = properties.get("name")
    geometry = feature.get("geometry") or {}
    # Natural Earth 10m ports are already published as points, so there is
    # nothing to derive: take the coordinate the registry gives.
    if not name or geometry.get("type") != "Point":
        continue
    longitude, latitude = geometry["coordinates"][:2]
    if longitude is None or latitude is None:
        continue
    # Country comes from the repository's own boundary resolver, so the reference
    # layer and the event layers agree on where a country starts and ends.
    country = country_at(longitude, latitude) or ""
    features.append(
        {
            "type": "Feature",
            "properties": {
                "name": name,
                "country": country,
                "class": properties.get("featurecla"),
            },
            "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
        }
    )

features.sort(key=lambda feature: (feature["properties"]["country"], feature["properties"]["name"]))

collection = {
    "type": "FeatureCollection",
    "metadata": {
        "registry_version": "2026-10",
        "publisher": "Natural Earth",
        "license": "Public domain",
        "license_url": "https://www.naturalearthdata.com/about/terms-of-use/",
        "source": SOURCE,
        "source_sha256": digest,
        "retrieved": "2026-10-16",
        "precision": "point",
        "feature_count": len(features),
        "note": (
            "Port reference points. A port location is not its throughput, condition or "
            "openness, and commercial or military use of a berth is not inferred."
        ),
        "extraction": (
            "Port coordinates taken exactly as published. Country resolved with the "
            "repository's own boundary test and left empty where a coastal point falls "
            "outside land, rather than guessed."
        ),
    },
    "features": features,
}

TARGET.parent.mkdir(parents=True, exist_ok=True)
TARGET.write_text(json.dumps(collection, separators=(",", ":")) + "\n", encoding="utf-8")

LICENSE.write_text(
    "\n".join(
        [
            "Reference layer sources for public/reference/.",
            "",
            "ports.geojson",
            "  Natural Earth 10m ports, public domain.",
            f"  {SOURCE}",
            f"  Downloaded source SHA256: {digest}",
            "  Port coordinates are taken exactly as published; no coordinate was",
            "  created, moved or inferred. Country is resolved with the repository's",
            "  own boundary test, which leaves coastal points unresolved rather than",
            "  guessing. Port presence is not throughput, condition or openness.",
            "",
            "Terminator geometry is computed at runtime from the solar ephemeris and",
            "carries no third-party data.",
            "",
        ]
    ),
    encoding="utf-8",
)

unresolved = sum(1 for feature in features if not feature["properties"]["country"])
print(f"ports={len(features)} country_unresolved={unresolved} sha256={digest}")
