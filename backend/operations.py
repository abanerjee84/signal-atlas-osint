"""Operational utilities shared by CLI tools and acceptance tests."""

import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def backup_database(source: Path, destination: Path, keep: int = 7) -> Path:
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    name = "osint-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".sqlite3"
    target = destination / name
    if not source.is_file():
        raise FileNotFoundError("Source database does not exist")
    with closing(sqlite3.connect(source)) as origin, closing(sqlite3.connect(target)) as backup:
        origin.backup(backup, pages=100, sleep=0.1)
        # Public discussion snapshots are deliberately excluded from recoverable archives.
        backup.execute("PRAGMA foreign_keys=ON")
        if backup.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'").fetchone():
            backup.execute("DELETE FROM events WHERE category='sentiment'")
            backup.commit()
        if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup integrity check failed")
    target.chmod(0o600)
    for old in sorted(destination.glob("osint-*.sqlite3"), reverse=True)[keep:]:
        if old.resolve().parent == destination:
            old.unlink()
    return target


def disk_status(database: Path) -> dict:
    usage = shutil.disk_usage(database.parent)
    return {
        "disk_total_bytes": usage.total,
        "disk_used_bytes": usage.used,
        "disk_free_bytes": usage.free,
        "database_bytes": database.stat().st_size if database.exists() else 0,
        "wal_bytes": database.with_name(database.name + "-wal").stat().st_size
        if database.with_name(database.name + "-wal").exists()
        else 0,
    }
