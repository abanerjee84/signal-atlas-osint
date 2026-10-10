"""Review (and optionally archive) mixed-feed records rejected by the current selection rule."""

import argparse
import json

from backend.config import Settings
from backend.connectors.registry import connectors
from backend.database import Database
from backend.models import stamp

parser = argparse.ArgumentParser()
parser.add_argument("--apply", action="store_true")
args = parser.parse_args()
settings = Settings()
database = Database(settings.database)
providers = [p for p in connectors(settings) if getattr(p, "topical", False)]
with database.connect() as db:
    rejected = []
    for provider in providers:
        for row in db.execute("SELECT * FROM reports WHERE source_id=?", (provider.source_id,)):
            item = dict(row)
            if not provider.select_records([item]):
                rejected.append(item)
    print(json.dumps({"count": len(rejected), "titles": [r["title"] for r in rejected]}, ensure_ascii=False))
    if args.apply and rejected:
        db.execute("BEGIN IMMEDIATE")
        archive = (
            settings.database.parent
            / "corrections"
            / ("news-selection-" + stamp().replace(":", "-") + ".json")
        )
        archive.parent.mkdir(parents=True, exist_ok=True)
        data = []
        for report in rejected:
            event = db.execute("SELECT * FROM events WHERE event_id=?", (report["event_id"],)).fetchone()
            raw = db.execute("SELECT * FROM raw_records WHERE report_id=?", (report["report_id"],)).fetchone()
            data.append(
                {"report": report, "event": dict(event) if event else None, "raw": dict(raw) if raw else None}
            )
        archive.write_text(
            json.dumps(
                {"reason": "Mixed-feed topic selection correction", "records": data}, ensure_ascii=False
            ),
            encoding="utf-8",
        )
        archive.chmod(0o600)
        for report in rejected:
            db.execute("DELETE FROM reports WHERE report_id=?", (report["report_id"],))
            db.execute(
                "DELETE FROM events WHERE event_id=? AND NOT EXISTS(SELECT 1 FROM reports WHERE event_id=?)",
                (report["event_id"], report["event_id"]),
            )
        print(json.dumps({"archived_to": str(archive), "corrected": len(data)}))
