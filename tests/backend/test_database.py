import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from pydantic import ValidationError

from backend.config import ROOT
from backend.geo import country_at
from backend.models import Category, Filters, Report, stamp, utcnow

SCHEMA_VERSION = len(list((ROOT / "backend/migrations").glob("*.sql")))


def test_migration_idempotent_and_wal(database):
    database.initialize()
    with database.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_future_schema_rejected(database):
    with database.connect() as db:
        db.execute("PRAGMA user_version=9")
    with pytest.raises(RuntimeError):
        database.initialize()


def test_dedup_retains_reports_and_tracking_url(database, report):
    event = database.ingest(report)
    assert database.ingest(report) == event
    second = report.model_copy(
        update={
            "external_id": "synthetic-2",
            "source_id": "another",
            "source_url": report.source_url + "?utm_source=test",
        }
    )
    assert database.ingest(second) == event
    detail = database.detail(event)
    assert detail["report_count"] == 2
    assert detail["confidence"] == "Single-source"  # Copies do not establish corroboration.
    with database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0] == 2


def test_observations_never_cluster_shared_provider_url(database, report):
    for category in ("environment", "aviation", "maritime", "cyber"):
        first = report.model_copy(update={"category": Category(category), "external_id": category + "-one"})
        second = first.model_copy(update={"external_id": category + "-two"})
        assert database.ingest(first) != database.ingest(second)


def test_similar_title_cluster_and_temporal_boundary(database, report):
    event = database.ingest(report)
    copy = report.model_copy(update={"external_id": "copy", "source_url": "https://another.example/test"})
    assert database.ingest(copy) == event
    later = copy.model_copy(
        update={
            "external_id": "later",
            "published_at": utcnow() + timedelta(days=2),
            "source_url": "https://another.example/later",
        }
    )
    assert database.ingest(later) != event


def test_geo_dateline_and_null(database, report):
    east = report.model_copy(
        update={"external_id": "east", "category": Category.environment, "longitude": 175.0}
    )
    west = east.model_copy(update={"external_id": "west", "longitude": -175.0})
    unlocated = east.model_copy(update={"external_id": "unknown", "latitude": None, "longitude": None})
    for item in (east, west, unlocated):
        database.ingest(item)
    result = database.events(Filters(bbox=(170, 10, -170, 30)))
    assert result["total"] == 2
    assert database.events(Filters(bbox=(170, 10, 180, 30)))["total"] == 1


def test_country_at_and_no_location_invention():
    assert country_at(78.0, 20.0) == "IN"
    assert country_at(-30.0, 0.0) is None


def test_time_basis_and_filter_validation(database, report):
    earlier = report.model_copy(update={"occurred_at": utcnow() - timedelta(days=5)})
    database.ingest(earlier)
    window = {"start": utcnow() - timedelta(days=1)}
    assert database.events(Filters(**window))["total"] == 0
    assert database.events(Filters(time_basis="published", **window))["total"] == 1
    with pytest.raises(ValidationError):
        Filters(bbox=(0, 90, 10, 89))
    with pytest.raises(ValidationError):
        Filters(bbox=(float("nan"), 0, 10, 10))
    with pytest.raises(ValidationError):
        Report(**{**report.model_dump(), "longitude": None})


def test_balanced_page_preserves_layers_regions_and_full_counts(database, report):
    records = []
    for number in range(520):
        records.append(
            report.model_copy(
                update={
                    "external_id": f"air-{number}",
                    "category": Category.aviation,
                    "longitude": 78.0,
                    "latitude": 20.0,
                }
            )
        )
    for category, longitude in [(Category.environment, -120.0), (Category.military, 10.0)]:
        records.append(
            report.model_copy(
                update={
                    "external_id": category.value,
                    "category": category,
                    "longitude": longitude,
                    "published_at": utcnow() - timedelta(hours=2),
                }
            )
        )
    records.append(
        report.model_copy(
            update={
                "external_id": "air-west",
                "category": Category.aviation,
                "longitude": -100.0,
                "published_at": utcnow() - timedelta(hours=1),
            }
        )
    )
    for index in range(0, len(records), 100):
        database.ingest_many(records[index : index + 100])
    result = database.events(Filters(), limit=5, balanced=True)
    assert result["total"] == 523
    assert result["category_counts"]["aviation"] == 521
    assert {item["category"] for item in result["items"]} == {"aviation", "military", "environment"}
    assert any(item["longitude"] == -100 for item in result["items"])
    second = database.events(Filters(), limit=5, offset=5, balanced=True)
    assert not {item["event_id"] for item in result["items"]} & {item["event_id"] for item in second["items"]}


def test_category_counts_follow_period_search_and_location_not_enabled_layers(database, report):
    database.ingest(report.model_copy(update={"category": Category.environment}))
    database.ingest(report.model_copy(update={"external_id": "plane", "category": Category.aviation}))
    result = database.events(Filters(categories=[Category.environment]), limit=1)
    assert result["total"] == 1
    assert result["category_counts"]["aviation"] == 1
    assert database.events(Filters(q="nonexistent"))["category_counts"] == {}


def test_literal_search_and_sql_injection(database, report):
    database.ingest(report)
    assert database.events(Filters(q="%' OR 1=1 --"))["total"] == 0
    assert database.events(Filters(q="%"))["total"] == 0
    assert database.events(Filters(q="peace"))["total"] == 1


def test_concurrent_duplicate_is_atomic(database, report):
    with ThreadPoolExecutor(max_workers=4) as pool:
        identifiers = list(pool.map(lambda _: database.ingest(report), range(8)))
    assert len(set(identifiers)) == 1
    assert database.detail(identifiers[0])["report_count"] == 1


def test_retention_preserves_aggregates_and_cascades(database, settings, report):
    old = report.model_copy(update={"occurred_at": utcnow() - timedelta(days=200)})
    database.ingest(old)
    result = database.maintenance(settings)
    assert result["events"] == 1
    with database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 0
        assert db.execute("SELECT SUM(count) FROM daily_stats").fetchone()[0] == 1


def test_raw_retention_leaves_source_metadata(database, settings, report):
    event = database.ingest(report)
    with database.connect() as db:
        db.execute("UPDATE raw_records SET ingested_at=?", (stamp(utcnow() - timedelta(days=31)),))
    database.maintenance(settings)
    assert database.detail(event)["reports"][0]["metadata"]["source_id"] == "synthetic"


def test_batch_rollback(database, report):
    invalid = report.model_copy(update={"description": None, "external_id": "bad"})
    with pytest.raises(sqlite3.IntegrityError):
        database.ingest_many([report, invalid])
    assert database.events(Filters())["total"] == 0


def test_job_lock(database):
    assert database.lock("test", "owner-one", 100)
    assert not database.lock("test", "owner-two", 100)
    database.unlock("test", "owner-two")
    assert not database.lock("test", "owner-two", 100)
    database.unlock("test", "owner-one")
    assert database.lock("test", "owner-two", 100)


def test_ordering_follows_selected_time_basis(database, report):
    first = report.model_copy(
        update={
            "external_id": "first",
            "category": Category.environment,
            "occurred_at": utcnow() - timedelta(days=3),
            "published_at": utcnow(),
        }
    )
    second = report.model_copy(
        update={
            "external_id": "second",
            "category": Category.environment,
            "occurred_at": utcnow() - timedelta(days=1),
            "published_at": utcnow() - timedelta(hours=1),
        }
    )
    first_id, second_id = database.ingest(first), database.ingest(second)
    assert database.events(Filters())["items"][0]["event_id"] == second_id
    assert database.events(Filters(time_basis="published"))["items"][0]["event_id"] == first_id
