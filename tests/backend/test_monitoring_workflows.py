import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.connectors.expanded import ReferenceFeed
from backend.main import create_app
from backend.models import Category, stamp, utcnow
from backend.monitoring import retain, save_directory
from backend.monitoring_geo import contains, distance, geometry, intersects, near
from backend.monitoring_workflows import (
    Watch,
    create_watch,
    entity_history,
    evaluate_watches,
    exposure,
    matches,
)


def shape(x=0, y=0, size=1):
    return {
        "type": "Polygon",
        "coordinates": [[[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]],
    }


def store(database, report, when, lon, lat, **extra):
    r = report.model_copy(
        update={
            "published_at": when,
            "occurred_at": when,
            "longitude": lon,
            "latitude": lat,
            "location_precision": "approximate",
            **extra,
        }
    )
    with database.connect() as db:
        retain(db, r, stamp(when))
    return r


def test_dateline_holes_and_route_distance_are_geographic():
    g = {"type": "Polygon", "coordinates": [[[179, -1], [-179, -1], [-179, 1], [179, 1], [179, -1]]]}
    assert contains(g, [179.5, 0]) and contains(g, [-179.5, 0])
    assert not contains(g, [0, 0])
    hole = shape(0, 0, 4)
    hole["coordinates"].append(shape(1, 1, 1)["coordinates"][0])
    assert contains(hole, [0.5, 0.5]) and not contains(hole, [1.5, 1.5])
    route = {"type": "LineString", "coordinates": [[179, 0], [-179, 0]]}
    assert near([180, 0.01], route, 2) and not near([0, 0], route, 2)
    assert distance([0, 0], [0, 1]) == pytest.approx(111.195, abs=0.01)


def test_geometry_validation_and_intersection():
    assert intersects(shape(), shape(0.5, 0.5))
    assert not intersects(shape(), shape(5, 5))
    for bad in [
        {"type": "Point", "coordinates": [200, 0]},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1]]]},
        {"type": "Point", "coordinates": [True, 1]},
        {"type": "Point", "coordinates": [float("nan"), 1]},
    ]:
        with pytest.raises(ValueError):
            geometry(bad)
    with pytest.raises(ValueError):
        geometry({"type": "LineString", "coordinates": [[0, 0]]})


def test_buffered_route_matches_nearby_geometry_even_when_vertices_are_distant():
    watch = Watch(
        name="Parallel route", geometry={"type": "LineString", "coordinates": [[-1, 0], [1, 0]]}, radius_km=1
    )
    item = {
        "source_id": "fixture",
        "entity_id": "route",
        "layers": [],
        "sensor": {"geometry": {"type": "LineString", "coordinates": [[-10, 0.005], [10, 0.005]]}},
    }
    assert matches(watch, item)


def test_watch_entry_exit_reentry_cooldown_and_late_fixes(database, report, monkeypatch):
    base = utcnow() - timedelta(minutes=10)
    watch = create_watch(
        database, Watch(name="Fixture area", geometry=shape(), include_existing=True, cooldown_seconds=60)
    )
    store(database, report, base, 0.5, 0.5)
    clock = base + timedelta(minutes=10)
    monkeypatch.setattr("backend.monitoring_workflows.utcnow", lambda: clock)
    assert evaluate_watches(database)["alerts_created"] == 1
    assert evaluate_watches(database)["alerts_created"] == 0
    store(database, report, base + timedelta(minutes=1), 2, 2)
    assert evaluate_watches(database)["alerts_created"] == 0
    store(database, report, base + timedelta(minutes=2), 0.5, 0.5)
    assert evaluate_watches(database)["alerts_created"] == 0  # Within the source/entity cooldown.
    store(database, report, base + timedelta(minutes=3), 2, 2)
    evaluate_watches(database)
    clock += timedelta(minutes=2)
    store(database, report, base + timedelta(minutes=4), 0.5, 0.5)
    assert evaluate_watches(database)["alerts_created"] == 1
    store(database, report, base - timedelta(minutes=1), 2, 2)
    assert evaluate_watches(database)["alerts_created"] == 0
    with database.connect() as db:
        state = db.execute("SELECT * FROM monitoring_rule_states WHERE rule_id=?", (watch,)).fetchone()
        assert state["inside"] == 1 and state["observed_at"] == stamp(base + timedelta(minutes=4))
        snapshots = [json.loads(r[0]) for r in db.execute("SELECT snapshot FROM monitoring_alerts")]
        db.execute("DELETE FROM monitoring_history")
    assert len(snapshots) == 2 and snapshots[0]["observation"]["title"] == report.title
    assert evaluate_watches(database)["alerts_created"] == 0  # Missing telemetry is not an exit.


