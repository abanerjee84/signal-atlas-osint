import gzip
from unittest.mock import AsyncMock

import pytest

from backend.attack_vectors import extract_vectors
from backend.connectors.base import ProviderError
from backend.connectors.imperva_map import dataset_rows
from backend.connectors.radware_map import RadwareMap, map_rows
from backend.connectors.threat_maps import BunkerWebMap, observation
from backend.connectors.threat_research import ArticleText, ResearchScraper
from backend.models import stamp
from backend.worker import collect


def test_reputation_outcomes_and_negated_techniques_are_not_vectors(settings):
    assert extract_vectors("BLACKLIST DNSBL reputation ransomware malware data breach")[0] == []
    assert extract_vectors("No evidence of SQL injection. Protect against phishing.")[0] == []
    vectors, evidence = extract_vectors("Attackers used SQL injection. A TCP flood caused the DDoS.")
    assert vectors == ["SQL injection", "TCP flood"]
    assert "SQL injection" in evidence and "TCP flood" in evidence
    assert extract_vectors(
        "Supply-chain attacks using fake CAPTCHA and active exploitation of CVE-2026-1234"
    )[0] == ["Supply-chain compromise", "ClickFix / fake CAPTCHA", "Vulnerability exploitation"]
    item = BunkerWebMap(settings).normalize(
        observation({"attacker": "US", "target": "DE", "reason": "BLACKLIST"}, "test", 0)
    )
    assert item.threat.attack_vectors == []
    assert [tag for tag in item.tags if tag.startswith("vector-status:")] == ["vector-status:reputation"]


def test_radware_missing_destinations_do_not_inherit_global_vectors(settings):
    sample = [
        [
            {
                "sourceCountry": "US",
                "destinationCountry": "  ",
                "type": "dDosAttackers",
                "attackTime": "2026-10-11T04:00:00",
                "ip": "192.0.2.1",
            },
            {
                "sourceCountry": "DE",
                "destinationCountry": "JP",
                "type": "scanners",
                "attackTime": "2026-10-11T04:00:01",
            },
            {
                "sourceCountry": "  ",
                "destinationCountry": "  ",
                "type": "scanners",
                "attackTime": "2026-10-11T04:00:02",
            },
        ]
    ]
    rows = map_rows(sample)
    assert len(rows) == 2 and rows[0]["target"] is None
    assert rows[0]["observation_id"] == map_rows(sample)[0]["observation_id"]
    item = RadwareMap(settings).normalize(rows[0])
    assert item.threat.traffic_origin_country == "US" and item.threat.traffic_target_country is None
    assert item.threat.attack_vectors == []
    assert item.threat.attack_kind == "DDoS (subtype unspecified)"
    assert item.occurred_at is None and "192.0.2.1" not in item.model_dump_json()
    # Scanner routes keep their explicit provider category; global percentages still never attach.
    assert RadwareMap(settings).normalize(rows[1]).threat.attack_vectors == [
        "Reconnaissance / scanning",
    ]


def test_imperva_prioritizes_explicit_techniques_within_country_sample():
    rows = dataset_rows(
        gzip.compress(
            b"US,DE,,Automated Threat,Business Logic,Bot,1,3\nUS,DE,,OWASP,SQL Injection,Bot,5,3\nSG,FR,,OWASP,XSS,Bot,3,3\n"
        ),
        "2026-10-09",
        3,
        2,
    )
    assert [row["reason"] for row in rows] == ["OWASP - SQL Injection", "OWASP - XSS"]


@pytest.mark.asyncio
async def test_radware_collection_and_retention_accept_the_new_provider(settings, database):
    provider = RadwareMap(settings)
    provider.fetch = AsyncMock(
        return_value=map_rows(
            [
                [
                    {
                        "sourceCountry": "DE",
                        "destinationCountry": "US",
                        "type": "scanners",
                        "attackTime": "2026-10-11T04:00:00",
                    }
                ]
            ]
        )
    )
    result = await collect(provider, database, AsyncMock())
    assert result["state"] == "ok" and result["stored"] == 1


def test_article_scraping_excludes_navigation_and_limits_text():
    parser = ArticleText()
    parser.feed(
        "<nav><p>SQL injection</p></nav><main><h1>Case study</h1><p>Attackers used phishing.</p><script>RCE</script><footer><p>XSS</p></footer></main>"
    )
    text = " ".join(parser.text)
    assert "phishing" in text and all(label not in text for label in ["SQL injection", "RCE", "XSS"])
    parser.feed("<article><p>" + "a" * 50000 + "</p></article>")
    assert parser.length <= 40000


@pytest.mark.asyncio
async def test_primary_article_uses_matched_evidence_without_storing_body(settings, monkeypatch):
    from backend.connectors.threat_reports import ThreatFeed

    record = {
        "title": "Malware campaign investigation",
        "description": "New report",
        "link": "https://unit42.paloaltonetworks.com/test-campaign/",
        "pubDate": stamp(),
    }
    monkeypatch.setattr(ThreatFeed, "fetch", AsyncMock(return_value=[record]))
    # Feed headline carries campaign wording; the vector only appears in HTML.
    http = AsyncMock()
    http.request.side_effect = [
        b"User-agent: *\nAllow: /\n",
        b"<main><p>Attackers used SQL injection to target organizations in Germany. Exploiting CVE-2026-1234 enabled remote code execution.</p></main>",
    ]
    http.robots_cache = {}
    scraper = ResearchScraper(
        settings,
        "test",
        "Test",
        "https://unit42.paloaltonetworks.com/feed/",
        "US",
        "unit42.paloaltonetworks.com",
    )
    rows = await scraper.fetch(http)
    assert len(scraper.select_records(rows)) == 1
    report = scraper.normalize(rows[0])
    assert "SQL injection" in report.threat.attack_vectors
    assert report.threat.cves == ["CVE-2026-1234"]
    assert "analysis_text" not in report.raw
    assert len(report.threat.vector_evidence) <= 800
    assert report.threat.attacker_country is None


@pytest.mark.asyncio
async def test_primary_article_denial_is_reported_without_bypass(settings, monkeypatch):
    from backend.connectors.threat_reports import ThreatFeed

    record = {
        "title": "SQL injection attack",
        "link": "https://unit42.paloaltonetworks.com/test/",
        "pubDate": stamp(),
    }
    monkeypatch.setattr(ThreatFeed, "fetch", AsyncMock(return_value=[record]))
    http = AsyncMock()
    http.request.side_effect = [b"User-agent: *\nAllow: /\n", ProviderError("denied", status_code=403)]
    http.robots_cache = {}
    scraper = ResearchScraper(
        settings,
        "test",
        "Test",
        "https://unit42.paloaltonetworks.com/feed/",
        "US",
        "unit42.paloaltonetworks.com",
    )
    with pytest.raises(ProviderError, match="denied"):
        await scraper.fetch(http)
