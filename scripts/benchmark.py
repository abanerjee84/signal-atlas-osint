"""Bounded performance sample with synthetic records in an isolated temporary database."""

import asyncio
import json
import platform
import statistics
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path

import httpx
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.config import Settings
from backend.main import create_app
from backend.models import Report, utcnow


async def run():
    began = time.perf_counter()
    process = psutil.Process()
    with tempfile.TemporaryDirectory(prefix="osint-benchmark-") as directory:
        settings = Settings(_env_file=None, database=Path(directory) / "synthetic.sqlite3")
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            database = app.state.database
            template = Report(
                external_id="synthetic",
                source_id="synthetic",
                source_url="https://example.org/synthetic",
                title="Synthetic benchmark observation",
                description="Synthetic record for isolated performance tests. " * 8,
                category="environment",
                latitude=20,
                longitude=78,
                published_at=utcnow(),
            )
            ingestion_began = time.perf_counter()
            for offset in range(0, 10000, 100):
                database.ingest_many(
                    [
                        template.model_copy(
                            update={
                                "external_id": str(index),
                                "published_at": utcnow() - timedelta(minutes=index),
                                "source_url": f"https://example.org/synthetic/{index}",
                            }
                        )
                        for index in range(offset, offset + 100)
                    ]
                )
            ingestion_seconds = time.perf_counter() - ingestion_began
            memory_after_ingestion = process.memory_info().rss
            durations, peaks = [], []
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, client=("benchmark", 123)), base_url="http://benchmark"
            ) as client:
                for _ in range(5):
                    await client.get("/api/events?limit=500")
                for _ in range(60):
                    request_began = time.perf_counter()
                    response = await client.get("/api/events?categories=environment&country=IN&limit=500")
                    assert response.status_code == 200
                    assert response.json()["total"] == 10000
                    durations.append((time.perf_counter() - request_began) * 1000)
                    peaks.append(process.memory_info().rss)
                concurrent_began = time.perf_counter()
                results = await asyncio.gather(*(client.get("/api/events?limit=100") for _ in range(20)))
                assert all(response.status_code == 200 for response in results)
                concurrency_ms = (time.perf_counter() - concurrent_began) * 1000
            result = {
                "timestamp_utc": utcnow().isoformat(),
                "environment": {
                    "os": platform.platform(),
                    "python": platform.python_version(),
                    "cpu_logical": psutil.cpu_count(),
                    "ram_bytes": psutil.virtual_memory().total,
                },
                "dataset": "10,000 synthetic environment observations; isolated temporary database deleted afterward",
                "transport": "In-process ASGI HTTP; no network or proxy. OS file cache warm. Not an Ubuntu deployment soak test.",
                "ingestion_seconds": round(ingestion_seconds, 2),
                "event_query_samples": len(durations),
                "event_query_p50_ms": round(statistics.median(durations), 2),
                "event_query_p95_ms": round(sorted(durations)[56], 2),
                "twenty_concurrent_requests_ms": round(concurrency_ms, 2),
                "memory_after_ingestion_bytes": memory_after_ingestion,
                "memory_peak_polling_bytes": max(peaks),
                "memory_after_polling_bytes": process.memory_info().rss,
                "database_bytes": settings.database.stat().st_size,
                "total_seconds": round(time.perf_counter() - began, 2),
                "limitation": "A short regression sample cannot establish long-running leak absence, 30 FPS map performance or target-hardware acceptance.",
            }
    (Path(__file__).resolve().parent.parent / "docs/benchmark.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


asyncio.run(run())
