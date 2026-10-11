"""Download public orbital-element files; publish a local snapshot, never a server."""

import asyncio
import json
import ssl
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.config import ROOT
from backend.models import stamp
from scripts.collection_status import write_status

INTERVAL = 6 * 3600
MAX_BYTES = 1024 * 1024
SOURCES = {
    "CelesTrak": "https://celestrak.org/NORAD/elements/gp.php?GROUP=visual&FORMAT=tle",
    "AMSAT": "https://www.amsat.org/tle/current/nasabare.txt",
}
# Publicly catalogued spacecraft only. Rocket bodies and debris are excluded.
CATALOG = {
    "25544": ("ISS", "International Space Station"),
    "48274": ("Tiangong", "Crewed space station"),
    "20580": ("Hubble", "Space telescope"),
    "25994": ("Terra", "Earth observation"),
    "27424": ("Aqua", "Earth observation"),
    "31598": ("COSMO-SkyMed 1", "Radar Earth observation"),
    "39766": ("ALOS-2", "Radar Earth observation"),
    "43641": ("SAOCOM 1A", "Radar Earth observation"),
    "46265": ("SAOCOM 1B", "Radar Earth observation"),
    "57800": ("XRISM", "X-ray observatory"),
    "43700": ("QO-100", "Amateur radio communications"),
    "07530": ("AO-7", "Amateur radio satellite"),
    "39444": ("AO-73", "Educational satellite"),
    "44909": ("RS-44", "Amateur radio satellite"),
    "41603": ("LAPAN-A3", "Earth observation"),
}


def parse_tle(text, source, now=None):
    now = now or datetime.now(timezone.utc)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    items = []
    for index, line in enumerate(lines[:-1]):
        if not line.startswith("1 ") or not lines[index + 1].startswith("2 "):
            continue
        second = lines[index + 1]
        number = line[2:7]
        if number not in CATALOG or number != second[2:7] or len(line) < 69 or len(second) < 69:
            continue
        try:
            # Checksum includes digits and '-' as one; malformed elements never reach the map.
            for tle in (line, second):
                total = sum(int(ch) if ch.isdigit() else 1 if ch == "-" else 0 for ch in tle[:68])
                if total % 10 != int(tle[68]):
                    raise ValueError("TLE checksum")
            year = int(line[18:20])
            year += 2000 if year < 57 else 1900
            epoch = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=float(line[20:32]) - 1)
            if abs((now - epoch).total_seconds()) > 14 * 86400:
                continue
            motion = float(second[52:63])
            if motion <= 0 or not 0 <= float(second[8:16]) <= 180:
                continue
        except (ValueError, OverflowError):
            continue
        name, purpose = CATALOG[number]
        items.append(
            {
                "catalog_id": int(number),
                "name": name,
                "purpose": purpose,
                "tle1": line,
                "tle2": second,
                "epoch": epoch.isoformat(),
                "period_minutes": round(1440 / motion, 2),
                "source": source,
                "source_url": SOURCES[source],
            }
        )
    return items


def collect_orbits(root=ROOT, now=None):
    now = now or datetime.now(timezone.utc)
    path = Path(root) / "public" / "orbital-elements.json"
    cache = Path(root) / "data" / "run" / "orbital-sources.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    try:
        previous = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    sources = {}
    for name, url in SOURCES.items():
        saved = previous.get(name, {})
        try:
            due = (now - datetime.fromisoformat(saved["attempted_at"])).total_seconds() >= INTERVAL
        except (KeyError, ValueError):
            due = True
        if not due:
            sources[name] = saved
            continue
        saved = {**saved, "attempted_at": now.isoformat()}
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "SignalAtlas/0.1 (public orbital elements)", "Accept": "text/plain"},
            )
            with urllib.request.urlopen(
                request, timeout=20, context=ssl.create_default_context()
            ) as response:
                raw = response.read(MAX_BYTES + 1)
                if response.status != 200 or len(raw) > MAX_BYTES:
                    raise ValueError("Invalid element download")
                items = parse_tle(raw.decode("utf-8"), name, now)
            if not items:
                raise ValueError("No current catalogued elements")
            saved.update(items=items, state="ok", collected_at=now.isoformat())
            saved.pop("error", None)
        except Exception as error:
            # Keep last good elements; browser independently rejects old epochs.
            saved.update(state="unavailable", error=type(error).__name__)
        sources[name] = saved
        # Persist each attempt so restarts cannot hammer an unavailable provider.
        write_status(cache, sources | {key: value for key, value in previous.items() if key not in sources})
    newest = {}
    for value in sources.values():
        for item in value.get("items", []):
            old = newest.get(item["catalog_id"])
            if not old or item["epoch"] > old["epoch"]:
                newest[item["catalog_id"]] = item
    payload = {
        "checked_at": stamp(),
        "items": list(newest.values()),
        "sources": [
            {"name": name, "state": value.get("state"), "collected_at": value.get("collected_at")}
            for name, value in sources.items()
        ],
    }
    write_status(path, payload, allow_inplace=True)
    return payload


async def orbital_loop(stopped, database=None):
    while not stopped.is_set():
        try:
            if database:
                await asyncio.to_thread(collect_orbits_locked, database)
            else:
                await asyncio.to_thread(collect_orbits)
        except OSError:
            # A temporarily locked runtime file must not end scheduled collection.
            pass
        await asyncio.to_thread(stopped.wait, 3600)


def collect_orbits_locked(database):
    """A shared lease prevents the main worker and dedicated gatherer overlapping."""
    owner = uuid.uuid4().hex
    if not database.lock("collect:orbital-elements", owner, 90):
        return None
    try:
        return collect_orbits()
    finally:
        database.unlock("collect:orbital-elements", owner)


if __name__ == "__main__":
    from backend.config import Settings
    from backend.database import Database

    result = collect_orbits_locked(Database(Settings().database))
    print(
        f"Published {len(result['items'])} public satellite element sets"
        if result
        else "Orbital collector already running"
    )
