import json
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.analytics import regional_anomalies
from backend.connectors.base import SafeHTTP
from backend.connectors.cisa import CISA
from backend.connectors.ncsc import NCSC
from backend.connectors.ofac import OFAC
from backend.connectors.opensky import OpenSky
from backend.connectors.vendor_geo import vendor_origin
from backend.main import create_app
from backend.models import Category, Confidence, Filters, stamp, utcnow
from backend.repair_context import repair
from backend.worker import collect


@pytest.mark.parametrize("time_basis", ["event", "published", "ingested"])
def test_regional_windows_keep_baseline_and_bind_all_filters(database, report, time_basis):
    end = utcnow() - timedelta(days=1)
    for index, hours in enumerate([1] * 15 + [8] * 3 + [40] * 2 + [80] * 4 + [-1] * 4):
        instant = end - timedelta(hours=hours)
        event_id = database.ingest(
            report.model_copy(
                update={
                    "external_id": str(index),
                    "source_url": f"https://example.org/{index}",
                    "category": Category.aviation,
                    "title": f"Regional probe {index}",
                    "published_at": instant,
                    "occurred_at": instant,
                    "latitude": 20,
                    "longitude": 75,
                }
            )
        )
        if time_basis == "ingested":
            with database.connect() as db:
                db.execute("UPDATE events SET ingested_at=? WHERE event_id=?", (stamp(instant), event_id))
    filters = Filters(
        categories=["aviation"],
        country="IN",
        q="Regional probe",
        start=end - timedelta(hours=24),
        end=end,
        bbox=(70, 15, 80, 25),
        time_basis=time_basis,
    )
    result = regional_anomalies(database, filters)
    assert len(result) == 1
    assert (result[0]["recent_count"], result[0]["previous_count"], result[0]["baseline_count"]) == (
        15,
        3,
        20,
    )
    assert regional_anomalies(database, filters.model_copy(update={"country": "US"})) == []
    assert regional_anomalies(database, filters.model_copy(update={"bbox": (-80, 15, -70, 25)})) == []


def test_layer_health_matches_status_freshness_and_access(settings):
    with TestClient(create_app(settings)) as client:
        db = client.app.state.database
        db.set_status("usgs", state="ok", last_success=stamp(utcnow() - timedelta(days=2)))
        db.set_status("ncsc", state="ok", last_success=stamp())
        states = {item["source_id"]: item for item in client.get("/api/status").json()["connectors"]}
        layers = {item["id"]: item for item in client.get("/api/layers").json()}
        assert states["usgs"]["stale"] is True
        assert layers["environment"]["health"]["stale"] == 1
        assert any(
            item["source_id"] == "usgs" and item["stale"]
            for item in layers["environment"]["health"]["detail"]
        )
        assert layers["cyber"]["health"]["current"] == 1
        assert states["opensky"]["state"] == "access_required"
        assert layers["aviation"]["health"]["needs_access"] == 1


def test_aircraft_collection_interval_is_suitable_for_visible_updates(settings):
    assert 10 <= OpenSky(settings).interval <= 30


@pytest.mark.parametrize("provider", [NCSC, OFAC])
def test_official_publication_is_single_source_and_country_context(settings, provider):
    record = {
        "title": "China advisory update",
        "description": "Iran mentioned as other context",
        "link": "https://example.org/advisory",
        "published": stamp(),
    }
    normalized = provider(settings).normalize(record)
    assert normalized.confidence == "Single-source"
    assert normalized.severity == "unknown"
    assert normalized.country_code == "CN"
    assert "attribution" not in normalized.tags
    assert provider(settings).normalize({**record, "title": "China and Russia advisory"}).latitude is None
    assert provider(settings).normalize({**record, "title": "General advisory"}).latitude is None


def test_cisa_country_centroid_is_regional_and_distributed_vendor_unlocated(settings):
    result = CISA(settings).normalize(
        {
            "cveID": "CVE-probe",
            "vendorProject": "Microsoft",
            "vulnerabilityName": "Probe",
            "shortDescription": "Probe",
            "requiredAction": "Update",
            "dateAdded": "2026-10-10",
        }
    )
    assert result.location_precision == "regional"
    assert "country centroid" in result.location_basis
    assert "not headquarters" in result.location_basis
    for vendor in ["GitLab", "Node.js", "PHP", "Perl", "Unknown"]:
        assert vendor_origin(vendor) is None


