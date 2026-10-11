import asyncio
import base64
import json
from datetime import datetime, timedelta

import httpx
import pytest

from backend.connectors.base import ProviderError, SafeHTTP
from backend.connectors.conflict_assessments import assessment_record
from backend.connectors.conflict_sources import Liveuamap, conflict_sources, conflict_type, parse_liveuamap
from backend.models import Category, Filters, utcnow


def venue(**changes):
    return {
        "id": 1001,
        "name": "Synthetic: drone attack reported near Kyiv",
        "timestamp": int((utcnow() - timedelta(hours=2)).timestamp()),
        "lat": "50.45",
        "lng": "30.52",
        "location": "Kyiv, Ukraine",
        "link": "https://liveuamap.com/en/2026/11-october-synthetic-test",
        "source": "https://example.org/original",
        "moreSources": ["javascript:alert(1)", "https://example.org/original"],
        **changes,
    }


def page(records):
    encoded = base64.b64encode(json.dumps({"venues": records}).encode()).decode()
    return f"<script>var renamed_initializer = '{encoded}';</script>".encode()


async def test_two_layers_share_one_page_and_keep_source_coordinates(settings, database):
    records = [
        venue(),
        venue(
            id=1002, name="Synthetic: peace negotiations announced", source="https://example.org/diplomacy"
        ),
        venue(id=1003, name="M4.5 earthquake in Myanmar"),
    ]
    calls = []

    def transport(request):
        calls.append(str(request.url))
        return httpx.Response(
            200, content=b"User-agent: *\nAllow: /" if request.url.path == "/robots.txt" else page(records)
        )

    military = Liveuamap(settings, "ukraine", "Ukraine", "liveuamap.com", "military")
    politics = Liveuamap(settings, "ukraine", "Ukraine", "liveuamap.com", "geopolitical")
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        http = SafeHTTP(settings, client)
        snapshots = await asyncio.gather(military.fetch(http), politics.fetch(http))
    assert calls.count("https://liveuamap.com/") == 1
    for provider, snapshot in zip((military, politics), snapshots):
        selected = provider.select_records(snapshot)
        assert len(selected) == 1
        database.ingest(provider.normalize(selected[0]))
    assert database.events(Filters())["total"] == 2
    event = next(item for item in database.events(Filters())["items"] if item["category"] == "military")
    assert event["country_code"] == "UA"
    assert event["location_precision"] == "approximate"
    assert event["latitude"] == 50.45
    assert event["occurred_at"] is None
    assert int(datetime.fromisoformat(event["published_at"]).timestamp()) == records[0]["timestamp"]
    assert database.detail(event["event_id"])["reports"][0]["metadata"]["news"]["upstream_sources"] == [
        "https://example.org/original"
    ]


async def test_irrawaddy_xml_trailer_is_not_executed(settings):
    provider = next(p for p in conflict_sources(settings) if p.source_id == "conflict_feed_irrawaddy")
    payload = b"<rss><channel><item><title>Myanmar negotiations</title><link>https://example.org/test</link><pubDate>2026-10-10T08:00:00Z</pubDate></item></channel></rss><script>never_execute()</script>"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=payload))
    ) as client:
        records = await provider.fetch(SafeHTTP(settings, client))
    assert len(records) == 1
    assert records[0]["title"] == "Myanmar negotiations"


@pytest.mark.parametrize(
    "changes",
    [
        {"timestamp": 0},
        {"timestamp": (utcnow() + timedelta(days=1)).timestamp()},
        {"lat": "NaN"},
        {"lng": "181"},
        {"link": "https://evil.example/en/2026/fake"},
        {"link": "javascript:alert(1)"},
    ],
)
def test_invalid_event_data_is_rejected(settings, changes):
    with pytest.raises(ValueError):
        Liveuamap(settings, "ukraine", "Ukraine", "liveuamap.com", "military").normalize(venue(**changes))


def test_static_landmarks_and_missing_payload_fail_visibly():
    encoded = base64.b64encode(json.dumps({"fvObjects": [venue()]}).encode()).decode()
    with pytest.raises(ProviderError):
        parse_liveuamap(f"var ignored = '{encoded}';".encode())
    with pytest.raises(ProviderError):
        parse_liveuamap(b"<html>Challenge or empty landing page</html>")


def test_original_feed_dates_and_topic_routing(settings):
    feeds = {provider.source_id: provider for provider in conflict_sources(settings)}
    provider = feeds["conflict_feed_irrawaddy"]
    date = (utcnow() - timedelta(days=3)).isoformat()
    report = provider.normalize(
        {
            "title": "Myanmar army drone attack reported",
            "description": "Source describes fighting in Myanmar.",
            "link": "https://www.irrawaddy.com/news/synthetic-test",
            "published": date,
        }
    )
    assert report.category == "military"
    assert report.published_at.isoformat() == date
    assert report.location_precision == "regional"
    assert report.country_code == "MM"
    assert (
        provider.select_records([{"title": "Football final victory", "description": "League fixtures"}]) == []
    )
    with pytest.raises(ValueError):
        provider.normalize({"title": "Myanmar negotiations", "link": "https://example.org/undated"})


def test_cross_region_copy_deduplicates_with_its_original_permalink(settings, database):
    record = venue(link="https://israelpalestine.liveuamap.com/en/2026/11-october-synthetic-test")
    ids = [
        database.ingest(Liveuamap(settings, region, region, host, "military").normalize(record))
        for region, host in [("ukraine", "liveuamap.com"), ("israel", "israelpalestine.liveuamap.com")]
    ]
    assert ids[0] == ids[1]
    assert database.events(Filters())["total"] == 1
    assert database.detail(ids[0])["confidence"] == "Single-source"


def test_assessment_requires_actual_original_publication():
    payload = b"""<meta property="og:title" content="Synthetic conflict assessment"><meta property="og:description" content="A short published assessment."><script type="application/ld+json">{"@graph":[{"@type":"Article","datePublished":"2026-10-10T08:00:00Z"}]}</script><article><p>Assessment source text.</p></article>"""
    result = assessment_record(payload, "https://understandingwar.org/research/test/assessment/")
    assert result["published"] == "2026-10-10T08:00:00Z"
    assert result["description"] == "A short published assessment."
    with pytest.raises(ValueError):
        assessment_record(payload.replace(b"datePublished", b"dateModified"), "https://example.org/test")


def test_civilian_crime_does_not_become_military_and_primary_rerouting_updates_category(settings, database):
    provider = next(p for p in conflict_sources(settings) if p.source_id == "conflict_feed_khaama")
    record = {
        "title": "Eight killed in Pennsylvania shooting",
        "description": "A civilian crime investigation.",
        "link": "https://example.org/civilian-test",
        "published": utcnow().isoformat(),
    }
    correct = provider.normalize(record)
    assert correct.category == "geopolitical"
    assert conflict_type(record["title"])["id"] == "security"
    event_id = database.ingest(correct.model_copy(update={"category": Category.military}))
    assert database.ingest(correct) == event_id
    assert database.detail(event_id)["category"] == "geopolitical"
