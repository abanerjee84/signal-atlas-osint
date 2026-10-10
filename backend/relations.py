"""Country discussion and publisher links with supporting reports; no inferred traffic."""

import hashlib
import json
from itertools import combinations

from .geo import countries, mentioned_countries
from .models import stamp


def report_country_codes(metadata, title, description):
    info = json.loads(metadata).get("news") or {}
    return sorted(
        set(info.get("mentioned_countries", [])) | set(mentioned_countries(title + " " + description))
    )


def country_network(rows, *, social=False, geography="mentions"):
    places = {f["properties"]["code"]: f["properties"] for f in countries()["features"]}
    edges, nodes = {}, {}

    def node(code, publisher=None):
        if code not in places:
            return
        place = places[code]
        item = nodes.setdefault(
            code,
            {"id": code, "name": place["name"], "coordinates": place["center"], "publishers": [], "count": 0},
        )
        if publisher and publisher not in item["publishers"]:
            item["publishers"].append(publisher)

    def edge(a, b, kind, row, source=""):
        if a == b or a not in places or b not in places:
            return
        node(a, source if kind == "publisher_to_country" else None)
        node(b)
        key = (a, b, kind, source)
        item = edges.setdefault(
            key,
            {
                "id": hashlib.sha256(repr(key).encode()).hexdigest()[:20],
                "from": a,
                "to": b,
                "kind": kind,
                "source_id": source,
                "count": 0,
                "report_ids": [],
                "event_ids": [],
                "titles": [],
                "urls": [],
                "from_coordinates": places[a]["center"],
                "to_coordinates": places[b]["center"],
                "score_sum": 0.0,
                "score_count": 0,
            },
        )
        item["count"] += 1
        # Tone of the wording carried by this edge, not opinion of the country
        # receiving it. Unscored (non-English) reports leave the mean undefined.
        if row["sentiment_score"] is not None:
            item["score_sum"] += row["sentiment_score"]
            item["score_count"] += 1
        if len(item["report_ids"]) < 10:
            for field, value in [
                ("report_ids", row["report_id"]),
                ("event_ids", row["event_id"]),
                ("titles", row["title"]),
                ("urls", row["source_url"]),
            ]:
                item[field].append(value)

    for row in rows:
        metadata = json.loads(row["metadata"])
        info = metadata.get("social") or {} if social else metadata.get("news") or {}
        mentioned = (
            sorted(set(info.get("mentioned_countries", [])) | set(info.get("context_countries", [])))
            if social
            else report_country_codes(row["metadata"], row["title"], row["description"])
        )
        if social:
            origin = info.get("origin_country")
            if geography == "origin":
                if origin:
                    node(origin)
                continue
            if origin:
                for code in mentioned:
                    edge(origin, code, "declared_origin_to_mention", row)
        else:
            origin = info.get("publisher_country")
            if origin:
                node(origin, row["source_id"])
                for code in mentioned:
                    edge(origin, code, "publisher_to_country", row, row["source_id"])
        for code in mentioned:
            node(code)
            if code in nodes:
                nodes[code]["count"] += 1
        for a, b in combinations(mentioned[:10], 2):
            edge(a, b, "country_co_mention", row)
    for item in edges.values():
        item["sentiment"] = item["score_sum"] / item["score_count"] if item["score_count"] else None
        item["sentiment_samples"] = item["score_count"]
        del item["score_sum"], item["score_count"]
    ordered = sorted(edges.values(), key=lambda item: (-item["count"], item["id"]))
    return {
        "nodes": list(nodes.values()),
        "edges": ordered[:100],
        "available_edges": len(ordered),
        "truncated": len(ordered) > 100,
        "methodology": "Publisher base and countries named in wording are geographic context. Co-mentions mean two countries occur in the same report/discussion, not movement, influence or verified interaction. All connections include supporting source references.",
    }


def report_rows(database, filters, scope="news"):
    selected = filters.model_copy(
        update={"start": None, "end": None, "q": "", "categories": [], "country": None, "bbox": None}
    )
    where, values = database.where(selected, "e")
    for instant, operator in [(filters.start, ">="), (filters.end, "<=")]:
        if instant:
            where += f" AND r.published_at{operator}?"
            values.append(stamp(instant))
    if filters.q:
        value = filters.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where += " AND (r.title LIKE ? ESCAPE '\\' OR r.description LIKE ? ESCAPE '\\')"
        values.extend([f"%{value}%"] * 2)
    places = {f["properties"]["code"]: f["properties"] for f in countries()["features"]}
    if filters.country or filters.bbox:
        allowed = set(places)
        if filters.country:
            allowed &= {filters.country}
        if filters.bbox:
            west, south, east, north = filters.bbox
            allowed &= {
                code
                for code, p in places.items()
                if south <= p["center"][1] <= north
                and (
                    west <= p["center"][0] <= east
                    if west <= east
                    else p["center"][0] >= west or p["center"][0] <= east
                )
            }
        if allowed:
            placeholders = ",".join("?" for _ in allowed)
            where += f" AND (EXISTS(SELECT 1 FROM json_each(text_country_codes(r.metadata,r.title,r.description)) WHERE value IN ({placeholders})) OR e.country_code IN ({placeholders}))"
            values.extend([*sorted(allowed), *sorted(allowed)])
        else:
            where += " AND 0=1"
    restriction = (
        "e.category='cyber' AND r.sentiment_kind IN ('news','official')"
        if scope == "cyber"
        else "e.category='geopolitical' AND r.sentiment_kind='news'"
        if scope == "news"
        else "(e.category='military' OR (e.category='geopolitical' AND r.sentiment_kind='news'))"
    )
    with database.connect() as db:
        db.create_function(
            "text_country_codes",
            3,
            lambda metadata, title, description: json.dumps(
                report_country_codes(metadata, title, description)
            ),
            deterministic=True,
        )
        rows = [
            dict(r)
            for r in db.execute(
                f"SELECT r.*,e.category AS event_category FROM reports r JOIN events e ON r.event_id=e.event_id WHERE {where} AND {restriction} GROUP BY r.source_url ORDER BY r.published_at DESC,r.report_id LIMIT 1000",
                values,
            )
        ]
    return rows


def news_relations(database, filters):
    rows = report_rows(database, filters)
    return {
        **country_network(rows),
        "report_count": len(rows),
        "report_limit": 1000,
        "sources": sorted({r["source_id"] for r in rows}),
    }


def cyber_relations(database, filters):
    rows = report_rows(database, filters, scope="cyber")
    return {
        **country_network(rows),
        "report_count": len(rows),
        "report_limit": 1000,
        "sources": sorted({r["source_id"] for r in rows}),
        "classification": "publisher_and_reported_country_context",
    }
