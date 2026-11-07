"""Immutable, bounded observation history shared by the live and playback workspace."""

import hashlib
import json
import math
import re
from datetime import timedelta

from .models import stamp


def layer(identifier, label, group, category=None, pattern=None, tag=None):
    return dict(id=identifier, label=label, group=group, category=category, pattern=pattern, tag=tag)


# Sublayers are overlapping views of observations, not independent intelligence feeds.
LAYERS = [
    layer("aircraft", "ADS-B aircraft", "Air & sea", "aviation"),
    layer("airborne", "Airborne aircraft", "Air & sea", "aviation", tag="airborne"),
    layer("grounded", "Aircraft on ground", "Air & sea", "aviation", tag="on-ground"),
    layer("rotorcraft", "Rotorcraft", "Air & sea", "aviation", tag="rotorcraft"),
    layer("vessels", "AIS vessels", "Air & sea", "maritime"),
    layer("cargo", "Cargo vessels", "Air & sea", "maritime", tag="cargo"),
    layer("tankers", "Tankers", "Air & sea", "maritime", tag="tanker"),
    layer("passenger", "Passenger vessels", "Air & sea", "maritime", tag="passenger"),
    layer("fishing", "Fishing vessels", "Air & sea", "maritime", tag="fishing"),
    layer("cctv", "Public traffic cameras", "Sensors", tag="cctv"),
    layer("radio", "Public radio receivers", "Sensors", tag="radio"),
    layer("ground-stations", "Satellite ground stations", "Sensors", tag="ground-station"),
    layer("gnss", "GNSS low-accuracy cells", "Sensors", tag="gnss-cell"),
    layer("military", "Military reporting", "Conflict", "military"),
    layer("drones", "Drone reports", "Conflict", "military", r"\b(drone|uav|shahed|fpv)"),
    layer("missiles", "Missile reports", "Conflict", "military", r"\b(missile|rocket)"),
    layer("airstrikes", "Airstrike reports", "Conflict", "military", r"\b(airstrike|air strike|bombing)"),
    layer("artillery", "Artillery reports", "Conflict", "military", r"\b(artillery|shelling|mortar)"),
    layer("naval", "Naval reporting", "Conflict", "military", r"\b(naval|warship|submarine)"),
    layer("exercises", "Military exercises", "Conflict", "military", r"\b(exercise|drill|readiness)"),
    layer("deployments", "Deployment reports", "Conflict", "military", r"\b(deploy|troops|reinforcement)"),
    layer("ceasefires", "Ceasefire reporting", "Conflict", "military", r"\b(ceasefire|truce)"),
    layer("evacuations", "Evacuation reports", "Conflict", "military", r"\b(evacuat|air.raid|siren)"),
    layer("diplomacy", "Geopolitical reporting", "World", "geopolitical"),
    layer("sanctions", "Sanctions reporting", "World", pattern=r"\b(sanction|ofac|embargo)"),
    layer("elections", "Election reporting", "World", "geopolitical", r"\b(election|ballot|voting)"),
    layer("protests", "Protest reporting", "World", "geopolitical", r"\b(protest|demonstration|unrest)"),
    layer("economy", "Economic reporting", "World", "economic"),
    layer("energy", "Energy reporting", "World", "economic", r"\b(oil|gas|energy|opec)"),
    layer(
        "humanitarian",
        "Humanitarian reporting",
        "Environment",
        "environment",
        r"\b(refugee|humanitarian|displac|relief)",
    ),
    layer("environment", "Environmental observations", "Environment", "environment"),
    layer("earthquakes", "Earthquakes", "Environment", "environment", r"\b(earthquake|seismic)"),
    layer("fires", "Thermal / fire observations", "Environment", "environment", r"\b(fire|thermal|firms)"),
    layer("floods", "Flood reporting", "Environment", "environment", r"\b(flood|inundation)"),
    layer("cyber", "Cyber reporting", "Cyber", "cyber"),
    layer("threats", "Threat reporting", "Cyber", "threat"),
    layer("infrastructure", "Cyber infrastructure", "Cyber", "infrastructure"),
    layer("malware", "Malware intelligence", "Cyber", pattern=r"\b(malware|ransomware|trojan|botnet)"),
    layer("c2", "C2 indicators", "Cyber", pattern=r"\b(c2|command.and.control|botnet_cc)\b"),
    layer(
        "vulnerabilities", "Vulnerability reporting", "Cyber", pattern=r"\b(cve-\d|vulnerabilit|exploited)"
    ),
    layer("scanning", "Scan observations", "Cyber", "infrastructure", r"\b(scan|dshield|honeypot)"),
    layer("shodan", "Shodan host observations", "Cyber", tag="shodan"),
    layer("discussion", "Public discussion", "World", "sentiment"),
]
LAYER_IDS = {row["id"] for row in LAYERS}
MATCHERS = {row["id"]: re.compile(row["pattern"], re.I) for row in LAYERS if row["pattern"]}


def memberships(item):
    tags = set(item.get("tags", []))
    aircraft = item.get("aircraft") or {}
    if aircraft.get("on_ground") is True:
        tags.add("on-ground")
    elif aircraft.get("on_ground") is False:
        tags.add("airborne")
    if item.get("aircraft_category") == 8:
        tags.add("rotorcraft")
    vessel_type = item.get("vessel_type") or 0
    for low, high, tag in [(70, 79, "cargo"), (80, 89, "tanker"), (60, 69, "passenger"), (30, 30, "fishing")]:
        if low <= vessel_type <= high:
            tags.add(tag)
    text = " ".join([item.get("title", ""), item.get("description", ""), *tags])
    return [
        row["id"]
        for row in LAYERS
        if (not row["category"] or row["category"] == item["category"])
        and (not row["tag"] or row["tag"] in tags)
        and (row["id"] not in MATCHERS or MATCHERS[row["id"]].search(text))
    ]


