"""Bounded deterministic derivatives; original evidence is never rewritten."""

import hashlib
import ipaddress
import re
from datetime import datetime
from itertools import combinations
from urllib.parse import urlsplit, urlunsplit

from langdetect import DetectorFactory, LangDetectException, detect
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from ..geo import countries, mentioned_countries
from ..models import stamp
from .repository import Repository, packed

DetectorFactory.seed = 0
SENTIMENT = SentimentIntensityAnalyzer()
STOP = set(
    "the and for with from that this have has are was will into over after before says said news world about their more than amid new not its his her our your live latest update updates".split()
)

INSTITUTIONS = {
    "North Atlantic Treaty Organization": r"\b(?:NATO|North Atlantic Treaty Organi[sz]ation)\b",
    "United Nations": r"\bUnited Nations\b",
    "European Union": r"\bEuropean Union\b",
    "World Health Organization": r"\bWorld Health Organi[sz]ation\b",
    "International Monetary Fund": r"\bInternational Monetary Fund\b",
    "World Bank": r"\bWorld Bank\b",
}


def stable(*parts):
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()[:32]


def tokens(text):
    return set(re.findall(r"[^\W\d_]{3,}", text.casefold())) - STOP


def normalize_indicator(value):
    value = value.strip().strip(".,;()[]")
    if re.fullmatch(r"CVE-\d{4}-\d{4,}", value, re.I):
        return "cve", value.upper()
    try:
        return "ip", str(ipaddress.ip_address(value))
    except ValueError:
        pass
    if re.fullmatch(r"[a-fA-F0-9]{32}|[a-fA-F0-9]{40}|[a-fA-F0-9]{64}", value):
        return "hash", value.lower()
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password:
        hostname = parsed.hostname.encode("idna").decode().lower()
        if parsed.port not in {None, 80, 443}:
            raise ValueError("Unsupported URL port")
        return "url", urlunsplit(
            (
                parsed.scheme.lower(),
                hostname + (f":{parsed.port}" if parsed.port else ""),
                parsed.path or "/",
                parsed.query,
                "",
            )
        )
    if re.fullmatch(r"(?:[\w-]+\.)+[a-zA-Z]{2,63}", value) and len(value) <= 253:
        return "domain", value.encode("idna").decode().lower()
    raise ValueError("Use an IP address, domain, HTTP(S) URL, file hash or CVE identifier")


def indicators(text):
    matches = re.findall(
        r"CVE-\d{4}-\d{4,}|https?://[^\s<>\"']+|\b(?:\d{1,3}\.){3}\d{1,3}\b|\b[a-fA-F0-9]{64}\b|\b[a-fA-F0-9]{40}\b|\b[a-fA-F0-9]{32}\b|\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,63}\b",
        text,
        re.I,
    )
    result = set()
    for value in matches[:100]:
        try:
            result.add(normalize_indicator(value))
        except (ValueError, UnicodeError):
            pass
    return sorted(result)


