"""Bounded scrapers of the two maps' observed public transports; no resident service."""

import asyncio
import hashlib
import json
import re
from contextlib import aclosing
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from ..attack_vectors import extract_vectors, reputation_reason
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


def socketio_packets(payload: bytes) -> list[str]:
    """Engine.IO packets, tolerating the framing the provider actually sends.

    The documented v3 scheme prefixes each packet with its length counted in
    UTF-16 code units. Bitdefender now answers with a four byte binary
    preamble ahead of an otherwise ordinary "0{...}" packet, which that scheme
    cannot decode. When strict parsing fails, fall back to splitting on the
    Engine.IO record separator and stripping a leading packet-type digit,
    which is valid for both v3 and v4 payloads. Strict parsing stays first so a
    genuinely malformed frame is still reported rather than half-parsed.
    """
    try:
        return engine_packets(payload)
    except (ValueError, UnicodeError):
        pass
    text = payload.decode("utf-8", "replace")
    decoder = json.JSONDecoder()
    result, index = [], 0
    while index < len(text) and len(result) < 1000:
        following = text[index + 1 : index + 2]
        if not (text[index].isdigit() and following and following in "{[\""):
            # Engine.IO control packets (open, close, ping, pong) carry no
            # JSON body, so they are a digit on its own. Skipping them would
            # report an idle-but-healthy stream as a malformed one.
            if (
                text[index] in "0123456"
                and (not following or not following.isdigit())
            ):
                result.append(text[index])
            index += 1
            continue
        try:
            _, end = decoder.raw_decode(text, index + 1)
        except ValueError:
            index += 1
            continue
        result.append(text[index:end])
        index = end
    if not result:
        raise ValueError("No Engine.IO packets in response")
    return result


def engine_payload(packets: list[str]) -> bytes:
    return "".join(f"{len(p.encode('utf-16-le')) // 2}:{p}" for p in packets).encode("utf-8")


async def robots(http, url):
    parsed = urlsplit(url)
    cache = getattr(http, "robots_cache", {})
    if not isinstance(cache, dict):
        cache = {}
    key = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    cached = cache.get(key)
    if cached and cached[0] > asyncio.get_running_loop().time():
        if cached[1] and not cached[1].can_fetch("SignalAtlas", url):
            raise ProviderError("Public threat stream disallowed by robots policy")
        return
    try:
        payload = await http.request(
            "GET", f"{parsed.scheme}://{parsed.netloc}/robots.txt", attempts=1, max_bytes=262144, redirects=3
        )
    except ProviderError as error:
        if error.status_code == 404:
            cache[key] = (asyncio.get_running_loop().time() + 600, None)
            return
        raise
    policy = RobotFileParser()
    policy.parse(payload.decode("utf-8", errors="replace").splitlines())
    cache[key] = (asyncio.get_running_loop().time() + 600, policy)
    if not policy.can_fetch("SignalAtlas", url):
        raise ProviderError("Public threat stream disallowed by robots policy")


