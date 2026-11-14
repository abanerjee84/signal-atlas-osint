"""Public sensor directories and an operator-supplied normalized ADS-B feed."""

import math
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

from ..models import AircraftMetadata, Report, utcnow
from .base import Connector, ProviderError


class PublicDirectory(Connector):
    category = "sensors"
    monitoring_directory = True
    interval = 3600
    limitation = "Public directory metadata, not a verified live stream or operational status"

    async def fetch(self, http):
        if self.source_id == "public_radio":
            return self.settings.public_radio_receivers[: self.settings.max_records]
        data = await http.json("GET", self.endpoint)
        if not isinstance(data, list):
            raise ProviderError("Sensor directory returned an unsupported response")
        return data

    def normalize(self, record):
        now = utcnow()
        if self.source_id == "tfl_cameras":
            props = {p["key"]: p["value"] for p in record.get("additionalProperties", [])}
            identifier, title = record["id"], record["commonName"]
            lat, lon = record["lat"], record["lon"]
            # Link out only; no third-party stream request until the operator follows it.
            url = props.get("videoUrl") or props.get("imageUrl") or self.homepage
            kind, extra = "cctv", {"catalog": "TfL JamCam", "stream_status": "Not verified"}
        elif self.source_id == "satnogs_stations":
            identifier, title = str(record["id"]), record["name"]
            lat, lon = record["lat"], record["lng"]
            url = f"https://network.satnogs.org/stations/{identifier}/"
            kind, extra = "ground-station", {"directory_status": str(record.get("status", "Unknown"))[:80]}
        else:
            identifier, title = str(record["id"]), record["name"]
            lat, lon, url = record["latitude"], record["longitude"], record["url"]
            kind, extra = "radio", {"bands": str(record.get("bands", "Not supplied"))[:200]}
        url = Report.safe_url(url)
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", identifier):
            raise ValueError("Invalid directory identifier")
        return Report(
            external_id=identifier,
            source_id=self.source_id,
            source_url=url,
            title=str(title)[:500],
            description=self.limitation,
            category=self.category,
            latitude=lat,
            longitude=lon,
            location_precision="approximate",
            location_basis="Coordinates supplied by public directory; not independently surveyed",
            published_at=now,
            tags=[kind],
            raw={"monitoring": {"kind": kind, **extra}},
        )


class TfLCameras(PublicDirectory):
    source_id = "tfl_cameras"
    name = "Transport for London public traffic cameras"
    homepage = "https://tfl.gov.uk/traffic/status/"
    endpoint = "https://api.tfl.gov.uk/Place/Type/JamCam"

    def access(self):
        return (
            None if self.settings.tfl_cameras_enabled else "TfL camera collection disabled in configuration"
        )


class GroundStations(PublicDirectory):
    source_id = "satnogs_stations"
    name = "SatNOGS public ground-station directory"
    homepage = "https://network.satnogs.org/stations/"
    endpoint = "https://network.satnogs.org/api/stations/?format=json"

    def access(self):
        return None if self.settings.satnogs_stations_enabled else "SatNOGS station collection disabled"


class PublicRadio(PublicDirectory):
    source_id = "public_radio"
    name = "Operator-configured public radio receivers"
    homepage = "https://kiwisdr.com/public/"

    def access(self):
        return None if self.settings.public_radio_receivers else "Configure OSINT_PUBLIC_RADIO_RECEIVERS"


class AccuracyADSB(Connector):
    source_id = "accuracy_adsb"
    name = "Operator-configured ADS-B navigation accuracy feed"
    category = "aviation"
    homepage = "https://www.adsbexchange.com/"
    interval = 60
    fast_monitoring = True
    limitation = "Provider-reported NACp indicates navigation accuracy; degradation does not prove jamming"

    def access(self):
        return (
            None if self.settings.monitoring_adsb_url else "Configure an authorized OSINT_MONITORING_ADSB_URL"
        )

    async def fetch(self, http):
        data = await http.json("GET", self.settings.monitoring_adsb_url)
        if not isinstance(data, dict) or not isinstance(data.get("aircraft"), list):
            raise ProviderError("Expected normalized ADS-B aircraft array")
        records = []
        parsed = urlsplit(self.settings.monitoring_adsb_url)
        reference = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        for row in data["aircraft"]:
            if not isinstance(row, dict):
                continue
            if "icao24" in row:
                records.append(row)
                continue
            # readsb/dump1090 aircraft.json. The file's `now` minus `seen_pos`
            # dates the position; missing position age cannot establish a fix.
            try:
                seen = float(row["seen_pos"])
                epoch = float(data["now"])
                if not math.isfinite(epoch) or not math.isfinite(seen) or not 0 <= seen <= 900:
                    continue
                when = datetime.fromtimestamp(epoch, timezone.utc) - timedelta(seconds=seen)
                records.append(
                    dict(
                        icao24=row["hex"],
                        observed_at=when.isoformat(),
                        source_url=reference,
                        latitude=row["lat"],
                        longitude=row["lon"],
                        nac_p=row.get("nac_p"),
                        on_ground=row.get("alt_baro") == "ground"
                        if row.get("alt_baro") is not None
                        else None,
                    )
                )
            except (KeyError, ValueError, TypeError, OverflowError, OSError):
                continue
        return records

    def normalize(self, record):
        icao = str(record["icao24"]).lower()
        if not re.fullmatch(r"[0-9a-f]{6}", icao):
            raise ValueError("Invalid ICAO24")
        when = datetime.fromisoformat(record["observed_at"].replace("Z", "+00:00"))
        if when.tzinfo is None or when > utcnow():
            raise ValueError("Observation must be timezone-aware and not in the future")
        nacp = record.get("nac_p")
        if nacp is not None and (type(nacp) is not int or not 0 <= nacp <= 11):
            raise ValueError("Invalid NACp")
        on_ground = record.get("on_ground")
        if on_ground is not None and type(on_ground) is not bool:
            raise ValueError("Invalid on_ground")
        return Report(
            external_id=icao,
            source_id=self.source_id,
            source_url=record["source_url"],
            title=f"ADS-B {icao}",
            description=self.limitation,
            category=self.category,
            latitude=record["latitude"],
            longitude=record["longitude"],
            location_precision="approximate",
            location_basis="Provider-reported ADS-B coordinates",
            occurred_at=when,
            published_at=when,
            tags=["ads-b", "navigation-accuracy"],
            aircraft=AircraftMetadata(icao24=icao, registration_country="Unknown", on_ground=on_ground),
            raw={"monitoring": {"nac_p": nacp, "on_ground": on_ground}},
        )


class ShodanHosts(Connector):
    source_id = "shodan"
    name = "Shodan passive host lookup (on demand)"
    category = "infrastructure"
    homepage = "https://developer.shodan.io/api"
    interval = 86400
    manual = True
    monitoring_lookup_only = True
    limitation = "Authenticated operator lookup only; no active scanning or scheduled global search"

    def access(self):
        return None if self.settings.shodan_api_key else "Configure OSINT_SHODAN_API_KEY"

    async def fetch(self, http):
        raise ProviderError("Use the protected monitoring host lookup endpoint")

    def normalize(self, record):
        raise ValueError("Host records are normalized by the protected lookup endpoint")


def monitoring_feeds(settings):
    return [
        TfLCameras(settings),
        GroundStations(settings),
        PublicRadio(settings),
        AccuracyADSB(settings),
        ShodanHosts(settings),
    ]
