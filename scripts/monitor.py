"""Print a resource snapshot and fail when disk space falls below the configured reserve."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.config import Settings
from backend.database import Database
from backend.models import stamp
from backend.operations import disk_status

settings = Settings()
snapshot = disk_status(settings.database)
snapshot["timestamp"] = stamp()
with Database(settings.database).connect() as db:
    snapshot["events"] = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
snapshot["disk_low"] = snapshot["disk_free_bytes"] < int(os.getenv("OSINT_DISK_RESERVE_BYTES", str(1024**3)))
print(json.dumps(snapshot))
raise SystemExit(1 if snapshot["disk_low"] else 0)
