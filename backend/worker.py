"""Separate bounded scheduler; python -m backend.worker [--once] [--source usgs]."""

import argparse
import asyncio
import json
import logging
import signal
import ssl
import time
import uuid
from contextlib import suppress
from datetime import timedelta

import httpx

from .config import Settings
from .connectors.base import Connector, ProviderError, SafeHTTP
from .connectors.registry import connectors
from .database import Database
from .models import stamp, utcnow

log = logging.getLogger("osint.worker")


async def collect(provider: Connector, database: Database, http: SafeHTTP) -> dict:
    owner = uuid.uuid4().hex
    identifier = "collect:" + provider.source_id
    if not await asyncio.to_thread(database.lock, identifier, owner, 600):
        return {"source_id": provider.source_id, "state": "already_running"}
    began = time.monotonic()
    try:
        if requirement := provider.access():
            await asyncio.to_thread(
                database.set_status, provider.source_id, state="access_required", error=requirement
            )
            return {"source_id": provider.source_id, "state": "access_required"}
        await asyncio.to_thread(
            database.set_status, provider.source_id, state="fetching", last_attempt=stamp()
        )
        # Whole-job timeout keeps lock lease longer than the job, including normalization/storage.
        async with asyncio.timeout(480):
            records = await provider.fetch(http)
            if not isinstance(records, list):
                raise ValueError("Provider returned invalid record collection")
            stored, rejected = 0, 0
            pending = []
            selected = provider.select_records(records)
            for record in selected:
                try:
                    normalized = provider.normalize(record)
                except (ValueError, KeyError, TypeError, IndexError, OverflowError, AttributeError):
                    rejected += 1
                    continue
                pending.append(normalized)
                if (
                    len(pending) == 100
                    and not provider.snapshot
                    and not getattr(provider, "live_aircraft", False)
                ):
                    await asyncio.to_thread(database.ingest_many, pending)
                    stored += len(pending)
                    pending = []
            if getattr(provider, "live_aircraft", False):
                from .aviation import save_snapshot

                if selected and not pending:
                    raise ProviderError("All provider records failed validation")
                stored = await asyncio.to_thread(save_snapshot, database, pending)
            elif provider.snapshot:
                if records and not pending:
                    raise ProviderError("All provider records failed validation")
                stored = await asyncio.to_thread(
                    database.replace_social_snapshot, provider.source_id, pending
                )
            elif pending:
                await asyncio.to_thread(database.ingest_many, pending)
                stored += len(pending)
            if selected and not stored:
                raise ProviderError("All provider records failed validation")
            if getattr(provider, "telemetry", False):
                await asyncio.to_thread(database.prune_threat_telemetry, provider.source_id)
            result = {
                "state": "ok",
                "last_success": stamp(),
                "error": None,
                "fetched": len(records),
                "stored": stored,
                "rejected": rejected,
                "truncated": max(0, len(records) - len(selected)),
            }
        result["duration_ms"] = round((time.monotonic() - began) * 1000, 2)
        await asyncio.to_thread(database.set_status, provider.source_id, **result)
        log.info(json.dumps({"source_id": provider.source_id, **result}))
        return {"source_id": provider.source_id, **result}
    except Exception as error:
        # Never log raw provider exceptions: URLs can contain credentials.
        message = (
            str(error) if isinstance(error, ProviderError) else f"Collection failed ({type(error).__name__})"
        )
        await asyncio.to_thread(
            database.set_status,
            provider.source_id,
            state="error",
            error=message,
            duration_ms=round((time.monotonic() - began) * 1000, 2),
            next_run=stamp(
                utcnow() + timedelta(seconds=max(provider.interval, getattr(error, "retry_after", 300)))
            ),
        )
        log.warning(json.dumps({"source_id": provider.source_id, "state": "error", "error": message}))
        return {
            "source_id": provider.source_id,
            "state": "error",
            "error": message,
            "retry_after": getattr(error, "retry_after", 300),
        }
    finally:
        await asyncio.to_thread(database.unlock, identifier, owner)


