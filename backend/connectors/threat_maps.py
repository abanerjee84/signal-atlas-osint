"""Bounded scrapers of the two maps' observed public transports; no resident service."""

import asyncio
import hashlib
import json
import re
from contextlib import aclosing
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from ..geo import countries
from ..models import Report, ThreatMetadata, stamp, utcnow
from .base import Connector, ProviderError, clean, parse_time

CHANNELS = (
    "botnet",
    "portscan",
    "telnet",
    "ssh",
    "rdp",
    "vnc",
    "mysql",
    "mssql",
    "http",
    "iot",
    "iot_botnet",
    "infections",
    "spam",
)


def engine_packets(payload: bytes) -> list[str]:
    """Engine.IO v3 text polling uses length prefixes in UTF-16 code units."""
    encoded = payload.decode("utf-8").encode("utf-16-le")
    result, pos = [], 0
    while pos < len(encoded):
        digits = ""
        while pos + 2 <= len(encoded):
            char = encoded[pos : pos + 2].decode("utf-16-le")
            pos += 2
            if char == ":":
                break
            if not char.isascii() or not char.isdigit() or len(digits) >= 8:
                raise ValueError("Invalid polling frame")
            digits += char
        else:
            raise ValueError("Incomplete polling prefix")
        length = int(digits) if digits else 0
        end = pos + length * 2
        if not length or end > len(encoded) or len(result) >= 1000:
            raise ValueError("Incomplete or oversized polling frame")
        result.append(encoded[pos:end].decode("utf-16-le"))
        pos = end
    return result


def engine_payload(packets: list[str]) -> bytes:
    return "".join(f"{len(p.encode('utf-16-le')) // 2}:{p}" for p in packets).encode("utf-8")


async def robots(http, url):
    parsed = urlsplit(url)
    try:
        payload = await http.request(
            "GET", f"{parsed.scheme}://{parsed.netloc}/robots.txt", attempts=1, max_bytes=262144, redirects=3
        )
    except ProviderError as error:
        if error.status_code == 404:
            return
        raise
    policy = RobotFileParser()
    policy.parse(payload.decode("utf-8", errors="replace").splitlines())
    if not policy.can_fetch("SignalAtlas", url):
        raise ProviderError("Public threat stream disallowed by robots policy")


class ThreatMap(Connector):
    category = "threat"
    interval = 120
    telemetry = True
    sample_seconds = 20
    sample_limit = 100
    limitation = (
        "Bounded samples of provider detections, not global attack totals or confirmed incidents. "
        "Traffic country describes infrastructure, never actor nationality. Coordinates are country centers. "
        "No IP addresses or request identifiers are stored. Provider coverage is incomplete."
    )

    def select_records(self, records):
        return records[: min(self.sample_limit, self.settings.max_records)]

    def metadata(self):
        return {
            **super().metadata(),
            "delivery": self.delivery,
            "sample_seconds": self.sample_seconds,
            "sample_limit": self.sample_limit,
            "retention": "7 days, at most 2,000 observations per source",
        }

    def normalize(self, record):
        places = {f["properties"]["code"]: f["properties"] for f in countries()["features"]}

        def code(value):
            return value if isinstance(value, str) and value in places else None

        received = parse_time(record["received_at"])
        origin, target, detection = None, None, None
        occurred = None
        provider_time = ""
        if self.source_id == "bunkerweb_threatmap":
            origin, target = code(record.get("attacker")), code(record.get("target"))
            kind = clean(record.get("reason", "Blocked web request"), 80) or "Blocked web request"
            # The observed feed gives HH:MM:SS only. Neither its date nor timezone is established.
            provider_time = clean(record.get("date", ""), 100)
            classification = "observed_traffic"
        else:
            channel = record.get("n")
            if channel not in CHANNELS:
                raise ValueError("Unknown Bitdefender event channel")
            kind = clean(record.get("detection") or channel, 80)
            if isinstance(record.get("loc"), dict):
                detection = code(record["loc"].get("c_iso"))
                classification = "detection"
            else:
                origin = code((record.get("from") or {}).get("c_iso"))
                target = code((record.get("to") or {}).get("c_iso"))
                classification = "observed_traffic"
            timestamp = record.get("ts")
            if timestamp is not None:
                provider_time = clean(timestamp, 100)
                try:
                    # moment(evt.ts) in the provider UI interprets numeric values as milliseconds.
                    occurred = (
                        datetime.fromtimestamp(timestamp / 1000, timezone.utc)
                        if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool)
                        else parse_time(str(timestamp))
                    )
                    if occurred.year < 2000 or occurred > received:
                        occurred = None
                except (ValueError, TypeError, OverflowError, OSError):
                    occurred = None
        if not any((origin, target, detection)):
            raise ValueError("No supported traffic or detection country")
        # Whitelist normalized public facts. Never persist the upstream payload/IPs/socket session.
        facts = {
            "classification": classification,
            "traffic_origin_country": origin,
            "traffic_target_country": target,
            "detection_country": detection,
            "attack_kind": kind,
            "provider_time": provider_time,
        }
        external = record.get("observation_id")
        if not isinstance(external, str) or not re.fullmatch(r"[a-f0-9]{64}", external):
            raise ValueError("Missing bounded collection observation identity")
        country = detection or target or origin
        lon, lat = places[country]["center"]
        path = f"{origin or 'Unknown origin'} → {target or 'Unknown target'}"
        title = f"{self.name}: {kind} · {detection if detection else path}"
        basis = "Provider traffic geolocation; infrastructure country does not identify an actor"
        threat = ThreatMetadata(
            **facts,
            received_at=received,
            attribution_basis=basis,
            victim_basis="Provider destination country; a blocked request does not establish compromise",
        )
        tags = ["threat-telemetry", "threat-classification:" + classification, "attack-kind:" + kind]
        for prefix, value in [
            ("traffic-origin-country:", origin),
            ("traffic-target-country:", target),
            ("detection-country:", detection),
        ]:
            if value:
                tags.append(prefix + value)
        return Report(
            external_id=external,
            source_id=self.source_id,
            source_url=self.homepage,
            title=title[:500],
            description=(
                f"{basis}. {threat.victim_basis}. Sample received {stamp(received)}. "
                + (
                    "Provider time has no established date/timezone; occurrence time is unknown. "
                    if not occurred
                    else ""
                )
                + "Sampled provider coverage, not a confirmed attack or global total."
            ),
            category="threat",
            country_code=country,
            longitude=lon,
            latitude=lat,
            location_precision="regional",
            location_basis="Illustrative country center from provider country code",
            occurred_at=occurred,
            published_at=received,
            tags=tags,
            threat=threat,
            evidence_basis="One provider detection; unverified, actor unknown",
            raw={**facts, "received_at": stamp(received)},
        )


