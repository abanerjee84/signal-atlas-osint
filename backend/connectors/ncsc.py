"""UK NCSC public advisories. National CERT reporting with agency geography."""

from ..feeds import parse_feed
from ..geo import unique_country_context
from ..models import Report
from .base import Connector, SafeHTTP, clean


class NCSC(Connector):
    source_id, name, category = "ncsc", "UK NCSC advisories and reports", "cyber"
    homepage = "https://www.ncsc.gov.uk/section/keep-up-to-date/all-newsletters"
    interval = 3600
    limitation = "One national CERT's public advisories. A single country named in a title is regional context, not incident geography or actor attribution. Multiple named countries remain unlocated. Publication does not establish corroboration or severity."

    async def fetch(self, http: SafeHTTP) -> list[dict]:
        payload = await http.request("GET", "https://www.ncsc.gov.uk/api/1/services/v1/all-rss-feed.xml")
        records = parse_feed(payload)
        if not records:
            raise ValueError("No RSS or Atom records")
        return records

    def normalize(self, record: dict) -> Report:
        title = clean(record["title"], 500)
        description = clean(record.get("description") or record.get("summary") or "", 3000)
        date = record.get("pubDate") or record.get("published") or record.get("updated") or record.get("date")
        if not date:
            raise ValueError("Feed item has no publication date")
        country = unique_country_context(title)
        basis = (
            "Single country named in advisory title; regional context, not actor attribution"
            if country
            else "No unambiguous country context in advisory title"
        )
        tags = ["ncsc", "cyber-advisory"]
        return Report(
            external_id=record.get("guid") or record.get("id") or record["link"],
            source_id=self.source_id,
            source_url=record["link"],
            title=title,
            description=description,
            category=self.category,
            latitude=country["center"][1] if country else None,
            longitude=country["center"][0] if country else None,
            country_code=country["code"] if country else None,
            location_precision="regional" if country else "unknown",
            location_basis=basis,
            published_at=self._time(date),
            confidence="Single-source",
            evidence_basis="One NCSC advisory; not independently corroborated and not verified actor responsibility",
            severity="unknown",
            severity_basis="No issuer severity score supplied",
            language="en",
            sentiment_kind="official",
            tags=tags,
            raw={"title": title, "link": record["link"], "published": date},
        )

    @staticmethod
    def _time(value: str):
        from .base import parse_time

        return parse_time(value)
