from ..geo import named_country
from ..models import Report
from .base import Connector, SafeHTTP, clean, parse_time


class GDELT(Connector):
    source_id, name, category = "gdelt", "GDELT news discovery", "geopolitical"
    homepage = "https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/"
    interval = 1800
    limitation = "Bounded 250 newest matching articles in a rolling 24-hour window. Publication time is GDELT first-seen time. Source country describes the publisher and is never used as event geography. Country mentions are regional context only."

    async def fetch(self, http: SafeHTTP) -> list[dict]:
        result = await http.json(
            "GET",
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "query": "(conflict OR protest OR election OR sanctions OR diplomacy)",
                "mode": "ArtList",
                "format": "json",
                "maxrecords": 250,
                "timespan": "24h",
                "sort": "DateDesc",
            },
        )
        return result.get("articles", [])

    def normalize(self, record: dict) -> Report:
        title = clean(record["title"], 500)
        country = named_country(title)
        return Report(
            external_id=record["url"],
            source_id=self.source_id,
            source_url=record["url"],
            title=title,
            description="Article discovered through GDELT. Open the original publisher for full context.",
            category=self.category,
            country_code=country["code"] if country else None,
            latitude=country["center"][1] if country else None,
            longitude=country["center"][0] if country else None,
            location_precision="regional" if country else "unknown",
            location_basis="Single explicit country mention in headline; representative country point, not event coordinates"
            if country
            else "No supported event location",
            published_at=parse_time(record["seendate"]),
            language=record.get("language", "unknown"),
            sentiment_kind="news",
            tags=["news", "gdelt"],
            raw=record,
        )
