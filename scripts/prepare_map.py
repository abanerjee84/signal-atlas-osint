"""Reduce a pinned Natural Earth country file to fields used by the application."""

import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
original = root / "public/natural-earth.original.json"
payload = original.read_bytes()
data = json.loads(payload)
features, excluded = [], []
for feature in data["features"]:
    properties = feature["properties"]
    code = properties.get("ISO_A2_EH") or properties.get("ISO_A2")
    if len(code) != 2 or code == "-99":
        excluded.append(properties["ADMIN"])
        continue
    feature["properties"] = {
        "name": properties["ADMIN"],
        "code": code,
        "iso3": properties.get("ISO_A3_EH", properties.get("ADM0_A3")),
        "center": [properties["LABEL_X"], properties["LABEL_Y"]],
    }
    features.append(feature)
(root / "public/countries.geojson").write_text(
    json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8"
)
(root / "public/MAP_LICENSE.txt").write_text(
    "Natural Earth 1:110m country boundaries, public domain.\n"
    "https://www.naturalearthdata.com/about/terms-of-use/\n"
    "Source: https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_countries.geojson\n"
    f"Downloaded source SHA256: {hashlib.sha256(payload).hexdigest()}\n"
    "Boundaries are illustrative and do not express a position on disputed sovereignty.\n"
    f"Features without ISO alpha-2 identifiers excluded: {', '.join(excluded) or 'none'}.\n",
    encoding="utf-8",
)
print(f"Prepared {len(features)} countries; excluded {excluded}")
