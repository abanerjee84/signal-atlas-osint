"""Read-only live API benchmark; timings exclude ingestion and external providers."""

import asyncio
import json
import math
import platform
import statistics
import time
from pathlib import Path

import httpx

from backend.config import Settings


async def main():
    settings = Settings()
    headers = {"Authorization": "Bearer " + settings.admin_token}
    result = {
        "environment": platform.platform(),
        "workload": "Retained live database; sequential warm requests, 10 samples/operation; concurrency 1",
        "external_latency_included": False,
        "ubuntu_8gb_acceptance": "not executed",
    }
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", headers=headers, timeout=15) as client:
        records = (await client.get("/api/v1/osint/search?limit=1")).json()
        result["record_count"] = records["meta"]["total"]
        entities = (await client.get("/api/v1/graph/entities?limit=1")).json()
        entity_id = entities["data"][0]["entity_id"]
        paths = {
            "internal_search": "/api/v1/osint/search?q=Ukraine&limit=50",
            "entity_detail": f"/api/v1/graph/entities/{entity_id}",
            "graph_neighborhood": f"/api/v1/graph/neighborhood/{entity_id}?nodes=80&edges=150",
            "narrative_aggregate": "/api/v1/narratives/sentiment",
            "source_registry": "/api/v1/sources?limit=50",
        }
        timings = {}
        for name, path in paths.items():
            samples = []
            for _ in range(10):
                start = time.perf_counter()
                response = await client.get(path)
                response.raise_for_status()
                samples.append((time.perf_counter() - start) * 1000)
            timings[name] = {
                "p95_ms": round(sorted(samples)[math.ceil(0.95*len(samples))-1], 2),
                "median_ms": round(statistics.median(samples), 2),
                "samples": 10,
            }
        result["timings"] = timings
    Path("docs/advanced-benchmark.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
