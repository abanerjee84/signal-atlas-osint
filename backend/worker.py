"""Separate bounded scheduler; python -m backend.worker [--once] [--source usgs]."""

import argparse
import asyncio
import json
import logging
import signal
import sqlite3
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


def database_busy(error):
    return isinstance(error, sqlite3.OperationalError) and (
        (getattr(error, "sqlite_errorcode", 0) or 0) & 255 in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
        or str(error) in {"database is locked", "database table is locked", "database schema is locked"}
    )


async def database_call(operation, *args, **kwargs):
    """Retry rolled-back database operations, never repeat an upstream download."""
    for attempt in range(3):
        try:
            return await asyncio.to_thread(operation, *args, **kwargs)
        except sqlite3.OperationalError as error:
            if not database_busy(error) or attempt == 2:
                raise
            await asyncio.sleep(0.25 * (attempt + 1))


async def repeat_job(operation, stopped, interval, once=False):
    """A busy database delays this lane without permanently ending collection."""
    while not stopped.is_set():
        try:
            await operation()
        except sqlite3.OperationalError as error:
            if once or not database_busy(error):
                raise
            log.warning("Database busy; collector will retry after a short pause")
        if once:
            break
        try:
            await asyncio.wait_for(stopped.wait(), timeout=interval)
        except TimeoutError:
            pass


