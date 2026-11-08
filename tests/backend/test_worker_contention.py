import asyncio
import sqlite3
from contextlib import suppress

import pytest

from backend.aviation import current_aircraft
from backend.connectors.opensky import OpenSky
from backend.models import Filters, utcnow
from backend.worker import run


async def test_collector_heartbeat_updates_during_a_slow_source_cycle(settings, database, monkeypatch):
    from backend.connectors.expanded import NWS

    started = asyncio.Event()
    provider = NWS(settings)

    async def slow_fetch(_):
        started.set()
        await asyncio.Event().wait()

    provider.fetch = slow_fetch
    monkeypatch.setattr("backend.worker.Settings", lambda: settings)
    monkeypatch.setattr("backend.worker.Database", lambda _: database)
    monkeypatch.setattr("backend.worker.connectors", lambda _: [provider])
    monkeypatch.setattr("backend.worker.browser_executable", lambda: None)
    task = asyncio.create_task(run(source="nws_alerts"))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)

        async def heartbeat():
            while True:
                with database.connect() as db:
                    row = db.execute("SELECT heartbeat FROM worker_state WHERE id=1").fetchone()
                if row:
                    return row[0]
                await asyncio.sleep(0.02)

        assert await asyncio.wait_for(heartbeat(), timeout=2)
        assert not task.done()  # The source has not completed, but the worker is alive.
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def test_busy_lane_survives_and_non_contention_errors_are_not_hidden():
    from backend.worker import repeat_job

    stopped = asyncio.Event()
    calls = []

    async def transient():
        calls.append(1)
        if len(calls) == 1:
            error = sqlite3.OperationalError("database is locked")
            error.sqlite_errorcode = sqlite3.SQLITE_BUSY_SNAPSHOT
            raise error
        stopped.set()

    await asyncio.wait_for(repeat_job(transient, stopped, 0.001), timeout=2)
    assert len(calls) == 2

    async def broken_schema():
        raise sqlite3.OperationalError("no such table: aircraft_snapshot")

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        await repeat_job(broken_schema, asyncio.Event(), 0.001)


async def test_worker_retries_lease_cleanup_without_refetching_aircraft(settings, database, monkeypatch):
    """The local crash escaped collect's finally block and ended the scheduler."""
    settings.opensky_client_id = settings.opensky_client_secret = "synthetic"
    provider = OpenSky(settings)
    now = int(utcnow().timestamp())
    calls = []

    async def fetch(_):
        calls.append(1)
        return [
            {
                "state": [
                    "abcdef",
                    "TEST123",
                    "Synthetic",
                    now,
                    now,
                    75,
                    20,
                    10000,
                    False,
                    250,
                    90,
                    0,
                    None,
                    10100,
                    None,
                    False,
                    0,
                    4,
                ],
                "time": now,
            }
        ]

    provider.fetch = fetch
    monkeypatch.setattr("backend.worker.Settings", lambda: settings)
    monkeypatch.setattr("backend.worker.Database", lambda _: database)
    monkeypatch.setattr("backend.worker.connectors", lambda _: [provider])

    async def no_investigation_work(*_):
        pass

    monkeypatch.setattr("backend.advanced.tasks.tick", no_investigation_work)
    unlock = database.unlock
    attempts = []

    def transient_lock(name, owner):
        if name == "collect:opensky":
            attempts.append(1)
            if len(attempts) == 1:
                error = sqlite3.OperationalError("database is locked")
                error.sqlite_errorcode = sqlite3.SQLITE_BUSY
                raise error
        return unlock(name, owner)

    monkeypatch.setattr(database, "unlock", transient_lock)
    await run(once=True, source="opensky")
    assert calls == [1]
    assert len(attempts) == 2
    assert database.statuses()[0]["state"] == "ok"
    assert len(current_aircraft(database, Filters())["items"]) == 1
    with database.connect() as db:
        assert not db.execute("SELECT 1 FROM job_locks WHERE name='collect:opensky'").fetchone()
