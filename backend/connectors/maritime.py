import asyncio
import json
import math
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
import websockets

from ..mid_flags import flag_of_mmsi
from ..models import Report
from .base import APPROVED_HOSTS, Connector, ProviderError, SafeHTTP, parse_time, spatial_sample

OPEN_WATERS = {
    "url": "wss://ais.openwaters.io/v1/stream",
    "name": "Open Waters AIS",
    "homepage": "https://openwaters.io/ais/",
}
OPEN_SEAFEED = {
    "url": "wss://stream.openseafeed.com/v1/stream",
    "name": "OpenSeaFeed",
    "homepage": "https://openseafeed.com/",
}
AISSTREAM = {
    "url": "wss://stream.aisstream.io/v0/stream",
    "name": "AIS Stream",
    "homepage": "https://aisstream.io/",
}
# Norwegian Coastal Administration open AIS, served through BarentsWatch under
# the Norwegian Licence for Open Government Data; free OAuth2 client
# credentials. Every streamed line carries the vessel name and ship type even
# for a pure position update, which the public fallbacks lack.
BARENTSWATCH = {
    "token_url": "https://id.barentswatch.no/connect/token",
    "live_url": "https://live.ais.barentswatch.no/v1/combined",
    "name": "BarentsWatch AIS",
    "homepage": "https://developer.barentswatch.no/",
    "region": "Norwegian EEZ / Svalbard zones",
}

# AIS Stream names every subscription with its message types. Positions and
# static data are all this collector stores, so every other decoded message type
# would be bandwidth spent on data it discards.
AISSTREAM_MESSAGE_TYPES = ["PositionReport", "ShipStaticData"]

# The anonymous OpenSeaFeed tier caps each connection at a 30,000 square-degree
# bounding box. Three full-latitude strips of 120 degrees of longitude
# (21,600 square degrees each) cover the whole globe on three concurrent
# connections, so one cycle samples worldwide instead of one region at a time.
WORLD_STRIPS = [
    ("Pacific", -90, -180, 90, -60),
    ("Atlantic / Americas", -90, -60, 90, 60),
    ("Asia / Indian Ocean", -90, 60, 90, 180),
]

# Open Waters' anonymous tier only allows one roughly 10-degree box per
# connection, so the fallback rotates through these high-traffic OSINT regions
# in order and covers all of them within a few cycles.
REGIONS = [
    ("North Atlantic / English Channel", 48, -10, 58, 0),
    ("North Sea / Baltic", 54, 8, 64, 18),
    ("Western Mediterranean", 32, 0, 42, 10),
    ("Eastern Mediterranean / Levant", 32, 20, 42, 32),
    ("Red Sea / Suez Canal", 12, 32, 22, 42),
    ("Gulf of Aden / Bab el-Mandeb", 10, 40, 20, 50),
    ("Persian Gulf / Strait of Hormuz", 22, 48, 30, 58),
    ("Gulf of Guinea / West Africa", -6, 2, 4, 12),
    ("South China Sea / Malacca Strait", 0, 98, 10, 108),
]


