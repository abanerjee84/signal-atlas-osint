"""Provider contracts and persistent evidence use temporary databases only."""

from datetime import timedelta
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.advanced.processing import index_batch
from backend.advanced.providers import lookup
from backend.advanced.repository import Repository
from backend.advanced.threats import store_catalog
from backend.config import Settings
from backend.connectors.base import ProviderError, SafeHTTP
from backend.connectors.observatory import CloudflareRadar, DShield, ISCHoneypots, ThreatFox
from backend.connectors.registry import connectors
from backend.cyber_observations import indicator_id, prune_observations
from backend.indicators import observed_indicator
from backend.main import create_app
from backend.models import Filters, stamp, utcnow
from backend.worker import collect


def dshield_row(**values):
    return {
        "source": "8.8.8.8",
        "day": utcnow().date().isoformat(),
        "reports": "12",
        "targets": "3",
        "received_at": stamp(),
        "source_url": "https://isc.sans.edu/api/",
        **values,
    }


def fox_row(**values):
    return {
        "id": "12",
        "ioc": "8.8.8.8:443",
        "ioc_type": "ip:port",
        "threat_type": "botnet_cc",
        "first_seen": stamp(utcnow() - timedelta(hours=2)),
        "last_seen": None,
        "malware": "win.fixture",
        "malware_printable": "Fixture Malware",
        "confidence_level": 75,
        "reference": "https://example.org/report",
        "received_at": stamp(),
        **values,
    }


@pytest.mark.parametrize(
    "kind,value,expected",
    [
        ("ip:port", "[2606:4700:4700::1111]:443", ("ip", "2606:4700:4700::1111", 443)),
        ("url", "HTTP://Example.org:3606/x#fragment", ("url", "http://example.org:3606/x", None)),
        ("domain", "EXAMPLE.ORG.", ("domain", "example.org", None)),
        ("sha256_hash", "A" * 64, ("hash", "a" * 64, None)),
    ],
)
def test_typed_iocs_preserve_ports_ipv6_and_non_geographic_indicators(kind, value, expected):
    assert observed_indicator(kind, value) == expected


@pytest.mark.parametrize(
    "kind,value",
    [
        ("ip", "127.0.0.1"),
        ("ip", "192.168.1.1"),
        ("ip:port", "8.8.8.8:65536"),
        ("url", "https://127.0.0.1/x"),
        ("url", "https://user:secret@example.org/"),
        ("sha256_hash", "a" * 32),
    ],
)
def test_invalid_and_private_indicators_are_rejected(kind, value):
    with pytest.raises(ValueError):
        observed_indicator(kind, value)


def test_daily_aggregate_repoll_updates_one_event_and_survives_indexer(settings, database):
    provider = DShield(settings)
    first = provider.normalize(dshield_row())
    event = database.ingest(first)
    revised = provider.normalize(
        dshield_row(reports="20", received_at=stamp(utcnow() + timedelta(minutes=5)))
    )
    assert database.ingest(revised) == event
    assert database.events(Filters())["total"] == 1
    assert revised.occurred_at is None and revised.latitude is None and revised.threat is None
    index_batch(database)
    repo = Repository(database)
    item = repo.one("SELECT * FROM cyber_observations")
    assert item["payload"]["report_count"] == 20
    assert repo.one("SELECT COUNT(*) n FROM indicator_evidence")["n"] == 1
    assert (
        repo.one("SELECT classification FROM indicator_evidence")["classification"]
        == "provider_reported_indicator"
    )
    assert repo.one("SELECT COUNT(*) n FROM relationships")["n"] == 0


@pytest.mark.asyncio
async def test_dshield_contract_uses_explicit_reporting_date_and_custom_agent(settings, database):
    def handle(request):
        assert "today" not in str(request.url)
        assert request.headers["user-agent"].startswith("SignalAtlas/")
        return httpx.Response(
            200,
            text="<topips><ipaddress><source>8.8.8.8</source><reports>12</reports><targets>3</targets></ipaddress></topips>",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await collect(DShield(settings), database, SafeHTTP(settings, client))
    assert result["state"] == "ok" and result["stored"] == 1


@pytest.mark.asyncio
async def test_threatfox_documented_response_and_schema_failure_are_visible(settings, database):
    settings.threatfox_auth_key = "fixture-secret"

    def handle(request):
        assert request.headers["auth-key"] == "fixture-secret"
        return httpx.Response(200, json={"query_status": "ok", "data": [fox_row()]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await collect(ThreatFox(settings), database, SafeHTTP(settings, client))
    assert result["state"] == "ok" and result["stored"] == 1
    observation = Repository(database).one("SELECT * FROM cyber_observations")["payload"]
    assert observation["indicator_value"] == "8.8.8.8" and observation["port"] == 443
    assert observation["malware_id"] == "win.fixture" and observation["provider_confidence"] == 75
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"query_status": "wrong_key"}))
    ) as client:
        result = await collect(ThreatFox(settings), database, SafeHTTP(settings, client))
    assert result["state"] == "error" and "fixture-secret" not in str(result)


