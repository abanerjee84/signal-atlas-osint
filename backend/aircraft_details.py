"""Callsign lookup and optional credited photos; never replaces OpenSky telemetry.

python -m backend.aircraft_details --callsign BFLO76 --icao24 7cf9cd
python -m backend.aircraft_details --watch   # files only, no listening socket
"""

import argparse
import asyncio
import hashlib
import json
import logging
import re
import ssl
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from urllib.parse import urlencode, urlsplit

from .config import ROOT, Settings
from .database import Database
from .models import stamp, utcnow
from scripts.collection_status import write_status

log = logging.getLogger(__name__)
DB = "https://static.airplanes.live/db/"
CALLS = "https://api.airplanes.live/v2/callsign/"
PHOTOS = "https://api.planespotters.net/pub/photos/hex/"
HOSTS = {"static.airplanes.live", "api.airplanes.live", "api.planespotters.net"}
HEX = re.compile(r"^[0-9a-f]{6}$")
CALLSIGN = re.compile(r"^[A-Z0-9-]{1,8}$")


def callsign(value):
    value = str(value or "").strip().upper()
    return value if CALLSIGN.fullmatch(value) else None


def safe_url(value, host, prefix):
    parts = urlsplit(str(value or ""))
    return (
        str(value) if parts.scheme == "https" and parts.netloc == host
        and parts.path.startswith(prefix) and not parts.fragment else None
    )


def photo_details(payload):
    for item in (payload.get("photos") or [])[:5]:
        if not isinstance(item, dict):
            continue
        thumbnail = item.get("thumbnail_large") or item.get("thumbnail") or {}
        url = safe_url(thumbnail.get("src"), "t.plnspttrs.net", "/") if isinstance(thumbnail, dict) else None
        link = safe_url(item.get("link"), "www.planespotters.net", "/photo/")
        credit = str(item.get("photographer") or "").strip()[:120]
        if url and link and credit:
            return {"url": url, "link": link, "credit": credit}
    return None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class AircraftLookup:
    def __init__(self, cache, now=time.time):
        self.cache, self.now = cache, now
        self.cache.mkdir(parents=True, exist_ok=True)
        self.memory = {}
        self.opener = urllib.request.build_opener(
            NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context())
        )

    def cache_path(self, url):
        return self.cache / (hashlib.sha256(url.encode()).hexdigest() + ".json")

    def saved(self, path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def ready(self, url):
        return self.saved(self.cache_path(url)).get("retry_at", 0) > self.now()

    def json(self, url, ttl):
        host = urlsplit(url).netloc
        if host not in HOSTS or not url.startswith("https://"):
            raise ValueError("Unapproved aircraft source")
        path = self.cache_path(url)
        saved = self.memory.get(url) or self.saved(path)
        if saved.get("retry_at", 0) > self.now():
            return saved.get("data", {}) if self.now() - saved.get("fetched_at", 0) <= 30 * 86400 else {}
        # An access rejection stops this host across query variations.
        host_path = self.cache / (host + ".json")
        if self.saved(host_path).get("retry_at", 0) > self.now():
            return saved.get("data", {}) if self.now() - saved.get("fetched_at", 0) <= 30 * 86400 else {}
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": "SignalAtlas/0.1 (+https://github.com/abanerjee84/signal-atlas-osint)",
                "Accept": "application/json",
            })
            with self.opener.open(request, timeout=15) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError("Aircraft source too large")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Invalid aircraft source")
            saved = {"data": data, "fetched_at": self.now(), "retry_at": self.now() + ttl}
        except (OSError, ValueError) as error:
            code = getattr(error, "code", None)
            delay = 86400 if code in (401, 403, 404) else 900
            if isinstance(error, urllib.error.HTTPError) and code == 429:
                try:
                    delay = max(900, min(86400, int(error.headers.get("Retry-After", 900))))
                except ValueError:
                    pass
            if code in (401, 403, 429):
                write_status(host_path, {"retry_at": self.now() + delay})
            saved = {**saved, "retry_at": self.now() + delay, "error": type(error).__name__}
            log.warning("Aircraft enrichment %s: %s", host, type(error).__name__)
        self.memory[url] = saved
        write_status(path, saved)
        # Registry failures may reuse bounded old identity data; positions are absent.
        return saved.get("data", {}) if self.now() - saved.get("fetched_at", 0) <= 30 * 86400 else {}

    def resolve(self, requested):
        """Batch exact callsigns, then join on ICAO; never accept a namesake flight."""
        names = sorted({name for _, name in requested if name})
        records = {}
        for start in range(0, len(names), 50):
            data = self.json(CALLS + ",".join(names[start:start + 50]), 300)
            for item in (data.get("ac") or [])[:1000]:
                if isinstance(item, dict):
                    identifier = str(item.get("hex", "")).lower()
                    if HEX.fullmatch(identifier):
                        records[(identifier, callsign(item.get("flight")))] = item
        return {identifier: records[(identifier, name)] for identifier, name in requested
                if (identifier, name) in records}

    def registry(self, identifier):
        upper = identifier.upper()
        for level in range(1, 7):
            prefix = upper[:level]
            data = self.json(DB + prefix + ".js", 86400)
            item = data.get(upper[level:])
            if isinstance(item, list):
                return item
            if upper[:level + 1] not in (data.get("children") or []):
                break
        return []

    def metadata(self, identifier, name, resolved=None):
        if not HEX.fullmatch(identifier):
            raise ValueError("Invalid ICAO24")
        resolved = resolved or {}
        registry = self.registry(identifier)
        registration = resolved.get("r") or (registry[0] if registry else None)
        type_code = resolved.get("t") or (registry[1] if len(registry) > 1 else None)
        types = self.json(DB + "icao_aircraft_types2.js", 86400)
        type_data = types.get(type_code, [])
        description = resolved.get("desc") or (registry[3] if len(registry) > 3 else None)
        description = description or (type_data[0] if type_data else None)
        flags = registry[2] if len(registry) > 2 else None
        military = bool(resolved["dbFlags"] & 1) if isinstance(resolved.get("dbFlags"), int) else (
            str(flags).startswith("1") if flags is not None else None
        )
        operator = None
        if name and re.match(r"^[A-Z]{3}[0-9]", name) and name != re.sub(r"[-+]", "", str(registration or "")):
            operators = self.json(DB + "operators.js", 86400)
            entry = operators.get(name[:3], {})
            if isinstance(entry, dict):
                operator = entry.get("n")
        # A small explicit allowlist makes accidental telemetry replacement impossible.
        return {
            "icao24": identifier, "callsign": name, "registration": registration,
            "type_code": type_code, "model": description, "military": military,
            "operator": operator, "operator_basis": "callsign prefix" if operator else None,
            "source_url": "https://globe.airplanes.live/?icao=" + identifier,
            "callsign_url": "https://globe.airplanes.live/?callsign=" + name if name else None,
            "identity_basis": "callsign_and_icao" if resolved else "opensky_icao_registry",
            "updated_at": stamp(),
        }

    def photo_url(self, details):
        query = {k: v for k, v in {"reg": details.get("registration"), "icaoType": details.get("type_code")}.items() if v}
        return PHOTOS + details["icao24"].upper() + ("?" + urlencode(query) if query else "")

    def lookup(self, flight, icao24=None):
        name = callsign(flight)
        if not name:
            raise ValueError("Enter an ADS-B callsign of 1–8 letters/digits")
        if icao24:
            identifier = icao24.lower()
            if not HEX.fullmatch(identifier):
                raise ValueError("Invalid ICAO24")
            resolved = self.resolve([(identifier, name)]).get(identifier)
        else:
            data = self.json(CALLS + name, 300)
            matches = [item for item in data.get("ac", []) if callsign(item.get("flight")) == name]
            if len(matches) != 1:
                return {"callsign": name, "available": False, "reason": "No unique callsign match"}
            resolved = matches[0]
            identifier = str(resolved.get("hex", "")).lower()
        result = self.metadata(identifier, name, resolved)
        result["photo"] = photo_details(self.json(self.photo_url(result), 7 * 86400))
        return result


