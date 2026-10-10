"""Independent free archive search, bounded by community and time; no Reddit credentials."""

import re
from datetime import datetime, timedelta, timezone

from ..geo import mentioned_countries
from ..models import Report, SocialMetadata, SocialRelation, utcnow
from ..sentiment import detect_language
from .base import Connector, ProviderError, clean


class RedditArchive(Connector):
    interval = 3600
    snapshot = True
    category = "sentiment"
    homepage = "https://github.com/ArthurHeitmann/arctic_shift"
    limitation = "Independent Arctic Shift archive, not Reddit's live API. Availability and archive delay are unguaranteed. Up to 25 public posts/comments per community from the last 7 days; no author locations. Removed/deleted wording is excluded. Snapshots expire locally after 24h and are excluded from backups."

    def __init__(self, settings, *, community, content_type="post"):
        super().__init__(settings)
        if not re.fullmatch(r"[A-Za-z0-9_]{2,40}", community) or content_type not in {"post", "comment"}:
            raise ValueError("Invalid archive collection")
        self.community, self.content_type = community, content_type
        self.source_id = f"reddit_archive_{community.lower()}_{content_type}"
        self.name = f"Reddit archive r/{community} {content_type}s"

    async def fetch(self, http):
        payload = await http.json(
            "GET",
            f"https://arctic-shift.photon-reddit.com/api/{self.content_type}s/search",
            attempts=1,
            params={
                "subreddit": self.community,
                "limit": 25,
                "sort": "desc",
                "after": int((utcnow() - timedelta(days=7)).timestamp()),
            },
        )
        records = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            raise ProviderError("Archive response does not contain a record list")
        return [
            r
            for r in records
            if isinstance(r, dict)
            and r.get("author") != "[deleted]"
            and r.get("body", r.get("selftext", "")) not in {"[deleted]", "[removed]"}
            and not r.get("removed_by_category")
        ]

    def normalize(self, record):
        identifier = str(record["id"])
        if not re.fullmatch(r"[a-z0-9]+", identifier):
            raise ValueError("Invalid archive record ID")
        is_comment = self.content_type == "comment"
        title = clean(record.get("title") or f"Comment in r/{self.community}", 500)
        text = clean(record["body"] if is_comment else title + " " + record.get("selftext", ""), 5000)
        if not text:
            raise ValueError("No usable public text")
        thread = str(record.get("link_id", "")).removeprefix("t3_") if is_comment else identifier
        if not re.fullmatch(r"[a-z0-9]+", thread):
            raise ValueError("Invalid thread ID")
        thread_url = f"https://www.reddit.com/r/{self.community}/comments/{thread}/"
        source_url = thread_url + "_/" + identifier + "/" if is_comment else thread_url
        relations = []
        if is_comment:
            relations.append(
                SocialRelation(kind="comment_on", target_id="t3_" + thread, target_url=thread_url)
            )
            parent = str(record.get("parent_id", ""))
            if re.fullmatch(r"t1_[a-z0-9]+", parent):
                relations.append(
                    SocialRelation(
                        kind="reply", target_id=parent, target_url=thread_url + "_/" + parent[3:] + "/"
                    )
                )
        return Report(
            external_id=("t1_" if is_comment else "t3_") + identifier,
            source_id=self.source_id,
            source_url=source_url,
            title=title,
            description=text,
            category="sentiment",
            published_at=datetime.fromtimestamp(float(record["created_utc"]), timezone.utc),
            language=detect_language(text),
            sentiment_kind="public",
            social=SocialMetadata(
                platform="reddit",
                post_id=("t1_" if is_comment else "t3_") + identifier,
                author=clean(record.get("author", ""), 200),
                community=self.community,
                content_type=self.content_type,
                mentioned_countries=mentioned_countries(text),
                relations=relations,
            ),
            tags=["reddit", "archive", self.content_type],
            raw={"delivery": "Arctic Shift JSON archive", "retrieved_on": record.get("retrieved_on")},
        )

    def metadata(self):
        return {
            **super().metadata(),
            "platform": "reddit",
            "content_type": self.content_type,
            "delivery": "Arctic Shift public JSON archive; free, no key",
        }