class ThreatMap(Connector):
    category = "threat"
    interval = 10
    telemetry = True
    sample_seconds = 4
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
        if self.source_id in {"bunkerweb_threatmap", "imperva_threatmap", "radware_threatmap"}:
            origin, target = code(record.get("attacker")), code(record.get("target"))
            kind = clean(record.get("reason", "Blocked web request"), 80) or "Blocked web request"
            # The observed feed gives HH:MM:SS only. Neither its date nor timezone is established.
            provider_time = clean(record.get("date", ""), 100)
            classification = "observed_traffic"
        else:
            channel = record.get("n")
            if channel not in CHANNELS and channel != "table_attack":
                raise ValueError("Unknown Bitdefender event channel")
            kind = clean(record.get("detection") or channel, 80)
            if isinstance(record.get("loc"), dict):
                detection = code(record["loc"].get("c_iso"))
                classification = "detection"
            else:
                origin = code((record.get("from") or {}).get("c_iso"))
                target = code((record.get("to") or {}).get("c_iso"))
                classification = "observed_traffic"
            provider_time = clean(record.get("table_time", ""), 100)
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
        vectors, _ = extract_vectors(kind, contextual=False)
        threat = ThreatMetadata(
            **facts,
            received_at=received,
            attribution_basis=basis,
            victim_basis="Provider destination country; a blocked request does not establish compromise",
            attack_vectors=vectors,
            vector_evidence="Provider category: " + kind if vectors else "",
        )
        tags = ["threat-telemetry", "threat-classification:" + classification, "attack-kind:" + kind]
        tags += ["attack-vector:" + value for value in vectors]
        tags.append(
            "vector-status:"
            + ("known" if vectors else "reputation" if reputation_reason(kind) else "unspecified")
        )
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
    delivery = "Public SSE used by the provider map; bounded 4-second sample every 10 seconds"

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
    interval = 120
    delivery = "Persistent public bottom-table scraper: ATTACK rows only; legacy HTTP transport when no renderer is supplied"

    async def fetch(self, http):
        reader = getattr(http, "threat_table_reader", None)
        if reader:
            await robots(http, self.homepage)
            return table_attacks(await reader.rows(self.homepage))
        await robots(http, self.polling_url)
        query = {"EIO": "3", "transport": "polling"}
        payload = await http.request("GET", self.polling_url, params=query, attempts=1, max_bytes=1_048_576)
        try:
            packets = socketio_packets(payload)
            hello = json.loads(next(p[1:] for p in packets if p.startswith("0")))
            sid = hello["sid"]
            if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", sid):
                raise ValueError("Invalid session")
            ping_seconds = max(1, min(30, float(hello["pingInterval"]) / 1000))
        except (ValueError, TypeError, KeyError, StopIteration, UnicodeError):
            raise ProviderError("Bitdefender live feed unavailable: no valid Socket.IO handshake") from None
        query["sid"] = sid
        subscriptions = [
            "42" + json.dumps(["subscribe", {"event_name": channel}])
            for channel in CHANNELS
            if channel not in {"infections", "spam"}
        ]
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
                        frames = socketio_packets(payload)
                        for frame in frames:
                            if frame == "1":
                                raise ProviderError("Bitdefender closed the public stream")
                            # A Socket.IO event packet is "42" when framed for
                            # websocket transport and "2" followed by the same
                            # JSON array when carried on the polling transport
                            # the provider answers. Both carry an identical
                            # payload after two characters, so both are read.
                            if not (frame.startswith("42") or frame.startswith("2[")):
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
                                if not isinstance(item, dict) or item.get("n") in {"infections", "spam"}:
                                    continue
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


def table_attacks(rows):
    """Literal five-column ATTACK rows; repeated snapshots retain their identities."""
    places = {f["properties"]["name"].casefold(): f["properties"]["code"] for f in countries()["features"]}
    places.update(
        {
            "united states": "US",
            "united kingdom": "GB",
            "russia": "RU",
            "south korea": "KR",
            "turkey": "TR",
            "vietnam": "VN",
        }
    )
    records = []
    received = utcnow().isoformat()
    for row in rows[:500]:
        if len(row) != 5 or clean(row[2]).casefold() != "attack":
            continue
        origin, target = (places.get(clean(row[i]).casefold()) for i in (3, 4))
        if not origin or not target:
            continue
        canonical = [clean(v, 100) for v in row]
        records.append(
            {
                "n": "table_attack",
                "from": {"c_iso": origin},
                "to": {"c_iso": target},
                "detection": canonical[1] if canonical[1].casefold() != "n/a" else "Attack",
                "table_time": canonical[0],
                "received_at": received,
                "observation_id": hashlib.sha256(
                    json.dumps([utcnow().year, *canonical], ensure_ascii=False).encode()
                ).hexdigest(),
            }
        )
    return records[:100]


def threat_maps(settings):
    from .imperva_map import ImpervaMap
    from .radware_map import RadwareMap

    return [BitdefenderMap(settings), BunkerWebMap(settings), ImpervaMap(settings), RadwareMap(settings)]
