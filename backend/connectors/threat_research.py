"""Bounded public article scrapers, discovered through publishers' RSS links."""

import asyncio
from html.parser import HTMLParser
from urllib.parse import urlsplit

from ..attack_vectors import extract_vectors
from ..models import utcnow
from .base import ProviderError, clean, parse_time
from .threat_maps import robots
from .threat_reports import ThreatFeed


class ArticleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scope = 0
        self.blocked = 0
        self.paragraph = 0
        self.text = []
        self.length = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"article", "main"}:
            self.scope += 1
        if tag in {"script", "style", "nav", "footer", "aside", "header"}:
            self.blocked += 1
        if tag in {"p", "h1", "h2", "h3", "li"}:
            self.paragraph += 1
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in {"article", "main"}:
            self.scope = max(0, self.scope - 1)
        if tag in {"script", "style", "nav", "footer", "aside", "header"}:
            self.blocked = max(0, self.blocked - 1)
        if tag in {"p", "h1", "h2", "h3", "li"}:
            self.paragraph = max(0, self.paragraph - 1)

    def handle_data(self, data):
        if self.scope and self.paragraph and not self.blocked and self.length < 40000:
            fragment = data[: 40000 - self.length]
            self.text.append(fragment)
            self.length += len(fragment)


class ResearchScraper(ThreatFeed):
    interval = 900
    article_limit = 8
    delivery = "Publisher RSS discovery followed by bounded public HTML article scraping; no API"

    def __init__(self, settings, identifier, name, feed, country, article_host):
        super().__init__(settings, identifier, name, feed, country)
        self.article_host = article_host
        self.limitation = "Public primary research, not live incidents. Only short excerpts and matched technique evidence are stored. Technique/country extraction is deterministic and unverified; unknown origins remain unknown. Older publication dates stay intact."

    async def fetch(self, http):
        await robots(http, self.url)
        candidates = await super().fetch(http)
        result = []
        attempted = 0
        for record in candidates:
            url = record.get("link", "")
            if urlsplit(url).hostname != self.article_host:
                continue
            try:
                published = parse_time(
                    record.get("pubDate") or record.get("published") or record.get("updated")
                )
                if (utcnow() - published).days > 45 or published > utcnow():
                    continue
                # Skip benign product posts before requesting article bodies.
                title = clean(record.get("title", ""))
                if not extract_vectors(title + " " + clean(record.get("description", "")))[
                    0
                ] and not self.select_records([record]):
                    continue
                await robots(http, url)
                if attempted >= self.article_limit:
                    break
                attempted += 1
                payload = await http.request("GET", url, attempts=1, max_bytes=2_097_152)
                parser = ArticleText()
                parser.feed(payload.decode("utf-8", errors="replace"))
                analysis = title + ". " + " ".join(parser.text)
                vectors, _ = extract_vectors(analysis)
                if not vectors or not self.select_records([{**record, "description": analysis}]):
                    continue
                result.append({**record, "analysis_text": analysis[:20000]})
            except ProviderError as error:
                if error.status_code in {403, 429, 503}:
                    raise
                continue
            except (ValueError, TypeError):
                continue
            if len(result) >= self.article_limit:
                break
            await asyncio.sleep(0.25)
        return result

    def metadata(self):
        return {**super().metadata(), "delivery": self.delivery, "article_limit": self.article_limit}

    def select_records(self, records):
        # Collection applies this selector after fetch as well. Preserve the
        # attack context found in the article even if the feed excerpt is terse.
        selected = super().select_records(
            [
                {**record, "description": record.get("analysis_text", record.get("description", ""))}
                for record in records
            ]
        )
        urls = {record.get("link") for record in selected}
        return [record for record in records if record.get("link") in urls]

    def normalize(self, record):
        # HTML bodies are used in memory only. Preserve a short feed excerpt and
        # at most 800 characters of matched evidence instead of full articles.
        record = {**record, "description": clean(record.get("description", ""), 600)}
        report = super().normalize(record)
        report.tags.append("primary-research-scrape")
        report.raw["vector_evidence"] = report.threat.vector_evidence
        return report


def research_scrapers(settings):
    return [
        ResearchScraper(
            settings,
            "research_unit42",
            "Unit 42 primary research",
            "https://unit42.paloaltonetworks.com/feed/",
            "US",
            "unit42.paloaltonetworks.com",
        ),
        ResearchScraper(
            settings,
            "research_securelist",
            "Securelist primary research",
            "https://securelist.com/feed/",
            None,
            "securelist.com",
        ),
        ResearchScraper(
            settings,
            "research_mandiant",
            "Google / Mandiant primary research",
            "https://feeds.feedburner.com/threatintelligence/pvexyqv7v0v",
            "US",
            "cloud.google.com",
        ),
    ]