def test_watch_default_starts_at_new_receipts_and_ignores_expired_references(database, report):
    when = utcnow() - timedelta(minutes=1)
    store(database, report, when, 0.5, 0.5)
    create_watch(database, Watch(name="Only new observations", geometry=shape()))
    assert evaluate_watches(database)["alerts_created"] == 0
    store(database, report, when + timedelta(seconds=10), 0.5, 0.5, raw={"monitoring": {"reference": True}})
    store(
        database,
        report,
        when + timedelta(seconds=20),
        0.5,
        0.5,
        raw={"monitoring": {"expires_at": stamp(when)}},
    )
    assert evaluate_watches(database)["alerts_created"] == 0


def test_regional_country_markers_do_not_trigger_site_alerts(database, report):
    create_watch(database, Watch(name="Site watch", geometry=shape(), include_existing=True))
    store(database, report, utcnow() - timedelta(seconds=1), 0.5, 0.5, location_precision="regional")
    assert evaluate_watches(database)["alerts_created"] == 0


def test_watch_receipt_cursor_survives_complete_history_pruning(database, report):
    when = utcnow() - timedelta(minutes=1)
    for i in range(3):
        store(database, report, when + timedelta(seconds=i), 0.5, 0.5)
    create_watch(database, Watch(name="New receipts after pruning", geometry=shape()))
    with database.connect() as db:
        db.execute("DELETE FROM monitoring_history")
        assert db.execute("SELECT COUNT(*) FROM monitoring_receipts").fetchone()[0] == 0
    store(database, report, when + timedelta(seconds=4), 0.5, 0.5)
    assert evaluate_watches(database)["alerts_created"] == 1


