import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.aviation import save_snapshot
from backend.connectors.base import ProviderError
from backend.connectors.monitoring import AccuracyADSB, GroundStations, TfLCameras
from backend.main import create_app
from backend.models import AircraftMetadata, Category, Filters, stamp, utcnow
from backend.monitoring import LAYERS, frame, gnss_cells, retain


def test_history_preserves_revisions_and_receipt_boundary(database, report):
    before = utcnow() - timedelta(hours=2)
    first = report.model_copy(update={"published_at": before, "title": "First version"})
    revised = first.model_copy(update={"title": "Revised version", "latitude": 30})
    with database.connect() as db:
        retain(db, first, stamp(before))
        retain(db, first, stamp(before + timedelta(minutes=1)))
        retain(db, revised, stamp(before + timedelta(hours=1)))
    earlier = frame(database, before + timedelta(minutes=30))
    later = frame(database, before + timedelta(hours=1, minutes=1))
    assert earlier["items"][0]["title"] == "First version"
    assert later["items"][0]["title"] == "Revised version"
    with database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM monitoring_history").fetchone()[0] == 2


def test_history_survives_live_vessel_replacement(database, report):
    when = utcnow() - timedelta(minutes=1)
    vessels = [
        report.model_copy(
            update={
                "category": Category.maritime,
                "external_id": f"mmsi:{mmsi}",
                "published_at": when,
                "raw": {},
            }
        )
        for mmsi in [123456789, 234567890]
    ]
    database.replace_vessel_snapshot(report.source_id, vessels)
    database.replace_vessel_snapshot(report.source_id, [])
    assert database.events(Filters())["total"] == 0
    result = frame(database, utcnow())
    assert {item["entity_id"] for item in result["items"]} == {"123456789", "234567890"}


def test_aircraft_snapshots_record_movement_between_half_hour_events(database, report):
    now = utcnow() - timedelta(minutes=1)
    first = report.model_copy(
        update={
            "category": Category.aviation,
            "published_at": now,
            "occurred_at": now,
            "aircraft": AircraftMetadata(icao24="abc123", registration_country="Unknown", on_ground=False),
        }
    )
    save_snapshot(database, [first])
    second = first.model_copy(update={"occurred_at": now + timedelta(seconds=30), "longitude": 79})
    save_snapshot(database, [second])
    with database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM monitoring_history").fetchone()[0] == 2
    assert frame(database, utcnow())["items"][0]["longitude"] == 79


def test_latest_entity_is_selected_before_layer_filter(database, report):
    before = utcnow() - timedelta(minutes=2)
    airborne = report.model_copy(
        update={
            "category": Category.aviation,
            "published_at": before,
            "occurred_at": before,
            "aircraft": AircraftMetadata(icao24="abc123", registration_country="Unknown", on_ground=False),
        }
    )
    landed = airborne.model_copy(
        update={
            "occurred_at": before + timedelta(minutes=1),
            "aircraft": AircraftMetadata(icao24="abc123", registration_country="Unknown", on_ground=True),
        }
    )
    with database.connect() as db:
        retain(db, airborne, stamp(before))
        retain(db, landed, stamp(before + timedelta(minutes=1)))
    assert not frame(database, utcnow(), selected={"airborne"})["items"]
    assert len(frame(database, utcnow(), selected={"grounded"})["items"]) == 1


def test_future_and_delayed_reports_do_not_leak_into_playback(database, report):
    now = utcnow()
    delayed = report.model_copy(update={"published_at": now - timedelta(days=1)})
    database.ingest(delayed)
    assert not frame(database, now - timedelta(hours=1), hours=48)["items"]
    future = report.model_copy(update={"external_id": "future", "published_at": now + timedelta(days=1)})
    database.ingest(future)
    with database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM monitoring_history").fetchone()[0] == 1


