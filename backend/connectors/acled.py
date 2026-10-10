from datetime import timedelta

from ..models import Report, utcnow
from .base import Connector, SafeHTTP, parse_time


class ACLED(Connector):
    source_id, name, category = "acled", "ACLED conflict reporting", "geopolitical"
    homepage = "https://acleddata.com/api-documentation/getting-started"
    interval = 21600
    limitation = "Account permissions and licensing apply. Newest bounded page from the last seven days; not exhaustive coverage. Date has day resolution, represented at midnight UTC."

    def access(self):
        return (
            None
            if self.settings.acled_email and self.settings.acled_password
            else "Authorized myACLED account and API access required"
        )

    async def fetch(self, http: SafeHTTP) -> list[dict]:
        auth = await http.json(
            "POST",
            "https://acleddata.com/oauth/token",
            data={
                "username": self.settings.acled_email,
                "password": self.settings.acled_password,
                "grant_type": "password",
                "client_id": "acled",
                "scope": "authenticated",
            },
        )
        result = await http.json(
            "GET",
            "https://acleddata.com/api/acled/read",
            headers={"Authorization": f"Bearer {auth['access_token']}"},
            params={
                "limit": min(self.settings.max_records, 500),
                "event_date": (utcnow() - timedelta(days=7)).strftime("%Y-%m-%d"),
                "event_date_where": ">=",
                "_format": "json",
            },
        )
        return result["data"]

    def normalize(self, record: dict) -> Report:
        happened = parse_time(record["event_date"] + "T00:00:00Z")
        from datetime import datetime, timezone

        publication = datetime.fromtimestamp(int(record["timestamp"]), timezone.utc)
        fatalities = int(record.get("fatalities", 0))
        precision = "approximate" if str(record.get("geo_precision")) == "1" else "regional"
        return Report(
            external_id=record["event_id_cnty"],
            source_id=self.source_id,
            source_url="https://acleddata.com/data",
            title=f"{record['event_type']}: {record.get('location', record.get('country', ''))}",
            description=record.get("notes", "")[:10000],
            category=self.category,
            latitude=float(record["latitude"]),
            longitude=float(record["longitude"]),
            location_precision=precision,
            location_basis=f"ACLED location precision {record.get('geo_precision')}; event date has day resolution",
            occurred_at=happened,
            published_at=publication,
            severity="high" if fatalities >= 10 else "moderate",
            severity_basis="Reported fatalities >=10: high; otherwise moderate; reported counts may be revised",
            tags=[record["event_type"], "conflict"],
            raw=record,
        )
