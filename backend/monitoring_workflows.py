"""Spatial watches, immutable alert evidence, entity history and asset exposure."""

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import stamp, utcnow
from .monitoring import LAYER_IDS, frame
from .monitoring_geo import geometry, geometry_distance, near, possibly_near


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Watch(Input):
    name: str = Field(min_length=3, max_length=150)
    geometry: dict | None = None
    radius_km: float = Field(0, ge=0, le=1000, allow_inf_nan=False)
    entity_id: str = Field("", max_length=512)
    source_id: str = Field("", max_length=100)
    layers: list[str] = Field(default_factory=list, max_length=80)
    mode: Literal["enter", "new_match"] = "enter"
    cooldown_seconds: int = Field(600, ge=60, le=86400)
    max_age_seconds: int = Field(3600, ge=60, le=604800)
    include_existing: bool = False

    @field_validator("geometry")
    @classmethod
    def valid_shape(cls, value):
        return geometry(value, max_vertices=500)

    @model_validator(mode="after")
    def selector(self):
        if not self.geometry and not self.entity_id:
            raise ValueError("Choose an area/route or an entity")
        if set(self.layers) - LAYER_IDS:
            raise ValueError("Unknown watch layer")
        if (
            self.geometry
            and self.geometry["type"] in {"Point", "LineString", "MultiLineString", "MultiPoint"}
            and self.radius_km <= 0
        ):
            raise ValueError("Point and route watches require a positive radius")
        return self


class AssetImport(Input):
    source_id: str = Field(pattern="^[a-z][a-z0-9_-]{1,70}$")
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["power-plant", "data-center", "cable", "supplier"]
    version: str = Field(min_length=1, max_length=100)
    license: str = Field(min_length=3, max_length=500)
    source_url: str = Field(max_length=2048)
    features: list[dict] = Field(max_length=500)


def create_watch(database, body):
    identifier = uuid.uuid4().hex
    with database.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT COUNT(*) FROM monitoring_rules").fetchone()[0] >= 100:
            raise ValueError("This deployment permits at most 100 spatial watches")
        cursor = (
            0
            if body.include_existing
            else db.execute("SELECT COALESCE(MAX(sequence),0) FROM monitoring_receipts").fetchone()[0]
        )
        db.execute(
            "INSERT INTO monitoring_rules VALUES(?,?,?,?,1,?)",
            (identifier, body.name, body.model_dump_json(), stamp(), cursor),
        )
    return identifier


def matches(body, item):
    if body.source_id and body.source_id != item["source_id"]:
        return False
    if body.entity_id and body.entity_id != item["entity_id"]:
        return False
    if body.layers and not set(body.layers).intersection(item["layers"]):
        return False
    if not body.geometry:
        return True
    sensor = item.get("sensor") or {}
    shape = sensor.get("geometry")
    if shape:
        return possibly_near(body.geometry, shape, body.radius_km) and (
            geometry_distance(body.geometry, shape) <= body.radius_km
        )
    if item.get("longitude") is None:
        return False
    return near([item["longitude"], item["latitude"]], body.geometry, body.radius_km)


def evaluate_watches(database):
    """Consume bounded pages in receipt order. Each alert retains its own immutable evidence."""
    now = utcnow()
    total = 0
    with database.connect() as db:
        rules = db.execute("SELECT * FROM monitoring_rules WHERE enabled=1 ORDER BY id LIMIT 100").fetchall()
    for rule in rules:
        body = Watch.model_validate_json(rule["config"])
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Re-read the cursor under the write lock so two tick callers cannot replay an entry transition.
            current = db.execute(
                "SELECT cursor FROM monitoring_rules WHERE id=? AND enabled=1", (rule["id"],)
            ).fetchone()
            if not current:
                continue
            rows = db.execute(
                "SELECT r.sequence,h.* FROM monitoring_receipts r "
                "JOIN monitoring_history h ON h.observation_id=r.observation_id "
                "WHERE r.sequence>? ORDER BY r.sequence LIMIT 2000",
                (current[0],),
            ).fetchall()
            for row in rows:
                item = json.loads(row["payload"])
                sensor = item.get("sensor") or {}
                if body.geometry and item["location_precision"] == "regional" and not sensor.get("geometry"):
                    continue
                if (
                    sensor.get("reference")
                    or "cctv" in item["layers"]
                    or row["observed_at"] < stamp(now - timedelta(seconds=body.max_age_seconds))
                    or row["observed_at"] > stamp(now)
                ):
                    continue
                if sensor.get("expires_at") and sensor["expires_at"] <= stamp(now):
                    continue
                ttl = sensor.get(
                    "freshness_seconds",
                    600 if item["category"] in {"aviation", "maritime"} else body.max_age_seconds,
                )
                if row["observed_at"] < stamp(now - timedelta(seconds=ttl)):
                    continue
                # Other sources/entities do not alter the selected entity's state.
                if (
                    body.source_id
                    and body.source_id != row["source_id"]
                    or body.entity_id
                    and body.entity_id != row["entity_id"]
                ):
                    continue
                state = db.execute(
                    "SELECT * FROM monitoring_rule_states WHERE rule_id=? AND source_id=? AND entity_id=?",
                    (rule["id"], row["source_id"], row["entity_id"]),
                ).fetchone()
                if state and state["observed_at"] > row["observed_at"]:
                    continue  # Late delivery of an older position cannot move an entity backwards.
                inside = matches(body, item)
                eligible = inside and (body.mode == "new_match" or not state or not state["inside"])
                cooled = (
                    not state
                    or not state["last_alert"]
                    or state["last_alert"] <= stamp(now - timedelta(seconds=body.cooldown_seconds))
                )
                last_alert = state["last_alert"] if state else None
                if eligible and cooled:
                    key = hashlib.sha256(
                        f"{rule['id']}:{row['observation_id']}:{body.mode}".encode()
                    ).hexdigest()
                    snapshot = {
                        "rule": body.model_dump(),
                        "observation": {
                            **item,
                            "id": row["observation_id"],
                            "received_at": row["received_at"],
                        },
                        "basis": "Observed source/entity matched the saved spatial rule; no causation or intent inferred",
                    }
                    inserted = db.execute(
                        "INSERT OR IGNORE INTO monitoring_alerts VALUES(?,?,?,?,?,?,NULL)",
                        (key, rule["id"], row["observation_id"], body.mode, stamp(now), json.dumps(snapshot)),
                    ).rowcount
                    total += inserted
                    if inserted:
                        last_alert = stamp(now)
                db.execute(
                    "INSERT INTO monitoring_rule_states VALUES(?,?,?,?,?,?) ON CONFLICT(rule_id,source_id,entity_id) DO UPDATE SET inside=excluded.inside,last_alert=excluded.last_alert,observed_at=excluded.observed_at",
                    (
                        rule["id"],
                        row["source_id"],
                        row["entity_id"],
                        int(inside),
                        last_alert,
                        row["observed_at"],
                    ),
                )
            if rows:
                db.execute(
                    "UPDATE monitoring_rules SET cursor=? WHERE id=?", (rows[-1]["sequence"], rule["id"])
                )
    return {"alerts_created": total, "evaluated_at": stamp(now)}


