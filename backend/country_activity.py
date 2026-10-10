"""Country comparison: complete event totals and bounded, deduplicated wording samples."""

import json

from .analytics import sentiment
from .geo import countries
from .relations import report_country_codes
from .social_analytics import social_sentiment

REPORT_LIMIT = 5000
INTELLIGENCE_CATEGORIES = {"geopolitical", "military", "maritime", "cyber", "economic", "environment"}


def country_activity(database, filters, kind="news", platform="all", geography="mentions"):
    # Selection highlights a country without destroying the comparison. Other
    # filters, including a requested viewport, still apply to the event totals.
    comparison = filters.model_copy(update={"country": None})
    where, values = database.where(comparison, "e")
    mention_where = (
        where
        + " AND e.category!='aviation' AND (r.sentiment_kind IS NOT NULL OR e.category IN ('geopolitical','military','maritime','cyber','economic'))"
    )
    places = {f["properties"]["code"]: f["properties"] for f in countries()["features"]}
    items = {}

    def item(code):
        if code not in places:
            return None
        return items.setdefault(
            code,
            {
                "country": code,
                "name": places[code]["name"],
                "mentions": 0,
                "mention_sources": set(),
                "records": 0,
                "intelligence_records": 0,
                "supported_records": 0,
                "categories": {},
                "score": None,
                "samples": 0,
            },
        )

    with database.connect() as db:
        totals = db.execute(
            f"""SELECT e.country_code,e.category,COUNT(*) AS count,
                SUM(CASE WHEN e.confidence IN ('Verified','Corroborated') THEN 1 ELSE 0 END) AS supported
                FROM events e WHERE {where} GROUP BY e.country_code,e.category""",
            values,
        ).fetchall()
        # Reports use the selected event time basis, just like the event list.
        # Multiple deliveries of one original URL count only once per country.
        rows = db.execute(
            f"""SELECT * FROM (SELECT r.*,ROW_NUMBER() OVER(
                PARTITION BY r.source_url ORDER BY r.ingested_at DESC,r.report_id) AS delivery_rank
                FROM reports r JOIN events e ON e.event_id=r.event_id WHERE {mention_where})
                WHERE delivery_rank=1 ORDER BY published_at DESC,report_id LIMIT ?""",
            [*values, REPORT_LIMIT],
        ).fetchall()
        available = db.execute(
            f"SELECT COUNT(DISTINCT r.source_url) FROM reports r JOIN events e ON e.event_id=r.event_id WHERE {mention_where}",
            values,
        ).fetchone()[0]

    for row in totals:
        entry = item(row["country_code"])
        if entry is None:
            continue
        entry["records"] += row["count"]
        if row["category"] in INTELLIGENCE_CATEGORIES:
            entry["categories"][row["category"]] = row["count"]
            entry["intelligence_records"] += row["count"]
            entry["supported_records"] += row["supported"]

    for row in rows:
        metadata = json.loads(row["metadata"])
        social = metadata.get("social") or {}
        codes = set(report_country_codes(row["metadata"], row["title"], row["description"]))
        codes.update(social.get("mentioned_countries", []))
        codes.update(social.get("context_countries", []))
        for code in codes:
            entry = item(code)
            if entry is not None:
                entry["mentions"] += 1
                entry["mention_sources"].add(row["source_id"])

    # Match the sentiment panel's dataset and geography, independently of the
    # physical overlays. Its publication dates and explicit limits are retained.
    wording_filters = comparison.model_copy(update={"categories": []})
    wording = (
        social_sentiment(database, wording_filters, kind, platform, geography)
        if kind == "public" or platform != "all"
        else sentiment(database, wording_filters, kind)
    )
    for region in wording["regions"]:
        entry = item(region["country"])
        if entry is not None:
            entry["score"] = region["score"]
            entry["samples"] = region["count"]
    for entry in items.values():
        entry["mention_sources"] = len(entry["mention_sources"])
        entry["layer_count"] = len(entry["categories"])
    return {
        "items": sorted(items.values(), key=lambda entry: (-entry["mentions"], entry["country"])),
        "selected_country": filters.country,
        "period": comparison.model_dump(mode="json"),
        "report_sample": len(rows),
        "report_available": available,
        "report_truncated": available > len(rows),
        "sentiment": {
            "kind": kind,
            "platform": platform,
            "geography": geography,
            "sample_count": wording["sample_count"],
            "available_count": wording["available_count"],
            "truncated": wording["truncated"],
        },
        "methodology": {
            "mentions": "Distinct original reporting/discussion URLs naming a country or using explicit thread country context; each URL counts once per country. Aviation telemetry and unscored environmental detections are excluded. Selected event filters apply. Country references do not establish incident locations.",
            "sentiment": "Mean wording score in the selected sentiment dataset, using publication time. Thin means fewer than 5 scored texts. This is not national opinion or sentiment toward the country.",
            "intelligence": "Rank by number of active intelligence layers, then verified/corroborated records, then record count. Aviation telemetry, sentiment and generated analysis are excluded. Totals cover all matching events assigned to the country, including regional context; layer breadth is not a threat score.",
        },
    }
