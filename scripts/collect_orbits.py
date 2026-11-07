"""Download public orbital-element files; publish a local snapshot, never a server."""

import asyncio
import io
import json
import math
import ssl
import urllib.error
import urllib.request
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.config import ROOT
from backend.models import stamp
from backend.orbital_catalog import mission_metadata
from scripts.collection_status import write_status

INTERVAL = 6 * 3600
MAX_BYTES = 2 * 1024 * 1024
SOURCES = {
    "CelesTrak": "https://celestrak.org/NORAD/elements/gp.php?GROUP=visual&FORMAT=json",
    "CelesTrak Military": "https://celestrak.org/NORAD/elements/gp.php?GROUP=military&FORMAT=json",
    "CelesTrak GEO": "https://celestrak.org/NORAD/elements/gp.php?GROUP=geo&FORMAT=json",
    "CelesTrak GPS": "https://celestrak.org/NORAD/elements/gp.php?GROUP=gps-ops&FORMAT=json",
    "AMSAT": "https://www.amsat.org/tle/current/nasabare.txt",
    "McCants observers": "https://www.mmccants.org/tles/classfd.zip",
}


def current_epoch(epoch, now):
    return -86400 <= (now - epoch).total_seconds() <= 14 * 86400


def parse_omm(text, source, now=None):
    """CelesTrak OMM JSON supports six-digit catalogue identifiers."""
    now = now or datetime.now(timezone.utc)
    records = json.loads(text)
    if not isinstance(records, list) or len(records) > 10000:
        raise ValueError("Invalid OMM collection")
    items = []
    for record in records:
        try:
            identifier = record["NORAD_CAT_ID"]
            if isinstance(identifier, bool) or int(identifier) != identifier or not 1 <= identifier <= 999999:
                continue
            metadata = mission_metadata(str(identifier).zfill(5), record["OBJECT_NAME"], source)
            if not metadata:
                continue
            epoch = datetime.fromisoformat(record["EPOCH"].replace("Z", "+00:00"))
            if epoch.tzinfo is None:
                epoch = epoch.replace(tzinfo=timezone.utc)
            fields = [
                "MEAN_MOTION",
                "ECCENTRICITY",
                "INCLINATION",
                "RA_OF_ASC_NODE",
                "ARG_OF_PERICENTER",
                "MEAN_ANOMALY",
                "BSTAR",
                "MEAN_MOTION_DOT",
                "MEAN_MOTION_DDOT",
            ]
            values = {key: float(record[key]) for key in fields}
            if not all(math.isfinite(value) for value in values.values()) or not current_epoch(epoch, now):
                continue
            if not (
                0 < values["MEAN_MOTION"] <= 18
                and 0 <= values["ECCENTRICITY"] < 1
                and 0 <= values["INCLINATION"] <= 180
            ):
                continue
            if not all(0 <= values[key] <= 360 for key in fields[3:6]):
                continue
            items.append(
                {
                    **metadata,
                    "catalog_id": identifier,
                    "omm": {**record, **values},
                    "epoch": epoch.isoformat(),
                    "period_minutes": round(1440 / values["MEAN_MOTION"], 2),
                    "inclination_deg": values["INCLINATION"],
                    "eccentricity": values["ECCENTRICITY"],
                    "source": source,
                    "source_url": SOURCES[source],
                    "element_basis": "Public catalogue elements",
                }
            )
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            continue
    return items


