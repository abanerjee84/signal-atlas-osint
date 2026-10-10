import sqlite3
from datetime import timedelta

import pytest

from backend.connectors.reddit_archive import RedditArchive
from backend.connectors.social import SocialFeed
from backend.geo import mentioned_countries
from backend.military import military_brief
from backend.models import Category, Filters, NewsMetadata, utcnow
from backend.operations import backup_database
from backend.relations import country_network, news_relations
from backend.social_analytics import social_sentiment


def comment(settings, **updates):
    source = SocialFeed(
        settings,
        source_id="reddit_test_comments",
        name="Test comments",
        url="https://www.reddit.com/r/worldnews/comments/.rss",
        content_type="comment",
    )
    return source.normalize(
        {
            "id": "t1_abc",
            "title": "/u/example on Russia attacks Ukraine",
            "content": "I am delighted and happy that the excellent peace agreement succeeded!",
            "link": "https://www.reddit.com/r/worldnews/comments/xyz/title/abc/",
            "updated": utcnow().isoformat(),
            **updates,
        }
    )


def test_comment_sentiment_uses_body_and_context_is_not_origin(settings, database):
    record = comment(settings)
    assert record.social.origin_country is None
    assert record.social.context_countries == ["RU", "UA"]
    assert record.social.mentioned_countries == []
    assert record.social.relations[0].target_id == "t3_xyz"
    database.ingest(record)
    result = social_sentiment(database, Filters())
    assert result["distribution"]["positive"] == 1
    assert result["known_origin_count"] == 0
    assert {r["country"] for r in result["regions"]} == {"RU", "UA"}
    assert result["map_network"]["edges"][0]["kind"] == "country_co_mention"
    assert result["discussion_network"]["edges"][0]["kind"] == "comment_on"
    origin = social_sentiment(database, Filters(), geography="origin")
    assert origin["regions"] == []
    assert origin["sample_count"] == 1


def test_duplicate_delivery_not_double_counted_and_language_excluded(settings, database):
    record = comment(settings)
    database.ingest(record)
    duplicate = record.model_copy(
        update={
            "source_id": "reddit_archive_test",
            "source_url": "https://www.reddit.com/r/worldnews/comments/xyz/_/abc/",
        }
    )
    database.ingest(duplicate)
    foreign = comment(
        settings,
        id="t1_def",
        content="Un texte en français pour une discussion différente",
        link="https://www.reddit.com/r/worldnews/comments/xyz/title/def/",
    ).model_copy(update={"language": "fr"})
    database.ingest(foreign)
    result = social_sentiment(database, Filters())
    assert result["dataset_count"] == 2
    assert result["sample_count"] == 1
    assert result["excluded_language_count"] == 1


def test_social_snapshot_replacement_and_backup_exclusion(settings, database, tmp_path, report):
    record = comment(settings)
    database.ingest(report)
    database.replace_social_snapshot(record.source_id, [record])
    path = backup_database(settings.database, tmp_path / "backup")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM reports WHERE sentiment_kind='public'").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM reports WHERE sentiment_kind='news'").fetchone()[0] == 1
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    database.replace_social_snapshot(record.source_id, [])
    assert social_sentiment(database, Filters())["dataset_count"] == 0


def test_archive_json_keeps_explicit_reply_links_and_original_date(settings):
    source = RedditArchive(settings, community="worldnews", content_type="comment")
    date = int((utcnow() - timedelta(days=2)).timestamp())
    record = source.normalize(
        {
            "id": "abc",
            "link_id": "t3_xyz",
            "parent_id": "t1_def",
            "body": "France and Germany announced a successful agreement today.",
            "created_utc": date,
            "author": "example",
        }
    )
    assert int(record.published_at.timestamp()) == date
    assert record.social.origin_country is None
    assert [r.kind for r in record.social.relations] == ["comment_on", "reply"]
    assert record.social.relations[1].target_url.endswith("/def/")
    assert record.social.mentioned_countries == ["DE", "FR"]


def test_youtube_uploads_never_count_as_public_discourse(settings, database):
    source = SocialFeed(
        settings,
        source_id="youtube_test",
        name="Channel",
        url="https://www.youtube.com/feeds/videos.xml",
        platform="youtube",
        content_type="video",
        publisher_country="GB",
    )
    record = source.normalize(
        {
            "id": "video_1",
            "title": "France and Germany announce defence agreement",
            "description": "The ministers have announced a new agreement today.",
            "link": "https://www.youtube.com/watch?v=test",
            "published": utcnow().isoformat(),
        }
    )
    assert record.sentiment_kind == "news"
    assert record.news.publisher_country == "GB"
    assert record.social.origin_country is None
    database.ingest(record)
    assert social_sentiment(database, Filters())["dataset_count"] == 0
    assert social_sentiment(database, Filters(), "news", "youtube")["dataset_count"] == 1


