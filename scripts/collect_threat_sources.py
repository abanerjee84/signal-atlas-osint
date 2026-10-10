"""Bounded, no-key collection of the threat sources; writes count-only verification."""

# ruff: noqa: E402 - allow invocation from outside the workspace.

import asyncio
import json
import ssl
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.advanced.processing import index_batch
from backend.advanced.providers import lookup
from backend.advanced.repository import Repository
from backend.advanced.threats import CATALOGS, match_reports, refresh_catalog
from backend.config import Settings
from backend.connectors.base import SafeHTTP
from backend.connectors.cyber_feeds import cyber_feeds
from backend.connectors.registry import connectors
from backend.database import Database
from backend.models import stamp
from backend.worker import collect


async def run():
    settings = Settings()
    database = Database(settings.database)
    database.initialize()
    repo = Repository(database)
    repo.register(connectors(settings))
    result = {"checked_at": stamp(), "catalogs": [], "feeds": []}
    async with httpx.AsyncClient(
        timeout=settings.http_timeout,
        verify=ssl.create_default_context(),
        headers={"User-Agent": "GlobalOSINT/0.1 public-source-research"},
    ) as client:
        for sid in CATALOGS:
            try:
                async with asyncio.timeout(180):
                    row = await refresh_catalog(repo, settings, client, sid)
                row["state"] = "ok"
            except Exception as error:
                # Safe summary only: provider errors can otherwise embed credentials or URLs.
                row = {"source_id": sid, "state": "error", "error_type": type(error).__name__}
            result["catalogs"].append(row)
            print(json.dumps(row), flush=True)
        http = SafeHTTP(settings, client)
        for provider in cyber_feeds(settings):
            if not repo.one("SELECT 1 FROM sources WHERE source_id=? AND enabled=1", (provider.source_id,)):
                continue
            row = await collect(provider, database, http)
            result["feeds"].append(row)
            print(json.dumps(row), flush=True)
        try:
            answer = await lookup(repo, settings, client, {"provider_id": "sans", "query": "8.8.8.8"})
            result["sans_ip_lookup"] = {"state": "ok", "classification": answer["classification"]}
        except Exception as error:
            result["sans_ip_lookup"] = {"state": "error", "error_type": type(error).__name__}
    # Bound local processing; the normal worker continues any remaining backlog.
    for _ in range(50):
        count = await asyncio.to_thread(index_batch, database, 200)
        if not count:
            break
    for _ in range(50):
        if not await asyncio.to_thread(match_reports, repo, 200):
            break
    result["active_entities"] = repo.rows(
        "SELECT type,COUNT(DISTINCT entity_id) AS count FROM threat_catalog_objects WHERE active=1 GROUP BY type"
    )
    result["report_matches"] = repo.rows(
        "SELECT status,COUNT(*) AS count FROM threat_report_matches GROUP BY status"
    )
    result["catalog_relations"] = repo.one(
        "SELECT COUNT(*) AS count FROM threat_catalog_relations WHERE active=1"
    )["count"]
    result["finished_at"] = stamp()
    path = ROOT / "docs/threat-source-live-verification.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verification": str(path), "active_entities": result["active_entities"]}), flush=True)


if __name__ == "__main__":
    asyncio.run(run())
