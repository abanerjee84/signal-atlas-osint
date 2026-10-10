"""Bounded social wording, coarse discussion geography and explicit feed relations."""

import json
from collections import Counter
from datetime import timedelta

from .geo import countries
from .models import stamp, utcnow
from .relations import country_network
from .sentiment import tokens

METHOD = "English VADER 3.3.2 compound scores on post/comment wording; positive >=0.05, negative <=-0.05. Language detection excludes uncertain or short text. Negation/emphasis are handled heuristically; sarcasm, stance and sampling bias remain unresolved. Thread-country context is distinct from an author's origin. These selected public feeds are not representative national public opinion."


def social_sentiment(database, filters, kind="public", platform="all", geography="mentions"):
    places = {f["properties"]["code"]: f["properties"] for f in countries()["features"]}
    terms, values = ["r.sentiment_kind=?", "json_extract(r.metadata,'$.social.platform') IS NOT NULL"], [kind]
    if kind == "public":
        terms.append("r.ingested_at>=?")
        values.append(stamp(utcnow() - timedelta(hours=24)))
    if platform != "all":
        terms.append("json_extract(r.metadata,'$.social.platform')=?")
        values.append(platform)
    for instant, operator in [(filters.start, ">="), (filters.end, "<=")]:
        if instant:
            terms.append(f"r.published_at{operator}?")
            values.append(stamp(instant))
    if filters.q:
        q = filters.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        terms.append("(r.title LIKE ? ESCAPE '\\' OR r.description LIKE ? ESCAPE '\\')")
        values.extend([f"%{q}%"] * 2)
    allowed = set(places)
    if filters.country:
        allowed &= {filters.country}
    if filters.bbox:
        west, south, east, north = filters.bbox
        allowed &= {
            code
            for code, place in places.items()
            if south <= place["center"][1] <= north
            and (
                west <= place["center"][0] <= east
                if west <= east
                else place["center"][0] >= west or place["center"][0] <= east
            )
        }
    if filters.country or filters.bbox:
        if not allowed:
            terms.append("0=1")
        else:
            placeholders = ",".join("?" for _ in allowed)
            if geography == "origin":
                terms.append(f"json_extract(r.metadata,'$.social.origin_country') IN ({placeholders})")
                values.extend(sorted(allowed))
            else:
                terms.append(
                    f"(EXISTS(SELECT 1 FROM json_each(r.metadata,'$.social.mentioned_countries') WHERE value IN ({placeholders})) OR EXISTS(SELECT 1 FROM json_each(r.metadata,'$.social.context_countries') WHERE value IN ({placeholders})))"
                )
                values.extend([*sorted(allowed), *sorted(allowed)])
    where = " AND ".join(terms)
    with database.connect() as db:
        rows = [
            dict(r)
            for r in db.execute(
                f"SELECT * FROM (SELECT r.*,ROW_NUMBER() OVER(PARTITION BY json_extract(r.metadata,'$.social.platform'),json_extract(r.metadata,'$.social.post_id') ORDER BY r.ingested_at DESC,r.report_id) AS delivery_rank FROM reports r WHERE {where}) WHERE delivery_rank=1 ORDER BY published_at DESC,report_id LIMIT 2000",
                values,
            )
        ]
        available = db.execute(
            f"SELECT COUNT(*) FROM (SELECT 1 FROM reports r WHERE {where} GROUP BY json_extract(r.metadata,'$.social.platform'),json_extract(r.metadata,'$.social.post_id'))",
            values,
        ).fetchone()[0]
    for row in rows:
        row["social"] = json.loads(row["metadata"])["social"]
    scored = [r for r in rows if r["sentiment_label"] is not None]
    distribution = Counter(r["sentiment_label"] for r in scored)
    regions, trend, frequency = {}, {}, Counter()
    for row in scored:
        info = row["social"]
        codes = (
            [info["origin_country"]]
            if geography == "origin" and info["origin_country"]
            else []
            if geography == "origin"
            else sorted(set(info["mentioned_countries"] + info["context_countries"]))
        )
        for code in codes:
            if code not in allowed:
                continue
            place = places[code]
            region = regions.setdefault(
                code,
                {
                    "country": code,
                    "name": place["name"],
                    "count": 0,
                    "sum": 0,
                    "longitude": place["center"][0],
                    "latitude": place["center"][1],
                },
            )
            region["count"] += 1
            region["sum"] += row["sentiment_score"]
        bucket = trend.setdefault(
            row["published_at"][:10], {"date": row["published_at"][:10], "count": 0, "sum": 0}
        )
        bucket["count"] += 1
        bucket["sum"] += row["sentiment_score"]
        frequency.update(tokens(row["description"]))
    posts = [
        {
            "report_id": r["report_id"],
            "event_id": r["event_id"],
            "source_id": r["source_id"],
            "url": r["source_url"],
            "title": r["title"],
            "text": r["description"],
            "published_at": r["published_at"],
            "language": r["language"],
            "label": r["sentiment_label"],
            "score": r["sentiment_score"],
            **r["social"],
        }
        for r in rows[:100]
    ]
    nodes, edges = {}, []
    for post in posts[:50]:
        identity = post["platform"] + ":" + post["post_id"]
        nodes[identity] = {
            "id": identity,
            "name": post["title"][:65],
            "url": post["url"],
            "label": post["label"],
            "report_id": post["report_id"],
            "in_sample": True,
        }
    for post in posts[:50]:
        source = post["platform"] + ":" + post["post_id"]
        for relation in post["relations"]:
            target = post["platform"] + ":" + relation["target_id"]
            nodes.setdefault(
                target,
                {
                    "id": target,
                    "name": "Linked thread (outside this sample)",
                    "url": relation["target_url"],
                    "label": None,
                    "in_sample": False,
                },
            )
            if len(edges) < 100:
                edges.append(
                    {
                        "source": source,
                        "target": target,
                        "kind": relation["kind"],
                        "report_id": post["report_id"],
                    }
                )
    return {
        "kind": kind,
        "platform": platform,
        "geography": geography,
        "topic": filters.q or "All collected feed wording",
        "period": filters.model_dump(mode="json"),
        "period_basis": "feed_publication_or_update",
        "sample_count": len(scored),
        "dataset_count": len(rows),
        "available_count": available,
        "truncated": available > len(rows),
        "excluded_language_count": len(rows) - len(scored),
        "methodology": METHOD,
        "distribution": {k: distribution[k] for k in ["positive", "negative", "neutral"]},
        "sources": dict(Counter(r["source_id"] for r in rows)),
        "languages": dict(Counter(r["language"] for r in rows)),
        "trend": [
            {**b, "score": b["sum"] / b["count"]} for b in sorted(trend.values(), key=lambda b: b["date"])
        ],
        "regions": [{**r, "score": r["sum"] / r["count"]} for r in regions.values()],
        "topic_frequency": [
            {
                "term": term,
                "count": count,
                "report_ids": [r["report_id"] for r in scored if term in tokens(r["description"])][:20],
            }
            for term, count in frequency.most_common(12)
        ],
        "supporting_report_ids": [r["report_id"] for r in scored[:100]],
        "known_origin_count": sum(bool(r["social"]["origin_country"]) for r in rows),
        "unknown_origin_count": sum(not r["social"]["origin_country"] for r in rows),
        "posts": posts,
        "post_limit": 100,
        "discussion_network": {"nodes": list(nodes.values()), "edges": edges, "post_limit": 50},
        "map_network": country_network(scored, social=True, geography=geography),
        "geography_basis": "Declared country origin only"
        if geography == "origin"
        else "Countries named in wording or Reddit thread title; not the poster's origin",
    }
