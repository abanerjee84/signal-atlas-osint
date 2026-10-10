"""Evidence briefing from official announcements and explicitly identified media wording."""

import re
from collections import Counter

from .geo import mentioned_countries
from .models import stamp, utcnow
from .relations import country_network, report_rows

SIGNALS = {
    "Exercises & readiness": r"\b(exercises?|drills?|readiness|training|maneuvers?|manoeuvres?)\b",
    "Procurement & capability": r"\b(procurement|weapons?|missiles?|drones?|fighter jets?|warships?|submarines?|air defence|air defense|munitions?|defence spending|defense spending)\b",
    "Defence cooperation": r"\b(military aid|defence cooperation|defense cooperation|arms deal|arms sales|security assistance|defence agreement|defense agreement|nato|military alliance)\b",
    "Conflict reporting": r"\b(airstrikes?|air strikes?|bombardment|troops?|armed forces|military|battlefield|ceasefire|invasion|artillery|offensive|shelling)\b",
    "Defence policy": r"\b(pentagon|defence minister|defense minister|military budget|deterrence|defence strategy|defense strategy|defence review|defense review)\b",
}
MATCHERS = {name: re.compile(pattern, re.I) for name, pattern in SIGNALS.items()}
MILITARY_WORDING = re.compile(
    r"\b(military|armed forces|defen[cs]e|nato|pentagon|troops?|naval|warships?|fighter jets?|munitions?|artillery|airstrikes?|air strikes?|ceasefire|combat|shelling|invasion|arms sales|arms deal)\b",
    re.I,
)


def military_brief(database, filters):
    rows = report_rows(database, filters, "military")
    selected = []
    for row in rows:
        text = row["title"] + " " + row["description"]
        topics = [name for name, matcher in MATCHERS.items() if matcher.search(text)]
        if row["event_category"] != "military" and not MILITARY_WORDING.search(text):
            continue
        historical = bool(re.search(r"world war (?:ii|i|2|1)\b", row["title"], re.I)) or any(
            int(year) < utcnow().year - 1 for year in re.findall(r"\b((?:19|20)\d{2})\b", row["title"])
        )
        if historical:
            topics = ["Historical background"]
        if not topics and row["event_category"] != "military":
            continue
        row["topics"] = topics or ["Other official defence reporting"]
        row["countries"] = mentioned_countries(text)
        selected.append(row)
    groups = []
    midpoint = (
        stamp(filters.start + (filters.end - filters.start) / 2) if filters.start and filters.end else None
    )
    for name in [*SIGNALS, "Other official defence reporting", "Historical background"]:
        records = [r for r in selected if name in r["topics"]]
        if not records:
            continue
        groups.append(
            {
                "name": name,
                "count": len(records),
                "network": country_network(records),
                "sources": sorted({r["source_id"] for r in records}),
                "countries": dict(Counter(c for r in records for c in r["countries"])),
                "event_ids": list(dict.fromkeys(r["event_id"] for r in records))[:30],
                "latest": max(r["published_at"] for r in records),
                "official_count": sum(r["sentiment_kind"] == "official" for r in records),
                "media_count": sum(r["sentiment_kind"] == "news" for r in records),
                "unlocated_count": sum(not r["countries"] for r in records),
                "period_comparison": {
                    "basis": "Earlier versus later half of the selected publication window. Report volume, not military activity.",
                    "midpoint": midpoint,
                    "earlier": sum(r["published_at"] < midpoint for r in records),
                    "later": sum(r["published_at"] >= midpoint for r in records),
                }
                if midpoint
                else None,
                "assessment": f"{len(records)} stored reports across {len({r['source_id'] for r in records})} feeds match this topic. These are wording signals, not independent corroboration.",
                "reports": [
                    {
                        "report_id": r["report_id"],
                        "event_id": r["event_id"],
                        "source_id": r["source_id"],
                        "source_url": r["source_url"],
                        "title": r["title"],
                        "excerpt": r["description"][:450],
                        "published_at": r["published_at"],
                        "basis": "Official announcement"
                        if r["sentiment_kind"] == "official"
                        else "Media reporting",
                        "countries": r["countries"],
                    }
                    for r in records[:12]
                ],
            }
        )
    return {
        "report_count": len(selected),
        "candidate_limit": 1000,
        "display_limit_per_topic": 12,
        "sources": sorted({r["source_id"] for r in selected}),
        "official_count": sum(r["sentiment_kind"] == "official" for r in selected),
        "media_count": sum(r["sentiment_kind"] == "news" for r in selected),
        "groups": groups,
        "network": country_network(selected),
        "methodology": "Topic counts use explicit words in dated public reports. Official claims and media reporting are labelled separately; repetition is not verification. Map countries are text context and publisher bases, not unit positions or confirmed movement. No military attribution is inferred from civilian aircraft data.",
    }
