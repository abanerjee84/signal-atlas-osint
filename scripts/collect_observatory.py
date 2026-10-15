"""One bounded collection of infrastructure observations; opens no server ports."""

import argparse
import asyncio
import json
import sqlite3
from datetime import timedelta

import httpx

from backend.advanced.repository import Repository
from backend.config import Settings
from backend.connectors.base import SafeHTTP
from backend.connectors.observatory import observation_feeds
from backend.database import Database
from backend.models import stamp, utcnow
from backend.tls import outbound_tls
from backend.worker import collect


async def run(source_ids):
    settings = Settings()
    database = Database(settings.database)
    # First upgrade preserves a consistent database copy, including private cases.
    # No filesystem copy of a live WAL database, and no old-backup deletion.
    if settings.database.exists():
        with sqlite3.connect(settings.database) as source:
            if source.execute("PRAGMA user_version").fetchone()[0] < 7:
                destination = (
                    settings.database.parent
                    / "backups"
                    / ("before-observatory-" + utcnow().strftime("%Y%m%dT%H%M%S%fZ") + ".sqlite3")
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                with sqlite3.connect(destination) as target:
                    source.backup(target)
                    # Match the application's backup policy for public discussion snapshots.
                    target.execute("PRAGMA foreign_keys=ON")
                    target.execute("DELETE FROM events WHERE category='sentiment'")
                    target.commit()
                    if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                        raise RuntimeError("Pre-upgrade backup integrity check failed")
                destination.chmod(0o600)
                print(json.dumps({"schema_backup": str(destination)}))
    database.initialize()
    providers = observation_feeds(settings)
    Repository(database).register(providers)
    if not set(source_ids) <= {provider.source_id for provider in providers}:
        raise ValueError("Unknown observation provider")
    results = []
    async with httpx.AsyncClient(timeout=settings.http_timeout, verify=outbound_tls()) as client:
        for provider in providers:
            if provider.source_id not in source_ids:
                continue
            with database.connect() as db:
                enabled = db.execute(
                    "SELECT enabled FROM sources WHERE source_id=?", (provider.source_id,)
                ).fetchone()[0]
            if not enabled:
                results.append({"source_id": provider.source_id, "state": "disabled"})
                continue
            previous = next(
                (row for row in database.statuses() if row["source_id"] == provider.source_id), {}
            )
            if previous.get("next_run") and previous["next_run"] > stamp():
                results.append(
                    {"source_id": provider.source_id, "state": "deferred", "next_run": previous["next_run"]}
                )
                continue
            result = await collect(provider, database, SafeHTTP(settings, client))
            if result["state"] != "already_running":
                database.set_status(
                    provider.source_id,
                    next_run=stamp(
                        utcnow() + timedelta(seconds=max(provider.interval, result.get("retry_after", 0)))
                    ),
                )
            results.append(result)
    print(json.dumps({"checked_at": stamp(), "server_lifecycle_actions": 0, "results": results}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", action="append", choices=["dshield", "isc_honeypots", "threatfox", "cloudflare_radar"]
    )
    asyncio.run(run(parser.parse_args().source or ["dshield", "threatfox", "cloudflare_radar"]))