def assets(database, kind="", limit=2000):
    sql = """WITH ranked AS (SELECT *, ROW_NUMBER() OVER(PARTITION BY source_id,entity_id ORDER BY received_at DESC,rowid DESC) AS rank FROM monitoring_assets)
      SELECT * FROM ranked WHERE rank=1"""
    args = []
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    sql += " ORDER BY received_at DESC,id LIMIT ?"
    args.append(limit + 1)
    with database.connect() as db:
        rows = db.execute(sql, args).fetchall()
    return {
        "items": [
            {
                **dict(r),
                "payload": json.loads(r["payload"]),
                "geometry": json.loads(r["geometry"]) if r["geometry"] else None,
            }
            for r in rows[:limit]
        ],
        "truncated": len(rows) > limit,
    }


def exposure(database, kind="supplier", radius_km=50, hours=24):
    references = assets(database, kind, 100)
    observations = frame(database, utcnow(), hours, limit=1000)
    output = []
    for asset in references["items"]:
        shape = asset["geometry"]
        if not shape:
            continue
        evidence = []
        for item in observations["items"]:
            if item["stale"] or item["expired"] or (item.get("sensor") or {}).get("reference"):
                continue
            if item["category"] not in {"environment", "military", "geopolitical"}:
                continue
            hazard = (item.get("sensor") or {}).get("geometry")
            if hazard:
                if not possibly_near(shape, hazard, radius_km):
                    continue
                separation = geometry_distance(shape, hazard)
            elif item.get("longitude") is not None:
                if item["location_precision"] == "regional":
                    continue
                separation = geometry_distance(
                    shape, {"type": "Point", "coordinates": [item["longitude"], item["latitude"]]}
                )
            else:
                continue
            if separation <= radius_km:
                evidence.append(
                    {
                        "observation_id": item["id"],
                        "title": item["title"],
                        "source_url": item["source_url"],
                        "distance_km": round(separation, 3),
                        "observed_at": item["observed_at"],
                        "precision": item["location_precision"],
                    }
                )
        if evidence:
            output.append({"asset": asset, "nearby_observations": evidence[:50]})
    return {
        "items": output,
        "radius_km": radius_km,
        "truncated": references["truncated"] or observations["truncated"],
        "basis": "Geographic proximity within the selected radius; not a damage, outage, dependency or probability estimate",
    }


def entity_history(database, source_id, entity_id, start, end, limit=1000):
    with database.connect() as db:
        rows = db.execute(
            "SELECT * FROM monitoring_history WHERE source_id=? AND entity_id=? AND observed_at>=? AND observed_at<=? AND received_at<=? ORDER BY observed_at,received_at,rowid LIMIT ?",
            (source_id, entity_id, stamp(start), stamp(end), stamp(end), limit + 1),
        ).fetchall()
    items = [
        {**json.loads(r["payload"]), "id": r["observation_id"], "received_at": r["received_at"]}
        for r in rows[:limit]
    ]
    # Never join lines across the dateline or long gaps in receipt coverage.
    parts = []
    line = []
    prior = None
    for item in items:
        if item.get("longitude") is None:
            continue
        p = [item["longitude"], item["latitude"]]
        broken = prior and (
            abs(prior[0] - p[0]) > 180
            or item["observed_at"] > stamp(datetime.fromisoformat(prior[2]) + timedelta(minutes=30))
        )
        if broken:
            if len(line) > 1:
                parts.append(line)
            line = []
        line.append(p)
        prior = [*p, item["observed_at"]]
    if len(line) > 1:
        parts.append(line)
    return {
        "items": items,
        "truncated": len(rows) > limit,
        "trail": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"basis": "Retained observations; gaps not interpolated"},
                    "geometry": {"type": "LineString", "coordinates": part},
                }
                for part in parts
            ],
        },
    }
