"""Opt-in webpage monitoring with pinned public DNS, robots and no redirects."""

import asyncio
import difflib
import hashlib
import ipaddress
import socket
import ssl
from datetime import timedelta
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from ..models import stamp, utcnow
from .repository import identifier, packed


def validate_url(url, allowed_hosts):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in allowed_hosts
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
        or parsed.fragment
    ):
        raise ValueError(
            "Monitor requires an explicitly allowed HTTPS hostname, port 443 and no credentials or fragment"
        )
    try:
        if not ipaddress.ip_address(parsed.hostname).is_global:
            raise ValueError("Non-public destination blocked")
    except ValueError as error:
        if "blocked" in str(error):
            raise
    return parsed


async def pinned_get(url, allowed_hosts, headers=None):
    parsed = validate_url(url, allowed_hosts)
    addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, 443, type=socket.SOCK_STREAM)
    ips = {item[4][0] for item in addresses}
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError("DNS resolves to a non-public destination")
    ip = sorted(ips)[0]
    host = f"[{ip}]" if ":" in ip else ip
    pinned = urlunsplit(("https", host, parsed.path, parsed.query, ""))
    # Connect to the validated IP; preserve the original hostname for TLS verification and HTTP.
    async with httpx.AsyncClient(
        verify=ssl.create_default_context(),
        timeout=20,
        trust_env=False,
        limits=httpx.Limits(max_connections=1),
    ) as client:
        async with client.stream(
            "GET",
            pinned,
            headers={"Host": parsed.hostname, "User-Agent": "GlobalOSINT-Watch/1.0", **(headers or {})},
            extensions={"sni_hostname": parsed.hostname},
            follow_redirects=False,
        ) as response:
            if response.status_code not in {200, 304, 404}:
                raise ValueError(f"Monitor HTTP {response.status_code}; redirects are not followed")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > 2_097_152:
                    raise ValueError("Monitor response exceeds 2 MB")
                body.extend(chunk)
            return response.status_code, dict(response.headers), bytes(body)


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skipped = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skipped += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.skipped = max(0, self.skipped - 1)

    def handle_data(self, data):
        if not self.skipped:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)


def normalized_text(body, content_type):
    if "html" in content_type:
        parser = TextParser()
        parser.feed(body.decode("utf-8", errors="replace"))
        return "\n".join(parser.parts)[:100000]
    if content_type.startswith("text/plain"):
        return "\n".join(
            " ".join(line.split())
            for line in body.decode("utf-8", errors="replace").splitlines()
            if line.strip()
        )[:100000]
    raise ValueError("Monitoring supports HTML and plain text only")


