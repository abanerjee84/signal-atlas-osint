from ..models import Report
from .base import Connector, SafeHTTP, parse_time
from .vendor_geo import BASIS, vendor_origin


class CISA(Connector):
    source_id, name, category = "cisa", "CISA known exploited vulnerabilities (catalog backlog)", "cyber"
    homepage = "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"
    interval = 21600
    limitation = (
        "Backlog of catalog additions, not a live incident feed and not a count of current threats. "
        "Entries are historical by construction. Coordinates are configured vendor country "
        "centroids, never headquarters coordinates or victim/attacker locations. Distributed "
        "and unknown vendors remain unlocated."
    )

    async def fetch(self, http: SafeHTTP) -> list[dict]:
        result = await http.json(
            "GET", "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
        )
        return sorted(result["vulnerabilities"], key=lambda item: item["dateAdded"], reverse=True)

    def normalize(self, record: dict) -> Report:
        vendor = record.get("vendorProject") or ""
        origin = vendor_origin(vendor)
        return Report(
            external_id=record["cveID"],
            source_id=self.source_id,
            source_url=self.homepage + "?search_api_fulltext=" + record["cveID"],
            title=f"{record['cveID']}: {record['vulnerabilityName']}",
            description=record["shortDescription"] + " Required action: " + record["requiredAction"],
            category=self.category,
            longitude=origin[0] if origin else None,
            latitude=origin[1] if origin else None,
            country_code=origin[2] if origin else None,
            location_precision="regional" if origin else "unknown",
            location_basis=BASIS
            if origin
            else f"No supported vendor country context for '{vendor or 'unknown'}'",
            published_at=parse_time(record["dateAdded"] + "T00:00:00Z"),
            confidence="Verified",
            evidence_basis="CISA authoritative catalog membership; not verification of a specific victim or incident",
            severity="high",
            severity_basis="Derived from inclusion in the known exploited vulnerabilities catalog",
            tags=[record["cveID"], vendor.lower() or "unknown-vendor", "kev", "catalog-backlog"],
            raw=record,
        )