async def collect(provider: Connector, database: Database, http: SafeHTTP) -> dict:
    owner = uuid.uuid4().hex
    identifier = "collect:" + provider.source_id
    if not await database_call(database.lock, identifier, owner, 600):
        return {"source_id": provider.source_id, "state": "already_running"}
    began = time.monotonic()
    try:
        if requirement := provider.access():
            await database_call(
                database.set_status, provider.source_id, state="access_required", error=requirement
            )
            return {"source_id": provider.source_id, "state": "access_required"}
        await database_call(database.set_status, provider.source_id, state="fetching", last_attempt=stamp())
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
                    await database_call(database.ingest_many, pending)
                    stored += len(pending)
                    pending = []
            if getattr(provider, "live_aircraft", False):
                from .aviation import save_snapshot

                if selected and not pending:
                    raise ProviderError("All provider records failed validation")
                stored = await database_call(save_snapshot, database, pending)
            elif provider.snapshot:
                if records and not pending:
                    raise ProviderError("All provider records failed validation")
                stored = await database_call(database.replace_social_snapshot, provider.source_id, pending)
            elif pending:
                await database_call(database.ingest_many, pending)
                stored += len(pending)
            if selected and not stored:
                raise ProviderError("All provider records failed validation")
            if getattr(provider, "telemetry", False):
                await database_call(database.prune_threat_telemetry, provider.source_id)
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
        await database_call(database.set_status, provider.source_id, **result)
        log.info(json.dumps({"source_id": provider.source_id, **result}))
        return {"source_id": provider.source_id, **result}
    except Exception as error:
        if database_busy(error):
            # Do not mislabel local contention as a provider outage or consume
            # provider quota by refetching during the database retry sequence.
            raise
        # Never log raw provider exceptions: URLs can contain credentials.
        message = (
            str(error) if isinstance(error, ProviderError) else f"Collection failed ({type(error).__name__})"
        )
        await database_call(
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
        await database_call(database.unlock, identifier, owner)


async def run(once: bool = False, source: str | None = None):
    settings = Settings()
    database = Database(settings.database)
    await database_call(database.initialize)
    from .advanced.repository import Repository
    from .advanced.tasks import tick as investigation_tick

    await database_call(Repository(database).register, connectors(settings))
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
    # httpx's bundled certificate store, not the platform store: on Windows
    # the system context prefers expired cross-signed intermediates and
    # rejects chains that verify fine everywhere else.
    async with httpx.AsyncClient(
        timeout=settings.http_timeout,
        verify=True,
        limits=httpx.Limits(max_connections=4),
        headers={"User-Agent": "GlobalOSINT/0.1 public-source-research"},
    ) as client:
        http = SafeHTTP(settings, client)
        local_deadlines = {}

        async def execute(provider):
            scheduled = utcnow()
            async with semaphore:
                local_deadlines[provider.source_id] = time.monotonic() + provider.interval
                result = await collect(provider, database, http)
                if result["state"] == "error":
                    local_deadlines[provider.source_id] = time.monotonic() + max(
                        provider.interval, result.get("retry_after", 300)
                    )
                # A second worker also consults persisted next_run before scheduling.
                await database_call(
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
        async def aircraft_poll(provider):
            from .aviation_demand import aviation_requested

            if not await database_call(aviation_requested, database):
                return
            if local_deadlines.get(provider.source_id, 0) > time.monotonic():
                return
            rows = {item["source_id"]: item for item in await database_call(database.statuses)}
            current = rows.get(provider.source_id, {})
            with database.connect() as db:
                enabled = db.execute(
                    "SELECT enabled FROM sources WHERE source_id=?", (provider.source_id,)
                ).fetchone()
            if enabled and enabled[0] and (not current.get("next_run") or current["next_run"] <= stamp()):
                began = utcnow()
                # Keep the provider cadence even if saving next_run later is
                # blocked by another local writer.
                local_deadlines[provider.source_id] = time.monotonic() + provider.interval
                result = await collect(provider, database, http)
                if result["state"] == "error":
                    local_deadlines[provider.source_id] = time.monotonic() + max(
                        provider.interval, result.get("retry_after", 300)
                    )
                deadline = (
                    utcnow() + timedelta(seconds=max(provider.interval, result.get("retry_after", 300)))
                    if result["state"] == "error"
                    else max(utcnow(), began + timedelta(seconds=provider.interval))
                )
                await database_call(database.set_status, provider.source_id, next_run=stamp(deadline))

        async def aircraft_loop(provider):
            await repeat_job(lambda: aircraft_poll(provider), stopped, 5)

        # Public orbital files have an independent slow lane. Positions are
        # computed in the browser; no per-position upstream requests are made.
        async def orbital_updates():
            from scripts.collect_orbits import collect_orbits_locked

            while not stopped.is_set():
                try:
                    await asyncio.to_thread(collect_orbits_locked, database)
                except OSError:
                    log.warning("Orbital snapshot temporarily unavailable")
                except sqlite3.OperationalError as error:
                    if not database_busy(error):
                        raise
                    log.warning("Database busy; orbital collection deferred")
                try:
                    await asyncio.wait_for(stopped.wait(), timeout=3600)
                except TimeoutError:
                    pass

        aircraft_tasks = []
        if not once:
            if not source:
                aircraft_tasks.append(asyncio.create_task(orbital_updates()))
            if not source or source == "opensky":
                from .aircraft_details import details_loop

                aircraft_tasks.append(asyncio.create_task(details_loop(database, stopped, require_viewer=True)))
            for provider in providers:
                if getattr(provider, "live_aircraft", False):
                    current = next(
                        (
                            row
                            for row in await database_call(database.statuses)
                            if row["source_id"] == provider.source_id
                        ),
                        {},
                    )
                    if current.get("state") == "ok" and (current.get("next_run") or "") > stamp(
                        utcnow() + timedelta(seconds=provider.interval)
                    ):
                        await database_call(database.set_status, provider.source_id, next_run=stamp())
                    aircraft_tasks.append(asyncio.create_task(aircraft_loop(provider)))

        def update_heartbeat():
            with database.connect() as db:
                db.execute(
                    "INSERT INTO worker_state VALUES (1,?) ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat",
                    (stamp(),),
                )

        async def cycle():
            nonlocal last_maintenance
            enabled = {
                row["source_id"]
                for row in Repository(database).rows("SELECT source_id FROM sources WHERE enabled=1")
            }
            statuses = {item["source_id"]: item for item in database.statuses()}
            due = [
                provider
                for provider in providers
                if provider.source_id in enabled
                and local_deadlines.get(provider.source_id, 0) <= time.monotonic()
                and (once or not getattr(provider, "live_aircraft", False))
                and (
                    once
                    or not statuses.get(provider.source_id, {}).get("next_run")
                    or statuses[provider.source_id]["next_run"] <= stamp()
                )
            ]
            results = await asyncio.gather(*(execute(provider) for provider in due), return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    raise result
            await investigation_tick(database, settings, client)
            await database_call(update_heartbeat)
            if time.monotonic() - last_maintenance > 3600:
                await database_call(database.maintenance, settings)
                last_maintenance = time.monotonic()

        try:
            await repeat_job(cycle, stopped, 15, once=once)
        finally:
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
