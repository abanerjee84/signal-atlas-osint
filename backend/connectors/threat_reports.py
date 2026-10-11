from ..geo import countries
from ..threat_activity import INCIDENT, extract_threat
from .base import clean
from .rss import RSS

THREAT_FEEDS = [
    ("cisco_talos", "Cisco Talos research", "https://blog.talosintelligence.com/rss/", "US"),
    ("bleepingcomputer", "BleepingComputer", "https://www.bleepingcomputer.com/feed/", "US"),
    ("securityweek", "SecurityWeek", "https://www.securityweek.com/feed/", "US"),
    ("hacker_news", "The Hacker News", "https://feeds.feedburner.com/TheHackersNews", None),
    ("record_media", "The Record", "https://therecord.media/feed", "US"),
    ("cybersecurity_dive", "Cybersecurity Dive", "https://www.cybersecuritydive.com/feeds/news/", "US"),
    ("eset_research", "ESET WeLiveSecurity", "https://www.welivesecurity.com/en/rss/feed/", "SK"),
    (
        "microsoft_security",
        "Microsoft Security research",
        "https://www.microsoft.com/en-us/security/blog/feed/",
        "US",
    ),
    # Added because these publish the whole article inside their own feed via
    # content:encoded, so actor and technique wording is actually present.
    # Measured mean encoded length in brackets: watchTowr 33k, Check Point
    # 33k, SentinelOne 18k, Krebs 17k, CyberScoop 6k, SANS ISC 3k.
    ("watchtowr", "watchTowr Labs research", "https://labs.watchtowr.com/rss/", "SG"),
    (
        "checkpoint_research",
        "Check Point Research",
        "https://research.checkpoint.com/feed/",
        "IL",
    ),
    (
        "sentinelone_labs",
        "SentinelOne Labs",
        "https://www.sentinelone.com/labs/feed/",
        "US",
    ),
    ("krebs", "Krebs on Security", "https://krebsonsecurity.com/feed/", "US"),
    ("cyberscoop", "CyberScoop", "https://cyberscoop.com/feed/", "US"),
    ("sans_isc", "SANS Internet Storm Center", "https://isc.sans.edu/rssfeed_full.xml", "US"),
    # These three put the full article in <description> rather than
    # content:encoded, so the existing excerpt path already carries the whole
    # body. Measured mean description: CISA 29k, Rapid7 14k, CSO 7k. CISA
    # returns 403 to a browser user agent and only answers the collector's own.
    ("cisa_advisories", "CISA advisories", "https://www.cisa.gov/cybersecurity-advisories/all.xml", "US"),
    ("rapid7_research", "Rapid7 research", "https://www.rapid7.com/rss.xml", "US"),
    ("cso_online", "CSO Online", "https://www.csoonline.com/feed/", "US"),
]


class ThreatFeed(RSS):
    interval = 900
    limitation = "Recent published attack and campaign reports, not live packet telemetry. Publisher feed text only; no article page is retrieved. Country attribution and targets are deterministic role extraction from that text, unverified and incomplete. No origin is inferred from actor aliases, IPs or publisher countries."

    def __init__(self, settings, identifier, name, url, country):
        super().__init__(
            settings,
            source_id="threat_" + identifier,
            name=name + " attack reports",
            url=url,
            category="threat",
            publisher_country=country,
            usage_notes="Linked headline and bounded feed text; publisher terms apply",
            # Where a publisher ships the whole article inside its own feed,
            # that text is used for actor and malware matching. Nothing is
            # fetched from the article page itself.
            # Bounded by the Report model's 10,000 character description
            # limit; anything longer fails validation and the record is lost.
            text_limit=9000,
        )

    def select_records(self, records):
        return super().select_records(
            [
                r
                for r in records
                if INCIDENT.search(clean(r.get("title", "") + " " + r.get("description", "")))
            ]
        )

    def normalize(self, record):
        report = super().normalize(record)
        threat = extract_threat(record.get("analysis_text") or report.title + ". " + report.description)
        if not threat:
            raise ValueError("No attack/campaign wording")
        report.threat = threat
        places = {f["properties"]["code"]: f["properties"] for f in countries()["features"]}
        victim = places.get(threat.victim_countries[0]) if len(threat.victim_countries) == 1 else None
        report.country_code = victim["code"] if victim else None
        report.longitude, report.latitude = victim["center"] if victim else (None, None)
        report.location_precision = "regional" if victim else "unknown"
        report.location_basis = (
            "Country explicitly named as a target in source excerpt; country center, not an incident coordinate"
            if victim
            else "No unique reported victim country; no incident point inferred"
        )
        # Tags also support older running APIs without requiring a service restart.
        report.tags += ["threat-report", "actor:" + threat.actor, "attack-kind:" + threat.attack_kind]
        report.tags += ["attack-vector:" + value for value in threat.attack_vectors]
        report.tags.append("vector-status:" + ("known" if threat.attack_vectors else "unspecified"))
        if threat.vector_evidence:
            report.tags.append("vector-evidence:" + threat.vector_evidence)
        report.tags += ["cve:" + value for value in threat.cves]
        if threat.attacker_country:
            report.tags.append("attributed-country:" + threat.attacker_country)
        report.tags += ["victim-country:" + code for code in threat.victim_countries]
        report.evidence_basis = (
            "Published cyber reporting; automated role extraction is unverified. " + threat.attribution_basis
        )
        return report


def threat_feeds(settings):
    from .threat_research import research_scrapers

    return [ThreatFeed(settings, *definition) for definition in THREAT_FEEDS] + research_scrapers(settings)
