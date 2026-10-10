import csv
import io

from ..models import Report
from .base import Connector, SafeHTTP, box, parse_time, spatial_sample


class FIRMS(Connector):
    source_id, name, category = "firms", "NASA FIRMS thermal detections", "environment"
    homepage = "https://firms.modaps.eosdis.nasa.gov/api/area/"
    interval = 3600
    limitation = "Worldwide or configured region; one day of VIIRS NOAA-20 NRT detections. Stored detections are sampled across geographic cells when the record bound is exceeded. Thermal anomalies can include industrial heat and are not confirmation of wildfire."

    def metadata(self):
        return {
            **super().metadata(),
            "coverage_scope": "world" if self.settings.firms_area == "world" else "regional",
            "coverage_area": self.settings.firms_area,
            "record_selection": "geographic_sample",
        }

    def select_records(self, records):
        return spatial_sample(
            records, self.settings.max_records, lambda record: (record["longitude"], record["latitude"])
        )

    def access(self):
        return None if self.settings.firms_map_key else "NASA FIRMS MAP_KEY required"

    async def fetch(self, http: SafeHTTP) -> list[dict]:
        if self.settings.firms_area != "world":
            box(self.settings.firms_area)
        area = self.settings.firms_area
        payload = await http.request(
            "GET",
            f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{self.settings.firms_map_key}/VIIRS_NOAA20_NRT/{area}/1",
        )
        return list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))

    def normalize(self, record: dict) -> Report:
        time = record["acq_time"].zfill(4)
        observed = parse_time(f"{record['acq_date']}T{time[:2]}:{time[2:]}:00Z")
        identifier = f"{record['latitude']}:{record['longitude']}:{record['acq_date']}:{time}"
        return Report(
            external_id=identifier,
            source_id=self.source_id,
            source_url="https://firms.modaps.eosdis.nasa.gov/map/",
            title="VIIRS thermal anomaly detection",
            description=f"Sensor confidence {record.get('confidence')}; radiative power {record.get('frp')} MW. Thermal detection is not confirmation of wildfire.",
            category=self.category,
            latitude=float(record["latitude"]),
            longitude=float(record["longitude"]),
            location_precision="approximate",
            location_basis="Satellite detection pixel center",
            occurred_at=observed,
            published_at=observed,
            evidence_basis="Single NASA satellite detection; wildfire cause unverified",
            tags=["thermal-anomaly", "viirs"],
            raw=record,
        )
