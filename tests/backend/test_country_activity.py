from datetime import timedelta

from backend.country_activity import country_activity
from backend.models import Category, Confidence, Filters, utcnow


def by_country(result):
    return {row["country"]: row for row in result["items"]}


def test_country_comparison_counts_mentions_once_per_url_and_keeps_global_context(database, report):
    first = report.model_copy(update={"title": "Synthetic India and France peace agreement", "news": None})
    database.ingest(first)
    # A second collector delivering the original URL must not inflate mentions.
    database.ingest(first.model_copy(update={"source_id": "second", "external_id": "copy"}))
    database.ingest(
        report.model_copy(
            update={
                "external_id": "fr-cyber",
                "source_url": "https://example.org/cyber/fr",
                "title": "Synthetic France cyber warning",
                "category": Category.cyber,
                "country_code": "FR",
                "latitude": 47,
                "longitude": 2,
                "confidence": Confidence.verified,
            }
        )
    )
    result = country_activity(database, Filters(country="IN"))
    rows = by_country(result)
    assert result["selected_country"] == "IN"
    assert result["period"]["country"] is None
    assert rows["IN"]["mentions"] == 1
    assert rows["FR"]["mentions"] == 2
    assert rows["FR"]["supported_records"] == 1
    assert rows["FR"]["categories"] == {"cyber": 1}
    # A co-mention does not add an intelligence event to the other country.
    assert rows["FR"]["intelligence_records"] == 1


def test_country_comparison_event_filters_and_aviation_exclusion(database, report):
    now = utcnow()
    database.ingest(report)
    database.ingest(
        report.model_copy(
            update={
                "external_id": "old",
                "source_url": "https://example.org/old",
                "title": "Synthetic France peace",
                "country_code": "FR",
                "latitude": 47,
                "longitude": 2,
                "published_at": now - timedelta(days=8),
            }
        )
    )
    database.ingest(
        report.model_copy(
            update={
                "external_id": "plane",
                "source_url": "https://example.org/plane",
                "category": Category.aviation,
                "aircraft_category": 4,
                "aircraft_track_deg": 90,
                "sentiment_kind": None,
            }
        )
    )
    rows = by_country(country_activity(database, Filters(start=now - timedelta(days=1))))
    assert "FR" not in rows
    assert rows["IN"]["records"] == 2
    assert rows["IN"]["intelligence_records"] == 1
    assert rows["IN"]["layer_count"] == 1
    rows = by_country(country_activity(database, Filters(categories=["cyber"])))
    # Sentiment remains the explicitly selected dataset, independently of physical layers.
    assert all(row["layer_count"] == 0 and row["mentions"] == 0 for row in rows.values())
    rows = by_country(country_activity(database, Filters(bbox=(0, 40, 10, 55))))
    assert "IN" not in rows


def test_intelligence_totals_are_not_the_loaded_map_sample(database, report):
    with database.connect() as db:
        for i in range(510):
            database.ingest(
                report.model_copy(
                    update={
                        "external_id": f"cyber-{i}",
                        "source_url": f"https://example.org/cyber/{i}",
                        "category": Category.cyber,
                        "title": f"Synthetic record {i}",
                        "sentiment_kind": None,
                    }
                ),
                connection=db,
            )
        db.commit()
    result = country_activity(database, Filters(categories=["cyber"]))
    assert by_country(result)["IN"]["intelligence_records"] == 510
    assert result["report_available"] == 510


def test_sentiment_sample_and_missing_score_are_explicit(database, report):
    database.ingest(report.model_copy(update={"title": "Synthetic peace victory", "language": "en"}))
    database.ingest(
        report.model_copy(
            update={
                "external_id": "unscored",
                "source_url": "https://example.org/unscored",
                "language": "unknown",
                "country_code": "FR",
                "latitude": 47,
                "longitude": 2,
            }
        )
    )
    rows = by_country(country_activity(database, Filters()))
    assert rows["IN"]["samples"] == 1
    assert rows["IN"]["score"] > 0
    assert rows["FR"]["samples"] == 0
    assert rows["FR"]["score"] is None