def save_snapshot(repo, watch, text, headers):
    digest = hashlib.sha256(text.encode()).hexdigest()
    with repo.database.connect() as db:
        previous = db.execute(
            "SELECT s.* FROM source_changes c JOIN webpage_snapshots s ON s.id=c.current_id WHERE c.watch_id=? ORDER BY c.created_at DESC,c.rowid DESC LIMIT 1",
            (watch["id"],),
        ).fetchone()
        sid = identifier()
        if not previous or previous["hash"] != digest:
            # Same text can reappear later; retain the historical change without violating hash uniqueness.
            existing = db.execute(
                "SELECT id FROM webpage_snapshots WHERE watch_id=? AND hash=?", (watch["id"], digest)
            ).fetchone()
            if existing:
                sid = existing[0]
            else:
                db.execute(
                    "INSERT INTO webpage_snapshots VALUES(?,?,?,?,?)",
                    (sid, watch["id"], digest, text, stamp()),
                )
            diff = "\n".join(
                list(
                    difflib.unified_diff(
                        (previous["text"] if previous else "").splitlines(),
                        text.splitlines(),
                        fromfile="previous",
                        tofile="current",
                    )
                )[:400]
            )
            change_id = identifier()
            db.execute(
                "INSERT INTO source_changes VALUES(?,?,?,?,?,?)",
                (change_id, watch["id"], previous["id"] if previous else None, sid, diff, stamp()),
            )
            # Changes are emitted through the shared evidence interface, with no invented publication date.
            values = (
                change_id,
                None,
                "watch_" + watch["id"],
                change_id,
                watch["url"],
                watch["title"] + " — source changed",
                diff[:10000],
                "und",
                "official",
                "analysis",
                None,
                stamp(),
                stamp(),
                stamp(),
                stamp(),
                digest,
                None,
                None,
                None,
                "unknown",
                "Unverified",
                packed(
                    {
                        "change_id": change_id,
                        "verification_status": "normalized text change",
                        "permission_basis": watch["permission_basis"],
                    }
                ),
                "authorized",
                None,
            )
            db.execute("INSERT INTO external_records VALUES(" + ",".join("?" for _ in values) + ")", values)
        db.execute(
            "UPDATE watch_sources SET etag=?,last_modified=?,last_success=?,next_run=?,failures=0,error=NULL WHERE id=?",
            (
                headers.get("etag"),
                headers.get("last-modified"),
                stamp(),
                stamp(utcnow() + timedelta(seconds=watch["interval_seconds"])),
                watch["id"],
            ),
        )
        # Retain last 20 snapshots and their associated changes; saved cases have immutable copies.
        old = [
            r[0]
            for r in db.execute(
                "SELECT s.id FROM webpage_snapshots s WHERE s.watch_id=? ORDER BY (SELECT MAX(c.created_at) FROM source_changes c WHERE c.current_id=s.id) DESC,s.rowid DESC LIMIT -1 OFFSET 20",
                (watch["id"],),
            )
        ]
        for oid in old:
            db.execute("DELETE FROM source_changes WHERE current_id=? OR previous_id=?", (oid, oid))
            db.execute("DELETE FROM webpage_snapshots WHERE id=?", (oid,))
    return {"hash": digest, "changed": not previous or previous["hash"] != digest}


async def poll(repo, settings, watch):
    try:
        parsed = validate_url(watch["url"], settings.watch_allowed_hosts)
        robots_url = urlunsplit(("https", parsed.hostname, "/robots.txt", "", ""))
        status, _, body = await pinned_get(robots_url, settings.watch_allowed_hosts)
        robots = RobotFileParser()
        robots.parse(body.decode("utf-8", errors="replace").splitlines() if status == 200 else [])
        if not robots.can_fetch("GlobalOSINT-Watch", watch["url"]):
            raise ValueError("Robots policy disallows this monitor")
        delay = robots.crawl_delay("GlobalOSINT-Watch") or robots.crawl_delay("*") or 0
        if delay > watch["interval_seconds"]:
            raise ValueError("Polling interval is shorter than robots crawl delay")
        conditional = {}
        if watch["etag"]:
            conditional["If-None-Match"] = watch["etag"]
        if watch["last_modified"]:
            conditional["If-Modified-Since"] = watch["last_modified"]
        status, headers, body = await pinned_get(watch["url"], settings.watch_allowed_hosts, conditional)
        if status == 304:
            with repo.database.connect() as db:
                db.execute(
                    "UPDATE watch_sources SET last_success=?,next_run=?,failures=0,error=NULL WHERE id=?",
                    (stamp(), stamp(utcnow() + timedelta(seconds=watch["interval_seconds"])), watch["id"]),
                )
            return {"changed": False, "http_status": 304}
        if status != 200:
            raise ValueError("Monitored page is unavailable")
        return save_snapshot(repo, watch, normalized_text(body, headers.get("content-type", "")), headers)
    except Exception as error:
        message = str(error) if isinstance(error, ValueError) else "Monitor transport failed"
        failures = min(10, watch["failures"] + 1)
        with repo.database.connect() as db:
            db.execute(
                "UPDATE watch_sources SET error=?,failures=?,next_run=? WHERE id=?",
                (
                    message[:300],
                    failures,
                    stamp(utcnow() + timedelta(seconds=min(86400, watch["interval_seconds"] * 2**failures))),
                    watch["id"],
                ),
            )
        raise ValueError(message) from None
