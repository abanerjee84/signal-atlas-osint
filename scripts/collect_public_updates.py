"""One bounded collection pass for public additions; never starts or stops a server."""

import argparse
import asyncio
import json
import ssl
from datetime import timedelta

import httpx

from backend.config import ROOT, Settings
from backend.connectors.base import SafeHTTP
from backend.connectors.public_discussion import discussion_feeds
from backend.connectors.registry import connectors
from backend.connectors.threat_maps import threat_maps
from backend.connectors.threat_reports import threat_feeds
from backend.connectors.world_feeds import world_feeds
from backend.database import Database
from backend.models import stamp, utcnow
from backend.worker import collect
from scripts.collection_status import write_status


async def collect_once(source_ids=None, *, table_reader=None, robots_cache=None):
    settings = Settings()
    database = Database(settings.database)
    # Uses the already initialized running database; no migration or resident worker.
    if not settings.database.exists():
        raise RuntimeError("Start the installed application yourself before this collection pass")
    providers = (
        threat_feeds(settings) + threat_maps(settings) + world_feeds(settings) + discussion_feeds(settings)
    )
    providers += [
        provider
        for provider in connectors(settings)
        if provider.source_id.startswith("reddit_")
        and "archive" not in provider.source_id
        and not getattr(provider, "manual", False)
    ]
    gate = asyncio.Semaphore(2)
    if source_ids:
        providers = [provider for provider in providers if provider.source_id in source_ids]
        if set(source_ids) != {provider.source_id for provider in providers}:
            raise ValueError("Unknown source ID")
    # Register new scraper metadata without initializing or touching any server.
    from backend.advanced.repository import Repository

    await asyncio.to_thread(Repository(database).register, providers)
    async with httpx.AsyncClient(
        timeout=settings.http_timeout,
        verify=ssl.create_default_context(),
        headers={"User-Agent": "SignalAtlas/0.1 public-source-research"},
        limits=httpx.Limits(max_connections=2),
    ) as client:
        http = SafeHTTP(settings, client)
        http.threat_table_reader = table_reader
        http.robots_cache = robots_cache if robots_cache is not None else {}

        async def run(provider):
            async with gate:
                statuses = {row["source_id"]: row for row in await asyncio.to_thread(database.statuses)}
                previous = statuses.get(provider.source_id, {})
                with database.connect() as db:
                    source = db.execute(
                        "SELECT enabled FROM sources WHERE source_id=?", (provider.source_id,)
                    ).fetchone()
                if source and not source["enabled"]:
                    return {"source_id": provider.source_id, "state": "disabled"}
                if previous.get("next_run") and previous["next_run"] > stamp():
                    return {
                        "source_id": provider.source_id,
                        "state": "deferred",
                        "next_run": previous["next_run"],
                    }
                scheduled = utcnow()
                result = await collect(provider, database, http)
                await asyncio.to_thread(
                    database.set_status,
                    provider.source_id,
                    next_run=stamp(
                        utcnow() + timedelta(seconds=max(provider.interval, result.get("retry_after", 0)))
                        if result["state"] == "error"
                        else max(utcnow(), scheduled + timedelta(seconds=provider.interval))
                    ),
                )
                return result

        results = await asyncio.gather(*(run(provider) for provider in providers))
    # Aggregate proof contains no posts, private cases, locations of individuals or credentials.
    proof = {"checked_at": stamp(), "server_lifecycle_actions": 0, "results": results}
    # Public aggregate health bridge for an older, already-running API. No event payloads.
    statuses = {row["source_id"]: row for row in database.statuses()}
    maps = []
    from backend.connectors.threat_research import research_scrapers

    for provider in threat_maps(settings) + research_scrapers(settings):
        current = statuses.get(provider.source_id, {"state": "never_run"})
        maps.append(
            {
                **provider.metadata(),
                **current,
                "stale": not current.get("last_success")
                or current["last_success"] < stamp(utcnow() - timedelta(seconds=provider.interval * 2)),
            }
        )
    status_file = ROOT / "public/threatmap-status.json"
    background = False
    heartbeat_file = settings.database.parent / "run/threat-map-thread.json"
    try:
        heartbeat = json.loads(heartbeat_file.read_text(encoding="utf-8"))
        background = heartbeat.get("running", False) and heartbeat.get("heartbeat", "") > stamp(
            utcnow() - timedelta(seconds=20)
        )
    except (ValueError, OSError):
        pass
    await asyncio.to_thread(
        write_status,
        status_file,
        {
            "checked_at": stamp(),
            "background_collection": background,
            "connectors": maps,
            "vector_summary": getattr(table_reader, "radware_summary", None),
        },
        allow_inplace=True,
    )
    print(json.dumps(proof, indent=2))
    proof_directory = settings.database.parent / "run"
    proof_directory.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(write_status, proof_directory / "public-updates-verification.json", proof)
    return proof


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", help="Collect only this source ID; repeat for more")
    args = parser.parse_args()
    await collect_once(args.source)


if __name__ == "__main__":
    asyncio.run(main())
