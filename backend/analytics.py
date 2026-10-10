from collections import Counter
from datetime import timedelta

from .database import Database
from .models import Filters, stamp, utcnow
from .sentiment import tokens

METHODOLOGY = (
    "English headline lexicon v1; distinct original URLs, not full articles. Neutral includes no lexicon match. "
    "No negation, sarcasm, translation, stance or representative sampling correction. "
    "Topic matching filters the dataset, but the score describes headline wording, not attitude toward the topic. "
    "Public discourse, news coverage and official statements are separate datasets. These results are not national public opinion."
)


def sentiment(database: Database, filters: Filters, kind: str) -> dict:
    # Sentiment is a report dataset: use each source publication date and wording,
    # rather than the primary report's clustered-event timestamp or title.
    where, values = database.where(filters.model_copy(update={"start": None, "end": None, "q": ""}), "e")
    for instant, operator in ((filters.start, ">="), (filters.end, "<=")):
        if instant:
            where += f" AND r.published_at{operator}?"
            values.append(stamp(instant))
    if filters.q:
        query_text = filters.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where += " AND (r.title LIKE ? ESCAPE '\\' OR r.description LIKE ? ESCAPE '\\')"
        values.extend([f"%{query_text}%"] * 2)
    # One report per original URL prevents a GDELT/RSS copy from doubling the sample.
    query = f"""SELECT r.*,e.country_code,e.latitude,e.longitude FROM reports r JOIN events e ON e.event_id=r.event_id
         WHERE {where} AND r.sentiment_kind=? GROUP BY r.source_url ORDER BY r.published_at DESC LIMIT 5000"""
    with database.connect() as db:
        rows = [dict(row) for row in db.execute(query, [*values, kind])]
        available = db.execute(
            f"SELECT COUNT(DISTINCT r.source_url) FROM reports r JOIN events e ON e.event_id=r.event_id WHERE {where} AND r.sentiment_kind=?",
            [*values, kind],
        ).fetchone()[0]
    scored = [row for row in rows if row["sentiment_label"] is not None]
    distribution = Counter(row["sentiment_label"] for row in scored)
    trend, regions = {}, {}
    frequency = Counter()
    for row in scored:
        day = row["published_at"][:10]
        bucket = trend.setdefault(day, {"date": day, "count": 0, "sum": 0})
        bucket["count"] += 1
        bucket["sum"] += row["sentiment_score"]
        frequency.update(tokens(row["title"]))
        if row["country_code"]:
            region = regions.setdefault(
                row["country_code"],
                {
                    "country": row["country_code"],
                    "count": 0,
                    "sum": 0,
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                },
            )
            region["count"] += 1
            region["sum"] += row["sentiment_score"]
    terms = [term for term, count in frequency.most_common(12)]
    # Transparent keyword groupings, not inferred semantic narratives.
    groups = [
        {
            "term": term,
            "count": frequency[term],
            "report_ids": [row["report_id"] for row in scored if term in tokens(row["title"])][:20],
        }
        for term in terms
    ]
    return {
        "kind": kind,
        "topic": filters.q or "All matching headlines",
        "period": filters.model_dump(mode="json"),
        "period_basis": "source_publication",
        "sample_count": len(scored),
        "dataset_count": len(rows),
        "available_count": available,
        "truncated": available > len(rows),
        "excluded_language_count": len(rows) - len(scored),
        "methodology": METHODOLOGY,
        "distribution": {key: distribution[key] for key in ("positive", "negative", "neutral")},
        "sources": dict(Counter(row["source_id"] for row in rows)),
        "languages": dict(Counter(row["language"] for row in rows)),
        "trend": [
            {"date": item["date"], "count": item["count"], "score": item["sum"] / item["count"]}
            for item in sorted(trend.values(), key=lambda item: item["date"])
        ],
        "regions": [{**item, "score": item["sum"] / item["count"]} for item in regions.values()],
        "topic_frequency": groups,
        "supporting_report_ids": [row["report_id"] for row in scored[:100]],
    }


