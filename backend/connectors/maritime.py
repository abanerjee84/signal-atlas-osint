from ..models import Report
from .base import Connector, SafeHTTP, parse_time


class Maritime(Connector):
    source_id, name, category = "maritime", "Authorized maritime feed", "maritime"
    homepage = "https://www.imo.org/en/OurWork/Safety/Pages/AIS.aspx"
    interval = 900
    limitation = "Administrator-provided licensed AIS JSON feed. Incomplete coverage. Provider must permit display and historical retention. Schema specified in docs/SOURCES.md."

    def access(self):
        return (
            None
            if self.settings.maritime_url
            else "Licensed maritime JSON endpoint and explicitly allowed host required"
        )

    async def fetch(self, http: SafeHTTP) -> list[dict]:
        headers = (
            {"Authorization": f"Bearer {self.settings.maritime_token}"}
            if self.settings.maritime_token
            else {}
        )
        result = await http.json("GET", self.settings.maritime_url, headers=headers)
        return result["observations"]

    def normalize(self, record: dict) -> Report:
        observed = parse_time(record["observed_at"])
        return Report(
            external_id=f"{record['mmsi']}:{record['observed_at']}",
            source_id=self.source_id,
            source_url=record["source_url"],
            title=f"Vessel {record.get('name') or record['mmsi']}",
            description=f"MMSI {record['mmsi']}; class {record.get('class', 'unknown')}; last reported position {record['observed_at']}.",
            category=self.category,
            latitude=record["latitude"],
            longitude=record["longitude"],
            location_precision="approximate",
            location_basis="Provider-reported AIS observation",
            occurred_at=observed,
            published_at=parse_time(record.get("published_at", record["observed_at"])),
            tags=["ais", str(record["mmsi"])],
            raw=record,
        )
