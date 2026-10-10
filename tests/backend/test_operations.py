import sqlite3

from backend.config import ROOT
from backend.database import Database
from backend.operations import backup_database

SCHEMA_VERSION = len(list((ROOT / "backend/migrations").glob("*.sql")))


def test_upgrade_existing_v1_schema(settings):
    with sqlite3.connect(settings.database) as db:
        db.executescript((ROOT / "backend/migrations/001_initial.sql").read_text())
        db.execute("PRAGMA user_version=1")
    database = Database(settings.database)
    database.initialize()
    with database.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert db.execute("SELECT COUNT(*) FROM evidence_reviews").fetchone()[0] == 0
        columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
        assert {"aircraft_track_deg", "aircraft_callsign", "aircraft_category"} <= columns


def test_online_backup_and_recovery(database, report, tmp_path):
    event = database.ingest(report)
    destination = tmp_path / "backups"
    for _ in range(3):
        path = backup_database(database.path, destination, keep=2)
    assert len(list(destination.glob("osint-*.sqlite3"))) == 2
    restored = Database(path)
    assert restored.detail(event)["title"] == report.title
    with restored.connect() as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