def observation(record, collection, sequence):
    if not isinstance(record, dict):
        return None
    return {
        **record,
        "received_at": utcnow().isoformat(),
        "observation_id": hashlib.sha256(f"{collection}:{sequence}".encode()).hexdigest(),
    }


class BunkerWebMap(ThreatMap):
    source_id = "bunkerweb_threatmap"
    name = "BunkerWeb WAF"
    homepage = "https://www.bunkerweb.io/threatmap/"
    stream_url = "https://threatmap.bunkerweb.io/stream"
    delivery = "Public SSE used by the provider map; bounded 20-second sample every 2 minutes"

    async def fetch(self, http):
        await robots(http, self.homepage)
        await robots(http, self.stream_url)
        records, data = [], []
        collection = utcnow().isoformat()
        try:
            async with asyncio.timeout(self.sample_seconds):
                async with aclosing(http.stream_lines(self.stream_url)) as lines:
                    async for line in lines:
                        if line.startswith("data:"):
                            data.append(line[5:].lstrip(" "))
                        elif line == "" and data:
                            try:
                                item = observation(json.loads("\n".join(data)), collection, len(records))
                            except (ValueError, TypeError):
                                raise ProviderError(
                                    "BunkerWeb stream returned malformed event JSON"
                                ) from None
                            data = []
                            if item:
                                records.append(item)
                            if len(records) >= min(self.sample_limit, self.settings.max_records):
                                break
        except TimeoutError:
            pass  # Normal end of the bounded sample; received events remain usable.
        return records


class BitdefenderMap(ThreatMap):
    source_id = "bitdefender_threatmap"
    name = "Bitdefender detections"
    homepage = "https://threatmap.bitdefender.com/"
    polling_url = homepage + "socket.io/"
    delivery = "Public Socket.IO / Engine.IO v3 polling used by the provider map; no authentication"

    async def fetch(self, http):
        await robots(http, self.polling_url)
        query = {"EIO": "3", "transport": "polling"}
        payload = await http.request("GET", self.polling_url, params=query, attempts=1, max_bytes=1_048_576)
        try:
            packets = engine_packets(payload)
            hello = json.loads(next(p[1:] for p in packets if p.startswith("0")))
            sid = hello["sid"]
            if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", sid):
                raise ValueError("Invalid session")
            ping_seconds = max(1, min(30, float(hello["pingInterval"]) / 1000))
        except (ValueError, TypeError, KeyError, StopIteration, UnicodeError):
            raise ProviderError("Bitdefender live feed unavailable: no valid Socket.IO handshake") from None
        query["sid"] = sid
        subscriptions = ["42" + json.dumps(["subscribe", {"event_name": channel}]) for channel in CHANNELS]
        records, collection = [], utcnow().isoformat()
        loop = asyncio.get_running_loop()
        next_ping = loop.time() + ping_seconds
        try:
            async with asyncio.timeout(self.sample_seconds):
                await http.request(
                    "POST",
                    self.polling_url,
                    params=query,
                    attempts=1,
                    content=engine_payload(subscriptions),
                    headers={"Content-Type": "text/plain;charset=UTF-8"},
                )
                while len(records) < min(self.sample_limit, self.settings.max_records):
                    if loop.time() >= next_ping:
                        await http.request(
                            "POST", self.polling_url, params=query, attempts=1, content=engine_payload(["2"])
                        )
                        next_ping = loop.time() + ping_seconds
                    payload = await http.request(
                        "GET", self.polling_url, params=query, attempts=1, max_bytes=1_048_576
                    )
                    try:
                        frames = engine_packets(payload)
                        for frame in frames:
                            if frame == "1":
                                raise ProviderError("Bitdefender closed the public stream")
                            if not frame.startswith("42"):
                                continue
                            message = json.loads(frame[2:])
                            if not isinstance(message, list) or len(message) != 2 or message[0] != "ev":
                                continue
                            batch = message[1]
                            values = (
                                batch.values()
                                if isinstance(batch, dict)
                                else batch
                                if isinstance(batch, list)
                                else []
                            )
                            for item in values:
                                row = observation(item, collection, len(records))
                                if row:
                                    records.append(row)
                                if len(records) >= min(self.sample_limit, self.settings.max_records):
                                    break
                    except (ValueError, UnicodeError, TypeError):
                        raise ProviderError("Bitdefender returned malformed public stream frames") from None
        except TimeoutError:
            pass
        return records


def threat_maps(settings):
    return [BitdefenderMap(settings), BunkerWebMap(settings)]