def test_gnss_uses_unique_airborne_known_accuracy_samples():
    def sample(icao, nacp, **extra):
        return {
            "entity_id": icao,
            "aircraft": {"icao24": icao},
            "category": Category.aviation,
            "latitude": 51.1,
            "longitude": -0.1,
            "observed_at": "2026-01-01T00:00:00+00:00",
            "stale": False,
            "sensor": {"nac_p": nacp, "on_ground": False},
            **extra,
        }

    items = [
        sample("a", 3),
        sample("b", 8),
        sample("c", 4),
        sample("d", 0),
        sample("e", None),
        sample("a", 3),
        sample("f", 2, stale=True),
        sample("g", 2, sensor={"nac_p": 2, "on_ground": True}),
    ]
    cells = gnss_cells(items)["features"]
    assert len(cells) == 1
    assert cells[0]["properties"]["aircraft"] == 3
    assert cells[0]["properties"]["low_accuracy"] == 2
    assert cells[0]["geometry"]["coordinates"][0][0] == [-1, 51]
    assert "not confirmed jamming" in cells[0]["properties"]["basis"]
    assert not gnss_cells(items[:2])["features"]


def test_sensor_normalization_and_invalid_accuracy(settings):
    camera = TfLCameras(settings).normalize(
        {
            "id": "JamCams_1",
            "commonName": "Public traffic camera",
            "lat": 51,
            "lon": 0,
            "additionalProperties": [{"key": "videoUrl", "value": "https://example.org/camera.mp4"}],
        }
    )
    assert camera.tags == ["cctv"] and "Not verified" == camera.raw["monitoring"]["stream_status"]
    station = GroundStations(settings).normalize(
        {"id": 1, "name": "Public station", "lat": 30, "lng": 20, "status": "Offline"}
    )
    assert station.raw["monitoring"]["directory_status"] == "Offline"
    feed = AccuracyADSB(settings)
    record = dict(
        icao24="abc123",
        observed_at=stamp(utcnow() - timedelta(minutes=1)),
        source_url="https://example.org/adsb",
        latitude=20,
        longitude=30,
        nac_p=3,
        on_ground=False,
    )
    assert feed.normalize(record).raw["monitoring"]["nac_p"] == 3
    for bad in [
        dict(nac_p=12),
        dict(nac_p=True),
        dict(on_ground="false"),
        dict(observed_at="2026-01-01T00:00:00"),
    ]:
        with pytest.raises(ValueError):
            feed.normalize({**record, **bad})


async def test_sensor_directories_do_not_create_incident_events(database, settings):
    from backend.worker import collect

    class HTTP:
        async def json(self, *args):
            return [{"id": 1, "name": "Synthetic station", "lat": 30, "lng": 20, "status": "Offline"}]

    result = await collect(GroundStations(settings), database, HTTP())
    assert result["stored"] == 1 and result["state"] == "ok"
    assert database.events(Filters())["total"] == 0
    assert len(frame(database, utcnow(), selected={"ground-stations"})["items"]) == 1


async def test_readsb_adapter_dates_positions_and_removes_endpoint_query(settings):
    settings.monitoring_adsb_url = "https://example.org/aircraft.json?token=synthetic-secret"
    now = utcnow() - timedelta(minutes=1)

    class HTTP:
        async def json(self, *args):
            return {
                "now": now.timestamp(),
                "aircraft": [
                    {"hex": "abc123", "lat": 51, "lon": 0, "nac_p": 3, "alt_baro": 25000, "seen_pos": 2},
                    {"hex": "abc124", "lat": 51, "lon": 0, "nac_p": 3, "seen_pos": 99999},
                    {"hex": "abc125", "lat": 51, "lon": 0, "nac_p": 3},
                ],
            }

    provider = AccuracyADSB(settings)
    rows = await provider.fetch(HTTP())
    assert len(rows) == 1
    report = provider.normalize(rows[0])
    assert report.occurred_at == now - timedelta(seconds=2)
    assert report.aircraft.on_ground is False
    assert report.source_url == "https://example.org/aircraft.json"