def timeline(database: Database, filters: Filters, interval: str = "hour") -> list[dict]:
    where, values = database.where(filters)
    column = {"event": "time_key", "published": "published_at", "ingested": "ingested_at"}[filters.time_basis]
    pattern = "%Y-%m-%dT%H:00:00Z" if interval == "hour" else "%Y-%m-%d"
    with database.connect() as db:
        rows = db.execute(
            f"SELECT strftime(?,{column}) AS time,category,COUNT(*) AS count FROM events WHERE {where} GROUP BY time,category ORDER BY time DESC LIMIT 3000",
            [pattern, *values],
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def regional_anomalies(database: Database, filters: Filters, cell_degrees: int = 10) -> list[dict]:
    """Compare each region's recent volume against its own recent baseline.

    A global category total hides the fact that one region can spike while the
    worldwide figure looks normal. Cells are coarse geographic blocks, never
    exact incident locations, and a small region total is never reported.
    """

    now = min(filters.end, utcnow()) if filters.end else utcnow()
    recent, previous = stamp(now - timedelta(hours=6)), stamp(now - timedelta(hours=12))
    since = stamp(now - timedelta(hours=72))
    # The selected end anchors the comparison; start must not truncate its 72h history.
    where, values = database.where(filters.model_copy(update={"start": None, "end": now}), "e")
    column = {"event": "time_key", "published": "published_at", "ingested": "ingested_at"}[filters.time_basis]
    with database.connect() as db:
        rows = db.execute(
            f"""SELECT CAST((longitude+180)/{cell_degrees} AS INTEGER) AS cx,
            CAST((latitude+90)/{cell_degrees} AS INTEGER) AS cy,
            SUM(CASE WHEN {column}>=? THEN 1 ELSE 0 END) AS recent,
            SUM(CASE WHEN {column}>=? AND {column}<? THEN 1 ELSE 0 END) AS previous,
            COUNT(*) AS baseline
            FROM events e WHERE {where} AND {column}>=? AND longitude IS NOT NULL AND latitude IS NOT NULL
            GROUP BY cx,cy""",
            [recent, previous, recent, *values, since],
        ).fetchall()
    results = []
    for row in rows:
        # Require enough history to compare against, and enough recent volume
        # that the ratio means something.
        if row["baseline"] < 20 or row["recent"] < 5 or row["previous"] < 2:
            continue
        if row["recent"] < 3 * row["previous"]:
            continue
        west, south = row["cx"] * cell_degrees - 180, row["cy"] * cell_degrees - 90
        results.append(
            {
                "longitude": min(west + cell_degrees / 2, 179.9),
                "latitude": min(south + cell_degrees / 2, 89.9),
                "cell_degrees": cell_degrees,
                "recent_count": row["recent"],
                "previous_count": row["previous"],
                "baseline_count": row["baseline"],
                "window_end": stamp(now),
                "time_basis": filters.time_basis,
                "basis": (
                    f"Region cell recorded {row['recent']} events in the last 6h against "
                    f"{row['previous']} in the prior 6h and {row['baseline']} in the trailing 72h. "
                    "Windows end at the selected end time and use the selected time basis; "
                    "the selected start does not truncate baseline history. "
                    "Collection and provider changes can produce this; it is not proof of a "
                    "world-event anomaly, and the cell is not an incident location."
                ),
            }
        )
    return sorted(results, key=lambda item: -item["recent_count"])[:20]


def cross_category(database: Database, filters: Filters) -> dict:
    """Regions where several categories cluster in the same window.

    This measures co-occurrence in the collection, not causal linkage: the same
    reporting burst can raise several categories at once.
    """

    since = stamp(utcnow() - timedelta(hours=24))
    where, values = database.where(filters.model_copy(update={"bbox": None}), "e")
    with database.connect() as db:
        rows = db.execute(
            f"""SELECT e.country_code,e.category,COUNT(*) AS count FROM events e
            WHERE {where} AND e.time_key>=? AND e.country_code IS NOT NULL
            GROUP BY e.country_code,e.category""",
            [*values, since],
        ).fetchall()
    per_country: dict[str, dict] = {}
    for row in rows:
        entry = per_country.setdefault(row["country_code"], {})
        entry[row["category"]] = row["count"]
    results = []
    for country, counts in per_country.items():
        if len(counts) < 2:
            continue
        # Only categories with real mass count toward the cross-category total.
        material = {key: value for key, value in counts.items() if value >= 3}
        if len(material) < 2:
            continue
        results.append(
            {
                "country": country,
                "categories": dict(sorted(material.items(), key=lambda item: -item[1])),
                "category_count": len(material),
                "total": sum(material.values()),
                "basis": (
                    f"{len(material)} categories each with 3+ records naming this country in the "
                    "last 24h. Co-occurrence in the collection is not evidence of a shared cause, "
                    "a coordinated event, or causal linkage between categories."
                ),
            }
        )
    return {
        "regions": sorted(results, key=lambda item: (-item["category_count"], -item["total"]))[:20],
        "window_hours": 24,
    }


def anomalies(database: Database) -> list[dict]:
    now = utcnow()
    with database.connect() as db:
        rows = db.execute(
            """SELECT category, SUM(CASE WHEN time_key>=? THEN 1 ELSE 0 END) recent,
            SUM(CASE WHEN time_key<? THEN 1 ELSE 0 END) previous FROM events WHERE time_key>=? GROUP BY category""",
            (
                stamp(now - timedelta(hours=6)),
                stamp(now - timedelta(hours=6)),
                stamp(now - timedelta(hours=12)),
            ),
        ).fetchall()
        results = []
        for row in rows:
            if row["recent"] >= 10 and row["previous"] >= 5 and row["recent"] >= 3 * row["previous"]:
                ids = [
                    item[0]
                    for item in db.execute(
                        "SELECT event_id FROM events WHERE category=? AND time_key>=? ORDER BY time_key DESC LIMIT 30",
                        (row["category"], stamp(now - timedelta(hours=6))),
                    )
                ]
                results.append(
                    {
                        "category": row["category"],
                        "recent_count": row["recent"],
                        "previous_count": row["previous"],
                        "event_ids": ids,
                        "basis": "Current 6h count >=10 and >=3 times prior 6h count, with prior count >=5. Collection changes can cause this; not proof of a world-event anomaly.",
                    }
                )
    return results
