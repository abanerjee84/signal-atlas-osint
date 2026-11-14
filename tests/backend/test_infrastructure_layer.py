"""Country-only enrichment and separate layer semantics; all input is synthetic."""

from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.advanced.repository import Repository
from backend.connectors.observatory import DShield, ThreatFox
from backend.indicators import public_ip
from backend.infrastructure_geo import enrich_locations
from backend.main import create_app
from backend.models import Filters, stamp, utcnow


def observation(settings, ip="8.8.8.8"):
    return DShield(settings).normalize(
        {
            "source": ip,
            "day": utcnow().date().isoformat(),
            "reports": "12",
            "targets": "3",
            "received_at": stamp(),
            "source_url": "https://isc.sans.edu/api/",
        }
    )


@pytest.mark.asyncio
async def test_country_estimate_uses_provider_only_cached_and_keeps_source_counts(settings, database):
    event_id = database.ingest(observation(settings))
    requests = []

    def handle(request):
        requests.append(request)
        assert request.url.host == "ipwho.is" and request.url.scheme == "https"
        assert request.url.params["fields"] == "ip,success,country_code"
        return httpx.Response(
            200, json={"success": True, "ip": "8.8.8.8", "country_code": "US", "latitude": 0, "longitude": 0}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        first = await enrich_locations(database, settings, client, interval=0)
        second = await enrich_locations(database, settings, client, interval=0)
    assert first["located"] == 1 and second["looked_up"] == 0 and len(requests) == 1
    detail = database.detail(event_id)
    assert detail["category"] == "infrastructure" and detail["country_code"] == "US"
    assert (detail["latitude"], detail["longitude"]) != (0, 0)
    assert detail["location_precision"] == "regional" and "not actor nationality" in detail["location_basis"]
    assert detail["cyber_observation"]["report_count"] == 12
    assert detail["reports"][0]["metadata"]["infrastructure_geo"]["provider"] == "ipwhois_geo"
    assert database.ingest(observation(settings)) == event_id
    assert database.detail(event_id)["country_code"] == "US"
    assert database.events(Filters(categories=["cyber"]))["total"] == 0
    assert (
        database.events(Filters(categories=["infrastructure"]))["items"][0]["infrastructure_geo"][
            "country_code"
        ]
        == "US"
    )


@pytest.mark.asyncio
async def test_429_is_persisted_and_prevents_further_lookups(settings, database):
    database.ingest(observation(settings))
    database.ingest(observation(settings, "1.1.1.1"))
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "3600"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        assert (await enrich_locations(database, settings, client, interval=0))["state"] == "provider_backoff"
        assert (await enrich_locations(database, settings, client, interval=0))["state"] == "provider_backoff"
    assert len(calls) == 1
    assert all(item["latitude"] is None for item in database.events(Filters())["items"])


@pytest.mark.asyncio
async def test_daily_budget_unknown_country_and_no_domain_resolution(settings, database):
    settings.infrastructure_geo_daily_budget = 1
    database.ingest(observation(settings))
    database.ingest(observation(settings, "1.1.1.1"))
    domain = ThreatFox(settings).normalize(
        {
            "id": "12",
            "ioc": "example.org",
            "ioc_type": "domain",
            "threat_type": "botnet_cc",
            "first_seen": stamp(utcnow() - timedelta(hours=1)),
            "received_at": stamp(),
        }
    )
    database.ingest(domain)
    calls = []

    def handle(request):
        calls.append(request)
        ip = public_ip(request.url.path[1:])
        return httpx.Response(200, json={"success": True, "ip": ip, "country_code": "ZZ"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await enrich_locations(database, settings, client, interval=0)
    assert result["state"] == "daily_budget" and len(calls) == 1
    assert all(item["latitude"] is None for item in database.events(Filters())["items"])


def test_migration_preserves_ids_evidence_and_moves_legacy_observations(settings, database):
    eid = database.ingest(observation(settings))
    with database.connect() as db:
        db.execute("UPDATE events SET category='cyber' WHERE event_id=?", (eid,))
        db.execute(
            "UPDATE reports SET metadata=json_set(metadata,'$.category','cyber') WHERE event_id=?", (eid,)
        )
        db.execute("UPDATE external_records SET category='cyber'")
        db.execute("PRAGMA user_version=7")
    database.initialize()
    assert database.detail(eid)["category"] == "infrastructure"
    assert Repository(database).one("SELECT category FROM external_records")["category"] == "infrastructure"
    assert Repository(database).one("SELECT COUNT(*) n FROM indicator_evidence")["n"] == 1


def test_public_layer_contract_provider_filter_and_location_coverage(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.database.ingest(observation(settings))
        app.state.database.ingest(
            ThreatFox(settings).normalize(
                {
                    "id": "12",
                    "ioc": "example.org",
                    "ioc_type": "domain",
                    "threat_type": "botnet_cc",
                    "first_seen": stamp(utcnow()),
                    "received_at": stamp(),
                }
            )
        )
        layer = next(row for row in client.get("/api/layers").json() if row["id"] == "infrastructure")
        assert set(layer["sources"]) == {
            "dshield", "isc_honeypots", "threatfox", "cloudflare_radar", "feodo", "urlhaus"
        }
        assert "shodan" not in layer["sources"]
        cy = next(row for row in client.get("/api/layers").json() if row["id"] == "cyber")
        assert "dshield" not in cy["sources"]
        result = client.get("/api/events?categories=infrastructure&infrastructure_provider=dshield").json()
        assert result["total"] == 1 and result["items"][0]["source_id"] == "dshield"
        assert result["items"][0]["cyber_observation"]["report_count"] == 12
        coverage = client.get("/api/infrastructure/coverage?infrastructure_provider=threatfox").json()
        assert coverage["total"] == 1 and coverage["located"] == 0
        assert client.get("/api/events?infrastructure_provider=invalid").status_code == 422