def _finite(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _course(value):
    result = _finite(value)
    return result if result is not None and 0 <= result < 360 else None


def _speed(value):
    result = _finite(value)
    return result if result is not None and result >= 0 else None


def _ship_type(value):
    # AIS ship type codes are integers in one byte; static reports also send
    # 0 when the code is unset, which stays "not supplied".
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    code = int(value)
    return code if 0 < code <= 255 else None


class Maritime(Connector):
    fast_monitoring = True
    source_id = "maritime"
    name = "AIS vessel observations"
    category = "maritime"
    homepage = AISSTREAM["homepage"]
    interval = 300
    per_cycle_cap = 1000
    # Positions are a live fleet, so each cycle replaces the previous one rather
    # than accumulating vessels that stopped reporting.
    vessel_snapshot = True
    limitation = (
        "Worldwide public AIS positions via AIS Stream when an account key is configured (three concurrent "
        "full-latitude strips, primary) or OpenSeaFeed (same strips, anonymous fallback), with Open Waters "
        "rotating high-traffic regions as the last resort, and BarentsWatch (Norwegian Coastal Administration, "
        "NLOD open data) as a registered-credentials lane covering the Norwegian EEZ, Svalbard and Jan Mayen "
        "zones with the ship type in every update. Measured on 17 October 2026: AIS Stream reports "
        "roughly one vessel for every thirteen OpenSeaFeed delivers but is the only one of the three that "
        "supplies vessel names, and this collector keeps at most 1,000 spatially sampled observations per "
        "cycle, so the extra unnamed positions OpenSeaFeed provides are discarded either way. One stored "
        "observation per vessel updates in place each cycle. Coverage is incomplete: vessels may switch AIS off "
        "and some waters have no receiver coverage; BarentsWatch omits fishing vessels under 15 metres and "
        "leisure craft under 45 metres by design. Vessel names are self-reported AIS static data and "
        "unverified; the flag state derives from the registered MMSI prefix, which the operator chooses and "
        "which may differ from beneficial ownership, and the type is the last self-reported AIS code. An AIS "
        "gap can reflect receiver coverage or equipment failure and is not evidence of sanctions evasion. An "
        "administrator-configured licensed feed takes precedence when set."
    )

    def __init__(self, settings):
        super().__init__(settings)
        self._region_index = -1
        self._collect_seconds = 20
        self._token: str | None = None
        self._token_expiry = 0.0

    def access(self):
        return None

    def metadata(self):
        return {
            **super().metadata(),
            "record_selection": (
                "licensed_then_keyed_aisstream_then_barentswatch_then_openseafeed_then_open_waters"
            ),
            "per_cycle_cap": self.per_cycle_cap,
            "keyed_primary_configured": bool(self.settings.aisstream_api_key),
            "keyed_norwegian_configured": bool(
                self.settings.barentswatch_client_id and self.settings.barentswatch_client_secret
            ),
            "world_strips": [name for name, *_ in WORLD_STRIPS],
            "fallback_regions": [region[0] for region in REGIONS],
        }

    async def fetch(self, http: SafeHTTP) -> list[dict]:
        if self.settings.maritime_url:
            headers = (
                {"Authorization": f"Bearer {self.settings.maritime_token}"}
                if self.settings.maritime_token
                else {}
            )
            result = await http.json("GET", self.settings.maritime_url, headers=headers)
            return result["observations"]
        attempts: list = []
        if self.settings.aisstream_api_key:
            # A keyed account is the only stream that names the vessels it
            # reports, so it is tried first. The anonymous streams stay behind it
            # so collection continues when the account is rate limited, out of
            # its three connections or suspended.
            attempts.append(self._collect_aisstream)
        if self.settings.barentswatch_client_id and self.settings.barentswatch_client_secret:
            # Norwegian coast lane: streamed open data with the ship type in
            # every update. A failure here falls through to the worldwide
            # lanes rather than implying they are broken.
            attempts.append(lambda: self._collect_barentswatch(http))
        attempts.append(self._collect_worldwide)
        attempts.append(lambda: self._collect_region(OPEN_WATERS))
        failure: Exception | None = None
        for attempt in attempts:
            try:
                return await attempt()
            except Exception as error:
                # The first failure is the most relevant one to report.
                failure = failure or error
        raise failure

    async def _collect_aisstream(self) -> list[dict]:
        host = urlsplit(AISSTREAM["url"]).hostname
        if host not in APPROVED_HOSTS:
            raise ProviderError("AIS stream destination is not approved")
        observed_at = datetime.now(timezone.utc)
        vessels: dict[int, dict] = {}
        strips = [
            [[south, west], [north, east]] for _, south, west, north, east in WORLD_STRIPS
        ]
        results = await asyncio.gather(
            *(self._listen_aisstream(bbox, vessels) for bbox in strips),
            return_exceptions=True,
        )
        if all(isinstance(result, BaseException) for result in results):
            raise ProviderError("AIS stream connection failed") from None
        if not vessels:
            raise ProviderError("AIS stream produced no vessel positions")
        return [
            {
                **record,
                "region": "worldwide",
                "provider": AISSTREAM["name"],
                "source_url": AISSTREAM["homepage"],
                "observed_at": observed_at.isoformat(),
            }
            for record in vessels.values()
        ]

    async def _listen_aisstream(self, bbox: list, vessels: dict[int, dict]) -> None:
        subscription = {
            "APIKey": self.settings.aisstream_api_key,
            "BoundingBoxes": [bbox],
            "FilterMessageTypes": AISSTREAM_MESSAGE_TYPES,
        }
        try:
            # Uncompressed connections are bandwidth limited and the service
            # drops the excess rather than queueing it, so compression is
            # negotiated deliberately rather than left to the default.
            async with websockets.connect(
                AISSTREAM["url"],
                open_timeout=15,
                close_timeout=5,
                max_size=2**20,
                compression="deflate",
            ) as socket:
                await socket.send(json.dumps(subscription))
                loop = asyncio.get_running_loop()
                deadline = loop.time() + self._collect_seconds
                while True:
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        break
                    try:
                        frame = await asyncio.wait_for(socket.recv(), timeout=min(remaining, 15))
                    except (asyncio.TimeoutError, TimeoutError):
                        continue
                    self._merge(vessels, self._parse_aisstream(frame))
        except websockets.WebSocketException:
            # One strip failing only loses that slice of the globe; the other
            # strips keep delivering.
            if not vessels:
                raise ProviderError("AIS stream connection failed") from None
        except (OSError, ValueError):
            if not vessels:
                raise ProviderError("AIS stream returned malformed data") from None

    async def _collect_barentswatch(self, http: SafeHTTP) -> list[dict]:
        host = urlsplit(BARENTSWATCH["live_url"]).hostname
        if host not in APPROVED_HOSTS:
            raise ProviderError("BarentsWatch stream destination is not approved")
        token = await self._barentswatch_token()
        observed_at = datetime.now(timezone.utc)
        vessels: dict[int, dict] = {}
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._collect_seconds
        try:
            async for line in http.stream_lines(
                BARENTSWATCH["live_url"],
                max_bytes=12 * 1024 * 1024,
                headers={"Authorization": f"Bearer {token}"},
                content_type="application/x-ndjson",
            ):
                if loop.time() > deadline:
                    break
                try:
                    frame = json.loads(line)
                except ValueError:
                    continue
                self._merge(vessels, self._parse_barentswatch(frame))
        except (OSError, ValueError):
            if not vessels:
                raise ProviderError("BarentsWatch stream returned malformed data") from None
        if not vessels:
            raise ProviderError("BarentsWatch stream produced no vessel positions")
        return [
            {
                **record,
                "region": BARENTSWATCH["region"],
                "provider": BARENTSWATCH["name"],
                "source_url": BARENTSWATCH["homepage"],
                "observed_at": observed_at.isoformat(),
            }
            for record in vessels.values()
        ]

    async def _barentswatch_token(self) -> str:
        if self._token and time.monotonic() < self._token_expiry:
            return self._token
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                BARENTSWATCH["token_url"],
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.settings.barentswatch_client_id,
                    "client_secret": self.settings.barentswatch_client_secret,
                    "scope": "ais",
                },
                headers={"User-Agent": "SignalAtlas/0.1 (+https://github.com/abanerjee84/signal-atlas-osint)"},
            )
        if response.status_code == 401:
            raise ProviderError("BarentsWatch credentials rejected", retry_after=3600)
        if response.status_code != 200:
            raise ProviderError("BarentsWatch token request failed")
        try:
            payload = response.json()
        except ValueError:
            raise ProviderError("BarentsWatch token response was malformed") from None
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise ProviderError("BarentsWatch token response was empty")
        lifetime = payload.get("expires_in")
        self._token = token
        self._token_expiry = time.monotonic() + (
            float(lifetime) - 60 if isinstance(lifetime, (int, float)) and lifetime > 60 else 3600
        )
        return token

    @staticmethod
    def _parse_barentswatch(frame):
        # The live endpoint streams one JSON object per vessel update; fields
        # follow the OpenAPI names (name, shipType, courseOverGround, ...).
        if not isinstance(frame, dict):
            return None
        mmsi = frame.get("mmsi")
        if not isinstance(mmsi, int) or not 0 < mmsi < 2**32:
            return None
        record = {
            "mmsi": mmsi,
            "name": str(frame.get("name") or "").strip()[:60] or None,
            "latitude": _finite(frame.get("latitude")),
            "longitude": _finite(frame.get("longitude")),
            "speed_kn": _speed(frame.get("speedOverGround")),
            "course_deg": _course(frame.get("courseOverGround")),
            # shipType is the AIS static code and is present on nearly every
            # line, so a position-only update no longer erases it.
            "type": _ship_type(frame.get("shipType")),
            "upstream": None,
        }
        return record if any(
            record[key] is not None for key in ("name", "latitude", "speed_kn", "course_deg")
        ) else None

    async def _collect_worldwide(self) -> list[dict]:
        host = urlsplit(OPEN_SEAFEED["url"]).hostname
        if host not in APPROVED_HOSTS:
            raise ProviderError("AIS stream destination is not approved")
        observed_at = datetime.now(timezone.utc)
        vessels: dict[int, dict] = {}
        strips = [
            [[south, west], [north, east]] for _, south, west, north, east in WORLD_STRIPS
        ]
        results = await asyncio.gather(
            *(self._listen_openseafeed(bbox, vessels) for bbox in strips),
            return_exceptions=True,
        )
        if all(isinstance(result, BaseException) for result in results):
            raise ProviderError("AIS stream connection failed") from None
        if not vessels:
            raise ProviderError("AIS stream produced no vessel positions")
        return [
            {
                **record,
                "region": "worldwide",
                "provider": OPEN_SEAFEED["name"],
                "source_url": OPEN_SEAFEED["homepage"],
                "observed_at": observed_at.isoformat(),
            }
            for record in vessels.values()
        ]

    async def _listen_openseafeed(self, bbox: list, vessels: dict[int, dict]) -> None:
        try:
            async with websockets.connect(
                OPEN_SEAFEED["url"], open_timeout=15, close_timeout=5, max_size=2**20
            ) as socket:
                await socket.send(json.dumps({"BoundingBoxes": [bbox]}))
                loop = asyncio.get_running_loop()
                deadline = loop.time() + self._collect_seconds
                while True:
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        break
                    try:
                        frame = await asyncio.wait_for(socket.recv(), timeout=min(remaining, 15))
                    except (asyncio.TimeoutError, TimeoutError):
                        continue
                    self._merge(vessels, self._parse_openseafeed(json.loads(frame)))
        except websockets.WebSocketException:
            # One strip failing only loses that slice of the globe; the other
            # strips keep delivering.
            if not vessels:
                raise ProviderError("AIS stream connection failed") from None

    async def _collect_region(self, provider: dict) -> list[dict]:
        host = urlsplit(provider["url"]).hostname
        if host not in APPROVED_HOSTS:
            raise ProviderError("AIS stream destination is not approved")
        self._region_index = (self._region_index + 1) % len(REGIONS)
        region_name, south, west, north, east = REGIONS[self._region_index]
        observed_at = datetime.now(timezone.utc)
        vessels: dict[int, dict] = {}
        try:
            async with websockets.connect(
                provider["url"], open_timeout=15, close_timeout=5, max_size=2**20
            ) as socket:
                await socket.send(json.dumps({"type": "subscribe", "bbox": [[south, west, north, east]]}))
                loop = asyncio.get_running_loop()
                deadline = loop.time() + self._collect_seconds
                while True:
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        break
                    try:
                        frame = await asyncio.wait_for(socket.recv(), timeout=min(remaining, 15))
                    except (asyncio.TimeoutError, TimeoutError):
                        continue
                    self._merge(vessels, self._parse_open_waters(json.loads(frame)))
        except websockets.WebSocketException:
            # An early close after partial delivery keeps what was already heard.
            if not vessels:
                raise ProviderError("AIS stream connection failed") from None
        except (OSError, ValueError):
            if not vessels:
                raise ProviderError("AIS stream returned malformed data") from None
        if not vessels:
            raise ProviderError("AIS stream produced no vessel positions")
        return [
            {
                **record,
                "region": region_name,
                "provider": provider["name"],
                "source_url": provider["homepage"],
                "observed_at": observed_at.isoformat(),
            }
            for record in vessels.values()
        ]

    @staticmethod
    def _parse_aisstream(frame):
        # AIS Stream sends binary WebSocket frames whose payload is UTF-8 JSON.
        if isinstance(frame, (bytes, bytearray)):
            frame = bytes(frame).decode("utf-8", "replace")
        if isinstance(frame, str):
            try:
                frame = json.loads(frame)
            except ValueError:
                return None
        if not isinstance(frame, dict):
            return None
        message_type = frame.get("MessageType")
        if not isinstance(message_type, str) or message_type not in AISSTREAM_MESSAGE_TYPES:
            # A SubscriptionConfirmation carries no AIS metadata, and any other
            # message type is not something this collector stores.
            return None
        metadata = frame.get("MetaData") or {}
        body = (frame.get("Message") or {}).get(message_type) or {}
        if not isinstance(metadata, dict) or not isinstance(body, dict):
            return None
        mmsi = metadata.get("MMSI") or body.get("UserID")
        if not isinstance(mmsi, int) or isinstance(mmsi, bool) or not 0 < mmsi < 2**32:
            return None
        # Static and voyage messages name the vessel but carry no position, and
        # position messages name it only when a recent static report supplied
        # one. Merging keeps whichever field each frame actually carried.
        name = metadata.get("ShipName") or body.get("Name")
        # Static data also carries the AIS ship type code; position messages
        # carry navigational status instead, a different field that must not
        # be misread as a type.
        ship_type = _ship_type(body.get("Type"))
        # AIS Stream normalises position into MetaData while speed and course
        # stay in the decoded message, so each field is read from both.
        latitude = _finite(body.get("Latitude"))
        if latitude is None:
            latitude = _finite(metadata.get("Latitude"))
        longitude = _finite(body.get("Longitude"))
        if longitude is None:
            longitude = _finite(metadata.get("Longitude"))
        record = {
            "mmsi": mmsi,
            # Ship names arrive space padded to the AIS field width.
            "name": str(name).strip()[:60] if name else None,
            "latitude": latitude,
            "longitude": longitude,
            "speed_kn": _speed(body.get("Sog")),
            "course_deg": _course(body.get("Cog")),
            "type": ship_type,
            "upstream": None,
        }
        return record if any(
            record[key] is not None
            for key in ("name", "latitude", "speed_kn", "course_deg")
        ) else None

    @staticmethod
    def _parse_open_waters(frame):
        if not isinstance(frame, dict) or frame.get("type") != "event":
            return None
        mmsi = frame.get("mmsi")
        if not isinstance(mmsi, int) or not 0 < mmsi < 2**32:
            return None
        record = {
            "mmsi": mmsi,
            "name": str(frame.get("name") or "").strip()[:60] or None,
            "latitude": _finite(frame.get("lat")),
            "longitude": _finite(frame.get("lon")),
            "speed_kn": _speed(frame.get("sog", frame.get("speed_kn"))),
            "course_deg": _course(frame.get("cog", frame.get("course_deg"))),
            "type": _ship_type(frame.get("ship_type")),
            "upstream": str(frame.get("source") or "")[:40] or None,
        }
        return record if any(
            record[key] is not None for key in ("name", "latitude", "speed_kn", "course_deg")
        ) else None

    @staticmethod
    def _parse_openseafeed(frame):
        if not isinstance(frame, dict):
            return None
        message = frame.get("Message")
        metadata = frame.get("Metadata") or {}
        if not isinstance(message, dict) or not message:
            return None
        body = next(iter(message.values()))
        mmsi = body.get("UserID") if isinstance(body, dict) else None
        mmsi = mmsi or (metadata.get("MMSI") if isinstance(metadata, dict) else None)
        if not isinstance(mmsi, int) or not 0 < mmsi < 2**32:
            return None
        record = {
            "mmsi": mmsi,
            "name": None,
            "latitude": None,
            "longitude": None,
            "speed_kn": None,
            "course_deg": None,
            "type": None,
            "upstream": None,
        }
        if isinstance(body, dict):
            record["latitude"] = _finite(body.get("Latitude"))
            record["longitude"] = _finite(body.get("Longitude"))
            record["speed_kn"] = _speed(body.get("Sog"))
            record["course_deg"] = _course(body.get("Cog"))
            record["type"] = _ship_type(body.get("Type"))
        for source in (body, metadata):
            if isinstance(source, dict):
                name = source.get("Name") or source.get("VesselName")
                if name:
                    record["name"] = str(name).strip()[:60]
                    break
        return record

    @staticmethod
    def _merge(vessels: dict[int, dict], record) -> None:
        if not record:
            return
        existing = vessels.get(record["mmsi"])
        if existing is None:
            if record["latitude"] is not None and record["longitude"] is not None:
                vessels[record["mmsi"]] = record
            return
        for field in ("name", "speed_kn", "course_deg", "type", "upstream"):
            if record.get(field) is not None:
                existing[field] = record[field]
        if record["latitude"] is not None and record["longitude"] is not None:
            existing["latitude"] = record["latitude"]
            existing["longitude"] = record["longitude"]

    def select_records(self, records):
        limit = min(self.per_cycle_cap, self.settings.max_records)
        return spatial_sample(records, limit, lambda record: (record.get("longitude"), record.get("latitude")))

    def normalize(self, record: dict) -> Report:
        if "provider" not in record:
            return self._normalize_licensed(record)
        mmsi = record["mmsi"]
        name = record.get("name") or str(mmsi)
        observed_at = parse_time(record["observed_at"])
        details = [f"MMSI {mmsi}"]
        if record.get("speed_kn") is not None:
            details.append(f"speed {record['speed_kn']:.1f} kn")
        if record.get("course_deg") is not None:
            details.append(f"course {record['course_deg']:.0f} degrees")
        details.append(f"region {record['region']}")
        attribution = record["provider"] + (
            f", upstream {record['upstream']}" if record.get("upstream") else ""
        )
        return Report(
            external_id=f"mmsi:{mmsi}",
            source_id=self.source_id,
            source_url=record["source_url"],
            title=f"Vessel {name}",
            description=(
                "; ".join(details)
                + f". Self-reported AIS static data via {attribution}; names unverified; incomplete coverage."
            ),
            category=self.category,
            latitude=record["latitude"],
            longitude=record["longitude"],
            location_precision="approximate",
            location_basis=f"Public AIS reported position via {record['provider']}; incomplete coverage",
            occurred_at=observed_at,
            published_at=observed_at,
            tags=["ais", str(mmsi)],
            vessel_course_deg=record.get("course_deg"),
            vessel_speed_kn=record.get("speed_kn"),
            # The flag state and the type come from self-assigned AIS data:
            # the flag is the registered prefix of the MMSI, which can
            # deliberately differ from ownership, and the type code is what
            # the transmitter last reported.
            vessel_type=record.get("type"),
            vessel_flag=flag_of_mmsi(mmsi),
            raw=record,
        )

    def _normalize_licensed(self, record: dict) -> Report:
        observed = parse_time(record["observed_at"])
        return Report(
            external_id=f"{record['mmsi']}:{record['observed_at']}",
            source_id=self.source_id,
            source_url=record["source_url"],
            title=f"Vessel {record.get('name') or record['mmsi']}",
            description=(
                f"MMSI {record['mmsi']}; class {record.get('class', 'unknown')}; "
                f"last reported position {record['observed_at']}."
            ),
            category=self.category,
            latitude=record["latitude"],
            longitude=record["longitude"],
            location_precision="approximate",
            location_basis="Provider-reported AIS observation",
            occurred_at=observed,
            published_at=parse_time(record.get("published_at", record["observed_at"])),
            tags=["ais", str(record["mmsi"])],
            raw=record,
        )
