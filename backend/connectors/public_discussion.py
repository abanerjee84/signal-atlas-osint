"""Keyless public RSS and Telegram's public HTML preview, without cookies or hidden endpoints."""

import re
from html.parser import HTMLParser
from urllib.robotparser import RobotFileParser

from .base import ProviderError, clean
from .social import SocialFeed

DISCUSSION_FEEDS = [
    (
        "mastodon_geopolitics",
        "Mastodon #geopolitics",
        "https://mastodon.social/tags/geopolitics.rss",
        "mastodon",
    ),
    ("mastodon_ukraine", "Mastodon #ukraine", "https://mastodon.social/tags/ukraine.rss", "mastodon"),
    (
        "mastodon_cybersecurity",
        "Mastodon #cybersecurity",
        "https://mastodon.social/tags/cybersecurity.rss",
        "mastodon",
    ),
    ("lemmy_world", "Lemmy World c/world", "https://lemmy.world/feeds/c/world.xml?sort=New", "lemmy"),
    (
        "lemmy_technology",
        "Lemmy World c/technology",
        "https://lemmy.world/feeds/c/technology.xml?sort=New",
        "lemmy",
    ),
]


class TelegramPreview(HTMLParser):
    """Read only timestamped, visible message text. Ignore media, scripts and profile metadata."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.records, self.record, self.frames = [], None, []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if tag == "div" and "tgme_widget_message" in classes:
            identity = attrs.get("data-post", "")
            self.record = {
                "id": identity,
                "link": "https://t.me/" + identity,
                "author": identity.split("/")[0],
                "text": [],
            }
        if tag not in {"br", "img", "input", "meta", "link", "hr", "source", "wbr"}:
            self.frames.append((tag, "tgme_widget_message_text" in classes, "tgme_widget_message" in classes))
        if self.record and tag == "time":
            self.record["published"] = attrs.get("datetime")

    def handle_endtag(self, tag):
        if not self.frames:
            return
        # Public page markup has nested text wrappers; unwind only the matching element.
        found = next((i for i in range(len(self.frames) - 1, -1, -1) if self.frames[i][0] == tag), None)
        if found is None:
            return
        closed = self.frames[found:]
        del self.frames[found:]
        if self.record and any(frame[2] for frame in closed):
            text = clean(" ".join(self.record.pop("text")), 5000)
            if (
                text
                and self.record.get("published")
                and re.fullmatch(r"[A-Za-z0-9_]{5,40}/\d+", self.record["id"])
            ):
                self.records.append({**self.record, "content": text, "title": text[:150]})
            self.record = None

    def handle_data(self, data):
        if (
            self.record
            and any(frame[1] for frame in self.frames)
            and not any(frame[0] in {"script", "style"} for frame in self.frames)
        ):
            self.record["text"].append(data)


class TelegramPublic(SocialFeed):
    interval = 900
    limitation = "Public Telegram channel HTML previews, no login/cookies/private groups. Channel publications are a selected discourse sample, not representative opinion. No author origin inferred. Visible timestamped text only; local snapshots expire after 24 hours."

    def __init__(self, settings, channel):
        if not re.fullmatch(r"[A-Za-z0-9_]{5,40}", channel):
            raise ValueError("Invalid public Telegram channel")
        super().__init__(
            settings,
            source_id="telegram_" + channel.lower(),
            name="Telegram public @" + channel,
            url="https://t.me/s/" + channel,
            platform="telegram",
        )

    async def fetch(self, http):
        try:
            robots = await http.request("GET", "https://t.me/robots.txt", attempts=1)
        except ProviderError as error:
            # A missing robots file permits public-page access. Denials, rate limits
            # and network errors must still stop collection.
            if error.status_code != 404:
                raise
        else:
            policy = RobotFileParser()
            policy.parse(robots.decode("utf-8", errors="replace").splitlines())
            if not policy.can_fetch("SignalAtlas", self.url):
                raise ProviderError("Public channel preview disallowed by robots policy")
        payload = await http.request("GET", self.url, attempts=1)
        parser = TelegramPreview()
        parser.feed(payload.decode("utf-8", errors="replace"))
        if not parser.records:
            raise ProviderError(
                "No public timestamped channel posts; private/login-only pages are not collected"
            )
        return parser.records[-40:]

    def metadata(self):
        return {
            **super().metadata(),
            "delivery": "Public channel HTML; robots checked, no API or authentication",
        }


def discussion_feeds(settings):
    providers = [
        SocialFeed(settings, source_id=sid, name=name, url=url, platform=platform)
        for sid, name, url, platform in DISCUSSION_FEEDS
    ]
    for provider in providers:
        provider.interval = 900
    providers += [TelegramPublic(settings, channel) for channel in settings.telegram_channels[:8]]
    return providers
