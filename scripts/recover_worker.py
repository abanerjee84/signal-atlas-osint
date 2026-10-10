"""Called only by START after it has stopped this checkout's previous processes."""

import argparse
import sqlite3
from contextlib import closing

from backend.config import ROOT, Settings
from backend.models import stamp

parser = argparse.ArgumentParser()
parser.add_argument("--after-project-shutdown", action="store_true", required=True)
parser.parse_args()
path = Settings().database.resolve()
if not path.is_relative_to((ROOT / "data").resolve()):
    print("Shared/external database: retaining worker leases until normal expiration.")
elif path.is_file():
    with closing(sqlite3.connect(path, timeout=10)) as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "job_locks" in tables:
            cleared = db.execute(
                "DELETE FROM job_locks WHERE name LIKE 'collect:%' OR name='advanced:worker'"
            ).rowcount
            if "investigation_jobs" in tables:
                db.execute(
                    "UPDATE investigation_jobs SET state='failed',error='Worker stopped during dashboard restart; submit again',updated_at=? WHERE state='running'",
                    (stamp(),),
                )
            if "connector_status" in tables:
                db.execute(
                    "UPDATE connector_status SET state='error',error='Collection interrupted by dashboard restart; scheduled to retry',next_run=NULL WHERE state='fetching'"
                )
            db.commit()
            print(f"Recovered {cleared} leases from stopped project workers.")