def index_batch(database, limit=200):
    repo = Repository(database)
    with database.connect() as db:
        db.execute(
            "UPDATE external_records SET indexed_at=? WHERE indexed_at IS NULL AND category IN ('aviation','maritime')",
            (stamp(),),
        )
    records = repo.rows(
        "SELECT * FROM external_records WHERE indexed_at IS NULL ORDER BY ingested_at DESC LIMIT ?", (limit,)
    )
    country_names = {f["properties"]["code"]: f["properties"]["name"] for f in countries()["features"]}
    for record in records:
        with database.connect() as db:
            # Connection is held only for bounded local work; no HTTP or AI here.
            rid = record["record_id"]
            db.execute("DELETE FROM entity_source_mentions WHERE record_id=?", (rid,))
            db.execute("DELETE FROM relationship_evidence WHERE record_id=?", (rid,))
            db.execute("DELETE FROM indicator_evidence WHERE record_id=?", (rid,))
            db.execute("DELETE FROM narrative_members WHERE record_id=?", (rid,))
            text = record["title"] + " " + record["text"]
            digest = hashlib.sha256(text.encode()).hexdigest()
            language = record["language"]
            if len(text) > 40 and record["kind"] in {"news", "official", "public"}:
                try:
                    language = detect(text)
                except LangDetectException:
                    language = "und"
            db.execute(
                "UPDATE external_records SET language=?,content_hash=?,indexed_at=? WHERE record_id=?",
                (language, digest, stamp(), rid),
            )
            if record["category"] in {"aviation", "maritime"}:
                continue
            country_codes = mentioned_countries(text)[:8]
            entities = [
                (
                    stable("country", code),
                    "country",
                    country_names.get(code, code),
                    "resolved-country-reference",
                )
                for code in country_codes
            ]
            entities += [
                (stable("institution", name), "institution", name, "explicit institutional text reference")
                for name, pattern in INSTITUTIONS.items()
                if re.search(pattern, text, re.I)
            ]
            if record["metadata"].get("cyber_observation"):
                from ..cyber_observations import index_observation
                from ..models import CyberObservation

                observation = CyberObservation.model_validate(record["metadata"]["cyber_observation"])
                index_observation(db, rid, record["source_id"], observation, record["confidence"])
            elif record["category"] == "cyber":
                for kind, value in indicators(text):
                    iid = stable(kind, value)
                    seen = record["published_at"] or record["observed_at"]
                    db.execute(
                        "INSERT INTO cyber_indicators VALUES(?,?,?,?,?,?) ON CONFLICT(type,normalized_value) DO UPDATE SET last_seen_at=MAX(COALESCE(last_seen_at,''),COALESCE(excluded.last_seen_at,'')),first_seen_at=CASE WHEN first_seen_at IS NULL THEN excluded.first_seen_at ELSE MIN(first_seen_at,COALESCE(excluded.first_seen_at,first_seen_at)) END",
                        (iid, kind, value, value, seen, seen),
                    )
                    db.execute(
                        "INSERT OR REPLACE INTO indicator_evidence VALUES(?,?,?,?)",
                        (
                            iid,
                            rid,
                            "official_vulnerability_advisory" if kind == "cve" else "mentioned_in_report",
                            record["confidence"],
                        ),
                    )
                    entities.append((iid, "infrastructure", value, "indicator-reference"))
            for eid, kind, name, ambiguity in entities:
                db.execute(
                    "INSERT OR IGNORE INTO entities VALUES(?,?,?,?,?,?)",
                    (eid, kind, name, name.casefold(), ambiguity, stamp()),
                )
                db.execute("INSERT OR IGNORE INTO entity_source_mentions VALUES(?,?)", (eid, rid))
            for a, b in combinations(entities[:12], 2):
                left, right = sorted((a[0], b[0]))
                edge = stable("co_mentioned", left, right)
                db.execute(
                    "INSERT OR IGNORE INTO relationships VALUES(?,?,?,?,?,?,?,?)",
                    (
                        edge,
                        left,
                        right,
                        "co_mentioned",
                        "reported",
                        None,
                        None,
                        "Both references occur in the same source text; no causal or operational relationship established.",
                    ),
                )
                db.execute("INSERT OR IGNORE INTO relationship_evidence VALUES(?,?)", (edge, rid))
            if record["kind"] not in {"news", "official", "public"} or record["source_id"].startswith(
                "watch_"
            ):
                continue
            words = tokens(record["title"])
            best, similarity = None, 0.0
            for row in db.execute(
                "SELECT * FROM narrative_clusters WHERE language=? ORDER BY created_at DESC LIMIT 200",
                (language,),
            ):
                prior = tokens(row["title"])
                overlap = len(words & prior) / max(1, len(words | prior))
                if overlap > similarity:
                    best, similarity = row["cluster_id"], overlap
            cluster_id = (
                best if similarity >= 0.38 else stable("narrative", language, record["title"].casefold())
            )
            db.execute(
                "INSERT OR IGNORE INTO narrative_clusters VALUES(?,?,?,?,?)",
                (
                    cluster_id,
                    record["title"],
                    language,
                    "title-token-jaccard-v1; threshold=0.38; bounded latest 200 clusters/language",
                    stamp(),
                ),
            )
            score = SENTIMENT.polarity_scores(text)["compound"] if language == "en" else None
            label = (
                "unclassified"
                if score is None
                else "positive"
                if score >= 0.05
                else "negative"
                if score <= -0.05
                else "neutral"
            )
            db.execute(
                "INSERT INTO narrative_members VALUES(?,?,?,?,?)",
                (
                    cluster_id,
                    rid,
                    label,
                    score,
                    "uncalibrated lexical classification" if score is not None else "unsupported language",
                ),
            )
    # Metrics derive from current members, so record updates/deletions cannot accumulate counts.
    if records:
        with database.connect() as db:
            db.execute("DELETE FROM narrative_metrics")
            db.execute(
                "INSERT INTO narrative_metrics SELECT n.cluster_id,SUBSTR(COALESCE(r.published_at,r.observed_at,r.ingested_at),1,10),r.language,COUNT(*) FROM narrative_members n JOIN external_records r USING(record_id) GROUP BY 1,2,3"
            )
    return len(records)


def candidates(repo, record_ids, weights):
    records = [repo.record(rid) for rid in dict.fromkeys(record_ids)]
    entities = {
        r["record_id"]: {
            e["name"]
            for e in repo.rows(
                "SELECT name FROM entity_source_mentions m JOIN entities e USING(entity_id) WHERE record_id=? LIMIT 100",
                (r["record_id"],),
            )
        }
        for r in records
    }
    result = []
    for left, right in combinations(records, 2):
        times = [r["published_at"] or r["observed_at"] for r in (left, right)]
        temporal = (
            max(
                0,
                1
                - abs((datetime.fromisoformat(times[0]) - datetime.fromisoformat(times[1])).total_seconds())
                / 86400,
            )
            if all(times)
            else 0
        )
        geography = float(bool(left["country"] and left["country"] == right["country"]))
        a, b = tokens(left["title"]), tokens(right["title"])
        topics = len(a & b) / max(1, len(a | b))
        score = sum(
            weights[k] * v for k, v in [("time", temporal), ("country", geography), ("topics", topics)]
        )
        basis = {
            "weights": weights,
            "temporal_similarity": temporal,
            "shared_country": geography,
            "title_token_overlap": topics,
            "shared_tokens": sorted(a & b),
            "shared_entities": sorted(entities[left["record_id"]] & entities[right["record_id"]]),
            "supporting_source_count": len({left["source_id"], right["source_id"]}),
            "limitations": "Heuristic association score, not causation or probability. Country mentions are regional context.",
        }
        if all(
            r["precision"] == "exact" and r["latitude"] is not None and r["longitude"] is not None
            for r in (left, right)
        ):
            from .geo import distance

            basis["distance_meters"] = distance(
                [(left["longitude"], left["latitude"]), (right["longitude"], right["latitude"])]
            )
        cid = stable("correlation-v1", left["record_id"], right["record_id"], packed(basis))
        with repo.database.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO correlations VALUES(?,?,?,?,?,?)",
                (
                    cid,
                    packed([left["record_id"], right["record_id"]]),
                    score,
                    "weighted-association-v1",
                    packed(basis),
                    stamp(),
                ),
            )
        result.append(
            {"id": cid, "record_ids": [left["record_id"], right["record_id"]], "score": score, "basis": basis}
        )
    return sorted(result, key=lambda r: r["score"], reverse=True)[:200]
