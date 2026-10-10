"""Public cyber feed excerpts. Publication and country context are not attack attribution."""

from ..geo import countries
from .rss import RSS


class CyberFeed(RSS):
    def __init__(self, settings, *, automated=False, **kwargs):
        super().__init__(settings, category="cyber", **kwargs)
        self.automated = automated
        self.interval = 3600
        self.limitation = "Public feed metadata and excerpt; country mentions are report context, not victim or attacker locations."
        if automated:
            self.limitation += " Automated secondary analysis without manual editorial review; follow cited original sources."

    async def fetch(self, http):
        if self.source_id == "sans_diary":
            from ..feeds import parse_feed

            payload = await http.request(
                "GET",
                self.url,
                attempts=1,
                headers={
                    "User-Agent": "GlobalOSINT/0.1 "
                    + (self.settings.sans_contact or "public-source-research")
                },
            )
            records = parse_feed(payload)
            if not records:
                raise ValueError("Empty SANS diary feed")
            return records
        return await super().fetch(http)

    def normalize(self, record):
        report = super().normalize(record)
        # Use all explicit country mentions in the supplied feed excerpt as context.
        codes = report.news.mentioned_countries if report.news else []
        if len(codes) == 1:
            place = next(
                (f["properties"] for f in countries()["features"] if f["properties"]["code"] == codes[0]),
                None,
            )
            if place:
                report.longitude, report.latitude = place["center"]
                report.country_code = codes[0]
                report.location_precision = "regional"
                report.location_basis = (
                    "Single country mentioned in feed title/excerpt; report context, not incident location"
                )
        elif len(codes) > 1:
            report.longitude = report.latitude = report.country_code = None
            report.location_precision = "unknown"
            report.location_basis = "Multiple countries mentioned; see contextual map connections"
        report.tags += ["cyber-report"] + (["automated-secondary-analysis"] if self.automated else [])
        if self.automated:
            report.evidence_basis = (
                "Automated secondary briefing; not independently verified actor attribution"
            )
        return report


def cyber_feeds(settings):
    definitions = [
        (
            "sans_diary",
            "SANS Internet Storm Center diary",
            "https://isc.sans.edu/rssfeed_full.xml",
            "US",
            False,
        ),
        ("citizen_lab", "Citizen Lab investigations and updates", "https://citizenlab.ca/feed/", "CA", False),
        ("krebs", "Krebs on Security investigations", "https://krebsonsecurity.com/feed/", "US", False),
        (
            "defend_network",
            "defend.network automated briefings",
            "https://defend.network/feed.xml",
            None,
            True,
        ),
    ]
    return [
        CyberFeed(
            settings,
            source_id=sid,
            name=name,
            url=url,
            publisher_country=country,
            automated=automated,
            usage_notes="Linked feed excerpts only; publisher terms apply; do not republish full articles",
        )
        for sid, name, url, country, automated in definitions
    ]