def collect_details(database, root=ROOT, photo_budget=12):
    owner = uuid.uuid4().hex
    if not database.lock("aircraft-details", owner, 900):
        return None
    try:
        with database.connect() as connection:
            row = connection.execute("SELECT payload FROM aircraft_snapshot WHERE id=1").fetchone()
        records = json.loads(row[0]) if row else []
        pairs = [(str(item.get("aircraft", {}).get("icao24", "")).lower(), callsign(item.get("aircraft_callsign")))
                 for item in records[:400] if utcnow().timestamp() - datetime.fromisoformat(item["time_key"]).timestamp() < 600]
        pairs = [(hex_id, name) for hex_id, name in pairs if HEX.fullmatch(hex_id)]
        client = AircraftLookup(root / "data/aircraft-details")
        # Remove obsolete photo/query caches, keeping growth bounded across flights.
        for path in client.cache.glob("*.json"):
            if time.time() - path.stat().st_mtime > 30 * 86400:
                path.unlink(missing_ok=True)
        resolved = client.resolve(pairs)
        details = {identifier: client.metadata(identifier, name, resolved.get(identifier)) for identifier, name in pairs}
        target = root / "public/aircraft-details.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        for item in details.values():
            saved = client.saved(client.cache_path(client.photo_url(item)))
            item["photo"] = photo_details(saved.get("data", {})) if client.now() - saved.get("fetched_at", 0) < 30 * 86400 else None
        write_status(target, {"updated_at": stamp(), "items": details})
        # Identity arrives immediately; photos are filled gradually and cached a week.
        remaining = photo_budget
        for item in details.values():
            url = client.photo_url(item)
            if remaining <= 0:
                break
            if client.ready(url):
                continue
            item["photo"] = photo_details(client.json(url, 7 * 86400))
            remaining -= 1
            time.sleep(1)
        write_status(target, {"updated_at": stamp(), "items": details})
        return {"aircraft": len(details), "photos": sum(bool(item["photo"]) for item in details.values())}
    finally:
        database.unlock("aircraft-details", owner)


async def details_loop(database, stopped, require_viewer=False):
    while not stopped.is_set():
        try:
            from .aviation_demand import aviation_requested

            if not require_viewer or await asyncio.to_thread(aviation_requested, database):
                await asyncio.to_thread(collect_details, database)
        except (OSError, ValueError, sqlite3.OperationalError) as error:
            log.warning("Aircraft details deferred: %s", type(error).__name__)
        try:
            await asyncio.wait_for(stopped.wait(), timeout=60)
        except TimeoutError:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--callsign")
    parser.add_argument("--icao24")
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.callsign:
        print(json.dumps(AircraftLookup(ROOT / "data/aircraft-details").lookup(args.callsign, args.icao24), indent=2))
    elif args.watch:
        asyncio.run(details_loop(Database(Settings().database), asyncio.Event()))
    else:
        print(json.dumps(collect_details(Database(Settings().database))))
