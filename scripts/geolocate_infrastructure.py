"""Bounded country enrichment of existing public-IP observations; no server lifecycle actions."""

import argparse
import asyncio
import json

import httpx

from backend.config import Settings
from backend.database import Database
from backend.infrastructure_geo import enrich_locations
from backend.tls import outbound_tls


async def run(limit):
    settings = Settings()
    database = Database(settings.database)
    database.initialize()
    async with httpx.AsyncClient(verify=outbound_tls(), timeout=8) as client:
        result = await enrich_locations(database, settings, client, limit=limit)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, choices=range(1, 51), default=50)
    asyncio.run(run(parser.parse_args().limit))
