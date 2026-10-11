import asyncio
import html
import ipaddress
import json
import math
import re
import socket
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

import httpx

from ..config import Settings
from ..models import Report

APPROVED_HOSTS = {
    "www.imperva.com",
    "threatmap.bitdefender.com",
    "threatmap.bunkerweb.io",
    "www.bunkerweb.io",
    "blog.talosintelligence.com",
    "www.bleepingcomputer.com",
    "www.securityweek.com",
    "feeds.feedburner.com",
    "therecord.media",
    "www.cybersecuritydive.com",
    "www.welivesecurity.com",
    "www.microsoft.com",
    "mastodon.social",
    "lemmy.world",
    "t.me",
    "www.crisisgroup.org",
    "www.al-monitor.com",
    "www.scmp.com",
    "feeds.npr.org",
    "arctic-shift.photon-reddit.com",
    "www.dvidshub.net",
    "earthquake.usgs.gov",
    "api.gdeltproject.org",
    "feeds.bbci.co.uk",
    "www.nato.int",
    "www.ecb.europa.eu",
    "www.eia.gov",
    "www.cisa.gov",
    "www.ncsc.gov.uk",
    "ofac.treasury.gov",
    "raw.githubusercontent.com",
    "firms.modaps.eosdis.nasa.gov",
    "api.reliefweb.int",
    "acleddata.com",
    "opensky-network.org",
    "auth.opensky-network.org",
    "openrouter.ai",
    "www.gov.uk",
    "www.reddit.com",
    "www.youtube.com",
    "www.aljazeera.com",
    "rss.dw.com",
    "www.theguardian.com",
    "www.france24.com",
    "news.un.org",
    "www.africanews.com",
    "en.mercopress.com",
    "buenosairesherald.com",
    "www.channelnewsasia.com",
    "www.rfi.fr",
    "www.abc.net.au",
    "www.euronews.com",
    "stat.ripe.net",
    "api.ioda.inetintel.cc.gatech.edu",
    "isc.sans.edu",
    "citizenlab.ca",
    "krebsonsecurity.com",
    "defend.network",
    "malpedia.caad.fkie.fraunhofer.de",
    "apt.etda.or.th",
}


class AccessRequired(Exception):
    pass


class ProviderError(Exception):
    """Safe message for status records. Never embeds request URLs or tokens."""

    def __init__(self, message, retry_after=0, status_code=None):
        super().__init__(message)
        self.retry_after = retry_after
        self.status_code = status_code


def clean(value: str, bound: int = 10000) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", str(value))))[:bound].strip()


def parse_time(value: str) -> datetime:
    from email.utils import parsedate_to_datetime

    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            result = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            result = parsedate_to_datetime(value)
    return (result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result).astimezone(timezone.utc)


def box(value: str) -> tuple[float, float, float, float]:
    from ..models import Filters

    coordinates = tuple(float(part) for part in value.split(","))
    return Filters(bbox=coordinates).bbox


