"""Public, keyless feeds. No login cookies, paid APIs or scraping fallback."""

import re
from urllib.parse import urlsplit

from ..feeds import parse_feed
from ..geo import mentioned_countries, named_country
from ..models import NewsMetadata, Report, SocialMetadata, SocialRelation
from ..sentiment import detect_language
from .base import Connector, ProviderError, clean, parse_time


class SocialFeed(Connector):
    interval = 1800
    snapshot = True
    limitation = "Public feed snapshot only. Origins are unavailable unless explicitly supplied; countries mentioned are discussion context. English VADER wording scores are not representative public opinion. Prior snapshot is replaced after each successful refresh; records expire after 24 hours."

    def __init__(
        self,
        settings,
        *,
        source_id,
        name,
        url,
        platform="reddit",
        content_type="post",
        publisher_country=None,
    ):
        super().__init__(settings)
        if platform not in {"reddit", "youtube", "x"} or content_type not in {"post", "comment", "video"}:
            raise ValueError("Invalid social feed definition")
        self.source_id, self.name, self.url, self.platform = source_id, name, url, platform
        self.homepage, self.content_type, self.publisher_country = url, content_type, publisher_country
        self.category = "geopolitical" if content_type == "video" else "sentiment"
        # Video upload wording belongs to media coverage, not viewer discourse.
        self.snapshot = content_type != "video"

    async def fetch(self, http):
        records = parse_feed(await http.request("GET", self.url))
        if not records:
            raise ProviderError("Feed returned no RSS/Atom entries; availability may have changed")
        return records

    def normalize(self, record):
        title = clean(record["title"], 500)
        content = clean(
            record.get("content") or record.get("summary") or record.get("description") or "", 5000
        )
        date = record.get("published") or record.get("pubDate") or record.get("updated")
        relations, context = [], []
        if self.platform == "reddit" and self.content_type == "comment":
            # Reddit's comment title contains the thread title, not the comment's wording.
            context = mentioned_countries(title.split(" on ", 1)[-1])
            text = content
            parts = urlsplit(record["link"]).path.strip("/").split("/")
            if "comments" in parts:
                index = parts.index("comments")
                if len(parts) > index + 2 and re.fullmatch(r"[a-zA-Z0-9]+", parts[index + 1]):
                    target = "t3_" + parts[index + 1]
                    parent_url = "https://www.reddit.com/" + "/".join(parts[: index + 2]) + "/"
                    relations.append(
                        SocialRelation(kind="comment_on", target_id=target, target_url=parent_url)
                    )
        elif self.platform == "reddit":
            # Feed markup appends submission/user/link boilerplate. Score title plus any selftext only.
            selftext = (record.get("content") or "").split("submitted by", 1)[0]
            selftext = clean(selftext, 5000)
            text = title + (" " + selftext if selftext and selftext != title else "")
        else:
            text = title + (" " + content if content else "")
        if not text.strip():
            raise ValueError("Feed entry has no usable text")
        social = SocialMetadata(
            platform=self.platform,
            post_id=record.get("id") or record.get("guid") or record["link"],
            author=clean(record.get("author", ""), 200),
            community=clean(record.get("community", ""), 200),
            content_type=self.content_type,
            mentioned_countries=mentioned_countries(text),
            context_countries=context,
            relations=relations,
            origin_basis="Public feed supplies no post-origin location. Author, subreddit and publisher country are not a poster's origin.",
        )
        media = self.content_type == "video"
        country = named_country(title) if media else None
        return Report(
            external_id=social.post_id,
            source_id=self.source_id,
            source_url=record["link"],
            title=title,
            description=text,
            category=self.category,
            published_at=parse_time(date),
            language=detect_language(text),
            sentiment_kind="news" if media else "public",
            social=social,
            country_code=country["code"] if country else None,
            longitude=country["center"][0] if country else None,
            latitude=country["center"][1] if country else None,
            location_precision="regional" if country else "unknown",
            location_basis="Country named in upload title; discussion context only"
            if country
            else "Post origin is unknown",
            news=NewsMetadata(
                publisher_country=self.publisher_country, mentioned_countries=social.mentioned_countries
            )
            if media
            else None,
            tags=["public-feed", self.platform, self.content_type],
            raw={
                "id": social.post_id,
                "title": title,
                "text": text,
                "url": record["link"],
                "published": date,
            },
        )

    def metadata(self):
        return {
            **super().metadata(),
            "platform": self.platform,
            "content_type": self.content_type,
            "delivery": "Public RSS/Atom; no API key",
            "publisher_country": self.publisher_country,
            "limitation": self.limitation
            + (
                " YouTube feeds contain uploads, not viewer comments."
                if self.platform == "youtube"
                else " Reddit has announced RSS retirement on 13 November 2026."
                if self.platform == "reddit"
                else ""
            ),
        }
