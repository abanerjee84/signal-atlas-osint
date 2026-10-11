"""Public conflict pages and publisher feeds. No API, login or article-body harvesting."""

import asyncio
import base64
import json
import math
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from xml.etree.ElementTree import ParseError

from ..config import ROOT
from ..geo import country_at, mentioned_countries, unique_country_context
from ..models import Category, NewsMetadata, Report, utcnow
from .base import Connector, ProviderError, clean
from .rss import RSS
from .threat_maps import robots

TYPES = json.loads((ROOT / "src/conflict-types.json").read_text(encoding="utf-8"))
RULES = [(rule, re.compile(rule["pattern"], re.I)) for rule in TYPES]
REGIONS = [
    ("ukraine", "Ukraine", "liveuamap.com"),
    ("israel_palestine", "Israel / Palestine", "israelpalestine.liveuamap.com"),
    ("sudan", "Sudan", "sudan.liveuamap.com"),
    ("myanmar", "Myanmar", "myanmar.liveuamap.com"),
    ("sahel", "Sahel", "sahel.liveuamap.com"),
    ("yemen", "Yemen", "yemen.liveuamap.com"),
    ("asia", "Asia", "asia.liveuamap.com"),
    ("latin_america", "Latin America", "latam.liveuamap.com"),
    ("iran", "Iran", "iran.liveuamap.com"),
]

# Publisher base is provenance, never the incident country. Explicitly dated feed excerpts only.
FEEDS = [
    ("long_war_journal", "Long War Journal", "https://www.longwarjournal.org/feed", "military", "US", False),
    (
        "defense_news",
        "Defense News",
        "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
        "military",
        "US",
        False,
    ),
    ("naval_news", "Naval News", "https://www.navalnews.com/feed/", "military", "FR", False),
    ("war_zone", "The War Zone", "https://www.twz.com/feed", "military", "US", False),
    ("defenceweb", "DefenceWeb · Africa", "https://www.defenceweb.co.za/feed/", "military", "ZA", True),
    ("irrawaddy", "The Irrawaddy · Myanmar", "https://www.irrawaddy.com/feed", "geopolitical", None, True),
    ("times_israel", "Times of Israel", "https://www.timesofisrael.com/feed/", "geopolitical", "IL", True),
    (
        "anadolu",
        "Anadolu world",
        "https://www.aa.com.tr/en/rss/default?cat=world",
        "geopolitical",
        "TR",
        True,
    ),
    ("ukrinform", "Ukrinform", "https://www.ukrinform.net/rss/block-lastnews", "geopolitical", "UA", True),
    (
        "kyiv_independent",
        "Kyiv Independent",
        "https://kyivindependent.com/news-archive/rss/",
        "geopolitical",
        "UA",
        True,
    ),
    (
        "bellingcat",
        "Bellingcat investigations",
        "https://www.bellingcat.com/feed/",
        "geopolitical",
        "NL",
        True,
    ),
    ("sudans_post", "Sudans Post", "https://www.sudanspost.com/feed/", "geopolitical", None, True),
    ("khaama", "Khaama Press · Afghanistan", "https://www.khaama.com/feed/", "geopolitical", "AF", True),
    ("dawn", "Dawn · Pakistan", "https://www.dawn.com/feeds/home", "geopolitical", "PK", True),
    (
        "premium_times",
        "Premium Times · Nigeria",
        "https://www.premiumtimesng.com/feed",
        "geopolitical",
        "NG",
        True,
    ),
    (
        "agencia_brasil",
        "Agência Brasil",
        "https://agenciabrasil.ebc.com.br/en/rss/ultimasnoticias/feed.xml",
        "geopolitical",
        "BR",
        True,
    ),
    ("taipei_times", "Taipei Times", "https://www.taipeitimes.com/xml/index.rss", "geopolitical", "TW", True),
    ("middle_east_eye", "Middle East Eye", "https://www.middleeasteye.net/rss", "geopolitical", "GB", True),
]


