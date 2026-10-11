import asyncio
import json
from contextlib import aclosing
from datetime import timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.connectors.base import ProviderError, SafeHTTP
from backend.connectors.threat_maps import (
    BitdefenderMap,
    BunkerWebMap,
    engine_packets,
    engine_payload,
    observation,
)
from backend.models import Filters, stamp, utcnow
from backend.worker import collect


def sample(**values):
    return observation(
        {"attacker": "SG", "target": "FR", "reason": "blacklist", "date": "17:30:51", **values},
        "synthetic-collection",
        0,
    )


def test_traffic_is_not_actor_attribution_and_time_of_day_is_not_an_occurrence(settings, database):
    item = BunkerWebMap(settings).normalize(
        sample(ip="192.0.2.1", token="never-store", attacker_latitude=0, target_longitude=0)
    )
    assert item.threat.actor == "Unknown actor"
    assert item.threat.attacker_country is None and item.threat.victim_countries == []
    assert item.threat.traffic_origin_country == "SG"
    assert item.threat.traffic_target_country == "FR"
    assert item.occurred_at is None
    assert item.threat.provider_time == "17:30:51"
    assert item.location_precision == "regional"
    assert item.longitude != 0 and item.latitude != 0
    assert "192.0.2.1" not in item.model_dump_json() and "never-store" not in item.model_dump_json()
    event_id = database.ingest(item)
    assert database.detail(event_id)["threat"]["classification"] == "observed_traffic"


def test_unknown_traffic_origin_remains_unknown_and_single_detections_have_no_edge_roles(settings):
    item = BunkerWebMap(settings).normalize(sample(attacker="ZZ"))
    assert item.threat.traffic_origin_country is None
    with pytest.raises(ValueError, match="No supported"):
        BunkerWebMap(settings).normalize(sample(attacker="ZZ", target="unknown"))
    row = observation(
        {"n": "infections", "loc": {"c_iso": "US", "lat": 0, "long": 0}, "ts": 1770000000000},
        "synthetic-bit",
        0,
    )
    detection = BitdefenderMap(settings).normalize(row)
    assert detection.threat.classification == "detection"
    assert detection.threat.detection_country == "US"
    assert detection.threat.traffic_origin_country is None
    assert detection.threat.traffic_target_country is None
    with pytest.raises(ValueError, match="cannot establish"):
        detection.threat.model_copy(update={"attacker_country": "US"}).__class__.model_validate(
            {**detection.threat.model_dump(), "attacker_country": "US"}
        )


def test_polling_frames_use_javascript_lengths_and_reject_truncation():
    packets = ['0{"sid":"synthetic"}', '42["ev",[{"detection":"test 🌐"}]]']
    assert engine_packets(engine_payload(packets)) == packets
    for broken in [b"ok", b"3:42", b"0:", b"-1:4", b"999999999999:a"]:
        with pytest.raises((ValueError, UnicodeError)):
            engine_packets(broken)


@pytest.mark.asyncio
async def test_bitdefender_plain_ok_is_visible_failure_and_retains_previous_data(settings, database):
    provider = BitdefenderMap(settings)
    row = observation({"n": "ssh", "from": {"c_iso": "SG"}, "to": {"c_iso": "FR"}}, "synthetic-bit", 0)
    database.ingest(provider.normalize(row))
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="ok"))
    ) as client:
        result = await collect(provider, database, SafeHTTP(settings, client))
    assert result["state"] == "error" and "no valid Socket.IO handshake" in result["error"]
    assert database.events(Filters(categories=["threat"]))["total"] == 1


@pytest.mark.asyncio
async def test_bitdefender_subscribes_to_real_channels_and_preserves_direction(settings):
    posts = []
    event = {"n": "ssh", "from": {"c_iso": "SG"}, "to": {"c_iso": "FR"}, "ip": "192.0.2.1"}

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.method == "POST":
            posts.extend(engine_packets(request.content))
            return httpx.Response(200, text="ok")
        if "sid" not in request.url.params:
            return httpx.Response(
                200,
                content=engine_payload(["0" + json.dumps({"sid": "synthetic", "pingInterval": 25000}), "40"]),
            )
        return httpx.Response(200, content=engine_payload(["42" + json.dumps(["ev", [event]])]))

    provider = BitdefenderMap(settings)
    provider.sample_limit = 1
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await provider.fetch(SafeHTTP(settings, client))
    assert len(posts) == 11 and '"subscribe"' in posts[0]
    assert all('"spam"' not in packet and '"infections"' not in packet for packet in posts)
    item = provider.normalize(records[0])
    assert (item.threat.traffic_origin_country, item.threat.traffic_target_country) == ("SG", "FR")
    assert "192.0.2.1" not in item.model_dump_json()


