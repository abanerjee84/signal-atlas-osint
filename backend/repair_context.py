"""Reapply corrected CISA/NCSC/OFAC projections to retained source records.

Run `python -m backend.repair_context --apply`. No network calls, new intelligence,
or changes to original evidence/ingestion dates; analyst reviews take precedence.
"""

import argparse
import json

from .config import Settings
from .connectors.cisa import CISA
from .connectors.ncsc import NCSC
from .connectors.ofac import OFAC
from .database import Database


def repair(database: Database, settings: Settings, apply: bool = False) -> dict:
    providers = {
        provider.source_id: provider for provider in (CISA(settings), NCSC(settings), OFAC(settings))
    }
    with database.connect() as db:
        rows = [
            dict(row)
            for row in db.execute(
                """SELECT r.*, raw.payload, raw.ingested_at AS raw_ingested_at FROM reports r
            JOIN raw_records raw ON raw.report_id=r.report_id
            WHERE r.source_id IN ('cisa','ncsc','ofac')"""
            )
        ]
    counts, skipped = {}, 0
    for row in rows:
        raw = json.loads(row["payload"])
        record = {**raw, "description": row["description"]}
        try:
            normalized = (
                providers[row["source_id"]]
                .normalize(record)
                .model_copy(update={"external_id": row["external_id"], "raw": raw})
            )
        except (ValueError, KeyError, TypeError, IndexError):
            skipped += 1
            continue
        if apply:
            with database.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                database.ingest(normalized, db)
                db.execute(
                    "UPDATE raw_records SET ingested_at=? WHERE report_id=?",
                    (row["raw_ingested_at"], row["report_id"]),
                )
        counts[row["source_id"]] = counts.get(row["source_id"], 0) + 1
    return {"applied": apply, "reports": counts, "skipped": skipped}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    config = Settings()
    database = Database(config.database)
    database.initialize()
    print(json.dumps(repair(database, config, args.apply)))
