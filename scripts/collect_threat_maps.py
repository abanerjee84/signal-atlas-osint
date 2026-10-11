"""A two-minute data-gathering thread. No listening socket or server lifecycle actions."""

import argparse
import asyncio
import os
import threading
import time
import uuid
from pathlib import Path

from backend.config import ROOT, Settings
from backend.database import Database
from backend.models import stamp
from scripts.collect_public_updates import collect_once
from scripts.collection_status import write_status

SOURCE_IDS = ("bitdefender_threatmap", "bunkerweb_threatmap")
INTERVAL = 120


def run_thread(database):
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

    def publish():
        with guard:
            state["heartbeat"] = stamp()
            payload = dict(state)
        write_status(heartbeat, payload)

    def gather():
        while not stopped.is_set():
            began = time.monotonic()
            with guard:
                state["last_cycle_started"] = stamp()
            try:
                result = asyncio.run(collect_once(SOURCE_IDS))
                with guard:
                    state["last_results"] = [
                        {"source_id": row["source_id"], "state": row["state"]} for row in result["results"]
                    ]
                    state.pop("error", None)
            except Exception as error:
                with guard:
                    state["error"] = "Collection cycle failed (" + type(error).__name__ + ")"
                    state["last_results"] = []
            with guard:
                state["cycles"] += 1
                state["last_cycle_finished"] = stamp()
            stopped.wait(max(0, INTERVAL - (time.monotonic() - began)))

    publish()
    thread = threading.Thread(target=gather, name="public-threat-map-gathering", daemon=True)
    thread.start()
    try:
        while thread.is_alive() and not stopped.wait(5):
            if not database.renew_lock("watch:threatmaps", owner, 30):
                break
            publish()
    except KeyboardInterrupt:
        pass
    finally:
        stopped.set()
        with guard:
            state["running"] = False
        publish()
        database.unlock("watch:threatmaps", owner)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true", help="Run the explicitly requested background thread")
    parser.add_argument("--workspace", type=Path, default=ROOT)
    args = parser.parse_args()
    if args.workspace.resolve() != ROOT.resolve():
        raise ValueError("Wrong project workspace")
    if args.watch:
        run_thread(Database(Settings().database))
    else:
        asyncio.run(collect_once(SOURCE_IDS))


if __name__ == "__main__":
    main()
