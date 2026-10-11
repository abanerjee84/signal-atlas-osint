"""A ten-second data-gathering thread. No listening socket or server lifecycle actions."""

import argparse
import asyncio
import os
import threading
import uuid
from pathlib import Path

from backend.config import ROOT, Settings
from backend.database import Database
from backend.models import stamp
from scripts.collect_orbits import orbital_loop
from scripts.collect_public_updates import collect_once
from scripts.collection_status import write_status
from scripts.threat_table_reader import ThreatTableReader

SOURCE_IDS = ("bitdefender_threatmap", "bunkerweb_threatmap", "imperva_threatmap", "radware_threatmap")
RESEARCH_IDS = ("threat_research_unit42", "threat_research_securelist", "threat_research_mandiant")
INTERVAL = 10


def run_thread(database, chromium=None, rendered_table=True):
    if not database.path.exists():
        raise RuntimeError("The application database must already be initialized")
    owner = uuid.uuid4().hex
    if not database.lock("watch:threatmaps", owner, 30):
        return
    stopped = threading.Event()
    guard = threading.Lock()
    state = {
        "pid": os.getpid(),
        "running": True,
        "interval_seconds": INTERVAL,
        "started_at": stamp(),
        "workspace": str(ROOT),
        "cycles": 0,
    }
    directory = database.path.parent / "run"
    directory.mkdir(parents=True, exist_ok=True)
    heartbeat = directory / "threat-map-thread.json"
    stop_file = directory / "threat-map-thread.stop"
    stop_file.unlink(missing_ok=True)

    def publish():
        with guard:
            state["heartbeat"] = stamp()
            payload = dict(state)
        write_status(heartbeat, payload)

    async def gathering_loop():
        reader = ThreatTableReader(chromium) if rendered_table else None
        policy_cache = {}
        loop = asyncio.get_running_loop()

        async def research_loop():
            while not stopped.is_set():
                try:
                    async with asyncio.timeout(90):
                        result = await collect_once(
                            RESEARCH_IDS, table_reader=reader, robots_cache=policy_cache
                        )
                    with guard:
                        state["research_results"] = [
                            {"source_id": row["source_id"], "state": row["state"]}
                            for row in result["results"]
                        ]
                except Exception as error:
                    with guard:
                        state["research_error"] = "Research scrape failed (" + type(error).__name__ + ")"
                await asyncio.to_thread(stopped.wait, 60)

        research = asyncio.create_task(research_loop())
        orbits = asyncio.create_task(orbital_loop(stopped, database))
        try:
            while not stopped.is_set():
                began = loop.time()
                with guard:
                    state["last_cycle_started"] = stamp()
                try:
                    async with asyncio.timeout(30):
                        result = await collect_once(
                            SOURCE_IDS, table_reader=reader, robots_cache=policy_cache
                        )
                    with guard:
                        state["last_results"] = [
                            {"source_id": row["source_id"], "state": row["state"]}
                            for row in result["results"]
                        ]
                        state.pop("error", None)
                except Exception as error:
                    with guard:
                        state["error"] = "Collection cycle failed (" + type(error).__name__ + ")"
                        state["last_results"] = []
                with guard:
                    state["cycles"] += 1
                    state["last_cycle_finished"] = stamp()
                    state["last_cycle_seconds"] = round(loop.time() - began, 2)
                # One sequential loop: overruns never launch overlapping collectors.
                await asyncio.to_thread(stopped.wait, max(0, INTERVAL - (loop.time() - began)))
        finally:
            research.cancel()
            orbits.cancel()
            await asyncio.gather(research, orbits, return_exceptions=True)
            if reader:
                await reader.close()

    def gather():
        asyncio.run(gathering_loop())

    publish()
    thread = threading.Thread(target=gather, name="public-threat-map-gathering", daemon=True)
    thread.start()
    try:
        while thread.is_alive() and not stopped.wait(5):
            if stop_file.exists():
                break
            if not database.renew_lock("watch:threatmaps", owner, 30):
                break
            publish()
    except KeyboardInterrupt:
        pass
    finally:
        stopped.set()
        thread.join(timeout=35)
        with guard:
            state["running"] = False
        publish()
        database.unlock("watch:threatmaps", owner)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true", help="Run the explicitly requested background thread")
    parser.add_argument("--workspace", type=Path, default=ROOT)
    parser.add_argument("--chromium", help="Optional installed Chromium path for the ATTACK table")
    parser.add_argument("--no-browser", action="store_true", help="Use the legacy HTTP transport only")
    args = parser.parse_args()
    if args.workspace.resolve() != ROOT.resolve():
        raise ValueError("Wrong project workspace")
    if args.watch:
        run_thread(Database(Settings().database), args.chromium, not args.no_browser)
    else:
        asyncio.run(collect_once(SOURCE_IDS))


if __name__ == "__main__":
    main()
