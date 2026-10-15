"""Bounded provider observations; no scans, IP geolocation or actor inference."""

import math
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from defusedxml import ElementTree

from ..indicators import observed_indicator, public_ip
from ..models import CyberObservation, Report, stamp, utcnow
from .base import Connector, ProviderError, clean, parse_time


def sans_headers(settings):
    return {"User-Agent": "SignalAtlas/0.1 " + (settings.sans_contact or "public-source-research")}


def provider_time(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Provider timestamp is missing")
    value = value.strip()
    if value.endswith(" UTC"):
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
    # Source-specific naive timestamps must be assigned a zone by the caller.
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Provider timestamp requires a timezone")
    return parsed.astimezone(timezone.utc)


def references(values):
    result = []
    for value in values:
        if not value:
            continue
        try:
            value = Report.safe_url(str(value))
            if len(value) <= 2048 and value not in result:
                result.append(value)
        except ValueError:
            pass
    return result[:10]


class IndicatorFeed(Connector):
    category = "infrastructure"
    observation_feed = True
    interval = 3600
    limitation = (
        "Provider-reported infrastructure observations, not confirmed compromises or actor attribution. "
        "Actor and target geography remain unknown. Repeated reports are not independent corroboration."
    )

    def metadata(self):
        return {
            **super().metadata(),
            "source_family": self.family,
            "delivery": "Provider API",
            "retention": f"{self.settings.cyber_observation_retention_days} days",
            "usage_terms": self.homepage,
            "license": self.license,
            "initial_enabled": self.initial_enabled,
        }

    def report(self, observation, title, description, source_url):
        return Report(
            external_id=observation.provider_record_id,
            source_id=self.source_id,
            source_url=source_url,
            category="infrastructure",
            title=title[:500],
            description=(description + " " + self.limitation)[:10000],
            published_at=observation.period_start or observation.first_seen or observation.received_at,
            occurred_at=observation.first_seen,
            language="en",
            cyber_observation=observation,
            tags=["cyber-observation", "provider:" + self.source_id, "source-family:" + self.family],
            evidence_basis="One provider assertion; not independently verified",
            raw={"observation": observation.model_dump(mode="json")},
        )


class DShield(IndicatorFeed):
    source_id = "dshield"
    name = "SANS DShield daily scan observations"
    homepage = "https://isc.sans.edu/api/"
    family = "sans_isc"
    license = "CC BY-NC-SA 4.0; no resale; SANS usage terms apply"
    interval = 3600

    @property
    def initial_enabled(self):
        return self.settings.dshield_enabled

    async def fetch(self, http):
        # An explicit UTC date avoids changing the meaning of a request across midnight.
        day = utcnow().date().isoformat()
        url = f"https://isc.sans.edu/api/topips/records/{self.settings.dshield_limit}/{day}"
        body = await http.request(
            "GET", url, attempts=1, max_bytes=1_048_576, headers=sans_headers(self.settings)
        )
        root = ElementTree.fromstring(body)
        if root.tag != "topips":
            raise ProviderError("SANS returned an invalid daily IP response")
        received = stamp()
        return [
            {
                **{child.tag: child.text for child in node},
                "day": day,
                "received_at": received,
                "source_url": url,
            }
            for node in root.findall("ipaddress")
        ]

    def normalize(self, row):
        ip = public_ip(str(row["source"]).strip())
        start = datetime.strptime(row["day"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        observation = CyberObservation(
            provider_record_id=f"{row['day']}:{ip}",
            source_family=self.family,
            kind="scan",
            indicator_type="ip",
            indicator_value=ip,
            native_type="daily_top_ip",
            period_start=start,
            period_end=start + timedelta(days=1),
            received_at=parse_time(row["received_at"]),
            report_count=int(row["reports"]),
            target_count=int(row["targets"]),
        )
        return self.report(
            observation,
            f"DShield: {ip} | daily scan reports",
            f"Reporting day {row['day']} UTC: {observation.report_count} provider reports, "
            f"{observation.target_count} target hosts. Daily aggregate, not individual attack events.",
            row["source_url"],
        )


class ISCHoneypots(IndicatorFeed):
    source_id = "isc_honeypots"
    name = "SANS ISC daily web honeypot observations"
    homepage = "https://isc.sans.edu/api/"
    family = "sans_isc"
    license = DShield.license

    @property
    def initial_enabled(self):
        return self.settings.isc_honeypots_enabled

    async def fetch(self, http):
        # Narrow, administrator-configurable UA scope; complete bounded payload or visible error.
        # Do not treat a truncated response as a complete daily aggregate.
        day = (utcnow().date() - timedelta(days=1)).isoformat()
        ua = quote(self.settings.isc_honeypots_user_agent, safe="")
        url = f"https://isc.sans.edu/api/webhoneypotreportsbyua/{ua}/{day}?json"
        rows = await http.json(
            "GET", url, attempts=1, max_bytes=2_097_152, headers=sans_headers(self.settings)
        )
        if not isinstance(rows, list) or len(rows) > 20000:
            raise ProviderError("SANS returned invalid or excessive honeypot records")
        groups = {}
        rejected = 0
        for row in rows:
            try:
                ip = public_ip(str(row["source"]).strip())
                if row["date"] != day:
                    raise ValueError("Unexpected reporting date")
                when = datetime.strptime(f"{day} {row['time']}", "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
                entry = groups.setdefault(
                    ip, {"source": ip, "day": day, "first": when, "last": when, "hits": 0, "paths": []}
                )
                entry["first"], entry["last"] = min(entry["first"], when), max(entry["last"], when)
                entry["hits"] += 1
                path = clean(row.get("url", ""), 150)
                if path and path not in entry["paths"] and len(entry["paths"]) < 3:
                    entry["paths"].append(path)
            except (ValueError, KeyError, TypeError):
                rejected += 1
        if rows and not groups:
            raise ProviderError("All SANS honeypot observations failed validation")
        received = stamp()
        return [
            {**entry, "received_at": received, "source_url": url, "rejected_rows": rejected}
            for entry in sorted(groups.values(), key=lambda item: (-item["hits"], item["source"]))
        ]

    def normalize(self, row):
        ip = public_ip(row["source"])
        start = datetime.strptime(row["day"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        observation = CyberObservation(
            provider_record_id=f"{row['day']}:{ip}",
            source_family=self.family,
            kind="web_probe",
            indicator_type="ip",
            indicator_value=ip,
            native_type="daily_honeypot_ip",
            first_seen=row["first"],
            last_seen=row["last"],
            period_start=start,
            period_end=start + timedelta(days=1),
            received_at=parse_time(row["received_at"]),
            request_count=row["hits"],
        )
        return self.report(
            observation,
            f"ISC honeypot: {ip} | web probes",
            f"{row['day']} UTC: {row['hits']} matching honeypot requests. "
            f"UA filter: {self.settings.isc_honeypots_user_agent}. "
            f"Sample paths: {', '.join(row['paths'])}. A probe does not establish intrusion.",
            row["source_url"],
        )


class ThreatFox(IndicatorFeed):
    source_id = "threatfox"
    name = "ThreatFox malware indicators"
    homepage = "https://threatfox.abuse.ch/"
    family = "abuse_ch"
    license = "abuse.ch community API fair-use terms; commercial access may differ"
    url = "https://threatfox-api.abuse.ch/api/v1/"

    @property
    def initial_enabled(self):
        return True  # Missing credentials remain visible as access_required.

    def access(self):
        return (
            None if self.settings.threatfox_auth_key else "Set OSINT_THREATFOX_AUTH_KEY for the ThreatFox API"
        )

    async def fetch(self, http):
        payload = await http.json(
            "POST",
            self.url,
            attempts=1,
            max_bytes=4_194_304,
            headers={"Auth-Key": self.settings.threatfox_auth_key},
            json={"query": "get_iocs", "days": 1},
        )
        if not isinstance(payload, dict):
            raise ProviderError("ThreatFox returned an invalid response")
        status = payload.get("query_status")
        if status == "no_result":
            return []
        if status != "ok" or not isinstance(payload.get("data"), list):
            raise ProviderError("ThreatFox API status or response schema failed validation")
        received = stamp()
        rows = payload["data"]
        supported = {"ip:port", "ip", "domain", "url", "md5_hash", "sha1_hash", "sha256_hash"}
        if rows and not any(isinstance(row, dict) and row.get("ioc_type") in supported for row in rows):
            raise ProviderError("ThreatFox returned no supported indicator types")
        # Selected records are validated by the worker and its rejected/truncated counters.
        return [{**row, "received_at": received} for row in rows if isinstance(row, dict)]

    def normalize(self, row):
        if not re.fullmatch(r"\d{1,30}", str(row["id"])):
            raise ValueError("Invalid ThreatFox IOC identifier")
        kind, value, port = observed_indicator(row["ioc_type"], row["ioc"])
        first = provider_time(row["first_seen"])
        last = provider_time(row["last_seen"]) if row.get("last_seen") else None
        malware = clean(row.get("malware_printable") or row.get("malware") or "", 200)
        observation = CyberObservation(
            provider_record_id=str(row["id"]),
            source_family=self.family,
            kind=clean(row["threat_type"], 80),
            indicator_type=kind,
            indicator_value=value,
            native_type=row["ioc_type"],
            port=port,
            first_seen=first,
            last_seen=last,
            received_at=parse_time(row["received_at"]),
            provider_confidence=row.get("confidence_level"),
            malware_id=clean(row.get("malware", ""), 200),
            malware_name=malware,
            references=references([row.get("reference"), row.get("malware_malpedia")]),
        )
        return self.report(
            observation,
            f"ThreatFox: {malware or 'malware indicator'} | {value}",
            f"Provider IOC #{row['id']}, type {row['ioc_type']}, threat type {observation.kind}. "
            f"Malware association: {malware or 'not supplied'}. "
            "Provider confidence is not local verification or actor responsibility.",
            f"https://threatfox.abuse.ch/ioc/{row['id']}/",
        )


class CloudflareRadar(Connector):
    source_id = "cloudflare_radar"
    name = "Cloudflare Radar global DDoS protocol mix"
    category = "infrastructure"
    homepage = "https://radar.cloudflare.com/security-and-attacks"
    interval = 3600
    initial_enabled = True
    ddos_aggregate = True
    url = "https://api.cloudflare.com/client/v4/radar/attacks/layer3/timeseries_groups/PROTOCOL"
    limitation = (
        "Global provider protocol percentages; not attack counts, actor attribution or country routes."
    )

    def access(self):
        return (
            None
            if self.settings.cloudflare_radar_token
            else "Set OSINT_CLOUDFLARE_RADAR_TOKEN for Radar read access"
        )

    async def fetch(self, http):
        payload = await http.json(
            "GET",
            self.url,
            attempts=1,
            max_bytes=1_048_576,
            headers={"Authorization": "Bearer " + self.settings.cloudflare_radar_token},
            params={"dateRange": "1d", "aggInterval": "1h", "normalization": "PERCENTAGE"},
        )
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise ProviderError("Cloudflare Radar API failed validation")
        result = payload.get("result", {})
        meta, series = result.get("meta", {}), result.get("serie_0", {})
        if meta.get("normalization") != "PERCENTAGE" or meta.get("aggInterval") != "ONE_HOUR":
            raise ProviderError("Cloudflare Radar returned unexpected units or interval")
        timestamps = series.get("timestamps")
        if not isinstance(timestamps, list) or len(timestamps) > 48:
            raise ProviderError("Cloudflare Radar returned invalid timestamps")
        protocols = {
            key.upper(): values
            for key, values in series.items()
            if key.lower() in {"tcp", "udp", "icmp", "gre"}
        }
        if not protocols or any(
            not isinstance(values, list) or len(values) != len(timestamps) for values in protocols.values()
        ):
            raise ProviderError("Cloudflare Radar protocol series is missing or misaligned")
        received = stamp()
        return [
            {
                "timestamp": timestamp,
                "protocols": {key: values[i] for key, values in protocols.items()},
                "received_at": received,
            }
            for i, timestamp in enumerate(timestamps)
        ]

    def normalize(self, row):
        start = provider_time(row["timestamp"])
        if start > parse_time(row["received_at"]):
            raise ValueError("Future Radar interval")
        protocols = {}
        for key, value in row["protocols"].items():
            if value is None:
                continue  # Missing measurements remain gaps, never zeroes.
            value = float(value)
            if not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError("Invalid Radar percentage")
            protocols[key] = value
        if not protocols:
            raise ValueError("Radar bucket has no measurements")
        return {
            "start_at": stamp(start),
            "end_at": stamp(start + timedelta(hours=1)),
            "protocols": protocols,
            "received_at": row["received_at"],
            "original_url": self.homepage,
        }


def observation_feeds(settings):
    return [DShield(settings), ISCHoneypots(settings), ThreatFox(settings), CloudflareRadar(settings)]