@pytest.mark.asyncio
async def test_missing_credentials_do_not_contact_network(settings, database):
    def handle(request):
        raise AssertionError("Unconfigured provider must not contact network")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        for provider in [ThreatFox(settings), CloudflareRadar(settings)]:
            assert (await collect(provider, database, SafeHTTP(settings, client)))[
                "state"
            ] == "access_required"


@pytest.mark.asyncio
async def test_isc_keeps_reporting_days_and_request_units(settings, database):
    provider = ISCHoneypots(settings)
    day = (utcnow().date() - timedelta(days=1)).isoformat()
    rows = [
        {"source": "8.8.8.8", "date": day, "time": "01:00:00", "url": "/x"},
        {"source": "8.8.8.8", "date": day, "time": "02:00:00", "url": "/y"},
    ]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=rows))
    ) as client:
        record = (await provider.fetch(SafeHTTP(settings, client)))[0]
    item = provider.normalize(record)
    assert item.cyber_observation.request_count == 2
    assert item.cyber_observation.kind == "web_probe"
    assert item.cyber_observation.source_family == DShield.family
    event = database.ingest(item)
    assert database.ingest(item) == event
    earlier = {
        **record,
        "day": (utcnow().date() - timedelta(days=2)).isoformat(),
        "first": record["first"] - timedelta(days=1),
        "last": record["last"] - timedelta(days=1),
    }
    assert database.ingest(provider.normalize(earlier)) != event


@pytest.mark.asyncio
async def test_response_limits_stop_large_isc_downloads(settings):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b" " * 2_097_153))
    ) as client:
        with pytest.raises(ProviderError, match="size limit"):
            await ISCHoneypots(settings).fetch(SafeHTTP(settings, client))


def test_out_of_order_first_last_seen_and_retention_cascade(settings, database):
    provider = ThreatFox(settings)
    later = provider.normalize(fox_row())
    earlier = provider.normalize(fox_row(id="13", first_seen=stamp(utcnow() - timedelta(days=2))))
    database.ingest(later)
    database.ingest(earlier)
    iid = indicator_id("ip", "8.8.8.8")
    repo = Repository(database)
    item = repo.one("SELECT * FROM cyber_indicators WHERE indicator_id=?", (iid,))
    assert item["first_seen_at"] < item["last_seen_at"]
    with patch("backend.cyber_observations.utcnow", return_value=utcnow() + timedelta(days=60)):
        prune_observations(database, 30)
    assert repo.one("SELECT COUNT(*) n FROM cyber_observations")["n"] == 0
    assert repo.one("SELECT COUNT(*) n FROM indicator_evidence")["n"] == 0
    assert database.events(Filters())["total"] == 0
    assert (
        repo.one("SELECT first_seen_at FROM cyber_indicators WHERE indicator_id=?", (iid,))["first_seen_at"]
        is None
    )


@pytest.mark.asyncio
async def test_radar_preserves_all_buckets_without_creating_incidents(settings, database):
    settings.cloudflare_radar_token = "fixture-secret"
    start = utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    timestamps = [stamp(start), stamp(start + timedelta(hours=1))]

    def handle(request):
        assert request.url.path.endswith("/timeseries_groups/PROTOCOL")
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "meta": {"normalization": "PERCENTAGE", "aggInterval": "ONE_HOUR"},
                    "serie_0": {"timestamps": timestamps, "tcp": ["30", "40"], "udp": ["70", "60"]},
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        for _ in range(2):
            result = await collect(CloudflareRadar(settings), database, SafeHTTP(settings, client))
    assert result["state"] == "ok" and result["stored"] == 2
    assert Repository(database).one("SELECT COUNT(*) n FROM cyber_ddos_series")["n"] == 4
    assert database.events(Filters())["total"] == 0