def conflict_type(text):
    # A labour strike, weather warning or natural disaster is not combat evidence.
    if re.search(
        r"\b(?:earthquake|magnitude|wildfire|hurricane|tsunami|labour strike|labor strike|workers.*strike)\b",
        text,
        re.I,
    ):
        return None
    rule = next((rule for rule, pattern in RULES if pattern.search(text)), None)
    if (
        rule
        and rule["id"] in {"security", "conflict"}
        and re.search(
            r"\b(?:military|army|armed forces|troops|navy|naval|frontline|rebels?|insurgents?|warfare)\b",
            text,
            re.I,
        )
    ):
        return (
            next(item for item in TYPES if item["id"] == "clashes")
            if rule["id"] == "security"
            else {**rule, "military": True}
        )
    return rule


def public_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        return Report.safe_url(value.strip())
    except ValueError:
        return None


def parse_liveuamap(payload: bytes) -> list[dict]:
    """Read only serialized venues; never evaluate scripts or import static map landmarks."""
    if len(payload) > 2_097_152:
        raise ProviderError("Conflict page exceeded size limit")
    html = payload.decode("utf-8", errors="replace")
    for match in re.finditer(r"\b(?:var|let|const)\s+\w+\s*=\s*['\"]([A-Za-z0-9+/=]{200,})['\"]", html):
        encoded = match[1]
        if len(encoded) > 1_500_000:
            continue
        try:
            data = json.loads(base64.b64decode(encoded, validate=True))
        except (ValueError, UnicodeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("venues"), list):
            return [venue for venue in data["venues"][:1000] if isinstance(venue, dict)]
    raise ProviderError("Conflict page did not contain a public dated event list")


class Liveuamap(Connector):
    interval = 900
    limitation = "Liveuamap editorial event positions are approximate. Publication time is not occurrence time. Linked upstream reporting is not independent corroboration."

    def __init__(self, settings, region, label, host, category):
        super().__init__(settings)
        self.source_id = f"conflict_liveuamap_{region}_{category}"
        self.name = f"Liveuamap · {label} · {'conflict' if category == 'military' else 'politics'}"
        self.category, self.homepage = category, f"https://{host}/"
        self.coverage = label

    async def fetch(self, http):
        # Two layer selectors share one page request and the same evidence, not duplicated incidents.
        cache = getattr(http, "conflict_page_cache", None)
        if cache is None:
            cache = http.conflict_page_cache = {}

        async def read():
            await robots(http, self.homepage)
            return parse_liveuamap(await http.request("GET", self.homepage, attempts=1, max_bytes=2_097_152))

        if self.homepage not in cache:
            cache[self.homepage] = asyncio.create_task(read())
        return await asyncio.shield(cache[self.homepage])

    def select_records(self, records):
        selected = []
        for record in records:
            rule = conflict_type(clean(record.get("name", ""), 1000))
            if rule:
                category = "military" if rule["military"] else "geopolitical"
                if category == self.category:
                    selected.append(record)
        return super().select_records(
            sorted(selected, key=lambda r: str(r.get("timestamp", "")), reverse=True)
        )

    def normalize(self, record):
        title = clean(record["name"], 500)
        rule = conflict_type(title)
        if not rule or ("military" if rule["military"] else "geopolitical") != self.category:
            raise ValueError("Not selected conflict evidence")
        published = datetime.fromtimestamp(float(record["timestamp"]), timezone.utc)
        if published > utcnow() + timedelta(hours=1) or published < utcnow() - timedelta(days=180):
            raise ValueError("Conflict publication time is outside retention")
        lat, lng = float(record["lat"]), float(record["lng"])
        if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError("Invalid approximate event coordinates")
        link = public_url(record.get("link"))
        host = urlsplit(link).hostname if link else ""
        if (
            not link
            or not (host == "liveuamap.com" or host.endswith(".liveuamap.com"))
            or not re.search(r"/en/\d{4}/", urlsplit(link).path)
        ):
            raise ValueError("Missing same-region event permalink")
        upstream = []
        values = [record.get("source", "")]
        if isinstance(record.get("moreSources"), list):
            values += record["moreSources"][:5]
        for value in values:
            url = public_url(value)
            if url and url not in upstream:
                upstream.append(url)
        place = clean(record.get("location", ""), 250)
        return Report(
            external_id=str(record["id"]),
            source_id=self.source_id,
            source_url=link,
            title=title,
            description=title,
            category=self.category,
            published_at=published,
            latitude=lat,
            longitude=lng,
            location_precision="approximate",
            country_code=country_at(lng, lat),
            location_basis=f"Liveuamap approximate event location: {place or self.coverage}. Map point is not a precise unit position.",
            evidence_basis="One Liveuamap editorial report, with original source links where supplied; not independently verified.",
            tags=["liveuamap", f"conflict:{rule['id']}", self.coverage],
            language="en",
            sentiment_kind="news",
            news=NewsMetadata(
                mentioned_countries=mentioned_countries(title + " " + place),
                upstream_sources=upstream[:5],
                reporting_location=place,
                event_type=rule["id"],
            ),
            raw={
                "id": record["id"],
                "title": title,
                "timestamp": record["timestamp"],
                "location": place,
                "link": link,
                "upstream_sources": upstream[:5],
                "lat": lat,
                "lng": lng,
            },
        )

    def metadata(self):
        return {
            **super().metadata(),
            "delivery": "Public HTML · serialized editorial events",
            "geographic_coverage": self.coverage,
            "usage_notes": "Attribution to Liveuamap required; upstream sources retain their own terms",
            "selection": "Explicit conflict/politics wording; natural disasters excluded; static landmarks excluded",
        }


