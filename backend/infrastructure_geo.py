"""Cached country estimates for public IP infrastructure; never actor locations."""

import asyncio
import json
import uuid
from datetime import timedelta
from urllib.parse import quote

from .connectors.base import ProviderError, SafeHTTP
from .cyber_observations import indicator_id
from .geo import countries
from .indicators import public_ip
from .models import InfrastructureLocation, stamp, utcnow

PROVIDER = "ipwhois_geo"
BASIS = "IPwho.is infrastructure country estimate, displayed at an illustrative country centre; not actor nationality, a victim location or a precise host position"


def places():
    return {feature["properties"]["code"]: feature["properties"] for feature in countries()["features"]}


def apply_cached_location(db, report):
    observation = report.cyber_observation
    if not observation or observation.indicator_type != "ip":
        return
    iid = indicator_id("ip", observation.indicator_value)
    cached = db.execute(
        "SELECT payload FROM advanced_provider_cache WHERE cache_key=? AND expires_at>?",
        ("infra_geo:" + iid, stamp()),
    ).fetchone()
    if not cached:
        return
    payload = json.loads(cached[0])
    if not payload.get("country_code"):
        return
    location = InfrastructureLocation.model_validate(payload)
    place = places().get(location.country_code)
    if place:
        report.longitude, report.latitude = place["center"]
        report.country_code, report.location_precision = location.country_code, "regional"
        report.location_basis, report.infrastructure_geo = location.basis, location


def cache_result(database, iid, payload, expires):
    with database.connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO advanced_provider_cache VALUES(?,?,?,?,?)",
            ("infra_geo:" + iid, PROVIDER, json.dumps(payload), stamp(), expires),
        )
        if not payload.get("country_code"):
            return
        place = places()[payload["country_code"]]
        longitude, latitude = place["center"]
        for row in db.execute(
            "SELECT r.report_id,r.event_id,r.metadata FROM cyber_observations o JOIN reports r ON r.report_id=o.record_id WHERE o.indicator_id=?",
            (iid,),
        ).fetchall():
            metadata = json.loads(row["metadata"])
            metadata.update(
                {
                    "infrastructure_geo": payload,
                    "latitude": latitude,
                    "longitude": longitude,
                    "country_code": payload["country_code"],
                    "location_precision": "regional",
                    "location_basis": BASIS,
                }
            )
            db.execute(
                "UPDATE reports SET metadata=?,updated_at=? WHERE report_id=?",
                (json.dumps(metadata), stamp(), row["report_id"]),
            )
            db.execute(
                "UPDATE events SET latitude=?,longitude=?,country_code=?,location_precision='regional',location_basis=?,updated_at=? WHERE event_id=? AND category='infrastructure'",
                (latitude, longitude, payload["country_code"], BASIS, stamp(), row["event_id"]),
            )


def reserve_request(database, budget):
    day = utcnow().date()
    key = "infra_geo:budget:" + day.isoformat()
    with database.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT payload FROM advanced_provider_cache WHERE cache_key=?", (key,)).fetchone()
        count = json.loads(row[0])["requests"] if row else 0
        if count >= budget:
            return False
        db.execute(
            "INSERT OR REPLACE INTO advanced_provider_cache VALUES(?,?,?,?,?)",
            (
                key,
                PROVIDER,
                json.dumps({"requests": count + 1}),
                stamp(),
                (day + timedelta(days=1)).isoformat() + "T00:00:00+00:00",
            ),
        )
    return True


def cooldown(database, error, seconds):
    with database.connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO advanced_provider_cache VALUES(?,?,?,?,?)",
            (
                "infra_geo:cooldown",
                PROVIDER,
                json.dumps({"error": error}),
                stamp(),
                stamp(utcnow() + timedelta(seconds=seconds)),
            ),
        )


async def enrich_locations(database, settings, client, *, limit=10, interval=1.1):
    """Bound network work independently of feed collection. No requests to observed hosts."""
    if not settings.infrastructure_geo_enabled:
        return {"state": "disabled", "looked_up": 0}
    owner = uuid.uuid4().hex
    if not await asyncio.to_thread(database.lock, "infrastructure:geolocation", owner, 600):
        return {"state": "already_running", "looked_up": 0}
    looked_up, located = 0, 0
    try:
        with database.connect() as db:
            paused = db.execute(
                "SELECT 1 FROM advanced_provider_cache WHERE cache_key='infra_geo:cooldown' AND expires_at>?",
                (stamp(),),
            ).fetchone()
            if paused:
                return {"state": "provider_backoff", "looked_up": 0}
            rows = db.execute(
                "SELECT DISTINCT i.indicator_id,i.normalized_value FROM cyber_indicators i JOIN cyber_observations o USING(indicator_id) LEFT JOIN advanced_provider_cache c ON c.cache_key='infra_geo:'||i.indicator_id AND c.expires_at>? WHERE i.type='ip' AND c.cache_key IS NULL ORDER BY o.received_at DESC LIMIT ?",
                (stamp(), max(1, min(limit, 50))),
            ).fetchall()
        http = SafeHTTP(settings, client)
        async with asyncio.timeout(480):
            for row in rows:
                address = public_ip(row["normalized_value"])
                if not await asyncio.to_thread(
                    reserve_request, database, settings.infrastructure_geo_daily_budget
                ):
                    return {"state": "daily_budget", "looked_up": looked_up, "located": located}
                if looked_up:
                    await asyncio.sleep(interval)
                looked_up += 1
                url = "https://ipwho.is/" + quote(address, safe="")
                try:
                    result = await http.json(
                        "GET",
                        url,
                        attempts=1,
                        timeout=8,
                        max_bytes=65536,
                        params={"fields": "ip,success,country_code"},
                    )
                    if not isinstance(result, dict) or result.get("success") is not True:
                        raise ValueError("IP country provider has no supported estimate")
                    if (
                        public_ip(result.get("ip", "")) != address
                        or result.get("country_code") not in places()
                    ):
                        raise ValueError("IP country response failed validation")
                    now = utcnow()
                    payload = InfrastructureLocation(
                        country_code=result["country_code"],
                        source_url=url,
                        retrieved_at=now,
                        expires_at=now + timedelta(days=1),
                        basis=BASIS,
                    ).model_dump(mode="json")
                    await asyncio.to_thread(
                        cache_result, database, row["indicator_id"], payload, stamp(now + timedelta(days=1))
                    )
                    located += 1
                except ProviderError as error:
                    await asyncio.to_thread(cooldown, database, str(error), max(300, error.retry_after))
                    return {
                        "state": "provider_backoff",
                        "looked_up": looked_up,
                        "located": located,
                        "error": str(error),
                    }
                except (ValueError, TypeError, KeyError):
                    await asyncio.to_thread(
                        cache_result,
                        database,
                        row["indicator_id"],
                        {"state": "unknown_country"},
                        stamp(utcnow() + timedelta(hours=1)),
                    )
        return {"state": "ok", "looked_up": looked_up, "located": located}
    finally:
        await asyncio.to_thread(database.unlock, "infrastructure:geolocation", owner)


def geolocation_status(database):
    with database.connect() as db:
        row = db.execute(
            "SELECT payload,expires_at FROM advanced_provider_cache WHERE cache_key='infra_geo:cooldown' AND expires_at>?",
            (stamp(),),
        ).fetchone()
    return (
        {"state": "provider_backoff", "retry_at": row["expires_at"], **json.loads(row["payload"])}
        if row
        else {"state": "ready"}
    )
