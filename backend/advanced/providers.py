"""Explicit public API adapters; no scanning or third-party social credentials."""

import ipaddress
import math
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlsplit

from ..connectors.base import ProviderError, SafeHTTP
from ..models import stamp, utcnow
from .processing import stable
from .repository import packed
from .watch import pinned_get

PUBLIC_PROVIDERS = [
    (
        "sans",
        "SANS ISC — public IP activity lookup",
        "https://isc.sans.edu/api/",
        "cyber",
        {
            "on_demand": True,
            "authentication": "None",
            "local_concurrency": 1,
            "limitations": "Observed IP activity and ASN context; false positives possible. No actor attribution or victim geography. Do not use top IP data as a blocklist.",
            "usage_terms": "https://isc.sans.edu/api/",
            "license": "CC BY-NC-SA 4.0; no resale",
        },
    ),
    (
        "ripe",
        "RIPE NCC — RIPEstat routing lookup",
        "https://stat.ripe.net/docs/data-api/ripestat-data-api",
        "cyber",
        {
            "on_demand": True,
            "authentication": "None",
            "provider_concurrency_limit": 8,
            "local_concurrency": 1,
            "limitations": "RIS routing observations, not cyber reputation or precise geolocation",
            "usage_terms": "https://www.ripe.net/about-us/legal/ripestat-service-terms-and-conditions",
        },
    ),
    (
        "greynoise",
        "GreyNoise Community - selected public IP lookup",
        "https://docs.greynoise.io/reference/getcommunityip",
        "cyber",
        {
            "on_demand": True,
            "authentication": "OSINT_GREYNOISE_API_KEY",
            "limitations": "Provider IP context, including benign scanner classifications; no actor attribution. Account quota applies. Cached for 24 hours.",
            "usage_terms": "https://www.greynoise.io/terms-of-service",
        },
    ),
    (
        "ioda",
        "Georgia Tech — IODA Internet outage observations",
        "https://api.ioda.inetintel.cc.gatech.edu/v2/",
        "cyber",
        {
            "scheduled": True,
            "frequency_seconds": 3600,
            "authentication": "None",
            "local_concurrency": 1,
            "coverage": "Country aggregates",
            "limitations": "Heuristic network availability observations; score is not probability or outage fraction",
            "usage_terms": "https://ioda.inetintel.cc.gatech.edu/resources",
        },
    ),
]


def register_public(repo, settings):
    with repo.database.connect() as db:
        for sid, name, official, category, capability in PUBLIC_PROVIDERS:
            db.execute(
                "INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET details=excluded.details,name=excluded.name,official_url=excluded.official_url,enabled=CASE WHEN sources.permissions_state='manual_only' THEN excluded.enabled ELSE sources.enabled END,permissions_state=excluded.permissions_state,integration=excluded.integration,access_class=excluded.access_class",
                (
                    sid,
                    name,
                    name,
                    category,
                    official,
                    "api",
                    "free",
                    "provider_terms",
                    "existing_connector",
                    int(bool(settings.greynoise_api_key)) if sid == "greynoise" else 1,
                    None,
                    packed(capability),
                ),
            )
            db.execute("INSERT OR REPLACE INTO source_capabilities VALUES(?,?)", (sid, packed(capability)))
        if settings.searxng_url:
            db.execute(
                "UPDATE sources SET enabled=1,permissions_state='existing_connector',access_class='free',official_url=?,details=? WHERE source_id='searxng'",
                (
                    settings.searxng_url,
                    packed(
                        {
                            "configured": True,
                            "limitations": "Administrator configured instance; external search sends the selected query to this provider",
                        }
                    ),
                ),
            )
            db.execute(
                "UPDATE source_capabilities SET capabilities=? WHERE source_id='searxng'",
                (packed({"collection": False, "on_demand": True, "format": "JSON search API"}),),
            )


def routing_resource(value):
    if re.fullmatch(r"AS\d{1,10}", value, re.I):
        number = int(value[2:])
        if not 1 <= number <= 4294967295:
            raise ValueError("Invalid autonomous system number")
        return "as-overview", "AS" + str(number)
    try:
        ip = ipaddress.ip_address(value)
        if not ip.is_global:
            raise ValueError("Only public IP routing lookups are supported")
        return "network-info", str(ip)
    except ValueError:
        if "/" not in value:
            raise ValueError("RIPEstat accepts a public IP, CIDR prefix or AS number") from None
        network = ipaddress.ip_network(value, strict=False)
        if not network.is_global:
            raise ValueError("Only public IP prefixes are supported")
        return "prefix-overview", str(network)


