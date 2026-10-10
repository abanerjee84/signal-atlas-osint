from datetime import timedelta

import httpx
from fastapi.testclient import TestClient

from backend.aviation import current_aircraft
from backend.connectors.base import SafeHTTP
from backend.connectors.opensky import OpenSky
from backend.connectors.registry import connectors
from backend.main import create_app
from backend.models import Filters, stamp, utcnow
from backend.worker import collect


def state(timestamp, longitude=75, altitude=10000, speed=250):
    return [
        "abcdef",
        "TEST123",
        "Synthetic",
        timestamp,
        timestamp,
        longitude,
        20,
        altitude,
        False,
        speed,
        90,
        1.5,
        None,
        altitude + 100,
        None,
        False,
        0,
        4,
    ]


async def test_live_moves_without_flooding_history_and_filters_apply(settings, database):
    settings.opensky_client_id = settings.opensky_client_secret = "synthetic"
    provider = OpenSky(settings)
    timestamp = int(utcnow().timestamp())
    records = [{"state": state(timestamp - 120), "time": timestamp}]

    async def fetch(_):
        return records

    provider.fetch = fetch
    await collect(provider, database, None)
    first = current_aircraft(database, Filters())["items"][0]
    records[:] = [{"state": state(timestamp, longitude=75.2), "time": timestamp}]
    await collect(provider, database, None)
    second = current_aircraft(database, Filters())["items"][0]
    assert second["event_id"] == first["event_id"] and second["longitude"] == 75.2
    assert second["aircraft"]["barometric_altitude_m"] == 10000
    assert second["aircraft"]["registration_country"] == "Synthetic"
    assert database.events(Filters(categories=["aviation"]))["total"] == 1
    assert current_aircraft(database, Filters(country="US"))["items"] == []
    assert current_aircraft(database, Filters(q="nonexistent"))["items"] == []
    assert current_aircraft(database, Filters(bbox=(-100, 0, -80, 50)))["items"] == []
    assert len(current_aircraft(database, Filters(q="TEST123", country="IN"))["items"]) == 1

    # Provider failure preserves the last successful snapshot; successful empty
    # snapshots clear it, and old positions cannot masquerade as current.
    async def broken(_):
        raise ValueError("synthetic failure")

    provider.fetch = broken
    await collect(provider, database, None)
    assert len(current_aircraft(database, Filters())["items"]) == 1
    provider.fetch = fetch
    records.clear()
    await collect(provider, database, None)
    assert current_aircraft(database, Filters())["items"] == []
    records[:] = [{"state": state(timestamp - 900), "time": timestamp}]
    await collect(provider, database, None)
    assert current_aircraft(database, Filters())["items"] == []


async def test_token_reused_and_quota_backoff_preserved(settings, database):
    settings.opensky_client_id = settings.opensky_client_secret = "synthetic"
    token_requests = []
    provider = OpenSky(settings)

    def handler(request):
        if request.method == "POST":
            token_requests.append(1)
            return httpx.Response(200, json={"access_token": "synthetic", "expires_in": 1800})
        return httpx.Response(429, headers={"X-Rate-Limit-Retry-After-Seconds": "3600"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        for _ in range(2):
            result = await collect(provider, database, SafeHTTP(settings, client))
    assert len(token_requests) == 1 and result["retry_after"] == 3600
    row = database.statuses()[0]
    assert row["next_run"] > stamp(utcnow() + timedelta(minutes=59))


def test_live_api_and_historical_cards_expose_measured_metadata(settings):
    settings.opensky_client_id = settings.opensky_client_secret = "synthetic"
    with TestClient(create_app(settings)) as client:
        database = client.app.state.database
        from backend.aviation import save_snapshot

        report = OpenSky(settings).normalize(
            {"state": state(int(utcnow().timestamp())), "time": int(utcnow().timestamp())}
        )
        save_snapshot(database, [report])
        result = client.get("/api/aviation/live").json()
        assert result["available"] and result["poll_seconds"] == 120 and len(result["items"]) == 1
        historical = client.get("/api/events?categories=aviation&aircraft_categories=4,5").json()["items"][0]
        assert historical["aircraft"]["speed_mps"] == 250
        assert (
            client.get(f"/api/events/{historical['event_id']}").json()["aircraft"]["barometric_altitude_m"]
            == 10000
        )


def test_economic_layer_has_free_daily_news_and_energy_sources(settings):
    economic = [c for c in connectors(settings) if c.category == "economic"]
    assert len(economic) >= 7
    assert all(c.access() is None for c in economic)
    bbc = next(c for c in economic if c.source_id == "bbc_business")
    report = bbc.normalize(
        {
            "title": "Oil supply update",
            "description": "India reports a fuel shortage.",
            "link": "https://example.org/fuel",
            "pubDate": stamp(),
        }
    )
    assert report.category == "economic" and report.country_code == "IN"
    assert report.location_precision == "regional" and "context" in report.location_basis
