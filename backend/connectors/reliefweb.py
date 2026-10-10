from ..models import Report
from .base import Connector, SafeHTTP, clean, parse_time


class ReliefWeb(Connector):
    source_id, name, category = "reliefweb", "ReliefWeb humanitarian reporting", "environment"
    homepage = "https://apidoc.reliefweb.int/"
    interval = 3600
    limitation = (
        "Newest 100 reports. Country-level reporting context only. Approved appname required by the provider."
    )

    def access(self):
        return None if self.settings.reliefweb_appname else "Provider-approved ReliefWeb appname required"

    async def fetch(self, http: SafeHTTP) -> list[dict]:
        result = await http.json(
            "GET",
            "https://api.reliefweb.int/v2/reports",
            params={
                "appname": self.settings.reliefweb_appname,
                "limit": 100,
                "profile": "full",
                "sort[]": "date.created:desc",
            },
        )
        return result["data"]

    def normalize(self, record: dict) -> Report:
        fields = record["fields"]
        countries = fields.get("country", [])
        country = countries[0] if len(countries) == 1 else {}
        code = country.get("iso3")
        from ..geo import countries as world

        match = next(
            (item["properties"] for item in world()["features"] if item["properties"].get("iso3") == code),
            None,
        )
        return Report(
            external_id=str(record["id"]),
            source_id=self.source_id,
            source_url=fields["url"],
            title=clean(fields["title"], 500),
            description=clean(fields.get("body", ""), 2000),
            category=self.category,
            published_at=parse_time(fields["date"]["created"]),
            country_code=match["code"] if match else None,
            longitude=match["center"][0] if match else None,
            latitude=match["center"][1] if match else None,
            location_precision="regional" if match else "unknown",
            location_basis="Provider report country; not incident coordinates",
            language="en"
            if any(lang.get("code") == "en" for lang in fields.get("language", []))
            else "unknown",
            sentiment_kind="official",
            tags=["humanitarian"],
            raw=record,
        )