async def lookup(repo, settings, client, payload):
    provider = payload["provider_id"]
    source = repo.one("SELECT * FROM sources WHERE source_id=? AND enabled=1", (provider,))
    if not source:
        raise ValueError("Provider is disabled or not configured")
    if provider == "greynoise":
        from ..indicators import public_ip

        resource = public_ip(payload["query"])
        if not settings.greynoise_api_key:
            raise ValueError("GreyNoise API key is not configured")
        key = stable("greynoise", resource)
        cached = repo.one(
            "SELECT payload FROM advanced_provider_cache WHERE cache_key=? AND expires_at>?", (key, stamp())
        )
        if cached:
            return {**cached["payload"], "cached": True}
        cooldown = repo.one(
            "SELECT 1 FROM advanced_provider_cache WHERE cache_key='greynoise:cooldown' AND expires_at>?",
            (stamp(),),
        )
        if cooldown:
            raise ValueError("GreyNoise requested a pause; wait for the provider backoff period")
        url = "https://api.greynoise.io/v3/community/" + quote(resource, safe="")
        try:
            result = await SafeHTTP(settings, client).json(
                "GET", url, attempts=1, max_bytes=65536, headers={"key": settings.greynoise_api_key}
            )
        except ProviderError as error:
            if error.status_code == 404:
                result = {
                    "ip": resource,
                    "noise": False,
                    "riot": False,
                    "message": "IP not observed in provider dataset",
                }
            else:
                if "HTTP 429" in str(error):
                    with repo.database.connect() as db:
                        db.execute(
                            "INSERT OR REPLACE INTO advanced_provider_cache VALUES(?,?,?,?,?)",
                            (
                                "greynoise:cooldown",
                                provider,
                                packed({"classification": "provider_backoff"}),
                                stamp(),
                                stamp(utcnow() + timedelta(seconds=error.retry_after)),
                            ),
                        )
                raise
        if (
            not isinstance(result, dict)
            or result.get("ip") != resource
            or not isinstance(result.get("noise"), bool)
            or not isinstance(result.get("riot"), bool)
        ):
            raise ValueError("GreyNoise response failed validation")
        answer = {
            "resource": resource,
            "source_id": provider,
            "original_url": url,
            "retrieved_at": stamp(),
            "data": {
                key: result[key]
                for key in ("ip", "noise", "riot", "classification", "name", "last_seen", "message")
                if key in result
            },
            "classification": "provider_ip_context",
            "cached": False,
            "limitations": source["details"]["limitations"],
        }
        with repo.database.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO advanced_provider_cache VALUES(?,?,?,?,?)",
                (key, provider, packed(answer), stamp(), stamp(utcnow() + timedelta(hours=24))),
            )
        return answer
    if provider == "sans":
        resource = str(ipaddress.ip_address(payload["query"]))
        if not ipaddress.ip_address(resource).is_global:
            raise ValueError("SANS lookup requires a public IP address")
        cooldown = repo.one(
            "SELECT 1 FROM advanced_provider_cache WHERE cache_key='sans:cooldown' AND expires_at>?",
            (stamp(),),
        )
        if cooldown:
            raise ValueError("SANS requested a pause; try again after the provider backoff period")
        key = stable("sans", resource)
        cached = repo.one(
            "SELECT payload FROM advanced_provider_cache WHERE cache_key=? AND expires_at>?", (key, stamp())
        )
        if cached:
            return {**cached["payload"], "cached": True}
        url = "https://isc.sans.edu/api/ip/" + quote(resource, safe="") + "?json"
        try:
            result = await SafeHTTP(settings, client).json(
                "GET",
                url,
                attempts=1,
                headers={
                    "User-Agent": "GlobalOSINT/0.1 " + (settings.sans_contact or "public-source-research")
                },
            )
        except ProviderError as error:
            if "HTTP 429" in str(error):
                with repo.database.connect() as db:
                    db.execute(
                        "INSERT OR REPLACE INTO advanced_provider_cache VALUES(?,?,?,?,?)",
                        (
                            "sans:cooldown",
                            "sans",
                            packed({"classification": "provider_backoff"}),
                            stamp(),
                            stamp(utcnow() + timedelta(seconds=error.retry_after)),
                        ),
                    )
            raise
        if not isinstance(result, dict) or not isinstance(result.get("ip"), dict):
            raise ValueError("SANS returned invalid IP observation data")
        answer = {
            "resource": resource,
            "source_id": "sans",
            "original_url": url,
            "retrieved_at": stamp(),
            "data": result["ip"],
            "classification": "reported_network_activity",
            "cached": False,
            "limitations": source["details"]["limitations"],
        }
    elif provider == "ripe":
        endpoint, resource = routing_resource(payload["query"])
        key = stable("ripe", endpoint, resource)
        url = (
            "https://stat.ripe.net/data/"
            + endpoint
            + "/data.json?resource="
            + quote(resource, safe="")
            + "&sourceapp=GlobalOSINT"
        )
        cached = repo.one(
            "SELECT payload FROM advanced_provider_cache WHERE cache_key=? AND expires_at>?", (key, stamp())
        )
        if cached:
            return {**cached["payload"], "cached": True}
        result = await SafeHTTP(settings, client).json("GET", url, attempts=1)
        if result.get("status") != "ok" or not isinstance(result.get("data"), dict):
            raise ValueError("RIPEstat response failed validation")
        answer = {
            "resource": resource,
            "endpoint": endpoint,
            "source_id": provider,
            "original_url": url,
            "retrieved_at": stamp(),
            "observed_at": result["data"].get("query_time"),
            "data": result["data"],
            "limitations": source["details"]["limitations"],
            "classification": "routing_observation",
            "cached": False,
        }
    elif provider == "ioda":
        end = utcnow()
        start = end - timedelta(hours=24)
        country = payload.get("country", "")
        key = stable("ioda", country or "world")
        url = (
            f"https://api.ioda.inetintel.cc.gatech.edu/v2/outages/events?from={int(start.timestamp())}&until={int(end.timestamp())}&entityType=country&limit=200&extendWindow=0"
            + ("&entityCode=" + country if country else "")
        )
        result = await SafeHTTP(settings, client).json("GET", url, attempts=1)
        if result.get("error") or not isinstance(result.get("data"), list):
            raise ValueError("IODA response failed validation")
        observations = []
        for item in result["data"][:200]:
            try:
                location = item["location"]
                if not re.fullmatch(r"country/[A-Z]{2}", location):
                    continue
                observed = datetime.fromtimestamp(int(item["start"]), timezone.utc)
                duration = int(item["duration"])
                if duration < 0:
                    continue
                score = float(item["score"]) if item.get("score") is not None else None
                if score is not None and not math.isfinite(score):
                    continue
                row = {
                    "id": stable("ioda", location, str(item["start"]), item["datasource"], item["method"]),
                    "source_id": "ioda",
                    "country": location[-2:],
                    "name": item.get("location_name", location[-2:]),
                    "start_at": stamp(observed),
                    "end_at": stamp(observed + timedelta(seconds=duration)),
                    "measurement_from": stamp(start),
                    "measurement_until": stamp(end),
                    "method": item["method"],
                    "datasource": item["datasource"],
                    "score": score,
                    "uncertainty": item.get("uncertainty"),
                    "original_url": url,
                    "retrieved_at": stamp(),
                }
                observations.append(row)
            except (KeyError, ValueError, TypeError, OverflowError):
                continue
        with repo.database.connect() as db:
            if country:
                db.execute("DELETE FROM cyber_disruptions WHERE country=?", (country,))
            else:
                db.execute("DELETE FROM cyber_disruptions")
            for row in observations:
                db.execute(
                    "INSERT OR REPLACE INTO cyber_disruptions VALUES(" + ",".join("?" for _ in row) + ")",
                    tuple(row.values()),
                )
        answer = {
            "source_id": "ioda",
            "items": observations,
            "measurement_period": {"from": stamp(start), "until": stamp(end)},
            "retrieved_at": stamp(),
            "original_url": url,
            "truncated": len(result["data"]) >= 200,
            "limitations": source["details"]["limitations"],
        }
    elif provider == "searxng":
        if not settings.searxng_url:
            raise ValueError("SearXNG instance is not configured")
        base = settings.searxng_url.rstrip("/")
        hostname = urlsplit(base).hostname
        url = base + "/search?format=json&q=" + quote(payload["query"], safe="")
        status, _, body = await pinned_get(url, [hostname])
        import json

        result = json.loads(body)
        if status != 200 or not isinstance(result.get("results"), list):
            raise ValueError("Configured SearXNG instance did not provide JSON search results")
        key = stable("searxng", payload["query"])
        answer = {
            "provider": "searxng",
            "items": result["results"][:50],
            "original_url": url,
            "retrieved_at": stamp(),
            "limitations": "External search results are unverified references, not locally confirmed evidence",
        }
    else:
        raise ValueError("No automated adapter for this provider")
    with repo.database.connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO advanced_provider_cache VALUES(?,?,?,?,?)",
            (key, provider, packed(answer), stamp(), stamp(utcnow() + timedelta(hours=1))),
        )
        db.execute("UPDATE sources SET last_verified_at=? WHERE source_id=?", (stamp(), provider))
    return answer
