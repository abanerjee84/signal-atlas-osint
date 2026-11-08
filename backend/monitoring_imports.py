"""Explicit application export contracts, not assumed private provider APIs."""

import csv
import io
import json


def csv_records(text, kind, limit=200):
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError("CSV needs unique named columns")
    records = []
    for row in reader:
        if len(records) >= limit:
            raise ValueError("Export exceeds the record budget; split it into smaller batches")
        if None in row:
            raise ValueError("CSV row has more fields than its header")
        if kind == "tinygs":
            record = {k: v for k, v in row.items() if v != ""}
            if row.get("latitude") and row.get("longitude"):
                record["station"] = {
                    "name": row.get("station_name"),
                    "latitude": float(row["latitude"]),
                    "longitude": float(row["longitude"]),
                }
            if row.get("norad_id"):
                record["noradId"] = int(row["norad_id"])
            records.append(record)
            continue
        shape = json.loads(row["geometry"]) if row.get("geometry") else None
        if shape is None and (row.get("latitude") or row.get("longitude")):
            shape = {"type": "Point", "coordinates": [float(row["longitude"]), float(row["latitude"])]}
        props = dict(row)
        if "value" in props and props["value"] == "":
            props["value"] = None
        if str(props.get("allow_download", "")).lower() in {"false", "0"}:
            props["allow_download"] = False
        records.append({"id": row.get("id") or row.get("sample_id"), "geometry": shape, "properties": props})
    if not records:
        raise ValueError("Export has no records")
    return records
