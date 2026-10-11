"""Dated public conflict assessments; retain short excerpts and cited references."""

import json
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .base import ProviderError, clean, parse_time
from .conflict_sources import ConflictRSS
from .threat_maps import robots
from .threat_research import ArticleText


class AssessmentPage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.metadata, self.structured = [], {}, []
        self.json_scope = False
        self.script = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "meta" and attrs.get("content"):
            self.metadata[attrs.get("property") or attrs.get("name")] = attrs["content"]
        if tag == "script" and attrs.get("type") == "application/ld+json":
            self.json_scope = True
            self.script = ""

    def handle_data(self, data):
        if self.json_scope and len(self.script) < 262144:
            self.script += data[: 262144 - len(self.script)]

    def handle_endtag(self, tag):
        if tag == "script" and self.json_scope:
            self.json_scope = False
            try:
                self.structured.append(json.loads(self.script))
            except ValueError:
                pass


def publication(data, depth=0):
    if depth > 8:
        return None
    if isinstance(data, dict):
        types = data.get("@type", [])
        if isinstance(types, str):
            types = [types]
        if any(t in {"Article", "NewsArticle", "BlogPosting"} for t in types) and data.get("datePublished"):
            return data["datePublished"]
        for value in data.values():
            if found := publication(value, depth + 1):
                return found
    elif isinstance(data, list):
        for value in data[:200]:
            if found := publication(value, depth + 1):
                return found
    return None


def assessment_record(payload, url):
    html = payload.decode("utf-8", errors="replace")
    page, article = AssessmentPage(), ArticleText()
    page.feed(html)
    article.feed(html)
    date = page.metadata.get("article:published_time") or publication(page.structured)
    title = clean(page.metadata.get("og:title", ""), 500)
    if not date or not title or not article.text:
        raise ValueError("Assessment requires article content, title and an original publication date")
    parse_time(date)  # A footer/crawl date is never a publication date.
    excerpt = clean(
        page.metadata.get("og:description") or page.metadata.get("description") or " ".join(article.text), 600
    )
    return {"title": title, "description": excerpt, "link": url, "published": date}


class ISW(ConflictRSS):
    interval = 1800
    limitation = "Dated ISW assessments, not independently observed incidents. Short source summaries only; country mentions do not locate military units."

    def __init__(self, settings):
        super().__init__(
            settings,
            source_id="conflict_assessment_isw",
            name="Institute for the Study of War assessments",
            category="military",
            url="https://understandingwar.org/",
            publisher_country="US",
        )

    async def fetch(self, http):
        await robots(http, self.url)
        landing = await http.request("GET", self.url, attempts=1, redirects=2, max_bytes=2_097_152)
        parser = AssessmentPage()
        parser.feed(landing.decode("utf-8", errors="replace"))
        urls = []
        for link in parser.links:
            url = urljoin(self.url, link)
            parsed = urlsplit(url)
            if (
                parsed.hostname == "understandingwar.org"
                and parsed.path.startswith("/research/")
                and len(parsed.path.strip("/").split("/")) >= 3
                and url not in urls
            ):
                urls.append(url)
        records = []
        for url in urls[:4]:
            await robots(http, url)
            payload = await http.request("GET", url, attempts=1, max_bytes=2_097_152)
            try:
                records.append(assessment_record(payload, url))
            except ValueError:
                continue
        if not records:
            raise ProviderError("ISW returned no dated public assessments")
        return records

    def normalize(self, record):
        report = super().normalize(record)
        report.tags += ["assessment", "conflict:conflict"]
        report.evidence_basis = (
            "ISW published assessment; analysts' claims are not independent incident verification"
        )
        report.news.event_type = "conflict"
        return report

    def metadata(self):
        return {
            **super().metadata(),
            "delivery": "Public HTML · bounded assessment discovery",
            "selection": "Up to four actual research article links with original publication dates",
        }
