from datetime import timedelta

import pytest

from backend.config import Settings
from backend.database import Database
from backend.models import Report, utcnow


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, database=tmp_path / "test.sqlite3", admin_token="test-access-token")


@pytest.fixture
def database(settings):
    database = Database(settings.database)
    database.initialize()
    return database


@pytest.fixture
def report():
    # Synthetic fixtures stay in temporary test databases; never seed the live application.
    return Report(
        external_id="synthetic-1",
        source_id="synthetic",
        source_url="https://example.org/report/1",
        title="Synthetic: regional peace agreement announcement",
        category="geopolitical",
        published_at=utcnow() - timedelta(hours=1),
        latitude=20,
        longitude=78,
        location_precision="regional",
        country_code="IN",
        language="en",
        sentiment_kind="news",
        description="Synthetic test fixture, not live intelligence",
        tags=["synthetic"],
        raw={"test": True},
    )