def test_watch_constraints_reject_empty_selector_unknown_layers_and_zero_width_route():
    for data in [
        {"name": "Empty"},
        {"name": "Unknown layer", "entity_id": "x", "layers": ["made-up"]},
        {"name": "Zero-width route", "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}},
    ]:
        with pytest.raises(ValidationError):
            Watch(**data)


def test_trails_split_at_dateline_and_receipt_time_blocks_future_knowledge(database, report):
    now = utcnow() - timedelta(hours=1)
    for index, lon in enumerate([179, 179.5, -179.5, -179]):
        store(database, report, now + timedelta(minutes=index), lon, 0)
    data = entity_history(database, report.source_id, report.external_id, now, utcnow())
    assert len(data["trail"]["features"]) == 2
    assert all(
        abs(b[0] - a[0]) < 180
        for f in data["trail"]["features"]
        for a, b in zip(f["geometry"]["coordinates"], f["geometry"]["coordinates"][1:])
    )
    late = report.model_copy(update={"external_id": "late", "published_at": now, "occurred_at": now})
    with database.connect() as db:
        retain(db, late, stamp())
    assert not entity_history(
        database, late.source_id, "late", now - timedelta(minutes=1), now + timedelta(minutes=1)
    )["items"]


def test_supplier_exposure_is_cited_proximity_not_a_risk_score(database, settings, report):
    p = ReferenceFeed(
        settings,
        {
            "source_id": "fixture_suppliers",
            "name": "Fixture suppliers",
            "kind": "supplier",
            "version": "1",
            "license": "Authorized fixture",
            "url": "https://example.org/suppliers",
        },
    )
    save_directory(
        database,
        [
            p.normalize(
                {
                    "id": "s1",
                    "geometry": {"type": "Point", "coordinates": [0.5, 0.5]},
                    "properties": {"name": "Fixture supplier"},
                }
            )
        ],
    )
    store(database, report, utcnow() - timedelta(minutes=1), 0.51, 0.5, category=Category.environment)
    result = exposure(database, radius_km=5)
    assert len(result["items"]) == 1
    hit = result["items"][0]["nearby_observations"][0]
    assert 0 < hit["distance_km"] < 2 and hit["source_url"] == report.source_url
    assert "score" not in result["items"][0] and "not a damage" in result["basis"]


def test_protected_import_watch_and_case_evidence_workflows(settings, report):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/monitoring/watches").status_code == 401
        headers = {"Authorization": "Bearer test-access-token"}
        asset = {
            "source_id": "fixture_assets",
            "name": "Fixture dataset",
            "kind": "supplier",
            "version": "v1",
            "license": "Authorized fixture only",
            "source_url": "https://example.org/dataset",
            "features": [
                {
                    "id": "a1",
                    "geometry": {"type": "Point", "coordinates": [1, 2]},
                    "properties": {"name": "Fixture supplier"},
                }
            ],
        }
        result = client.post("/api/monitoring/assets/import", headers=headers, json=asset)
        assert result.status_code == 200 and result.json()["stored"] == 1
        assets = client.get("/api/monitoring/assets", headers=headers).json()["items"]
        assert assets[0]["version"] == "v1"
        assert client.get("/api/events").json()["total"] == 0
        created = client.post(
            "/api/monitoring/watches",
            headers=headers,
            json={"name": "Fixture entity watch", "entity_id": "vessel1"},
        )
        assert created.status_code == 200
        wid = created.json()["id"]
        assert (
            client.post(
                f"/api/monitoring/watches/{wid}/enabled", headers=headers, json={"enabled": False}
            ).json()["enabled"]
            is False
        )
        case = client.post("/api/v1/cases", headers=headers, json={"title": "Fixture case"}).json()["data"]
        attached = client.post(
            "/api/monitoring/evidence",
            headers=headers,
            json={"case_id": case["id"], "kind": "asset", "reference_id": assets[0]["id"]},
        )
        assert attached.status_code == 200
        snapshot = attached.json()["snapshot"]
        assert snapshot["metadata"]["monitoring_snapshot"]["sensor"]["reference_version"] == "v1"
        assert len(attached.json()["sha256"]) == 64


def test_invalid_import_is_validated_before_any_storage(settings):
    with TestClient(create_app(settings)) as client:
        headers = {"Authorization": "Bearer test-access-token"}
        payload = {
            "kind": "wastewater_export",
            "permission_basis": "Authorized synthetic laboratory export",
            "records": [
                {
                    "geometry": None,
                    "properties": {
                        "sample_id": "a",
                        "analyte": "fixture",
                        "sampled_at": stamp(),
                        "value": 1,
                        "unit": "copies/g",
                        "source_url": "https://example.org/lab",
                    },
                },
                {
                    "geometry": None,
                    "properties": {
                        "sample_id": "b",
                        "analyte": "fixture",
                        "sampled_at": stamp(),
                        "value": 1,
                        "source_url": "https://example.org/lab",
                    },
                },
            ],
        }
        assert (
            client.post("/api/monitoring/observations/import", headers=headers, json=payload).status_code
            == 422
        )
        assert client.get("/api/monitoring/frame?layers=wastewater").json()["items"] == []


def test_authorized_csv_samples_preserve_non_detects_and_units(settings):
    with TestClient(create_app(settings)) as client:
        headers = {"Authorization": "Bearer test-access-token"}
        csv_text = (
            "sample_id,analyte,sampled_at,value,unit,quality,source_url,latitude,longitude\n"
            + f"sample-csv,Synthetic analyte,{stamp()},,copies/g,non-detect,https://example.org/lab,1,2\n"
        )
        response = client.post(
            "/api/monitoring/observations/import",
            headers=headers,
            json={
                "kind": "wastewater_export",
                "permission_basis": "Authorized synthetic export",
                "csv_text": csv_text,
            },
        )
        assert response.status_code == 200 and response.json()["stored"] == 1
        item = client.get("/api/monitoring/frame?layers=wastewater").json()["items"][0]
        assert item["sensor"]["value"] is None and item["sensor"]["quality"] == "non-detect"
        assert item["longitude"] == 2 and item["sensor"]["unit"] == "copies/g"
