import asyncio
import json

import httpx
import pytest

from backend.connectors.base import ProviderError, SafeHTTP
from backend.connectors.cisa import CISA
from backend.connectors.firms import FIRMS
from backend.connectors.gdelt import GDELT
from backend.connectors.opensky import OpenSky
from backend.connectors.rss import RSS
from backend.connectors.usgs import USGS
from backend.models import Filters, utcnow
from backend.worker import collect


def synthetic_quake():
    now = int(utcnow().timestamp() * 1000)
    return {
        "id": "synthetic-quake",
        "properties": {
            "title": "Synthetic earthquake fixture",
            "type": "earthquake",
            "mag": 5,
            "time": now,
            "updated": now,
            "url": "https://earthquake.usgs.gov/earthquakes/eventpage/synthetic",
            "status": "reviewed",
        },
        "geometry": {"type": "Point", "coordinates": [78, 20, 10]},
    }


async def test_source_database_api_path(settings, database):
    fixture = synthetic_quake()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"features": [fixture, {}]}))
    ) as client:
        result = await collect(USGS(settings), database, SafeHTTP(settings, client))
    assert result["state"] == "ok"
    assert result["stored"] == 1
    assert result["rejected"] == 1
    event = database.events(Filters())["items"][0]
    assert database.detail(event["event_id"])["reports"][0]["metadata"]["external_id"] == fixture["id"]


async def test_provider_failure_keeps_last_success(settings, database):
    successful = synthetic_quake()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"features": [successful]}))
    ) as client:
        await collect(USGS(settings), database, SafeHTTP(settings, client))
    last = database.statuses()[0]["last_success"]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(403))
    ) as client:
        result = await collect(USGS(settings), database, SafeHTTP(settings, client))
    assert result["state"] == "error"
    assert database.statuses()[0]["last_success"] == last
    assert database.events(Filters())["total"] == 1


async def test_credentials_fail_closed(settings, database):
    def unexpected(request):
        raise AssertionError("Credential-dependent feed must not be called")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        assert (await collect(FIRMS(settings), database, SafeHTTP(settings, client)))[
            "state"
        ] == "access_required"


async def test_errors_do_not_leak_secrets(settings, database):
    settings.firms_map_key = "synthetic-secret-never-log"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(403))
    ) as client:
        result = await collect(FIRMS(settings), database, SafeHTTP(settings, client))
    assert "synthetic-secret" not in json.dumps(result)
    assert "synthetic-secret" not in json.dumps(database.statuses())


async def test_size_redirect_and_ssrf(settings):
    settings.max_feed_bytes = 1024
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 1025))
    ) as client:
        with pytest.raises(ProviderError, match="size limit"):
            await SafeHTTP(settings, client).request("GET", "https://earthquake.usgs.gov/test")
        with pytest.raises(ProviderError, match="approved"):
            await SafeHTTP(settings, client).request("GET", "https://127.0.0.1/internal")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(302, headers={"Location": "http://127.0.0.1"})
        )
    ) as client:
        with pytest.raises(ProviderError, match="302"):
            await SafeHTTP(settings, client).request("GET", "https://earthquake.usgs.gov/test")


async def test_rate_limit_retry(monkeypatch, settings):
    calls = []

    async def no_sleep(seconds):
        calls.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(429, headers={"Retry-After": "3"}))
    ) as client:
        with pytest.raises(ProviderError, match="429"):
            await SafeHTTP(settings, client).json("GET", "https://earthquake.usgs.gov/test")
    assert calls == [3, 3]


def test_gdelt_never_uses_publisher_country_for_incident(settings):
    report = GDELT(settings).normalize(
        {
            "url": "https://example.org/synthetic",
            "title": "Synthetic headline without a country",
            "seendate": "20261010T060000Z",
            "sourcecountry": "India",
            "language": "English",
        }
    )
    assert report.latitude is None and report.country_code is None
    named = GDELT(settings).normalize(
        {
            "url": "https://example.org/synthetic",
            "title": "Synthetic news about India",
            "seendate": "20261010T060000Z",
            "sourcecountry": "United States",
            "language": "English",
        }
    )
    assert named.location_precision == "regional" and named.country_code == "IN"


async def test_xml_entities_rejected(settings):
    payload = b'<!DOCTYPE rss [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><rss><channel><item><title>&xxe;</title></item></channel></rss>'
    provider = RSS(
        settings,
        source_id="test",
        name="Synthetic",
        category="geopolitical",
        url="https://feeds.bbci.co.uk/test",
    )
    from defusedxml.common import DefusedXmlException

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=payload))
    ) as client:
        with pytest.raises(DefusedXmlException):
            await provider.fetch(SafeHTTP(settings, client))


def test_firms_not_wildfire_assertion(settings):
    report = FIRMS(settings).normalize(
        {
            "latitude": "20",
            "longitude": "78",
            "acq_date": "2026-10-10",
            "acq_time": "630",
            "confidence": "h",
            "frp": "15",
        }
    )
    assert "not confirmation" in report.description
    assert report.confidence == "Single-source"


def test_cisa_has_no_precise_coordinates(settings):
    report = CISA(settings).normalize(
        {
            "cveID": "CVE-synthetic",
            "vulnerabilityName": "Synthetic vulnerability",
            "shortDescription": "Synthetic",
            "requiredAction": "Synthetic action",
            "dateAdded": "2026-10-10",
            "vendorProject": "Synthetic",
        }
    )
    assert report.latitude is None and report.longitude is None


def test_geographic_sampling_does_not_keep_only_first_region(settings):
    settings.max_records = 10
    records = [{"longitude": 78, "latitude": 20, "id": index} for index in range(200)]
    records += [
        {"longitude": -120, "latitude": 40, "id": "west"},
        {"longitude": 150, "latitude": -30, "id": "south"},
    ]
    selected = FIRMS(settings).select_records(records)
    assert len(selected) == 10
    assert {record["id"] for record in selected} >= {"west", "south"}
    assert len({record["id"] for record in selected}) == 10


async def test_opensky_world_request_and_missing_callsign(settings):
    settings.opensky_client_id = "synthetic-client"
    settings.opensky_client_secret = "synthetic-secret"
    settings.opensky_bbox = "world"
    now = int(utcnow().timestamp())
    state = ["abcdef", None, "Synthetic", now, now, -120, 40, 1000, False, 100]

    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"access_token": "synthetic-token"})
        assert dict(request.url.params) == {"extended": "1"}
        return httpx.Response(200, json={"time": now, "states": [state]})

    provider = OpenSky(settings)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await provider.fetch(SafeHTTP(settings, client))
    assert provider.normalize(records[0]).title == "Aircraft abcdef"
    assert provider.metadata()["coverage_scope"] == "world"


async def test_firms_world_request(settings):
    settings.firms_map_key = "synthetic-key"
    settings.firms_area = "world"

    def handler(request):
        assert request.url.path.endswith("/VIIRS_NOAA20_NRT/world/1")
        return httpx.Response(200, content=b"latitude,longitude\n40,-120\n")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await FIRMS(settings).fetch(SafeHTTP(settings, client))
    assert records[0]["longitude"] == "-120"
