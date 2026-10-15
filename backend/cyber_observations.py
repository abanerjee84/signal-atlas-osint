"""Persist typed indicator evidence in the dashboard's existing transaction."""

import hashlib
import json
from datetime import timedelta

from .models import stamp, utcnow


def indicator_id(kind, value):
    return hashlib.sha256((kind + "\x00" + value).encode()).hexdigest()[:32]


def refresh_indicator_times(db, iid):
    times = db.execute(
        "SELECT MIN(COALESCE(o.first_seen,o.period_start,r.observed_at,r.published_at)),MAX(COALESCE(o.last_seen,o.first_seen,o.period_start,r.observed_at,r.published_at)) FROM indicator_evidence e JOIN external_records r USING(record_id) LEFT JOIN cyber_observations o USING(record_id) WHERE e.indicator_id=?",
        (iid,),
    ).fetchone()
    db.execute(
        "UPDATE cyber_indicators SET first_seen_at=?,last_seen_at=? WHERE indicator_id=?", (*times, iid)
    )


def index_observation(db, record_id, source_id, observation, confidence):
    data = observation.model_dump(mode="json")
    for field in ("first_seen", "last_seen", "period_start", "period_end", "received_at"):
        data[field] = stamp(getattr(observation, field)) if getattr(observation, field) else None
    iid = indicator_id(observation.indicator_type, observation.indicator_value)
    previous = db.execute(
        "SELECT indicator_id FROM cyber_observations WHERE record_id=?", (record_id,)
    ).fetchone()
    if previous and previous[0] != iid:
        db.execute(
            "DELETE FROM entity_source_mentions WHERE record_id=? AND entity_id=?", (record_id, previous[0])
        )
    first = data["first_seen"] or data["period_start"]
    last = data["last_seen"] or data["first_seen"] or data["period_start"]
    db.execute(
        "INSERT INTO cyber_indicators VALUES(?,?,?,?,?,?) ON CONFLICT(type,normalized_value) DO UPDATE SET first_seen_at=CASE WHEN first_seen_at IS NULL THEN excluded.first_seen_at WHEN excluded.first_seen_at IS NULL THEN first_seen_at ELSE MIN(first_seen_at,excluded.first_seen_at) END,last_seen_at=CASE WHEN last_seen_at IS NULL THEN excluded.last_seen_at WHEN excluded.last_seen_at IS NULL THEN last_seen_at ELSE MAX(last_seen_at,excluded.last_seen_at) END",
        (
            iid,
            observation.indicator_type,
            observation.indicator_value,
            observation.indicator_value,
            first,
            last,
        ),
    )
    db.execute(
        "DELETE FROM indicator_evidence WHERE record_id=? AND classification='provider_reported_indicator'",
        (record_id,),
    )
    db.execute(
        "INSERT INTO cyber_observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(record_id) DO UPDATE SET indicator_id=excluded.indicator_id,kind=excluded.kind,first_seen=excluded.first_seen,last_seen=excluded.last_seen,period_start=excluded.period_start,period_end=excluded.period_end,received_at=excluded.received_at,payload=excluded.payload",
        (
            record_id,
            iid,
            source_id,
            observation.source_family,
            observation.provider_record_id,
            observation.kind,
            first,
            data["last_seen"],
            data["period_start"],
            data["period_end"],
            data["received_at"],
            json.dumps(data),
        ),
    )
    db.execute(
        "INSERT OR REPLACE INTO indicator_evidence VALUES(?,?,?,?)",
        (iid, record_id, "provider_reported_indicator", str(confidence)),
    )
    db.execute(
        "INSERT OR IGNORE INTO entities VALUES(?,?,?,?,?,?)",
        (
            iid,
            "infrastructure",
            observation.indicator_value,
            observation.indicator_value.casefold(),
            "indicator-reference; no actor attribution",
            stamp(),
        ),
    )
    db.execute("INSERT OR IGNORE INTO entity_source_mentions VALUES(?,?)", (iid, record_id))
    refresh_indicator_times(db, iid)
    if previous and previous[0] != iid:
        refresh_indicator_times(db, previous[0])
    return iid


def save_ddos_series(database, records):
    with database.connect() as db:
        for row in records:
            db.execute(
                "DELETE FROM cyber_ddos_series WHERE source_id='cloudflare_radar' AND start_at=?",
                (row["start_at"],),
            )
            for protocol, value in row["protocols"].items():
                db.execute(
                    "INSERT INTO cyber_ddos_series VALUES(?,?,?,?,?,?,?) ON CONFLICT(source_id,start_at,protocol) DO UPDATE SET end_at=excluded.end_at,percentage=excluded.percentage,retrieved_at=excluded.retrieved_at",
                    (
                        "cloudflare_radar",
                        row["start_at"],
                        row["end_at"],
                        protocol,
                        value,
                        row["original_url"],
                        row["received_at"],
                    ),
                )
        db.execute("DELETE FROM cyber_ddos_series WHERE start_at<?", (stamp(utcnow() - timedelta(days=30)),))
    return len(records)


def prune_observations(database, days):
    cutoff = stamp(utcnow() - timedelta(days=days))
    with database.connect() as db:
        affected = db.execute(
            "SELECT DISTINCT indicator_id FROM cyber_observations WHERE COALESCE(period_end,last_seen,first_seen,received_at)<?",
            (cutoff,),
        ).fetchall()
        # Cascades remove observations and evidence; case snapshots remain immutable.
        db.execute(
            "DELETE FROM events WHERE event_id IN (SELECT r.event_id FROM cyber_observations o JOIN external_records r USING(record_id) WHERE COALESCE(o.period_end,o.last_seen,o.first_seen,o.received_at)<?)",
            (cutoff,),
        )
        for row in affected:
            refresh_indicator_times(db, row[0])
