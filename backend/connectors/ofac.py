"""OFAC sanctions program changes. Real economic-policy geography, not headlines."""

from datetime import timedelta

from ..feeds import parse_feed
from ..geo import unique_country_context
from ..models import Report, utcnow
from .base import Connector, SafeHTTP, clean, parse_time

# The OFAC program feed republishes long-standing program pages, so most items
# carry a date months old. Retention purges anything beyond the event window, so
# only recent guidance is kept; older program pages are reference material, not
# news, and re-ingesting them every hour only churns the database.
MAX_AGE_DAYS = 21


class OFAC(Connector):
    source_id, name, category = "ofac", "OFAC sanctions guidance (recent publications only)", "economic"
    homepage = "https://ofac.treasury.gov/sanctions-programs-and-country-information"
    interval = 3600
    limitation = (
        "Recent sanctions guidance publications only, not enforcement actions or economic "
        "measurements. The public program feed republishes long-standing program pages, so "
        "this layer is frequently empty by design. Named countries are program scope, not an "
        "assertion about events occurring there."
    )

    async def fetch(self, http: SafeHTTP) -> list[dict]:
        payload = await http.request("GET", "https://ofac.treasury.gov/rss.xml")
        records = parse_feed(payload)
        if not records:
            raise ValueError("No RSS or Atom records")
        cutoff = utcnow() - timedelta(days=MAX_AGE_DAYS)
        recent = []
        for record in records:
            date = (
                record.get("pubDate")
                or record.get("published")
                or record.get("updated")
                or record.get("date")
            )
            if not date:
                continue
            try:
                if parse_time(date) < cutoff:
                    continue
            except (ValueError, TypeError, IndexError):
                continue
            recent.append(record)
        return recent

    def normalize(self, record: dict) -> Report:
        title = clean(record["title"], 500)
        description = clean(record.get("description") or "", 2000)
        date = record.get("pubDate") or record.get("published") or record.get("updated") or record.get("date")
        if not date:
            raise ValueError("Feed item has no publication date")
        country = unique_country_context(title)
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
            location_basis="Sanctions program scope country; policy context, not an incident location"
            if country
            else "No supported program scope country",
            published_at=parse_time(date),
            confidence="Single-source",
            evidence_basis="One official US Treasury sanctions publication; not independent corroboration or evidence of enforcement action",
            severity="unknown",
            severity_basis="No issuer severity score supplied",
            language="en",
            sentiment_kind="official",
            tags=["ofac", "sanctions"],
            raw={"title": title, "link": record["link"], "published": date},
        )