def test_monitoring_api_validation_and_empty_history(settings):
    with TestClient(create_app(settings)) as client:
        catalog = client.get("/api/monitoring/catalog").json()
        assert catalog["layer_count"] == len(LAYERS) >= 40
        assert catalog["source_count"] >= 60
        assert catalog["healthy_source_count"] == 0
        assert catalog["history"]["first"] is None
        assert client.get("/api/monitoring/frame").json()["items"] == []
        for query in ["at=2026-01-01T00:00:00", "hours=999", "layers=nonexistent", "limit=99999"]:
            assert client.get("/api/monitoring/frame?" + query).status_code == 422
        assert client.post("/api/monitoring/shodan", json={"ip": "8.8.8.8"}).status_code == 401
        assert (
            client.post(
                "/api/monitoring/shodan",
                headers={"Authorization": "Bearer test-access-token"},
                json={"ip": "127.0.0.1"},
            ).status_code
            == 422
        )


def test_shodan_is_passive_cached_and_budgeted(settings, monkeypatch):
    settings.shodan_api_key = "synthetic-server-secret"
    settings.shodan_daily_budget = 1
    requests = []

    async def response(self, method, url, **kwargs):
        requests.append((method, url, kwargs))
        return {
            "ip_str": "8.8.8.8",
            "org": "Synthetic fixture",
            "ports": [53, -1, True],
            "latitude": 37,
            "longitude": -97,
            "last_update": "2026-01-01T00:00:00",
        }

    monkeypatch.setattr("backend.monitoring_api.SafeHTTP.json", response)
    with TestClient(create_app(settings)) as client:
        headers = {"Authorization": "Bearer test-access-token"}
        first = client.post("/api/monitoring/shodan", headers=headers, json={"ip": "8.8.8.8"})
        assert first.status_code == 200
        assert first.json()["ports"] == [53]
        assert "synthetic-server-secret" not in first.text
        assert client.post("/api/monitoring/shodan", headers=headers, json={"ip": "8.8.8.8"}).json()["cached"]
        assert len(requests) == 1 and requests[0][1] == "https://api.shodan.io/shodan/host/8.8.8.8"
        assert (
            client.post("/api/monitoring/shodan", headers=headers, json={"ip": "1.1.1.1"}).status_code == 429
        )
        item = client.get("/api/monitoring/frame?layers=shodan").json()["items"][0]
        assert item["sensor"]["provider_updated_at"] == "2026-01-01T00:00:00"


def test_failed_shodan_never_leaks_provider_secret(settings, monkeypatch):
    settings.shodan_api_key = "synthetic-secret"

    async def fail(*args, **kwargs):
        raise ProviderError("Upstream could include synthetic-secret")

    monkeypatch.setattr("backend.monitoring_api.SafeHTTP.json", fail)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/monitoring/shodan",
            headers={"Authorization": "Bearer test-access-token"},
            json={"ip": "8.8.8.8"},
        )
        assert response.status_code == 502 and "synthetic-secret" not in response.text


def test_history_retention_and_orbit_cutoff(database, settings, report):
    old = utcnow() - timedelta(days=8)
    with database.connect() as db:
        retain(db, report.model_copy(update={"published_at": old}), stamp(old))
        db.execute("INSERT INTO monitoring_orbits VALUES(?,?)", (stamp(old), json.dumps({"items": []})))
    database.maintenance(settings)
    with database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM monitoring_history").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM monitoring_orbits").fetchone()[0] == 0


def test_orbital_elements_are_archived_and_never_read_from_future(settings, monkeypatch):
    from scripts.collect_orbits import collect_orbits_locked

    snapshot = {"checked_at": stamp(), "items": [], "sources": []}
    monkeypatch.setattr("scripts.collect_orbits.collect_orbits", lambda: snapshot)
    with TestClient(create_app(settings)) as client:
        database = client.app.state.database
        earlier = stamp(utcnow() - timedelta(minutes=1))
        assert collect_orbits_locked(database) == snapshot
        assert client.get("/api/monitoring/orbits", params={"at": earlier}).json()["snapshot"] is None
        assert client.get("/api/monitoring/orbits").json()["snapshot"] == snapshot
