import re

from ..models import Category
from .acled import ACLED
from .cisa import CISA
from .conflict_sources import conflict_sources
from .cyber_feeds import cyber_feeds
from .expanded import expanded_feeds
from .firms import FIRMS
from .gdelt import GDELT
from .maritime import Maritime
from .monitoring import monitoring_feeds
from .ncsc import NCSC
from .observatory import observation_feeds
from .ofac import OFAC
from .opensky import OpenSky
from .public_discussion import discussion_feeds
from .reddit_archive import RedditArchive
from .reddit_browser import RedditBrowser
from .reliefweb import ReliefWeb
from .rss import RSS
from .social import SocialFeed
from .threat_maps import threat_maps
from .threat_reports import threat_feeds
from .usgs import USGS
from .world_feeds import world_feeds


def connectors(settings):
    providers = [
        RedditBrowser(settings),
        USGS(settings),
        GDELT(settings),
        ACLED(settings),
        FIRMS(settings),
        ReliefWeb(settings),
        OpenSky(settings),
        Maritime(settings),
        CISA(settings),
        NCSC(settings),
        OFAC(settings),
        RSS(
            settings,
            source_id="bbc",
            name="BBC world headlines",
            category="geopolitical",
            url="https://feeds.bbci.co.uk/news/world/rss.xml",
            publisher_country="GB",
        ),
        RSS(
            settings,
            source_id="ecb",
            name="ECB releases and statements",
            category="economic",
            url="https://www.ecb.europa.eu/rss/press.html",
            kind="official",
        ),
        RSS(
            settings,
            source_id="uk_mod",
            name="UK Ministry of Defence announcements",
            category="military",
            url="https://www.gov.uk/government/organisations/ministry-of-defence.atom",
            kind="official",
            publisher_country="GB",
        ),
    ]
    providers.extend(cyber_feeds(settings))
    providers.extend(monitoring_feeds(settings))
    providers.extend(expanded_feeds(settings))
    providers.extend(observation_feeds(settings))
    providers.extend(threat_feeds(settings))
    providers.extend(threat_maps(settings))
    providers.extend(world_feeds(settings))
    providers.extend(conflict_sources(settings))
    providers.extend(discussion_feeds(settings))
    for identifier, name, url, country, kind in [
        (
            "bbc_business",
            "BBC business and global economy",
            "https://feeds.bbci.co.uk/news/business/rss.xml",
            "GB",
            "news",
        ),
        (
            "guardian_business",
            "Guardian business and economy",
            "https://www.theguardian.com/uk/business/rss",
            "GB",
            "news",
        ),
        (
            "guardian_energy",
            "Guardian energy industry",
            "https://www.theguardian.com/business/energy-industry/rss",
            "GB",
            "news",
        ),
        (
            "cna_business",
            "CNA international business",
            "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6936",
            "SG",
            "news",
        ),
        (
            "eia_energy",
            "US EIA Today in Energy",
            "https://www.eia.gov/rss/todayinenergy.xml",
            "US",
            "official",
        ),
    ]:
        providers.append(
            RSS(
                settings,
                source_id=identifier,
                name=name,
                category="economic",
                url=url,
                publisher_country=country,
                kind=kind,
            )
        )
    providers.append(
        RSS(
            settings,
            source_id="dvids",
            name="DVIDS military public reporting",
            category="military",
            url="https://www.dvidshub.net/rss/news",
            kind="official",
            publisher_country="US",
        )
    )
    for region in ["africa", "asia", "europe", "latin_america", "middle_east", "us_and_canada"]:
        providers.append(
            RSS(
                settings,
                source_id="bbc_" + region,
                name="BBC " + region.replace("_", " ") + " headlines",
                category="geopolitical",
                url=f"https://feeds.bbci.co.uk/news/world/{region}/rss.xml",
                publisher_country="GB",
            )
        )
    for identifier, name, url, country in [
        ("aljazeera", "Al Jazeera headlines", "https://www.aljazeera.com/xml/rss/all.xml", "QA"),
        ("dw", "DW international headlines", "https://rss.dw.com/rdf/rss-en-all", "DE"),
        ("guardian", "Guardian world headlines", "https://www.theguardian.com/world/rss", "GB"),
        ("france24", "France 24 English headlines", "https://www.france24.com/en/rss", "FR"),
    ]:
        providers.append(
            RSS(
                settings,
                source_id=identifier,
                name=name,
                category="geopolitical",
                url=url,
                publisher_country=country,
            )
        )
    # Public publisher feeds verified 2026-10-10; keep original links and published excerpts.
    for identifier, name, url, country, coverage in [
        (
            "un_news",
            "UN News — global diplomacy and humanitarian reporting",
            "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
            None,
            "Worldwide; UN reporting",
        ),
        (
            "africanews",
            "Africanews — Africa headlines",
            "https://www.africanews.com/feed/rss",
            None,
            "Africa",
        ),
        (
            "mercopress",
            "MercoPress — South Atlantic and Latin America",
            "https://en.mercopress.com/rss",
            None,
            "South Atlantic; Latin America",
        ),
        (
            "buenos_aires_herald",
            "Buenos Aires Herald — Argentina and regional affairs",
            "https://buenosairesherald.com/feed",
            "AR",
            "Argentina; Latin America",
        ),
        (
            "cna_world",
            "CNA — world headlines",
            "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6311",
            "SG",
            "Worldwide",
        ),
        (
            "cna_asia",
            "CNA — Asia headlines",
            "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6511",
            "SG",
            "Asia-Pacific",
        ),
        ("rfi", "RFI — international headlines", "https://www.rfi.fr/en/rss", "FR", "Worldwide; Africa"),
        (
            "abc_world",
            "ABC Australia — selected international and political headlines",
            "https://www.abc.net.au/news/feed/51120/rss.xml",
            "AU",
            "Worldwide; Asia-Pacific",
        ),
        (
            "euronews",
            "Euronews — international reporting",
            "https://www.euronews.com/rss?level=theme&name=news",
            None,
            "Europe; worldwide",
        ),
        (
            "guardian_africa",
            "Guardian — Africa headlines",
            "https://www.theguardian.com/world/africa/rss",
            "GB",
            "Africa",
        ),
        (
            "guardian_americas",
            "Guardian — Americas headlines",
            "https://www.theguardian.com/world/americas/rss",
            "GB",
            "Americas",
        ),
        (
            "guardian_asia",
            "Guardian — Asia headlines",
            "https://www.theguardian.com/world/asia/rss",
            "GB",
            "Asia-Pacific",
        ),
    ]:
        providers.append(
            RSS(
                settings,
                source_id=identifier,
                name=name,
                category="geopolitical",
                url=url,
                publisher_country=country,
                coverage=coverage,
                usage_notes="Personal, non-commercial feed use; Mediacorp terms apply"
                if identifier.startswith("cna_")
                else "Publisher terms; retain attribution and original links; no full-article scraping",
                kind="official" if identifier == "un_news" else "news",
                topical=identifier in {"abc_world", "euronews", "africanews", "buenos_aires_herald"},
            )
        )
    for community in settings.reddit_subreddits[:6]:
        if not re.fullmatch(r"[A-Za-z0-9_]{2,40}", community):
            raise ValueError("Invalid subreddit name")
        for content_type in ["post", "comment"]:
            providers.append(RedditArchive(settings, community=community, content_type=content_type))
        for content_type, path in [("post", "new"), ("comment", "comments")]:
            providers.append(
                SocialFeed(
                    settings,
                    source_id=f"reddit_{community.lower()}_{path}",
                    name=f"Reddit r/{community} {path}",
                    url=f"https://www.reddit.com/r/{community}/{path}/.rss?limit=100",
                    content_type=content_type,
                )
            )
    for channel in settings.youtube_channels[:24]:
        if not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", channel["id"]):
            raise ValueError("Invalid YouTube channel ID")
        providers.append(
            SocialFeed(
                settings,
                source_id="youtube_" + channel["id"],
                name=channel["name"] + " uploads",
                url="https://www.youtube.com/feeds/videos.xml?channel_id=" + channel["id"],
                platform="youtube",
                content_type="video",
                publisher_country=channel.get("country"),
                category=channel.get("category"),
            )
        )
    for definition in settings.social_feeds[:10]:
        if not re.fullmatch(r"[a-z0-9_-]{1,60}", definition["source_id"]):
            raise ValueError("Invalid social feed identifier")
        providers.append(SocialFeed(settings, **definition))
    for definition in settings.extra_rss[:20]:
        if not re.fullmatch(r"[a-z0-9_-]{1,60}", definition["source_id"]):
            raise ValueError("Invalid RSS source identifier")
        Category(definition["category"])
        if definition.get("kind", "news") not in {"news", "public", "official"}:
            raise ValueError("Invalid sentiment category")
        providers.append(RSS(settings, **definition))
    if len({provider.source_id for provider in providers}) != len(providers):
        raise ValueError("Duplicate source identifiers")
    return providers