def spatial_sample(records: list[dict], limit: int, coordinates) -> list[dict]:
    """Bound stored observations with round-robin coverage across 30-degree cells."""
    if len(records) <= limit:
        return records
    cells = {}
    for record in records:
        cell = (999, 999)
        try:
            longitude, latitude = (float(value) for value in coordinates(record))
            if (
                math.isfinite(longitude)
                and math.isfinite(latitude)
                and -180 <= longitude <= 180
                and -90 <= latitude <= 90
            ):
                cell = (int((longitude + 180) // 30), int((latitude + 90) // 30))
        except (ValueError, TypeError, KeyError, IndexError):
            pass
        cells.setdefault(cell, deque()).append(record)
    groups = [cells[key] for key in sorted(cells)]
    selected = []
    while groups:
        for group in groups:
            selected.append(group.popleft())
            if len(selected) == limit:
                return selected
        groups = [group for group in groups if group]
    return selected


class SafeHTTP:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings, self.client = settings, client

    async def validate(self, url: str) -> None:
        parsed = urlsplit(url)
        allowed = APPROVED_HOSTS | set(self.settings.extra_allowed_hosts)
        if parsed.scheme != "https" or parsed.hostname not in allowed or parsed.username or parsed.password:
            raise ProviderError("Outbound destination is not approved HTTPS")
        if parsed.port not in {None, 443}:
            raise ProviderError("Outbound port is not approved")
        if parsed.hostname not in APPROVED_HOSTS:
            # Defense for administrator-configured feeds. Deployment egress controls also recommended.
            addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, 443)
            if not addresses or any(
                not ipaddress.ip_address(address[4][0]).is_global for address in addresses
            ):
                raise ProviderError("Configured feed resolves to a non-public address")

    async def request(
        self, method: str, url: str, *, attempts: int = 3, max_bytes=None, redirects=0, **kwargs
    ) -> bytes:
        await self.validate(url)
        bound = self.settings.max_feed_bytes if max_bytes is None else min(max_bytes, 100_663_296)
        for attempt in range(attempts):
            try:
                async with self.client.stream(method, url, follow_redirects=False, **kwargs) as response:
                    if (
                        response.status_code in {301, 302, 303, 307, 308}
                        and method == "GET"
                        and 0 < redirects <= 3
                    ):
                        destination = urljoin(url, response.headers.get("location", ""))
                        # Explicit opt-in only for public robots reads; every hop is validated.
                        await response.aclose()
                        return await self.request(
                            method,
                            destination,
                            attempts=attempts,
                            max_bytes=bound,
                            redirects=redirects - 1,
                            **kwargs,
                        )
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt + 1 == attempts:
                            try:
                                retry_after = max(
                                    300,
                                    float(
                                        response.headers.get(
                                            "X-Rate-Limit-Retry-After-Seconds",
                                            response.headers.get("Retry-After", "300"),
                                        )
                                    ),
                                )
                                retry_after = min(86400, retry_after) if math.isfinite(retry_after) else 300
                            except ValueError:
                                try:
                                    retry_after = max(
                                        300,
                                        (
                                            parse_time(response.headers["Retry-After"])
                                            - datetime.now(timezone.utc)
                                        ).total_seconds(),
                                    )
                                except (ValueError, TypeError, KeyError):
                                    retry_after = 300
                            raise ProviderError(
                                f"Provider HTTP {response.status_code}; retry budget exhausted",
                                retry_after=retry_after,
                            )
                        try:
                            delay = min(15, max(1, float(response.headers.get("Retry-After", 2**attempt))))
                        except ValueError:
                            delay = 2**attempt
                        await asyncio.sleep(delay)
                        continue
                    if not 200 <= response.status_code < 300:
                        raise ProviderError(
                            f"Provider HTTP {response.status_code}", status_code=response.status_code
                        )
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > bound:
                            raise ProviderError("Provider response exceeded configured size limit")
                        chunks.append(chunk)
                    return b"".join(chunks)
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt + 1 == attempts:
                    raise ProviderError("Provider network failure or timeout") from None
                await asyncio.sleep(2**attempt)
        raise ProviderError("Provider request failed")

    async def json(self, method: str, url: str, **kwargs) -> dict:
        try:
            return json.loads(await self.request(method, url, **kwargs))
        except (ValueError, UnicodeError):
            raise ProviderError("Provider returned malformed JSON") from None

    async def stream_lines(self, url: str, *, max_bytes=1_048_576):
        """Validated, bounded public SSE read. Caller sets a total time budget."""
        await self.validate(url)
        try:
            async with self.client.stream("GET", url, follow_redirects=False) as response:
                if response.status_code == 429 or response.status_code >= 500:
                    try:
                        delay = float(response.headers.get("Retry-After", "300"))
                        delay = min(86400, max(300, delay)) if math.isfinite(delay) else 300
                    except ValueError:
                        delay = 300
                    raise ProviderError("Public stream temporarily unavailable", retry_after=delay)
                if response.status_code != 200:
                    raise ProviderError(
                        f"Provider HTTP {response.status_code}", status_code=response.status_code
                    )
                if not response.headers.get("content-type", "").startswith("text/event-stream"):
                    raise ProviderError("Provider did not return a public event stream")
                # Decode incrementally; a peer cannot grow an unterminated line unboundedly.
                pending, size = b"", 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > min(max_bytes, self.settings.max_feed_bytes):
                        raise ProviderError("Public stream exceeded configured size limit")
                    pending += chunk
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        yield line.rstrip(b"\r").decode("utf-8", errors="replace")
                    if len(pending) > 65536:
                        raise ProviderError("Public stream line exceeded size limit")
        except (httpx.TimeoutException, httpx.NetworkError):
            raise ProviderError("Public stream network failure or timeout") from None


class Connector(ABC):
    source_id: str
    name: str
    category: str
    homepage: str
    interval: int = 900
    limitation: str
    independence: str = "Source assertions do not establish independent corroboration"
    snapshot: bool = False

    def __init__(self, settings: Settings):
        self.settings = settings

    def access(self) -> str | None:
        return None

    def select_records(self, records: list[dict]) -> list[dict]:
        return records[: self.settings.max_records]

    def metadata(self) -> dict:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "category": self.category,
            "homepage": self.homepage,
            "interval_seconds": self.interval,
            "limitation": self.limitation,
            "access_requirement": self.access(),
        }

    @abstractmethod
    async def fetch(self, http: SafeHTTP) -> list[dict]: ...

    @abstractmethod
    def normalize(self, record: dict) -> Report: ...
