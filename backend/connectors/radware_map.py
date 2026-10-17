"""Scrape Radware's normally rendered public site; no direct API client."""

import hashlib
import json
import re
from collections import deque

from ..models import utcnow
from .base import ProviderError, clean
from .threat_maps import ThreatMap, robots

TYPES = {
    "dDosAttackers": "DDoS (subtype unspecified)",
    "webAttackers": "Web attack (technique unspecified)",
    "intruders": "Intrusion attempt (technique unspecified)",
    "scanners": "Reconnaissance / scanning",
    "anonymizers": "Anonymizer / reputation",
    "botnets": "Botnet activity (technique unspecified)",
}


def map_rows(batches, limit=100):
    """Only public country/type/time facts; strip all other upstream fields."""
    if not isinstance(batches, list) or len(batches) > 200:
        raise ValueError("Invalid Radware sample")
    groups, seen = {}, set()
    received = utcnow().isoformat()
    rows = (row for batch in batches for row in (batch if isinstance(batch, list) else [batch]))
    for index, row in enumerate(rows):
        if index >= 20000:
            break
        if not isinstance(row, dict) or row.get("type") not in TYPES:
            continue
        origin, target = row.get("sourceCountry"), row.get("destinationCountry")
        if not isinstance(origin, str) or not re.fullmatch(r"[A-Z]{2}", origin):
            origin = None
        if not isinstance(target, str) or not re.fullmatch(r"[A-Z]{2}", target):
            target = None
        if not origin and not target:
            continue
        when = clean(row.get("attackTime", ""), 100)
        if not when:
            continue
        canonical = [
            origin,
            target,
            row["type"],
            when,
            clean(row.get("weight", ""), 30),
            row.get("millisecond"),
        ]
        identity = hashlib.sha256(json.dumps(canonical, ensure_ascii=False).encode()).hexdigest()
        if identity in seen:
            continue
        seen.add(identity)
        record = {
            "attacker": origin,
            "target": target,
            "reason": TYPES[row["type"]],
            "date": when,
            "received_at": received,
            "observation_id": identity,
        }
        groups.setdefault((row["type"], origin, target), deque()).append(record)
    ordered = sorted(groups, key=lambda key: (key[0] != "dDosAttackers", key[0] == "scanners", key[0]))
    records = []
    while ordered and len(records) < limit:
        for key in ordered[:]:
            records.append(groups[key].popleft())
            if not groups[key]:
                ordered.remove(key)
            if len(records) >= limit:
                break
    return records


class RadwareMap(ThreatMap):
    source_id = "radware_threatmap"
    name = "Radware detections"
    homepage = "https://livethreatmap.radware.com/"
    delivery = "Normal public-page renderer; sampled map countries and a separate DOM statistics breakdown"
    interval = 120
    sample_seconds = 0
    limitation = (
        ThreatMap.limitation
        + " Radware supplies broad route categories only; scanner routes keep their explicit category. Detailed network vectors are global hourly percentages, never joined to an individual route."
    )

    async def fetch(self, http):
        await robots(http, self.homepage)
        reader = getattr(http, "threat_table_reader", None)
        if reader is None:
            raise ProviderError(
                "Radware requires the optional public-page scraper; no API credentials are used",
                retry_after=60,
            )
        return map_rows(await reader.radware_rows(), min(self.sample_limit, self.settings.max_records))

    def normalize(self, record):
        report = super().normalize(record)
        report.threat.victim_basis = "Provider destination country; anonymized sampled attack telemetry does not establish victim compromise"
        report.description = (
            "Radware's public map category: "
            + report.threat.attack_kind
            + ". "
            + self.limitation
            + " Provider timestamp has no timezone suffix; timeline uses receipt time."
        )
        report.evidence_basis = (
            "Sampled provider attack telemetry; detailed vector is unspecified for this country pair"
        )
        return report
