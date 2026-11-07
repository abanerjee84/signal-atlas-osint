"""Vessel registry identity from Global Fishing Watch; never replaces AIS telemetry.

python -m backend.vessel_details --mmsi 232035583
python -m backend.vessel_details --watch   # files only, no listening socket
"""

import argparse
import asyncio
import hashlib
import json
import logging
import sqlite3
import ssl
import time
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlsplit

from scripts.collection_status import write_status

from .config import ROOT, Settings
from .database import Database
from .models import stamp

log = logging.getLogger(__name__)

SEARCH = "https://gateway.api.globalfishingwatch.org/v3/vessels/search?datasets=public-global-vessel-identity%3Alatest&limit=5&query="
DETAIL = "https://gateway.api.globalfishingwatch.org/v3/vessels?datasets=public-global-vessel-identity%3Alatest&ids%5B0%5D="
HOSTS = {"gateway.api.globalfishingwatch.org"}


def safe_mmsi(value):
    digits = str(value or "").strip()
    return digits if digits.isdigit() and 3 <= len(digits) <= 9 else None


def as_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if isinstance(value, bool) or 2**32 <= abs(number):
        return None
    return number


def identity_from_values(payload: dict) -> dict | None:
    """Flatten a GFW registry entry to the identity fields it publishes."""
    if not isinstance(payload, dict):
        return None
    registry = payload.get("registryInfo")
    if not isinstance(registry, list) or not registry:
        return None
    latest = None
    for entry in registry:
        if isinstance(entry, dict) and (
            latest is None
            or str(entry.get("transmissionDateTo") or "") > str(latest.get("transmissionDateTo") or "")
        ):
            latest = entry
    if not isinstance(latest, dict):
        return None
    owners = []
    for owner in payload.get("registryOwners") or []:
        if isinstance(owner, dict) and owner.get("name"):
            owners.append(
                {
                    "name": str(owner["name"])[:200],
                    "flag": str(owner.get("flag") or "")[:60] or None,
                    "year_from": owner.get("yearFrom"),
                    "year_to": owner.get("yearTo"),
                }
            )
    types = [str(item.get("name")) for item in payload.get("shiptypes") or [] if isinstance(item, dict)]
    mmsi = safe_mmsi(payload.get("mmsis")[-1] if isinstance(payload.get("mmsis"), list) and payload.get("mmsis") else None)
    return {
        "mmsi": mmsi or payload.get("mmsi"),
        "shipname": str(latest.get("shipname") or "").strip()[:80] or None,
        "callsign": str(latest.get("callsign") or "").strip()[:20] or None,
        "imo": str(latest.get("imo") or "").strip()[:10] or None,
        "flag": str(latest.get("flag") or "").strip()[:60] or None,
        "length_m": as_int(latest.get("lengthM")),
        "tonnage_gt": as_int(latest.get("tonnageGt")),
        "types": types[:3],
        "owners": owners[:3],
        "identity_basis": "registry_and_ais",
        "source_url": "https://globalfishingwatch.org/our-apis/",
        "updated_at": stamp(),
    }


class RegistryLookup:
    """GFW API with the same on-disk backoff rules as the aircraft lane."""

    def __init__(self, cache, token, now=time.time):
        self.cache, self.token, self.now = cache, token or "", now
        self.cache.mkdir(parents=True, exist_ok=True)
        self.memory = {}
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl.create_default_context())
        )

    def cache_path(self, url):
        return self.cache / (hashlib.sha256(url.encode()).hexdigest() + ".json")

    def saved(self, path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def host_path(self, url):
        return self.cache / (urlsplit(url).netloc + ".json")

    def json(self, url, ttl):
        host = urlsplit(url).netloc
        if host not in HOSTS or not url.startswith("https://"):
            raise ValueError("Unapproved vessel registry source")
        path = self.cache_path(url)
        saved = self.memory.get(url) or self.saved(path)
        if saved.get("retry_at", 0) > self.now() or self.saved(self.host_path(url)).get("retry_at", 0) > self.now():
            return saved.get("data", {}) if self.now() - saved.get("fetched_at", 0) <= 30 * 86400 else {}
        fresh_data = {}
        try:
            data = fresh_data = self._fetch(url)
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
                write_status(self.host_path(url), {"retry_at": self.now() + delay})
            saved = {**saved, "retry_at": self.now() + delay, "error": type(error).__name__}
            log.warning("Vessel registry %s: %s", host, type(error).__name__)
        self.memory[url] = saved
        write_status(path, saved)
        # Registry identity failures may reuse bounded old identity data for a month.
        return fresh_data or (saved.get("data", {}) if self.now() - saved.get("fetched_at", 0) <= 30 * 86400 else {})

    def _fetch(self, url):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "SignalAtlas/0.1 (+https://github.com/abanerjee84/signal-atlas-osint)",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )
        with self.opener.open(request, timeout=20) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError("Vessel registry source too large")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Invalid vessel registry source")
        return data

    def resolve(self, mmsi):
        key = safe_mmsi(mmsi)
        if not key:
            return {"mmsi": "", "available": False, "reason": "Invalid MMSI"}
        entries = (self.json(SEARCH + key, 300).get("entries") or [])[:10]
        match = next((item for item in entries if as_int(item.get("mmsi")) == int(key)), None)
        if not isinstance(match, dict):
            return {"mmsi": key, "available": False}
        vessels = self.json(DETAIL + str(match.get("id", "")), 7 * 86400).get("vessels")
        if not isinstance(vessels, list):
            return {"mmsi": key, "available": False}
        target = next((item for item in vessels if as_int(item.get("mmsi")) == int(key)), None)
        identity = identity_from_values(target) if isinstance(target, dict) else None
        if not identity:
            return {"mmsi": key, "available": False}
        return identity