def retain(db, report, received_at=None):
    """Called within the collector's transaction; no foreign key to mutable event rows."""
    item = report.model_dump(mode="json", exclude={"raw"})
    observed = stamp(report.occurred_at or report.published_at)
    received = received_at or stamp()
    if observed > received:
        return  # Future-dated source assertions cannot become live telemetry.
    entity = report.external_id
    if report.aircraft:
        entity = report.aircraft.icao24
    elif report.category == "maritime":
        match = re.search(r"(?:^|:)(\d{9})(?=:|$)", report.external_id)
        entity = str(report.raw.get("mmsi") or (match[1] if match else report.external_id))
    sensor = report.raw.get("monitoring")
    if sensor:
        item["sensor"] = sensor  # Only connector-normalized, explicitly public metadata.
    item.update(observed_at=observed, entity_id=entity, layers=memberships(item))
    payload = json.dumps(item, sort_keys=True, separators=(",", ":"))
    key = hashlib.sha256(payload.encode()).hexdigest()
    db.execute(
        "INSERT OR IGNORE INTO monitoring_history VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            key,
            report.source_id,
            entity,
            observed,
            received,
            report.category,
            report.latitude,
            report.longitude,
            json.dumps(item["layers"]),
            payload,
        ),
    )


def save_directory(database, reports):
    """Directory entries are retained metadata, excluded from incident/event analytics."""
    for start in range(0, len(reports), 100):
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for report in reports[start : start + 100]:
                retain(db, report)
    return len(reports)


def frame(database, at, hours=24, selected=None, limit=2000):
    cutoff, start = stamp(at), stamp(at - timedelta(hours=hours))
    args = [start, cutoff, cutoff]
    where = ""
    if selected:
        where = (
            "WHERE EXISTS (SELECT 1 FROM json_each(layers) WHERE value IN ("
            + ",".join("?" * len(selected))
            + "))"
        )
        args.extend(sorted(selected))
    # Rank before filtering layers: an aircraft that landed must not reappear airborne.
    sql = f"""WITH ranked AS (
        SELECT *, ROW_NUMBER() OVER (
          PARTITION BY source_id,entity_id ORDER BY observed_at DESC,received_at DESC,rowid DESC
        ) AS rank FROM monitoring_history
        WHERE observed_at>=? AND observed_at<=? AND received_at<=?
      ) SELECT * FROM ranked {where + " AND" if where else "WHERE"} rank=1
      ORDER BY observed_at DESC,observation_id LIMIT ?"""
    with database.connect() as db:
        rows = db.execute(sql, [*args, limit + 1]).fetchall()
    items = []
    for row in rows[:limit]:
        item = json.loads(row["payload"])
        item.update(id=row["observation_id"], received_at=row["received_at"])
        # Sensor metadata has a long useful window; mobile fixes have short freshness.
        ttl = 600 if item["category"] in {"aviation", "maritime"} else 86400
        item["stale"] = row["observed_at"] < stamp(at - timedelta(seconds=ttl))
        items.append(item)
    return dict(
        at=cutoff,
        items=items,
        truncated=len(rows) > limit,
        limit=limit,
        basis="Latest retained observation per source and entity known at this UTC time; no interpolation",
    )


def gnss_cells(items, minimum=3):
    """Unique airborne transponders per 1 degree cell; unknown NACp is excluded."""
    cells = {}
    for item in items:
        sensor = item.get("sensor") or {}
        nacp = sensor.get("nac_p")
        lat, lon = item.get("latitude"), item.get("longitude")
        if (
            item.get("stale")
            or item["category"] != "aviation"
            or sensor.get("on_ground") is not False
            or type(nacp) is not int
            or not 1 <= nacp <= 11
            or lat is None
            or lon is None
        ):
            continue
        key = (min(179, math.floor(lon)), min(89, math.floor(lat)))
        # The same aircraft from two receivers counts once, using its newest observation.
        aircraft = (item.get("aircraft") or {}).get("icao24", item["entity_id"])
        previous = cells.setdefault(key, {}).get(aircraft)
        if previous is None or item["observed_at"] > previous["observed_at"]:
            cells[key][aircraft] = item
    features = []
    for (lon, lat), aircraft in cells.items():
        if len(aircraft) < minimum:
            continue
        low = sum(item["sensor"]["nac_p"] <= 4 for item in aircraft.values())
        if not low:
            continue
        features.append(
            dict(
                type="Feature",
                geometry=dict(
                    type="Polygon",
                    coordinates=[
                        [[lon, lat], [lon + 1, lat], [lon + 1, lat + 1], [lon, lat + 1], [lon, lat]]
                    ],
                ),
                properties=dict(
                    aircraft=len(aircraft),
                    low_accuracy=low,
                    fraction=low / len(aircraft),
                    basis="NACp 1-4 among NACp 1-11 airborne samples; possible interference, not confirmed jamming",
                ),
            )
        )
    return dict(type="FeatureCollection", features=features)
