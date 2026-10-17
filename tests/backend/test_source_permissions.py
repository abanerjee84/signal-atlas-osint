"""WM-P0: source redistribution permissions gate commercial collection."""

import types

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.worker import permission_refusal

# Named in docs/WORLDMONITOR_INCORPORATION_PLAN.md section I as needing commercial review.
REVIEW_SOURCES = ["opensky", "dshield", "isc_honeypots", "sans_diary", "cna_world"]


def provider(source_id, commercial):
    return types.SimpleNamespace(
        source_id=source_id, settings=types.SimpleNamespace(commercial_use=commercial)
    )


def test_review_sources_are_seeded_not_cleared(database):
    registered = {row["source_id"] for row in database.permissions()}
    assert set(REVIEW_SOURCES) <= registered
    for source_id in REVIEW_SOURCES:
        decision = database.permission(source_id)
        assert decision["commercial_use"] == "review_required"
        # The seed records an internal review flag, not a licence claim.
        assert decision["reviewed_at"] is None
        assert decision["basis"]


def test_unrecorded_source_has_no_permission_row(database):
    assert database.permission("never_registered") is None


def test_research_deployment_collects_everything_it_is_configured_for(database):
    assert permission_refusal(database, provider("opensky", False)) is None
    assert permission_refusal(database, provider("never_registered", False)) is None


def test_commercial_deployment_refuses_sources_awaiting_review(database):
    refusal = permission_refusal(database, provider("opensky", True))
    assert refusal is not None
    assert "Commercial use awaiting review" in refusal


def test_commercial_deployment_refuses_sources_with_no_recorded_decision(database):
    refusal = permission_refusal(database, provider("never_registered", True))
    assert refusal == "No recorded permission decision for commercial use"


def test_cleared_decision_unblocks_commercial_collection(database):
    database.set_permission("opensky", commercial_use="cleared", basis="Reviewed for the pilot scope only")
    assert permission_refusal(database, provider("opensky", True)) is None


def test_blocked_decision_refuses_in_every_deployment(database):
    database.set_permission(
        "publisher_restricted", commercial_use="blocked", basis="Publisher prohibits redistribution"
    )
    refusal = permission_refusal(database, provider("publisher_restricted", False))
    assert "Blocked by recorded permission decision" in refusal


def test_set_permission_rejects_unreviewed_fields(database):
    with pytest.raises(ValueError):
        database.set_permission("opensky", approved_by="someone")


def test_collected_status_records_the_refusal_reason(database):
    database.set_status("opensky", state="permission_required", error="Commercial use awaiting review")
    status = next(row for row in database.statuses() if row["source_id"] == "opensky")
    assert status["state"] == "permission_required"
    assert "review" in status["error"]


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        _env_file=None,
        database=tmp_path / "test.sqlite3",
        admin_token="test-access",
        evidence_directory=tmp_path / "evidence",
    )
    with TestClient(create_app(settings)) as test_client:
        test_client.headers["Authorization"] = "Bearer test-access"
        yield test_client


def test_register_is_readable_and_separates_recorded_decisions(client):
    body = client.get("/api/v1/sources/permissions").json()["data"]
    assert body["commercial_use_declared"] is False
    rows = {row["source_id"]: row for row in body["sources"]}
    assert rows["opensky"]["recorded"] is True
    assert rows["opensky"]["commercial_use"] == "review_required"
    # Unrecorded sources are shown as open questions rather than hidden or implied.
    unrecorded = [row for row in body["sources"] if not row["recorded"]]
    assert unrecorded
    assert all(row["commercial_use"] == "review_required" for row in unrecorded)


def test_permission_decision_requires_a_substantive_basis(client):
    response = client.put(
        "/api/v1/sources/opensky/permission",
        json={"display_class": "attribution", "commercial_use": "cleared", "basis": "cleared"},
    )
    assert response.status_code == 422


def test_recording_a_decision_is_audited_and_changes_the_gate(client):
    response = client.put(
        "/api/v1/sources/opensky/permission",
        json={
            "display_class": "attribution",
            "commercial_use": "cleared",
            "export_allowed": True,
            "basis": "Reviewed 2026-10-16 for the isolated pilot scope only",
        },
    )
    assert response.status_code == 200
    row = next(row for row in response.json()["data"]["sources"] if row["source_id"] == "opensky")
    assert row["commercial_use"] == "cleared"
    assert row["export_allowed"] is True
    assert row["reviewed_at"]

    database = client.app.state.database
    with database.connect() as db:
        logged = db.execute(
            "SELECT action FROM audit_log WHERE resource_id='opensky' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert logged["action"] == "source.permission"

    commercial = provider("opensky", True)
    assert permission_refusal(database, commercial) is None


def test_register_needs_read_access_but_writing_needs_administrator(client):
    client.headers.pop("Authorization")
    assert client.get("/api/v1/sources/permissions").status_code == 401
    response = client.put(
        "/api/v1/sources/opensky/permission",
        json={
            "display_class": "attribution",
            "commercial_use": "cleared",
            "basis": "Reviewed 2026-10-16 for the isolated pilot scope only",
        },
    )
    assert response.status_code == 401