async def run(once: bool = False, source: str | None = None):
    settings = Settings()
    database = Database(settings.database)
    database.initialize()
    from .advanced.repository import Repository
    from .advanced.tasks import tick as investigation_tick

    Repository(database).register(connectors(settings))
    providers = [
        provider
        for provider in connectors(settings)
        if (not source or provider.source_id == source) and not getattr(provider, "manual", False)
    ]
    if not providers:
        raise ValueError("Unknown source")
    stopped = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, stopped.set)
        except NotImplementedError:
            pass
    semaphore = asyncio.Semaphore(settings.connector_concurrency)
    async with httpx.AsyncClient(
        timeout=settings.http_timeout,
        verify=ssl.create_default_context(),
        limits=httpx.Limits(max_connections=4),
        headers={"User-Agent": "GlobalOSINT/0.1 public-source-research"},
    ) as client:
        http = SafeHTTP(settings, client)

        async def execute(provider):
            scheduled = utcnow()
            async with semaphore:
                result = await collect(provider, database, http)
                # A second worker also consults persisted next_run before scheduling.
                await asyncio.to_thread(
                    database.set_status,
                    provider.source_id,
                    next_run=stamp(
                        utcnow() + timedelta(seconds=max(provider.interval, result.get("retry_after", 300)))
                        if result["state"] == "error"
                        else max(utcnow(), scheduled + timedelta(seconds=provider.interval))
                    ),
                )
                return result

        last_maintenance = 0

        # Frequent aircraft reads have their own bounded lane, so long RSS or
        # archive jobs cannot delay them behind an entire collection cycle.
        async def aircraft_loop(provider):
            while not stopped.is_set():
                rows = {item["source_id"]: item for item in await asyncio.to_thread(database.statuses)}
                current = rows.get(provider.source_id, {})
                with database.connect() as db:
                    enabled = db.execute(
                        "SELECT enabled FROM sources WHERE source_id=?", (provider.source_id,)
                    ).fetchone()
                if enabled and enabled[0] and (not current.get("next_run") or current["next_run"] <= stamp()):
                    began = utcnow()
                    result = await collect(provider, database, http)
                    deadline = (
                        utcnow() + timedelta(seconds=max(provider.interval, result.get("retry_after", 300)))
                        if result["state"] == "error"
                        else max(utcnow(), began + timedelta(seconds=provider.interval))
                    )
                    await asyncio.to_thread(database.set_status, provider.source_id, next_run=stamp(deadline))
                try:
                    await asyncio.wait_for(stopped.wait(), timeout=5)
                except TimeoutError:
                    pass

        aircraft_tasks = []
        if not once:
            for provider in providers:
                if getattr(provider, "live_aircraft", False):
                    current = next(
                        (row for row in database.statuses() if row["source_id"] == provider.source_id), {}
                    )
                    if current.get("state") == "ok" and current.get("next_run", "") > stamp(
                        utcnow() + timedelta(seconds=provider.interval)
                    ):
                        database.set_status(provider.source_id, next_run=stamp())
                    aircraft_tasks.append(asyncio.create_task(aircraft_loop(provider)))
        while not stopped.is_set():
            enabled = {
                row["source_id"]
                for row in Repository(database).rows("SELECT source_id FROM sources WHERE enabled=1")
            }
            statuses = {item["source_id"]: item for item in database.statuses()}
            due = [
                provider
                for provider in providers
                if provider.source_id in enabled
                and (once or not getattr(provider, "live_aircraft", False))
                and (
                    once
                    or not statuses.get(provider.source_id, {}).get("next_run")
                    or statuses[provider.source_id]["next_run"] <= stamp()
                )
            ]
            await asyncio.gather(*(execute(provider) for provider in due))
            await investigation_tick(database, settings, client)
            with database.connect() as db:
                db.execute(
                    "INSERT INTO worker_state VALUES (1,?) ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat",
                    (stamp(),),
                )
            if time.monotonic() - last_maintenance > 3600:
                await asyncio.to_thread(database.maintenance, settings)
                last_maintenance = time.monotonic()
            if once:
                break
            try:
                await asyncio.wait_for(stopped.wait(), timeout=15)
            except TimeoutError:
                pass
        for task in aircraft_tasks:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--source")
    arguments = parser.parse_args()
    asyncio.run(run(arguments.once, arguments.source))
