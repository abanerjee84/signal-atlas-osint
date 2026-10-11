"""One bounded collection pass for public additions; never starts or stops a server."""

import argparse
import asyncio
import json
import ssl

import httpx

from backend.config import Settings
from backend.connectors.base import SafeHTTP
from backend.connectors.public_discussion import discussion_feeds
from backend.connectors.registry import connectors
from backend.connectors.threat_reports import threat_feeds
from backend.connectors.world_feeds import world_feeds
from backend.database import Database
from backend.models import stamp
from backend.worker import collect


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", help="Collect only this source ID; repeat for more")
    args = parser.parse_args()
    settings = Settings()
    database = Database(settings.database)
    # Uses the already initialized running database; no migration or resident worker.
    if not settings.database.exists():
        raise RuntimeError("Start the installed application yourself before this collection pass")
    providers = threat_feeds(settings) + world_feeds(settings) + discussion_feeds(settings)
    providers += [
        provider
        for provider in connectors(settings)
        if provider.source_id.startswith("reddit_")
        and "archive" not in provider.source_id
        and not getattr(provider, "manual", False)
    ]
    gate = asyncio.Semaphore(2)
    if args.source:
        providers = [provider for provider in providers if provider.source_id in args.source]
        if set(args.source) != {provider.source_id for provider in providers}:
            raise ValueError("Unknown source ID")
    async with httpx.AsyncClient(
        timeout=settings.http_timeout,
        verify=ssl.create_default_context(),
        headers={"User-Agent": "SignalAtlas/0.1 public-source-research"},
        limits=httpx.Limits(max_connections=2),
    ) as client:
        http = SafeHTTP(settings, client)

        async def run(provider):
            async with gate:
                statuses = {row["source_id"]: row for row in await asyncio.to_thread(database.statuses)}
                previous = statuses.get(provider.source_id, {})
                if previous.get("next_run") and previous["next_run"] > stamp():
                    return {
                        "source_id": provider.source_id,
                        "state": "deferred",
                        "next_run": previous["next_run"],
                    }
                return await collect(provider, database, http)

        results = await asyncio.gather(*(run(provider) for provider in providers))
    # Aggregate proof contains no posts, private cases, locations of individuals or credentials.
    proof = {"checked_at": stamp(), "server_lifecycle_actions": 0, "results": results}
    print(json.dumps(proof, indent=2))
    proof_directory = settings.database.parent / "run"
    proof_directory.mkdir(parents=True, exist_ok=True)
    (proof_directory / "public-updates-verification.json").write_text(
        json.dumps(proof, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    asyncio.run(main())
