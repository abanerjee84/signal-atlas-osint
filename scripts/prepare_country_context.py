"""Extract reference points for countries omitted by the bundled 1:110m boundaries.

Pass a downloaded Natural Earth ne_10m_admin_0_countries.geojson as the argument.
This script reads local files only. Points support regional context, never borders.
"""

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    payload = args.source.read_bytes()
    original = json.loads((root / "public/countries.geojson").read_text(encoding="utf-8"))
    existing = {feature["properties"]["code"] for feature in original["features"]}
    points = {}
    for feature in json.loads(payload)["features"]:
        props = feature["properties"]
        code = props.get("ISO_A2_EH") or props.get("ISO_A2")
        if not isinstance(code, str) or len(code) != 2 or code == "-99" or code in existing:
            continue
        center = [props["LABEL_X"], props["LABEL_Y"]]
        points[code] = {
            "type": "Feature",
            "properties": {
                "code": code,
                "name": props["ADMIN"],
                "iso3": props.get("ISO_A3_EH"),
                "center": center,
                "location_basis": "Natural Earth country label point; regional context only, no boundary polygon",
            },
            "geometry": {"type": "Point", "coordinates": center},
        }
    target = root / "public/country-context.geojson"
    target.write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": [points[code] for code in sorted(points)]}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "public/COUNTRY_CONTEXT_LICENSE.txt").write_text(
        "Natural Earth 1:10m country label coordinates, public domain.\n"
        "https://www.naturalearthdata.com/about/terms-of-use/\n"
        "Source: https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_10m_admin_0_countries.geojson\n"
        f"Downloaded source SHA256: {hashlib.sha256(payload).hexdigest()}\n"
        "Extracted reference points only; no new or inferred boundaries.\n",
        encoding="utf-8",
    )
    print(f"Prepared {len(points)} regional reference points")


if __name__ == "__main__":
    main()
