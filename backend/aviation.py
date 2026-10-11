"""Bounded current aircraft positions, independent of paginated event history."""

import hashlib
import json
from datetime import timedelta

from .geo import country_at
from .models import stamp, utcnow


def save_snapshot(database, reports):
    now = stamp()
    items = []
    for report in reports:
        data = report.model_dump(mode="json", exclude={"raw"})
        data.update(
            event_id=hashlib.sha256(("live:opensky:" + report.aircraft.icao24).encode()).hexdigest()[:32],
            time_key=stamp(report.occurred_at),
            ingested_at=now,
            updated_at=now,
            country_code=report.country_code or country_at(report.longitude, report.latitude),
            live=True,
            report_count=1,
            reports=[
                {
                    "source_id": report.source_id,
                    "source_url": report.source_url,
                    "title": report.title,
                    "published_at": stamp(report.published_at),
                }
            ],
        )
        items.append(data)
    with database.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT history_at FROM aircraft_snapshot WHERE id=1").fetchone()
        history_at = previous[0] if previous else None
        # Preserve the prior history cadence without storing hundreds of rows every two minutes.
        retain = bool(reports) and (not history_at or history_at < stamp(utcnow() - timedelta(minutes=30)))
        if retain:
            for report in reports:
                database.ingest(report, db)
            history_at = now
        db.execute(
            "INSERT INTO aircraft_snapshot VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET collected_at=excluded.collected_at,history_at=excluded.history_at,payload=excluded.payload",
            (now, history_at, json.dumps(items)),
        )
    return len(items)


def current_aircraft(database, filters):
    with database.connect() as db:
        row = db.execute("SELECT collected_at,payload FROM aircraft_snapshot WHERE id=1").fetchone()
    items = json.loads(row[1]) if row else []
    visible = []
    cutoff = stamp(utcnow() - timedelta(minutes=10))
    for item in items:
        if item["time_key"] < cutoff or (filters.aircraft_categories and item["aircraft_category"] not in filters.aircraft_categories):
            continue
        if filters.country and item["country_code"] != filters.country:
            continue
        if filters.q and filters.q.casefold() not in (item["title"] + " " + item["description"]).casefold():
            continue
        column = {"event": "time_key", "published": "published_at", "ingested": "ingested_at"}[
            filters.time_basis
        ]
        if (
            filters.start
            and item[column] < stamp(filters.start)
            or filters.end
            and item[column] > stamp(filters.end)
        ):
            continue
        if filters.bbox:
            w, s, e, n = filters.bbox
            lon, lat = item["longitude"], item["latitude"]
            if not s <= lat <= n or not (w <= lon <= e if w <= e else lon >= w or lon <= e):
                continue
        visible.append(item)
    return {
        "items": visible,
        "collected_at": row[0] if row else None,
        "available": bool(row),
        "stale": not row or row[0] < stamp(utcnow() - timedelta(minutes=4)),
        "position_basis": "Reported ADS-B positions; brief transitions between observations; no extrapolation. Departure and destination airports unavailable.",
    }
