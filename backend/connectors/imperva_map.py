"""Bounded country-pair samples from the public dataset behind Imperva's table."""

import csv
import hashlib
import io
import json
import zlib
from collections import deque
from datetime import datetime, timedelta, timezone

from ..attack_vectors import extract_vectors
from ..models import stamp, utcnow
from .base import ProviderError, clean
from .threat_maps import ThreatMap, robots


def dataset_rows(payload, end_day, hour, limit=100):
    inflater = zlib.decompressobj(47)
    expanded = inflater.decompress(payload, 8_388_609)
    if len(expanded) > 8_388_608 or not inflater.eof:
        raise ValueError("Oversized or incomplete Imperva dataset")
    groups = {}
    seen = set()
    for row in csv.reader(io.StringIO(expanded.decode("utf-8"))):
        if len(row) != 8 or len(row[0]) != 2 or len(row[1]) != 2 or not row[6].isdigit():
            continue
        canonical = [clean(value, 100) for value in row]
        identity = hashlib.sha256(json.dumps([end_day, hour, *canonical]).encode()).hexdigest()
        if identity in seen:
            continue
        seen.add(identity)
        groups.setdefault((row[0], row[1]), deque()).append(
            {
                "attacker": row[0],
                "target": row[1],
                "reason": clean(f"{row[3]} - {row[4]}", 80),
                "date": end_day,
                "period_end": end_day,
                "industry": canonical[2],
                "client": canonical[5],
                "requests": int(row[6]),
                "received_at": utcnow().isoformat(),
                "observation_id": identity,
            }
        )
    records = []
    # Retain country diversity but take explicit techniques before generic bot
    # and business-logic rows, which otherwise dominate each country's queue.
    for pair, rows in groups.items():
        groups[pair] = deque(
            sorted(rows, key=lambda row: not bool(extract_vectors(row["reason"], contextual=False)[0]))
        )
    # A small sample must not be exhausted by generic categories before reaching
    # country pairs for which the provider actually supplies a technique.
    groups = dict(
        sorted(
            groups.items(),
            key=lambda item: not bool(extract_vectors(item[1][0]["reason"], contextual=False)[0]),
        )
    )
    while groups and len(records) < limit:
        for pair in list(groups):
            records.append(groups[pair].popleft())
            if not groups[pair]:
                del groups[pair]
            if len(records) >= limit:
                break
    return records


class ImpervaMap(ThreatMap):
    source_id = "imperva_threatmap"
    name = "Imperva daily attack requests"
    homepage = "https://www.imperva.com/cyber-threat-attack-map/"
    data_root = "https://www.imperva.com/public/threat-map-data-v2/"
    interval = 900
    sample_seconds = 0
    delivery = (
        "Public compressed CSV backing the rotating table; daily reporting period, checked every 15 minutes"
    )

    async def fetch(self, http):
        await robots(http, self.data_root)
        reader = getattr(http, "threat_table_reader", None)
        if reader:
            payload, day, hour = await reader.imperva_dataset()
            parsed = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if parsed > utcnow() or parsed < utcnow() - timedelta(days=14):
                raise ProviderError("Imperva public page supplied a stale reporting period")
            return dataset_rows(payload, day, hour, min(self.sample_limit, self.settings.max_records))
        index = json.loads(
            await http.request("GET", self.data_root + "index.json", attempts=1, max_bytes=4096)
        )
        day = index.get("last_update_day", "")
        try:
            parsed = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if parsed > utcnow() or parsed < utcnow() - timedelta(days=14):
                raise ValueError("Invalid reporting period")
            hour = utcnow().hour
            payload = await http.request(
                "GET", f"{self.data_root}day={day}/data/{hour}.gz", attempts=1, max_bytes=1_048_576
            )
            if payload.lstrip().startswith(b"<"):
                raise ProviderError(
                    "Imperva returned an interruption page; use the optional normal-page renderer or leave collection blocked",
                    retry_after=900,
                )
            return dataset_rows(payload, day, hour, min(self.sample_limit, self.settings.max_records))
        except (ValueError, zlib.error, UnicodeError):
            raise ProviderError(
                "Imperva daily dataset is invalid, stale or exceeds collection bounds"
            ) from None

    def normalize(self, record):
        report = super().normalize(record)
        end = datetime.strptime(record["period_end"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        start = end - timedelta(days=1)
        period = f"{start.date()} to {end.date()}"
        report.published_at = end
        report.evidence_basis = (
            "One provider's daily request aggregate; country geography, not actor attribution"
        )
        report.description = f"Imperva daily reporting period {period}. {record['requests']:,} provider attack requests in this sampled table row; not distinct incidents or live arrivals. Industry: {record['industry'] or 'unspecified'}. Client: {record['client'] or 'unspecified'}. Country codes describe traffic infrastructure; actor identity and compromise are unknown. Sample received {stamp(report.threat.received_at)}. Country-pair stratified bounded sample, not the complete dataset."
        report.tags += [
            "daily-aggregate",
            "reporting-period:" + period,
            "provider-requests:" + str(record["requests"]),
        ]
        report.raw.update(
            {
                "reporting_period": period,
                "provider_requests": record["requests"],
                "industry": record["industry"],
                "client": record["client"],
            }
        )
        return report