def collect_details(database, root=ROOT, identity_budget=40) -> dict | None:
    """Write public/vessel-details.json keyed by MMSI from the live AIS snapshot.

    Missing or stale GFW entries are simply absent from the file; the frontend
    keeps the AIS facts and never shows registry data for a vessel it has not
    resolved. Requests are throttled to stay polite to the free API.
    """
    owner = uuid.uuid4().hex
    if not database.lock("vessel-details", owner, 900):
        return None
    try:
        with database.connect() as connection:
            rows = connection.execute(
                """SELECT tags FROM events WHERE category='maritime' AND source_id='maritime'
                ORDER BY time_key DESC LIMIT 1000"""
            ).fetchall()
        requested = []
        for (tags,) in rows:
            try:
                values = json.loads(tags or "[]")
            except ValueError:
                continue
            mmsi = safe_mmsi(values[1]) if isinstance(values, list) and len(values) > 1 else None
            if mmsi and mmsi not in requested:
                requested.append(mmsi)
        client = RegistryLookup(root / "data/vessel-details", Settings().gfw_api_token)
        # Remove obsolete query caches, keeping growth bounded across vessels.
        for path in client.cache.glob("*.json"):
            try:
                if time.time() - path.stat().st_mtime > 30 * 86400:
                    path.unlink(missing_ok=True)
            except OSError:
                continue
        details = {}
        budget = identity_budget
        for mmsi in requested:
            if budget <= 0:
                break
            search_url = SEARCH + mmsi
            if client.saved(client.cache_path(search_url)).get("retry_at", 0) > client.now():
                continue
            payload = client.json(search_url, 3600)
            entries = payload.get("entries") if isinstance(payload, dict) else None
            match = next((item for item in (entries or []) if as_int(item.get("mmsi")) == int(mmsi)), None)
            if not isinstance(match, dict):
                continue
            detail_url = DETAIL + str(match.get("id", ""))
            identity = identity_from_values(client.json(detail_url, 7 * 86400))
            if identity:
                identity["mmsi"] = mmsi
                details[mmsi] = identity
                budget -= 1
                time.sleep(1)
        target = root / "public/vessel-details.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        write_status(target, {"updated_at": stamp(), "items": details})
        return {"vessels": len(details)}
    finally:
        database.unlock("vessel-details", owner)


async def details_loop(database, stopped):
    while not stopped.is_set():
        try:
            if Settings().gfw_api_token:
                await asyncio.to_thread(collect_details, database)
        except (OSError, ValueError, sqlite3.OperationalError) as error:
            log.warning("Vessel details deferred: %s", type(error).__name__)
        try:
            await asyncio.wait_for(stopped.wait(), timeout=300)
        except TimeoutError:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mmsi")
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.mmsi:
        print(json.dumps(RegistryLookup(ROOT / "data/vessel-details", Settings().gfw_api_token).resolve(args.mmsi), indent=2))
    elif args.watch:
        asyncio.run(details_loop(Database(Settings().database), asyncio.Event()))
    else:
        print(json.dumps(collect_details(Database(Settings().database)) or {"skipped": "another run holds the lock"}))