def parse_tle(text, source, now=None):
    now = now or datetime.now(timezone.utc)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    items = []
    for index, line in enumerate(lines[:-1]):
        if not line.startswith("1 ") or not lines[index + 1].startswith("2 "):
            continue
        second = lines[index + 1]
        number = line[2:7]
        if not number.isdigit() or number != second[2:7] or len(line) < 69 or len(second) < 69:
            continue
        try:
            raw_name = lines[index - 1] if index and not lines[index - 1].startswith(("1 ", "2 ")) else ""
            metadata = mission_metadata(number, raw_name, source)
            if not metadata:
                continue
            # Checksum includes digits and '-' as one; malformed elements never reach the map.
            for tle in (line, second):
                total = sum(int(ch) if ch.isdigit() else 1 if ch == "-" else 0 for ch in tle[:68])
                if total % 10 != int(tle[68]):
                    raise ValueError("TLE checksum")
            year = int(line[18:20])
            year += 2000 if year < 57 else 1900
            epoch = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=float(line[20:32]) - 1)
            if not current_epoch(epoch, now):
                continue
            motion = float(second[52:63])
            eccentricity = float("0." + second[26:33])
            if (
                not math.isfinite(motion)
                or not 0 < motion <= 18
                or not 0 <= float(second[8:16]) <= 180
                or not 0 <= eccentricity < 1
            ):
                continue
        except (ValueError, OverflowError):
            continue
        items.append(
            {
                **metadata,
                "catalog_id": int(number),
                "tle1": line,
                "tle2": second,
                "epoch": epoch.isoformat(),
                "period_minutes": round(1440 / motion, 2),
                "inclination_deg": float(second[8:16]),
                "eccentricity": eccentricity,
                "source": source,
                "source_url": SOURCES[source],
                "element_basis": "Observer-derived elements"
                if source == "McCants observers"
                else "Public catalogue elements",
            }
        )
    return items


def collect_orbits(root=ROOT, now=None):
    now = now or datetime.now(timezone.utc)
    path = Path(root) / "public" / "orbital-elements.json"
    cache = Path(root) / "data" / "run" / "orbital-sources.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        previous = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    sources = {}
    for name, url in SOURCES.items():
        saved = previous.get(name, {})
        if saved.get("url") == url and saved.get("blocked_http"):
            sources[name] = saved
            continue
        try:
            due = (now - datetime.fromisoformat(saved["attempted_at"])).total_seconds() >= INTERVAL
        except (KeyError, ValueError):
            due = True
        if not due and saved.get("url", url) == url:
            sources[name] = saved
            continue
        saved = {**saved, "url": url, "attempted_at": now.isoformat()}
        saved.pop("blocked_http", None)
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
                if name == "McCants observers":
                    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                        entry = next(
                            info for info in archive.infolist() if info.filename.lower().endswith(".tle")
                        )
                        if entry.file_size > MAX_BYTES:
                            raise ValueError("Oversized element archive")
                        items = parse_tle(archive.read(entry).decode("utf-8"), name, now)
                elif "FORMAT=json" in url:
                    items = parse_omm(raw.decode("utf-8"), name, now)
                else:
                    items = parse_tle(raw.decode("utf-8"), name, now)
            if not items:
                raise ValueError("No current catalogued elements")
            saved.update(items=items, state="ok", collected_at=now.isoformat())
            saved.pop("error", None)
        except urllib.error.HTTPError as error:
            # Stop querying an HTTP-rejected URL until intervention or URL change.
            saved.update(state="unavailable", error="HTTPError", blocked_http=error.code)
        except Exception as error:
            # Keep last good elements; browser independently rejects old epochs.
            saved.update(state="unavailable", error=type(error).__name__)
        sources[name] = saved
        # Persist each attempt so restarts cannot hammer an unavailable provider.
        write_status(cache, sources | {key: value for key, value in previous.items() if key not in sources})
    newest = {}
    for value in sources.values():
        for item in value.get("items", []):
            try:
                if not current_epoch(datetime.fromisoformat(item["epoch"]), now):
                    continue
            except (KeyError, ValueError, TypeError):
                continue
            metadata = mission_metadata(str(item["catalog_id"]).zfill(5), item["name"], item["source"])
            if not metadata:
                continue
            item = {**item, **metadata}
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
    if not database.lock("collect:orbital-elements", owner, 300):
        return None
    try:
        result = collect_orbits()
        if isinstance(result, dict) and result.get("checked_at"):
            # Archive when this set became known locally; source ages remain in the payload.
            with database.connect() as db:
                db.execute(
                    "INSERT OR IGNORE INTO monitoring_orbits VALUES(?,?)", (stamp(), json.dumps(result))
                )
        return result
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
