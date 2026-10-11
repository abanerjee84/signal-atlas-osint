"""Regional public feeds supplement worldwide reporting; availability is visible in status."""

from .rss import RSS

WORLD_FEEDS = [
    (
        "guardian_middle_east",
        "Guardian Middle East",
        "https://www.theguardian.com/world/middleeast/rss",
        "GB",
    ),
    ("guardian_europe", "Guardian Europe", "https://www.theguardian.com/world/europe-news/rss", "GB"),
    (
        "guardian_south_asia",
        "Guardian South Asia",
        "https://www.theguardian.com/world/south-and-central-asia/rss",
        "GB",
    ),
    ("guardian_australia", "Guardian Australia", "https://www.theguardian.com/australia-news/rss", "AU"),
    ("al_monitor", "Al-Monitor Middle East", "https://www.al-monitor.com/rss", "US"),
    ("crisis_group", "International Crisis Group analysis", "https://www.crisisgroup.org/rss.xml", "BE"),
    ("scmp_world", "SCMP world reporting", "https://www.scmp.com/rss/91/feed/", "HK"),
    ("npr_world", "NPR world", "https://feeds.npr.org/1004/rss.xml", "US"),
]


def world_feeds(settings):
    return [
        RSS(
            settings,
            source_id=sid,
            name=name,
            url=url,
            category="geopolitical",
            publisher_country=country,
            topical=sid == "guardian_australia",
        )
        for sid, name, url, country in WORLD_FEEDS
    ]
