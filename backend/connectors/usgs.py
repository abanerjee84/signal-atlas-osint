from datetime import datetime, timezone

from ..models import Report
from .base import Connector, SafeHTTP


class USGS(Connector):
    source_id, name, category = "usgs", "USGS earthquakes", "environment"
    homepage = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php"
    interval = 300
    limitation = "M2.5+ observations from the last 30 days. Hypocenter coordinates; parameters may be revised. No inferred national attribution near borders."

    async def fetch(self, http: SafeHTTP) -> list[dict]:
        payload = await http.json(
            "GET", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_month.geojson"
        )
        return payload["features"]

    def normalize(self, record: dict) -> Report:
        properties = record["properties"]
        lon, lat, depth = record["geometry"]["coordinates"][:3]
        magnitude = properties.get("mag")
        if properties.get("type") != "earthquake":
            raise ValueError("Not an earthquake observation")
        reviewed = properties.get("status") == "reviewed"
        severity = (
            "critical"
            if magnitude is not None and magnitude >= 7
            else "high"
            if magnitude is not None and magnitude >= 6
            else "moderate"
            if magnitude is not None and magnitude >= 4.5
            else "low"
        )
        return Report(
            external_id=record["id"],
            source_id=self.source_id,
            source_url=properties["url"],
            title=properties["title"],
            description=f"Magnitude {magnitude}; depth {depth} km. USGS status: {properties.get('status', 'unknown')}. Parameters may be revised.",
            category=self.category,
            longitude=lon,
            latitude=lat,
            location_precision="approximate",
            location_basis="USGS reported hypocenter, subject to observational uncertainty",
            occurred_at=datetime.fromtimestamp(properties["time"] / 1000, timezone.utc),
            published_at=datetime.fromtimestamp(properties["updated"] / 1000, timezone.utc),
            confidence="Verified" if reviewed else "Unverified",
            evidence_basis="Provider-reviewed instrumental observation"
            if reviewed
            else "Automatic instrumental observation awaiting provider review",
            severity=severity,
            severity_basis="Magnitude thresholds: critical >=7, high >=6, moderate >=4.5; not a casualty estimate",
            tags=["earthquake", f"magnitude:{magnitude}"],
            raw=record,
        )
