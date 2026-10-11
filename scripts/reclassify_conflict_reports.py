"""Repair only new conflict-source topic labels from their stored public evidence. No server actions."""

import json

from backend.config import Settings
from backend.connectors.conflict_sources import conflict_sources, conflict_type
from backend.database import Database
from backend.models import Category, Report


def repair(database, providers):
    definitions = {provider.source_id: provider for provider in providers}
    with database.connect() as db:
        rows = db.execute(
            "SELECT r.*,x.payload AS raw_payload FROM reports r LEFT JOIN raw_records x ON x.report_id=r.report_id WHERE r.source_id LIKE 'conflict_%' LIMIT 5000"
        ).fetchall()
    pending = []
    for row in rows:
        source = definitions.get(row["source_id"])
        if not source:
            continue
        metadata = json.loads(row["metadata"])
        report = Report.model_validate(
            {
                **metadata,
                "title": row["title"],
                "description": row["description"],
                "raw": json.loads(row["raw_payload"] or "{}"),
            }
        )
        rule = conflict_type(report.title)
        if (
            rule
            and rule["id"] in {"security", "conflict"}
            and not row["source_id"].startswith("conflict_liveuamap_")
        ):
            rule = conflict_type(report.title + " " + report.description) or rule
        if not rule or "assessment" in report.tags:
            continue
        category = Category.military if rule["military"] else Category.geopolitical
        if not row["source_id"].startswith("conflict_liveuamap_") and source.category == "military":
            category = Category.military
        tag = f"conflict:{rule['id']}"
        if report.category == category and tag in report.tags:
            continue
        report.category = category
        report.tags = [tag for tag in report.tags if not tag.startswith("conflict:")] + [tag]
        if report.news:
            report.news.event_type = rule["id"]
        pending.append(report)
    if pending:
        database.ingest_many(pending)
    return {
        "checked_reports": len(rows),
        "updated_topic_labels": len(pending),
        "original_dates_and_raw_evidence_preserved": True,
        "server_lifecycle_actions": 0,
    }


if __name__ == "__main__":
    settings = Settings()
    print(json.dumps(repair(Database(settings.database), conflict_sources(settings)), indent=2))
