from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from backend.config import Settings
from backend.connectors.base import ProviderError
from backend.connectors.public_discussion import TelegramPreview, TelegramPublic, discussion_feeds
from backend.connectors.social import SocialFeed
from backend.connectors.threat_reports import ThreatFeed
from backend.models import Filters, utcnow
from backend.social_analytics import social_sentiment
from backend.threat_activity import extract_threat


@pytest.mark.parametrize(
    "text,origin,victims",
    [
        ("Russian-backed hackers target Ukraine banks with malware.", "RU", ["UA"]),
        ("North Korean hackers launch cyberattacks on South Korean banks.", "KP", ["KR"]),
        ("Chinese hackers target Japan and Taiwan using malware.", "CN", ["JP", "TW"]),
        ("Lazarus malware found by researchers in Germany.", None, []),
        ("Not Russian hackers. Unknown actors target Ukraine with malware.", None, ["UA"]),
        ("Chinese hackers did not target Japan with malware.", "CN", []),
        ("Russian hackers and Chinese hackers target Japan with malware.", None, ["JP"]),
        ("China-nexus UAT-11587 targets Taiwan and India with a backdoor.", "CN", ["IN", "TW"]),
        ("China-linked APT41 targets India with malware.", "CN", ["IN"]),
        ("Russian state-sponsored hackers target Ukraine banks.", "RU", ["UA"]),
        ("Chinese hackers target Japan banks, according to researchers in Germany.", "CN", ["JP"]),
        (
            "An APT spear-phishing campaign against individuals affiliated with Taiwan research organizations.",
            None,
            ["TW"],
        ),
    ],
)
def test_role_specific_country_extraction(text, origin, victims):
    item = extract_threat(text)
    assert item.attacker_country == origin
    assert item.victim_countries == victims


def test_catalog_name_does_not_infer_country_and_source_is_preserved(database):
    provider = ThreatFeed(Settings(), "test", "Test publisher", "https://example.org/feed", "US")
    item = provider.normalize(
        {
            "title": "Lazarus hackers target Ukraine banks",
            "description": "No attribution country supplied.",
            "link": "https://example.org/attack",
            "pubDate": utcnow().isoformat(),
        }
    )
    assert item.threat.attacker_country is None
    assert item.country_code == "UA"
    assert item.location_precision == "regional"
    event_id = database.ingest(item)
    detail = database.detail(event_id)
    assert detail["threat"]["victim_countries"] == ["UA"]
    assert detail["reports"][0]["source_url"] == "https://example.org/attack"
    assert database.events(Filters(categories=["threat"]))["items"][0]["threat"]["actor"] == "Lazarus"


def test_mastodon_text_without_title_is_scored_once_and_deduplicated(database):
    now = utcnow().isoformat()
    for identifier in ("one", "two"):
        provider = SocialFeed(
            Settings(),
            source_id=identifier,
            name="Hashtag feed",
            url="https://example.org/feed",
            platform="mastodon",
        )
        item = provider.normalize(
            {
                "description": "I strongly oppose this terrible war in Ukraine and Russia.",
                "guid": "https://example.org/@person/123",
                "link": "https://example.org/@person/123",
                "pubDate": now,
            }
        )
        assert item.description.count("terrible") == 1
        assert item.social.origin_country is None
        database.ingest(item)
    result = social_sentiment(database, Filters(start=utcnow() - timedelta(days=1)), platform="mastodon")
    assert result["dataset_count"] == 1
    assert result["sample_count"] == 1
    assert result["distribution"]["negative"] == 1
    assert {row["country"] for row in result["regions"]} == {"RU", "UA"}
    assert result["known_origin_count"] == 0


def test_public_html_parser_ignores_script_media_and_undated_text():
    parser = TelegramPreview()
    parser.feed(
        '<div class="tgme_widget_message" data-post="examplechannel/42"><div class="tgme_widget_message_text">Public text about Ukraine.<b>Peace matters.</b><script>private()</script></div><time datetime="2026-10-11T00:00:00Z"></time></div><div class="tgme_widget_message" data-post="examplechannel/43"><div class="tgme_widget_message_text">No timestamp</div></div>'
    )
    assert len(parser.records) == 1
    assert "private()" not in parser.records[0]["content"]
    assert parser.records[0]["link"] == "https://t.me/examplechannel/42"
    assert "Peace matters" in parser.records[0]["content"]


def test_discussion_sources_need_no_credentials():
    providers = discussion_feeds(Settings(telegram_channels=["examplechannel"]))
    assert {provider.platform for provider in providers} == {"mastodon", "lemmy", "telegram"}
    assert all(provider.access() is None and provider.snapshot for provider in providers)


@pytest.mark.asyncio
async def test_missing_robots_allows_only_public_timestamped_posts():
    html = b'<div class="tgme_widget_message" data-post="examplechannel/42"><div class="tgme_widget_message_text">Terrible war in Ukraine.</div><time datetime="2026-10-11T00:00:00Z"></time></div>'
    http = AsyncMock()
    http.request.side_effect = [ProviderError("Provider HTTP 404", status_code=404), html]
    provider = TelegramPublic(Settings(), "examplechannel")
    records = await provider.fetch(http)
    report = provider.normalize(records[0])
    assert report.description.count("Terrible") == 1
    assert report.social.origin_country is None
    assert http.request.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [403, 429, 503])
async def test_public_preview_does_not_bypass_denials_or_rate_limits(code):
    http = AsyncMock()
    http.request.side_effect = ProviderError(f"Provider HTTP {code}", status_code=code)
    with pytest.raises(ProviderError):
        await TelegramPublic(Settings(), "examplechannel").fetch(http)
    assert http.request.call_count == 1


@pytest.mark.asyncio
async def test_public_preview_respects_robots_disallow():
    http = AsyncMock()
    http.request.return_value = b"User-agent: *\nDisallow: /s/\n"
    with pytest.raises(ProviderError, match="robots policy"):
        await TelegramPublic(Settings(), "examplechannel").fetch(http)
    assert http.request.call_count == 1