class ConflictRSS(RSS):
    def select_records(self, records):
        if self.topical:
            records = [
                record
                for record in records
                if conflict_type(
                    clean(
                        record.get("title", "")
                        + " "
                        + (record.get("description") or record.get("summary") or ""),
                        2000,
                    )
                )
            ]
        return Connector.select_records(self, records)

    async def fetch(self, http):
        # Publisher-offered public feeds; bounded redirects still use the HTTP allowlist.
        from ..feeds import parse_feed

        payload = await http.request("GET", self.url, redirects=3, attempts=1)
        try:
            records = parse_feed(payload)
        except ParseError:
            # This publisher appends analytics HTML after a complete XML document.
            # Retain strict, entity-safe XML parsing; never execute the trailing content.
            end = payload.rfind(b"</rss>")
            if self.source_id != "conflict_feed_irrawaddy" or end < 0:
                raise
            records = parse_feed(payload[: end + 6])
        if not records:
            raise ProviderError("Publisher feed contained no dated records")
        return records

    def normalize(self, record):
        report = super().normalize(record)
        if report.published_at > utcnow() + timedelta(hours=1) or report.published_at < utcnow() - timedelta(
            days=180
        ):
            raise ValueError("Publisher date outside retention")
        text = report.title + " " + report.description
        rule = conflict_type(report.title) or conflict_type(text)
        if rule and rule["id"] in {"security", "conflict"}:
            rule = conflict_type(text) or rule
        if rule:
            report.tags.append(f"conflict:{rule['id']}")
            report.news.event_type = rule["id"]
            if self.category == "geopolitical" and rule["military"]:
                report.category = Category.military
        report.description = clean(report.description, 600)
        if not report.country_code:
            country = unique_country_context(text)
            if country:
                report.country_code = country["code"]
                report.longitude, report.latitude = country["center"]
                report.location_precision = "regional"
                report.location_basis = "One country explicitly named in feed headline/excerpt; country context, not an incident location"
        return report

    def metadata(self):
        return {
            **super().metadata(),
            "categories": ["geopolitical", "military"] if self.category == "geopolitical" else ["military"],
            "selection": "Military wording routes to Military OSINT; diplomacy and governance routes to Geopolitics",
        }


def conflict_sources(settings):
    from .conflict_assessments import ISW

    pages = [
        Liveuamap(settings, region, label, host, category)
        for region, label, host in REGIONS
        for category in ("military", "geopolitical")
    ]
    feeds = [
        ConflictRSS(
            settings,
            source_id="conflict_feed_" + sid,
            name=name,
            url=url,
            category=category,
            publisher_country=country,
            topical=topical,
        )
        for sid, name, url, category, country, topical in FEEDS
    ]
    return pages + feeds + [ISW(settings)]