@pytest.mark.asyncio
async def test_sse_rejoins_data_lines_and_closes_at_sample_bound(settings):
    payload = b': heartbeat\n\ndata: {"attacker":"SG",\ndata: "target":"FR","reason":"blacklist","date":"17:30:51"}\n\n'

    def handler(request):
        return (
            httpx.Response(404)
            if request.url.path == "/robots.txt"
            else httpx.Response(200, headers={"content-type": "text/event-stream"}, content=payload)
        )

    provider = BunkerWebMap(settings)
    provider.sample_limit = 1
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await provider.fetch(SafeHTTP(settings, client))
    assert len(rows) == 1
    assert provider.normalize(rows[0]).threat.traffic_target_country == "FR"


@pytest.mark.asyncio
async def test_sse_time_budget_keeps_received_sample_and_closes(settings):
    closed = []

    async def lines(url):
        try:
            yield 'data: {"attacker":"SG","target":"FR"}'
            yield ""
            await asyncio.sleep(10)
        finally:
            closed.append(True)

    http = AsyncMock()
    http.request.return_value = b"User-agent: *\nDisallow:\n"
    http.stream_lines = lines
    provider = BunkerWebMap(settings)
    provider.sample_seconds = 0.01
    rows = await provider.fetch(http)
    assert len(rows) == 1 and closed == [True]


@pytest.mark.asyncio
async def test_stream_rejects_denials_redirects_and_oversized_lines(settings):
    for response, match in [
        (httpx.Response(403), "403"),
        (httpx.Response(302, headers={"Location": "https://127.0.0.1/"}), "302"),
        (httpx.Response(429, headers={"Retry-After": "600"}), "unavailable"),
        (httpx.Response(200, text="<html>login</html>"), "event stream"),
        (
            httpx.Response(200, headers={"content-type": "text/event-stream"}, content=b"x" * 65537),
            "line exceeded",
        ),
    ]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response)) as client:
            with pytest.raises(ProviderError, match=match):
                async with aclosing(
                    SafeHTTP(settings, client).stream_lines(BunkerWebMap.stream_url)
                ) as lines:
                    async for _ in lines:
                        pass


@pytest.mark.asyncio
async def test_robots_redirect_is_validated_and_disallow_stops_collection(settings):
    def handler(request):
        if request.url.host == "threatmap.bunkerweb.io":
            return httpx.Response(301, headers={"Location": "https://127.0.0.1/internal"})
        return httpx.Response(200, text="User-agent: *\nDisallow:\n")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError, match="approved"):
            await BunkerWebMap(settings).fetch(SafeHTTP(settings, client))
    http = AsyncMock()
    http.request.return_value = b"User-agent: *\nDisallow: /threatmap/\n"
    with pytest.raises(ProviderError, match="robots policy"):
        await BunkerWebMap(settings).fetch(http)
    assert http.request.call_count == 1


def test_retention_caps_telemetry_without_deleting_published_reports(settings, database, report):
    database.ingest(report)
    provider = BunkerWebMap(settings)
    for index in range(2002):
        database.ingest(
            provider.normalize(observation({"attacker": "SG", "target": "FR"}, "synthetic-cap", index))
        )
    assert database.prune_threat_telemetry(provider.source_id) == 2
    assert database.events(Filters(categories=["threat"]))["total"] == 2000
    with database.connect() as db:
        db.execute(
            "UPDATE events SET ingested_at=? WHERE source_id=?",
            (stamp(utcnow() - timedelta(days=8)), provider.source_id),
        )
    assert database.prune_threat_telemetry(provider.source_id) == 2000
    assert database.events(Filters())["total"] == 1
    with database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0] == 1
    with pytest.raises(ValueError):
        database.prune_threat_telemetry(report.source_id)