def test_retained_context_repair_preserves_evidence_dates_and_analyst_review(settings, database):
    provider = NCSC(settings)
    normalized = provider.normalize(
        {"title": "China advisory update", "link": "https://example.org/advisory", "published": stamp()}
    )
    event_id = database.ingest(
        normalized.model_copy(update={"confidence": Confidence.corroborated, "severity": "moderate"})
    )
    before = database.detail(event_id)
    report_id = before["reports"][0]["report_id"]
    assert repair(database, settings)["applied"] is False
    assert database.detail(event_id)["confidence"] == "Corroborated"
    repair(database, settings, True)
    after = database.detail(event_id)
    assert after["confidence"] == "Single-source" and after["severity"] == "unknown"
    assert after["ingested_at"] == before["ingested_at"]
    assert after["reports"][0]["ingested_at"] == before["reports"][0]["ingested_at"]
    with database.connect() as db:
        db.execute(
            "INSERT INTO evidence_reviews(event_id,confidence,basis,report_ids,reviewed_at) VALUES (?,?,?,?,?)",
            (
                event_id,
                "Disputed",
                "Analyst reviewed conflicting evidence with explicit basis",
                json.dumps([report_id]),
                stamp(),
            ),
        )
    repair(database, settings, True)
    assert database.detail(event_id)["confidence"] == "Disputed"


def aircraft_state(now, category=4, track=90):
    return [
        "abcdef",
        "TEST123 ",
        "Synthetic",
        now,
        now,
        -120,
        40,
        1000,
        False,
        100,
        track,
        0,
        None,
        1000,
        None,
        False,
        0,
        category,
    ]


@pytest.mark.parametrize("region", ["world", "70,10,90,30"])
async def test_extended_aircraft_data_survives_ingestion(settings, database, region):
    settings.opensky_client_id, settings.opensky_client_secret = "synthetic", "synthetic"
    settings.opensky_bbox = region
    now = int(utcnow().timestamp())

    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"access_token": "synthetic"})
        assert request.url.params["extended"] == "1"
        assert ("lamin" in request.url.params) == (region != "world")
        return httpx.Response(200, json={"time": now, "states": [aircraft_state(now)]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await collect(OpenSky(settings), database, SafeHTTP(settings, client))
    assert result["stored"] == 1
    event = database.events(Filters(aircraft_categories=[4, 5]))["items"][0]
    assert (event["aircraft_category"], event["aircraft_track_deg"], event["aircraft_callsign"]) == (
        4,
        90,
        "TEST123",
    )


async def test_actual_aircraft_selection_bound_and_zero_eligible_success(settings, database):
    settings.opensky_client_id, settings.opensky_client_secret = "synthetic", "synthetic"
    now = int(utcnow().timestamp())
    provider = OpenSky(settings)
    records = [{"state": [f"{i:06x}", *aircraft_state(now)[1:]], "time": now} for i in range(1050)]
    records += [
        {"state": aircraft_state(now, category=6), "time": now},
        {"state": aircraft_state(now, track=None), "time": now},
    ]

    async def fetch(_):
        return records

    provider.fetch = fetch
    result = await collect(provider, database, None)
    assert result["stored"] == 1000 and result["truncated"] == 52
    records[:] = [{"state": aircraft_state(now, track=None), "time": now}]
    result = await collect(provider, database, None)
    assert result["state"] == "ok" and result["stored"] == 0 and result["truncated"] == 1


def test_aircraft_filter_applies_before_pagination_and_to_counts(settings, report):
    with TestClient(create_app(settings)) as client:
        db = client.app.state.database
        for index, (category, track) in enumerate([(None, 90), (6, 90), (4, None), (4, 0), (5, 270)]):
            db.ingest(
                report.model_copy(
                    update={
                        "category": Category.aviation,
                        "external_id": str(index),
                        "source_url": f"https://example.org/air/{index}",
                        "aircraft_category": category,
                        "aircraft_track_deg": track,
                    }
                )
            )
        db.ingest(report)
        result = client.get("/api/events?aircraft_categories=4,5&limit=1&order=balanced").json()
        assert result["total"] == 3 and result["category_counts"]["aviation"] == 2
        assert client.get("/api/events?categories=aviation&aircraft_categories=4,5").json()["total"] == 2
        assert client.get("/api/events?categories=aviation&aircraft_categories=6").json()["total"] == 1
        # OpenSky documents classes 0-20; only values outside that range are rejected.
        assert client.get("/api/events?aircraft_categories=20").status_code == 200
        assert client.get("/api/events?aircraft_categories=21").status_code == 422


def test_collector_preserves_rare_classes_in_bounded_global_sample(settings):
    provider = OpenSky(settings)
    now = int(utcnow().timestamp())
    records = [{"state": [f"{i:06x}", *aircraft_state(now, category=0)[1:]], "time": now} for i in range(1500)]
    records += [{"state": aircraft_state(now, category=category), "time": now} for category in range(1, 7)]
    selected = provider.select_records(records)
    assert len(selected) == 1000
    assert set(range(7)) == {record["state"][17] for record in selected}
