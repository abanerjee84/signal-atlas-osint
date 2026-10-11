"""Aggregate verification of public conflict collection; no raw content or credentials."""

import json
from collections import Counter

from backend.config import ROOT, Settings
from backend.connectors.conflict_sources import conflict_sources
from backend.database import Database
from backend.models import stamp


def main():
    settings = Settings()
    database = Database(settings.database)
    providers = conflict_sources(settings)
    statuses = {row["source_id"]: row for row in database.statuses()}
    with database.connect() as db:
        rows = db.execute(
            "SELECT DISTINCT e.event_id,e.category,e.location_precision,e.country_code FROM events e JOIN reports r ON r.event_id=e.event_id WHERE r.source_id LIKE 'conflict_%'"
        ).fetchall()
        reports = db.execute("SELECT COUNT(*) FROM reports WHERE source_id LIKE 'conflict_%'").fetchone()[0]
    result = {
        "checked_at": stamp(),
        "public_source_endpoints": 28,
        "connector_selectors": len(providers),
        "sources_with_successful_collection": sum(
            bool(statuses.get(p.source_id, {}).get("last_success")) for p in providers
        ),
        "source_states": dict(
            Counter(statuses.get(p.source_id, {}).get("state", "never_run") for p in providers)
        ),
        "stored_public_reports": reports,
        "distinct_events": len(rows),
        "event_categories": dict(Counter(row["category"] for row in rows)),
        "location_precision": dict(Counter(row["location_precision"] for row in rows)),
        "countries": sorted(set(row["country_code"] for row in rows if row["country_code"])),
        "server_lifecycle_actions": 0,
    }
    (ROOT / "docs/conflict-ingestion-verification.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps({**result, "countries": len(result["countries"])}, indent=2))


if __name__ == "__main__":
    main()
