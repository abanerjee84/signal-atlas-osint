from datetime import timedelta

from fastapi.testclient import TestClient
from backend.aviation_demand import aviation_requested, set_demand
from backend.main import create_app
from backend.models import stamp, utcnow


def test_multiple_viewers_and_expired_hidden_tab(database):
    first, second = "a" * 32, "b" * 32
    assert not aviation_requested(database)
    set_demand(database, first, True)
    set_demand(database, second, True)
    set_demand(database, first, False)
    assert aviation_requested(database)
    with database.connect() as connection:
        connection.execute("UPDATE job_locks SET expires_at=?", (stamp(utcnow() - timedelta(seconds=1)),))
    assert not aviation_requested(database)
    set_demand(database, second, False)
    assert not aviation_requested(database)


def test_live_route_records_and_releases_viewer_without_admin(settings, database):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/aviation/live?viewer=" + "a" * 32).status_code == 200
        assert aviation_requested(database)
        assert client.get("/api/aviation/live?viewer=" + "a" * 32 + "&active=false").status_code == 200
        assert not aviation_requested(database)
        assert client.get("/api/aviation/live?viewer=../../bad").status_code == 422
