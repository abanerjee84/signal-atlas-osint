"""Explicit public browser captures; never reads cookies or controls a browser."""

from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import Report, SocialRelation, stamp, utcnow
from .social import SocialFeed


class BrowserRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    post_id: str = Field(pattern=r"^t[13]_[a-z0-9]+$")
    title: str = Field(min_length=1, max_length=500)
    text: str = Field(default="", max_length=5000)
    url: str = Field(max_length=2048)
    published_at: str = Field(max_length=80)
    author: str = Field(default="", max_length=200)
    community: str = Field(pattern=r"^[A-Za-z0-9_]{2,40}$")
    content_type: str = Field(pattern="^(post|comment)$")
    thread_title: str = Field(default="", max_length=500)
    parent_id: str | None = Field(default=None, pattern=r"^t[13]_[a-z0-9]+$")

    @model_validator(mode="after")
    def public_reference(self):
        Report.safe_url(self.url)
        url = urlsplit(self.url)
        if (
            url.scheme != "https"
            or url.hostname not in {"reddit.com", "www.reddit.com"}
            or url.port
            or url.query
        ):
            raise ValueError("Only original public Reddit HTTPS references are accepted")
        if not url.path.startswith(f"/r/{self.community}/comments/"):
            raise ValueError("URL must match the declared public community")
        if (self.content_type == "comment") != self.post_id.startswith("t1_"):
            raise ValueError("Post identity and content type disagree")
        parts = url.path.rstrip("/").split("/")
        if len(parts) < 5:
            raise ValueError("Public thread ID is missing")
        date = datetime.fromisoformat(self.published_at.replace("Z", "+00:00"))
        if not date.tzinfo:
            raise ValueError("Original publication timestamp needs a timezone")
        if self.content_type == "post" and parts[4] != self.post_id[3:]:
            raise ValueError("Post URL and identity disagree")
        if self.content_type == "comment" and parts[-1] != self.post_id[3:]:
            raise ValueError("Comment URL and identity disagree")
        return self


class BrowserCapture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    records: list[BrowserRecord] = Field(min_length=1, max_length=100)


class RedditBrowser(SocialFeed):
    manual = True
    interval = 86400
    limitation = "Explicit public browser capture, not unattended collection. Capture records expire locally after 24h, are excluded from backups and do not provide author origins. The signed-in browser is used only by the person/assistant capturing the visible public thread; server never reads cookies."

    def __init__(self, settings):
        super().__init__(
            settings,
            source_id="reddit_browser",
            name="Reddit public browser captures",
            url="https://www.reddit.com/",
            content_type="comment",
        )

    def normalize_capture(self, record):
        if record.community.lower() not in {value.lower() for value in self.settings.reddit_subreddits}:
            raise ValueError("Community is outside configured public capture scope")
        source = SocialFeed(
            self.settings,
            source_id=self.source_id,
            name=self.name,
            url=self.url,
            content_type=record.content_type,
        )
        report = source.normalize(
            {
                "id": record.post_id,
                "title": f"{record.author} on {record.thread_title}"
                if record.content_type == "comment"
                else record.title,
                "content": record.text,
                "link": record.url,
                "published": record.published_at,
                "author": record.author,
                "community": record.community,
            }
        )
        report.title = record.title
        report.raw = {"delivery": "Explicit public browser capture", "captured_at": stamp()}
        report.tags = ["reddit", "browser-capture", record.content_type]
        if record.parent_id and record.parent_id.startswith("t1_"):
            thread = report.social.relations[0].target_url
            report.social.relations.append(
                SocialRelation(
                    kind="reply",
                    target_id=record.parent_id,
                    target_url=thread + "comment/" + record.parent_id[3:] + "/",
                )
            )
        if report.published_at > utcnow():
            raise ValueError("Public post timestamp is in the future")
        return report

    def metadata(self):
        return {
            **super().metadata(),
            "manual": True,
            "delivery": "Visible public browser capture; free, no API key",
            "limitation": self.limitation,
        }
