import re

from ..feeds import parse_feed
from ..geo import mentioned_countries, named_country, unique_country_context
from ..models import NewsMetadata, Report
from .base import Connector, SafeHTTP, clean, parse_time


class RSS(Connector):
    interval = 1800
    limitation = "Headline and feed excerpt only. Country mentions provide regional context, not incident locations. Provider terms govern reuse."

    def __init__(
        self,
        settings,
        *,
        source_id: str,
        name: str,
        category: str,
        url: str,
        kind: str = "news",
        publisher_country: str | None = None,
        coverage: str = "Worldwide",
        usage_notes: str = "Publisher terms; headline and feed excerpt only",
        topical: bool = False,
        text_limit: int = 2000,
    ):
        super().__init__(settings)
        self.source_id, self.name, self.category = source_id, name, category
        self.url, self.homepage, self.kind = url, url, kind
        self.publisher_country = publisher_country
        self.coverage, self.usage_notes = coverage, usage_notes
        self.topical = topical
        self.text_limit = text_limit

    async def fetch(self, http: SafeHTTP) -> list[dict]:
        payload = await http.request("GET", self.url)
        records = parse_feed(payload)
        if not records:
            raise ValueError("No RSS or Atom records")
        return records

    def select_records(self, records):
        if self.topical:
            pattern = r"\b(?:wars?|conflicts?|attack\w*|strikes?|defen[cs]e|military|army|navy|aircraft carrier|deployment|forces|troops|IRGC|ISW|BGP|cyber\w*|diploma\w*|election\w*|president|minister|ministr\w*|parliament|government|protest\w*|sanction\w*|refugee\w*|migrant\w*|humanitarian|climate|energy|solar|trade|border\w*|terror\w*|ceasefire|nuclear|security|court|rights|space race|united nations|NATO|IMF|World Bank|central bank|privati[sz]\w*|exploitation|aid cuts|peace prize|outbreak|Ebola|pandemic|flood\w*|hurricane\w*|tsunami\w*|earthquake\w*|wildfires?|catastrophe|missing persons|Trump|Zelensky\w*|Putin)\b"
            pattern = (
                pattern[:-3]
                + r"|candidates?|votes?|incursion\w*|kidnap\w*|tornado\w*|waterspout\w*|weather|drought)\b"
            )
            records = [
                r
                for r in records
                if re.search(
                    pattern,
                    clean(r.get("title", "") + " " + r.get("description", "") + " " + r.get("category", "")),
                    re.I,
                )
            ]
        return super().select_records(records)

    def normalize(self, record: dict) -> Report:
        title = clean(record["title"], 500)
        country = named_country(title)
        date = record.get("pubDate") or record.get("published") or record.get("updated") or record.get("date")
        if not date:
            raise ValueError("Feed item has no publication date")
        description = clean(
            record.get("description") or record.get("summary") or record.get("content") or "",
            self.text_limit,
        )
        # Publishers that ship the whole article in their own feed put it in
        # content:encoded, which parse_feed exposes as "encoded". Preferring it
        # uses text the publisher volunteered, so it stays within the stated
        # no-scraping terms, while a feed that sends only an excerpt is
        # unaffected.
        if len(record.get("encoded") or "") > len(description):
            description = clean(record["encoded"], self.text_limit)
        if not country and self.category == "economic":
            country = unique_country_context(title + " " + description)

        return Report(
            external_id=record.get("guid") or record.get("id") or record["link"],
            source_id=self.source_id,
            source_url=record["link"],
            title=title,
            description=description,
            category=self.category,
            published_at=parse_time(date),
            country_code=country["code"] if country else None,
            latitude=country["center"][1] if country else None,
            longitude=country["center"][0] if country else None,
            location_precision="regional" if country else "unknown",
            location_basis="Country named in headline or excerpt; regional economic context only"
            if country and self.category == "economic"
            else "Country named in headline; regional context only"
            if country
            else "No supported event location",
            sentiment_kind=self.kind,
            language="en",
            tags=["rss", self.kind],
            news=NewsMetadata(
                publisher_country=self.publisher_country,
                mentioned_countries=mentioned_countries(title + " " + description),
            )
            if self.kind in {"news", "official"}
            else None,
            raw={"title": title, "description": description, "link": record["link"], "published": date},
        )

    def metadata(self):
        return {
            **super().metadata(),
            "publisher_country": self.publisher_country,
            "delivery": "RSS/Atom",
            "geographic_coverage": self.coverage,
            "usage_notes": self.usage_notes,
            "selection": "Geopolitical, security, diplomacy, governance, humanitarian, energy and climate terms in mixed news feeds"
            if self.topical
            else "Publisher feed selection",
        }