def test_military_brief_maps_multicountry_evidence_without_forcing_incident(settings, database, report):
    official = report.model_copy(
        update={
            "external_id": "official",
            "source_id": "defence",
            "source_url": "https://example.org/defence",
            "title": "France and Germany announce joint military exercise",
            "description": "A public announcement about training and readiness.",
            "category": Category.military,
            "sentiment_kind": "official",
            "latitude": None,
            "longitude": None,
            "country_code": None,
            "news": NewsMetadata(publisher_country="GB", mentioned_countries=["FR", "DE"]),
        }
    )
    media = official.model_copy(
        update={
            "external_id": "media",
            "source_id": "media",
            "source_url": "https://example.net/report",
            "category": Category.geopolitical,
            "sentiment_kind": "news",
        }
    )
    database.ingest(official)
    database.ingest(media)
    database.ingest(report)
    filters = Filters(country="DE")
    brief = military_brief(database, filters)
    assert brief["report_count"] == 2
    assert brief["official_count"] == 1 and brief["media_count"] == 1
    group = next(g for g in brief["groups"] if g["name"] == "Exercises & readiness")
    assert group["count"] == 2
    assert {r["basis"] for r in group["reports"]} == {"Media reporting", "Official announcement"}
    assert group["network"]["edges"]
    assert all(e["report_ids"] and e["urls"] for e in group["network"]["edges"])
    assert news_relations(database, filters)["report_count"] == 1
    assert military_brief(database, Filters(country="JP"))["report_count"] == 0


def test_military_brief_excludes_civilian_training_and_separates_history(database, report):
    school = report.model_copy(
        update={
            "external_id": "school",
            "source_url": "https://example.org/school",
            "title": "France announces new teacher training programme",
            "description": "More classroom exercises are planned.",
        }
    )
    history = report.model_copy(
        update={
            "external_id": "history",
            "source_url": "https://example.org/history",
            "title": "German military adaptation in World War II (1942)",
            "category": Category.military,
            "sentiment_kind": "official",
        }
    )
    database.ingest(school)
    database.ingest(history)
    result = military_brief(database, Filters())
    assert result["report_count"] == 1
    assert [g["name"] for g in result["groups"]] == ["Historical background"]


def test_country_context_matches_abbreviations_without_us_pronoun():
    assert mentioned_countries("US and UK announced defence cooperation with Kuwait") == ["GB", "KW", "US"]
    assert mentioned_countries("Help us understand the Indian Ocean and British Columbia") == []


def test_legacy_metadata_uses_current_country_wording_for_filters(database, report):
    legacy = report.model_copy(
        update={
            "external_id": "legacy",
            "source_url": "https://example.org/legacy",
            "title": "US and UK discuss defence cooperation",
            "country_code": None,
            "latitude": None,
            "longitude": None,
            "news": None,
        }
    )
    database.ingest(legacy)
    assert news_relations(database, Filters(country="US"))["report_count"] == 1
    assert military_brief(database, Filters(country="GB"))["report_count"] == 1


def _mention_row(url, score):
    return {
        "report_id": url,
        "event_id": "e1",
        "title": "t",
        "description": "d",
        "source_url": url,
        "source_id": "s1",
        "sentiment_score": score,
        "metadata": '{"news": {"publisher_country": "US", "mentioned_countries": ["IN"]}}',
    }


def test_edge_sentiment_is_the_mean_tone_of_its_own_reports():
    network = country_network([_mention_row("a", -1.0), _mention_row("b", -1.0), _mention_row("c", 1.0)])
    edge = network["edges"][0]
    assert edge["count"] == 3
    assert edge["sentiment_samples"] == 3
    assert edge["sentiment"] == pytest.approx(-1 / 3)
    assert not [k for k in edge if k.startswith("score_")]


def test_edge_sentiment_stays_undefined_for_unscored_wording():
    edge = country_network([_mention_row("a", None)])["edges"][0]
    assert edge["sentiment"] is None
    assert edge["sentiment_samples"] == 0