@pytest.mark.asyncio
async def test_greynoise_uses_selected_ip_contract_caches_and_preserves_benign(settings, database):
    settings.greynoise_api_key = "fixture-secret"
    repo = Repository(database)
    repo.register(connectors(settings))
    calls = []

    def handle(request):
        calls.append(request)
        assert request.url.path == "/v3/community/8.8.8.8"
        assert request.headers["key"] == "fixture-secret"
        return httpx.Response(
            200, json={"ip": "8.8.8.8", "noise": False, "riot": True, "classification": "benign"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        first = await lookup(repo, settings, client, {"provider_id": "greynoise", "query": "8.8.8.8"})
        second = await lookup(repo, settings, client, {"provider_id": "greynoise", "query": "8.8.8.8"})
    assert len(calls) == 1 and second["cached"] is True
    assert first["data"]["classification"] == "benign" and "fixture-secret" not in str(first)


def test_api_history_source_family_case_snapshot_and_private_access(tmp_path):
    settings = Settings(
        _env_file=None,
        database=tmp_path / "api.db",
        evidence_directory=tmp_path / "evidence",
        admin_token="fixture-token",
        threat_catalogs_enabled=False,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/v1/cyber/observations").status_code == 401
        client.headers["Authorization"] = "Bearer fixture-token"
        app.state.database.ingest(DShield(settings).normalize(dshield_row()))
        response = client.get("/api/v1/cyber/observations?provider=dshield&q=8.8.8.8")
        assert response.status_code == 200, response.text
        row = response.json()["data"][0]
        detail = client.get("/api/v1/cyber/indicators/" + row["indicator_id"]).json()["data"]
        assert detail["source_families"] == ["sans_isc"]
        assert detail["evidence"][0]["classification"] == "provider_reported_indicator"
        repo = Repository(app.state.database)
        case = client.post(
            "/api/v1/cases", json={"title": "Synthetic indicator review", "description": "", "tags": []}
        ).json()["data"]
        saved = repo.attach(case["id"], "record", row["record_id"])
        app.state.database.ingest(DShield(settings).normalize(dshield_row(reports="40")))
        assert saved["snapshot"]["metadata"]["cyber_observation"]["report_count"] == 12
        assert client.get("/api/v1/cyber/ddos").json()["meta"]["configured"] is False
        disabled = repo.one("SELECT enabled FROM sources WHERE source_id='isc_honeypots'")
        assert disabled["enabled"] == 0
        malpedia = "https://malpedia.caad.fkie.fraunhofer.de/details/win.fixture"
        store_catalog(
            repo,
            "mitre_attack",
            {
                "type": "bundle",
                "objects": [
                    {
                        "id": "malware--11111111-1111-4111-8111-111111111111",
                        "type": "malware",
                        "name": "Alternate catalog malware name",
                        "external_references": [{"source_name": "malpedia", "url": malpedia}],
                    }
                ],
            },
            "a" * 64,
        )
        app.state.database.ingest(
            ThreatFox(settings).normalize(
                fox_row(ioc_type="url", ioc="http://example.org:3606/x", malware_malpedia=malpedia)
            )
        )
        response = client.post(
            "/api/v1/cyber/enrich",
            json={"indicator": "HTTP://EXAMPLE.ORG:3606/x#fragment", "provider_id": "local"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["normalized_value"] == "http://example.org:3606/x"
        lead = response.json()["data"]["malware_candidates"][0]
        assert lead["name"] == "Alternate catalog malware name"
        assert lead["match_basis"].startswith("Shared provider/catalog reference")


def test_corrected_provider_ioc_replaces_old_evidence_and_extrema(settings, database):
    provider = ThreatFox(settings)
    event = database.ingest(provider.normalize(fox_row()))
    assert database.ingest(provider.normalize(fox_row(ioc="1.1.1.1:443"))) == event
    repo = Repository(database)
    old = indicator_id("ip", "8.8.8.8")
    assert repo.one("SELECT COUNT(*) n FROM indicator_evidence WHERE indicator_id=?", (old,))["n"] == 0
    assert repo.one("SELECT COUNT(*) n FROM entity_source_mentions WHERE entity_id=?", (old,))["n"] == 0
    assert (
        repo.one("SELECT first_seen_at FROM cyber_indicators WHERE indicator_id=?", (old,))["first_seen_at"]
        is None
    )


def test_radar_missing_measurements_remain_gaps(settings, database):
    from backend.cyber_observations import save_ddos_series

    provider = CloudflareRadar(settings)
    row = {
        "timestamp": stamp(utcnow() - timedelta(hours=1)),
        "received_at": stamp(),
        "protocols": {"TCP": 20, "UDP": 80},
    }
    save_ddos_series(database, [provider.normalize(row)])
    row["protocols"]["TCP"] = None
    save_ddos_series(database, [provider.normalize(row)])
    measurements = Repository(database).rows("SELECT * FROM cyber_ddos_series")
    assert len(measurements) == 1 and measurements[0]["protocol"] == "UDP"
