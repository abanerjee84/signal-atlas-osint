"""Provider adapters for the additional monitoring domains. No synthetic locations."""

import csv
import hashlib
import io
import json
import math
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlsplit

from defusedxml import ElementTree

from ..models import CyberObservation, Report, stamp, utcnow
from ..monitoring_geo import geometry
from ..monitoring_imports import csv_records
from .base import Connector, ProviderError, clean
from .observatory import IndicatorFeed
from .rss import RSS


def instant(value, *, naive_utc=False):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value / 1000 if value > 1e12 else value, timezone.utc)
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if not result.tzinfo:
        if not naive_utc:
            raise ValueError("Provider timestamp lacks timezone")
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def number(value):
    if isinstance(value, bool):
        raise ValueError("Invalid measurement")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Invalid measurement")
    return value


def array(value, key=None):
    rows = value.get(key) if key and isinstance(value, dict) else value
    if not isinstance(rows, list):
        raise ProviderError("Provider returned an unsupported record collection")
    return rows


class Feed(Connector):
    category = "sensors"
    monitoring_directory = True
    interval = 3600
    limitation = "Public provider observation; coverage and source age vary"
    license = "Provider terms; retain attribution"
    reference = False
    requirement = None

    @property
    def initial_enabled(self):
        return self.source_id in self.settings.expansion_enabled

    def access(self):
        if self.requirement and not getattr(self.settings, self.requirement):
            return "Configure OSINT_" + self.requirement.upper()
        return None

    def metadata(self):
        return {
            **super().metadata(),
            "initial_enabled": self.initial_enabled,
            "license": self.license,
            "record_kind": "reference" if self.reference else "observation",
        }

    def make(
        self,
        identity,
        title,
        *,
        observed=None,
        lat=None,
        lon=None,
        url=None,
        tags=(),
        shape=None,
        description="",
        sensor=None,
        category=None,
    ):
        observed = observed or utcnow() if self.reference else observed
        if observed is None:
            raise ValueError("A measurement requires a provider observation time")
        info = {
            "kind": self.source_id,
            "reference": self.reference,
            "license": self.license,
            "freshness_seconds": 86400 if self.reference else 3600,
            **(sensor or {}),
        }
        if shape:
            info["geometry"] = geometry(shape)
        return Report(
            external_id=str(identity)[:512],
            source_id=self.source_id,
            source_url=url or self.homepage,
            title=clean(str(title), 500),
            description=clean((description + " " + self.limitation).strip(), 10000),
            category=category or self.category,
            latitude=lat,
            longitude=lon,
            location_precision="approximate" if lat is not None else "unknown",
            location_basis="Provider-supplied coordinates; precision follows the original record"
            if lat is not None
            else "No supported point location; inspect provider geometry where supplied",
            published_at=observed,
            occurred_at=observed,
            tags=list(tags),
            raw={"monitoring": info},
        )


class Feodo(IndicatorFeed):
    source_id, name, family = "feodo", "Feodo Tracker botnet C2 observations", "abuse_ch"
    homepage = "https://feodotracker.abuse.ch/blocklist/"
    license = "Feodo Tracker terms; provider indicators, not actor attribution"
    interval = 900

    @property
    def initial_enabled(self):
        return self.source_id in self.settings.expansion_enabled

    async def fetch(self, http):
        return array(await http.json("GET", "https://feodotracker.abuse.ch/downloads/ipblocklist.json"))

    def normalize(self, row):
        received = utcnow()
        port = int(row.get("dst_port") or row["port"])
        first = instant(row["first_seen"], naive_utc=True) if row.get("first_seen") else None
        last = instant(row["last_online"], naive_utc=True) if row.get("last_online") else first
        obs = CyberObservation(
            provider_record_id=f"{row['ip_address']}:{port}",
            source_family=self.family,
            kind="botnet_c2",
            indicator_type="ip",
            indicator_value=row["ip_address"],
            native_type="botnet_c2",
            port=port,
            first_seen=first,
            last_seen=last,
            received_at=received,
            malware_name=str(row.get("malware", ""))[:200],
            references=[self.homepage],
        )
        report = self.report(
            obs,
            f"Feodo C2: {row['ip_address']}",
            f"Provider status: {row.get('status', 'Not supplied')}; malware: {obs.malware_name}.",
            self.homepage,
        )
        report.tags += ["malware", "c2"]
        report.occurred_at = received
        report.published_at = received
        report.raw["monitoring"] = {
            "kind": "provider_indicator_assertion",
            "provider_status": row.get("status"),
            "first_seen": stamp(first) if first else None,
            "last_online": stamp(last) if last else None,
            "basis": "Provider feed assertion at retrieval; first/last online are preserved separately",
        }
        return report


class URLhaus(Feodo):
    source_id, name = "urlhaus", "URLhaus malicious URL observations"
    homepage = "https://urlhaus.abuse.ch/"

    def access(self):
        return None if self.settings.urlhaus_auth_key else "Configure OSINT_URLHAUS_AUTH_KEY"

    async def fetch(self, http):
        data = await http.json(
            "GET",
            "https://urlhaus-api.abuse.ch/v1/urls/recent/limit/100/",
            headers={"Auth-Key": self.settings.urlhaus_auth_key},
        )
        if data.get("query_status") == "no_results":
            return []
        return array(data, "urls")

    def normalize(self, row):
        source = f"https://urlhaus.abuse.ch/url/{int(row['id'])}/"
        when = instant(row["dateadded"], naive_utc=True)
        obs = CyberObservation(
            provider_record_id=str(row["id"]),
            source_family=self.family,
            kind="malicious_url",
            indicator_type="url",
            indicator_value=row["url"],
            native_type="malware_url",
            first_seen=when,
            received_at=utcnow(),
            malware_name=str(row.get("threat", ""))[:200],
            references=[source],
        )
        report = self.report(
            obs,
            f"URLhaus malware URL {row['id']}",
            f"Provider status: {row.get('url_status', 'Not supplied')}. The target URL is an indicator and is never fetched.",
            source,
        )
        report.tags += ["malware", "malware-url"]
        return report


class NWS(Feed):
    source_id, name = "nws_alerts", "US National Weather Service active warning polygons"
    homepage = "https://www.weather.gov/"
    category, monitoring_directory = "environment", False
    interval = 300
    limitation = "Official warning, not confirmation of observed damage; US jurisdictional coverage"

    async def fetch(self, http):
        return array(
            await http.json("GET", "https://api.weather.gov/alerts/active?status=actual"), "features"
        )

    def normalize(self, row):
        p = row["properties"]
        report = self.make(
            row["id"],
            p.get("headline") or p["event"],
            observed=instant(p["sent"]),
            url=p.get("web") or p.get("@id") or self.homepage,
            tags=["weather-alert"],
            shape=row.get("geometry"),
            description=f"{p.get('description', '')} {p.get('instruction') or ''}",
            sensor={
                "expires_at": stamp(instant(p["expires"])),
                "event": p["event"],
                "severity": p.get("severity"),
                "certainty": p.get("certainty"),
                "effective_at": p.get("effective"),
                "area": p.get("areaDesc"),
                "freshness_seconds": 86400,
            },
        )
        return report


class SWPC(Feed):
    source_id, name = "swpc", "NOAA SWPC geomagnetic index and solar events"
    homepage = "https://www.swpc.noaa.gov/"
    interval = 600
    limitation = "Space-weather context; does not identify the cause of a local GNSS or radio anomaly"

    async def fetch(self, http):
        kp = array(await http.json("GET", "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"))
        events = array(await http.json("GET", "https://services.swpc.noaa.gov/json/edited_events.json"))
        return [{"type": "kp", "data": r} for r in kp[-24:]] + [
            {"type": "event", "data": r} for r in events[-50:]
        ]

    def normalize(self, row):
        r = row["data"]
        if row["type"] == "kp":
            when = instant(r["time_tag"], naive_utc=True)
            return self.make(
                "kp:" + stamp(when),
                "Geomagnetic Kp index",
                observed=when,
                tags=["space-weather"],
                sensor={"value": number(r["kp_index"]), "unit": "Kp index", "freshness_seconds": 1800},
            )
        when = instant(r.get("begin_datetime") or r.get("beginDateTime") or r.get("time_tag"), naive_utc=True)
        return self.make(
            "solar:"
            + str(r.get("event_id") or hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()),
            f"Solar event: {r.get('type', 'Not supplied')}",
            observed=when,
            tags=["space-weather"],
            sensor={
                "event_type": r.get("type"),
                "classification": r.get("classtype") or r.get("particulars1"),
                "freshness_seconds": 86400,
            },
        )


class Cameras(Feed):
    reference = True
    limitation = "Transport-agency camera directory; media availability is not independently verified; no footage archived"

    def normalize(self, r):
        return self.make(
            r["id"],
            r["name"],
            lat=r["latitude"],
            lon=r["longitude"],
            url=r.get("url") or self.homepage,
            tags=["cctv"],
            sensor={
                "kind": "cctv",
                "media_url": r.get("media_url"),
                "media_type": r.get("media_type", "image"),
                "provider_updated_at": r.get("updated"),
                "stream_status": "Not verified",
            },
        )


class Caltrans(Cameras):
    source_id, name = "caltrans_cameras", "Caltrans public traffic camera directories"
    homepage = "https://cwwp2.dot.ca.gov/"

    async def fetch(self, http):
        result = []
        for district in self.settings.caltrans_districts[:12]:
            if type(district) is not int or not 1 <= district <= 12:
                raise ValueError("Invalid Caltrans district")
            data = await http.json(
                "GET", f"https://cwwp2.dot.ca.gov/data/d{district}/cctv/cctvStatusD{district:02d}.json"
            )
            for item in array(data, "data"):
                r = item["cctv"]
                loc = r["location"]
                image = r.get("imageData", {})
                still = image.get("static", {})
                result.append(
                    dict(
                        id=f"d{district}:{r.get('index') or r.get('recording') or loc.get('locationName')}",
                        name=loc.get("locationName") or "Caltrans camera",
                        latitude=loc["latitude"],
                        longitude=loc["longitude"],
                        media_url=still.get("currentImageURL"),
                        updated=image.get("updateTime"),
                    )
                )
        return result


class NYCCameras(Cameras):
    source_id, name = "nyc_cameras", "NYC DOT public traffic cameras"
    homepage = "https://webcams.nyctmc.org/"

    async def fetch(self, http):
        rows = array(await http.json("GET", "https://webcams.nyctmc.org/api/cameras"))
        return [
            dict(
                id=r["id"],
                name=r.get("name") or "NYC DOT camera",
                latitude=r["latitude"],
                longitude=r["longitude"],
                media_url=f"https://webcams.nyctmc.org/api/cameras/{quote(str(r['id']), safe='')}/image",
            )
            for r in rows
        ]


class SingaporeCameras(Cameras):
    source_id, name = "singapore_cameras", "Singapore data.gov.sg traffic camera snapshots"
    homepage = "https://data.gov.sg/"

    async def fetch(self, http):
        result = []
        for item in array(
            await http.json("GET", "https://api.data.gov.sg/v1/transport/traffic-images"), "items"
        ):
            for r in item["cameras"]:
                result.append(
                    dict(
                        id=r["camera_id"],
                        name=f"Singapore traffic camera {r['camera_id']}",
                        latitude=r["location"]["latitude"],
                        longitude=r["location"]["longitude"],
                        media_url=r["image"],
                        updated=r.get("timestamp") or item.get("timestamp"),
                    )
                )
        return result


class Trains(Feed):
    interval, fast_monitoring = 60, True
    limitation = "Provider-reported passenger train position; regional coverage, not a global rail feed"

    def normalize(self, r):
        return self.make(
            r["id"],
            r["name"],
            observed=instant(r["time"]),
            lat=r["lat"],
            lon=r["lon"],
            tags=["rail"],
            sensor={
                "operator": r.get("operator"),
                "speed": r.get("speed"),
                "speed_unit": r.get("speed_unit"),
                "freshness_seconds": 300,
            },
        )


class Amtraker(Trains):
    source_id, name = "amtraker", "Amtraker US passenger train positions"
    homepage = "https://www.amtraker.com/"

    async def fetch(self, http):
        data = await http.json("GET", "https://api.amtraker.com/v3/trains")
        if not isinstance(data, dict):
            raise ProviderError("Invalid Amtraker response")
        return [
            dict(
                id=r.get("trainID") or r["trainNum"],
                name=f"Amtrak {r.get('routeName', '')} {r['trainNum']}",
                lat=r["lat"],
                lon=r["lon"],
                time=r["updatedAt"],
                operator="Amtrak",
                speed=r.get("velocity"),
                speed_unit="mph",
            )
            for values in data.values()
            for r in array(values)
        ]


class Digitraffic(Trains):
    source_id, name = "digitraffic", "Fintraffic Finland train positions"
    homepage = "https://www.digitraffic.fi/en/railway-traffic/"

    async def fetch(self, http):
        return [
            dict(
                id=f"{r['departureDate']}:{r['trainNumber']}",
                name=f"Finland train {r['trainNumber']}",
                lon=r["location"]["coordinates"][0],
                lat=r["location"]["coordinates"][1],
                time=r["timestamp"],
                operator="Finnish railway network",
                speed=r.get("speed"),
                speed_unit="km/h",
            )
            for r in array(
                await http.json("GET", "https://rata.digitraffic.fi/api/v1/train-locations/latest")
            )
        ]


def maidenhead(value):
    text = str(value).upper()
    if not re.fullmatch(r"[A-R]{2}[0-9]{2}(?:[A-X]{2}(?:[0-9]{2})?)?", text):
        raise ValueError("Invalid Maidenhead grid")
    lon, lat = (ord(text[0]) - 65) * 20 - 180, (ord(text[1]) - 65) * 10 - 90
    lon += int(text[2]) * 2
    lat += int(text[3])
    dx, dy = 2, 1
    if len(text) >= 6:
        dx, dy = 2 / 24, 1 / 24
        lon += (ord(text[4]) - 65) * dx
        lat += (ord(text[5]) - 65) * dy
    if len(text) == 8:
        dx /= 10
        dy /= 10
        lon += int(text[6]) * dx
        lat += int(text[7]) * dy
    return lon + dx / 2, lat + dy / 2


class KiwiSDR(Feed):
    source_id, name = "kiwisdr", "KiwiSDR public receiver directory"
    homepage = "https://kiwisdr.com/public/"
    reference = True
    limitation = "Published public receiver listing; coordinates are operator-supplied; tuning is external"

    async def fetch(self, http):
        payload = (await http.request("GET", "https://rx.linkfanel.net/kiwisdr_com.js")).decode("utf-8")
        start = payload.find("[")
        if start < 0:
            raise ProviderError("Receiver directory format unsupported")
        data, _ = json.JSONDecoder().raw_decode(payload[start:])
        return array(data)

    def normalize(self, r):
        loc = r.get("gps")
        if isinstance(loc, str):
            match = re.fullmatch(r"\(?\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)?", loc)
            if not match:
                raise ValueError("Missing receiver coordinates")
            lat, lon = map(float, match.groups())
        else:
            lat, lon = number(r["lat"]), number(r["lon"])
        url = Report.safe_url(r.get("url") or r["u"])
        return self.make(
            hashlib.sha256(url.encode()).hexdigest(),
            r.get("name") or r.get("n") or "KiwiSDR receiver",
            lat=lat,
            lon=lon,
            url=url,
            tags=["radio"],
            sensor={"kind": "radio", "antenna": str(r.get("antenna", ""))[:300]},
        )


class PSKReporter(Feed):
    source_id, name = "psk_reporter", "PSK Reporter public digital-mode receptions"
    homepage = "https://pskreporter.info/pskdev.html"
    requirement, interval = "psk_callsign", 600
    limitation = (
        "Reported amateur-radio reception; grid-centre coordinates, not precise transmitter locations"
    )

    async def fetch(self, http):
        if not re.fullmatch(r"[A-Za-z0-9/\-]{3,20}", self.settings.psk_callsign):
            raise ValueError("Invalid amateur-radio callsign")
        payload = await http.request(
            "GET",
            "https://retrieve.pskreporter.info/query",
            params={"senderCallsign": self.settings.psk_callsign, "flowStartSeconds": -900, "mode": "FT8"},
        )
        root = ElementTree.fromstring(payload)
        return [dict(e.attrib) for e in root.iter("receptionReport")]

    def normalize(self, r):
        lon, lat = maidenhead(r["receiverLocator"])
        when = instant(int(r["flowStartSeconds"]))
        return self.make(
            hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest(),
            f"Radio reception {r.get('senderCallsign', '?')} to {r.get('receiverCallsign', '?')}",
            observed=when,
            lat=lat,
            lon=lon,
            tags=["radio-reception"],
            sensor={
                "mode": r.get("mode"),
                "frequency_hz": number(r["frequency"]),
                "snr_db": number(r["sNR"]) if r.get("sNR") else None,
                "grid": r["receiverLocator"],
                "sender": r.get("senderCallsign"),
                "receiver": r.get("receiverCallsign"),
                "freshness_seconds": 1800,
            },
        )


class TinyGS(Feed):
    source_id, name = "tinygs", "TinyGS satellite reception metadata"
    homepage, requirement = "https://tinygs.com/", "tinygs_token"
    limitation = (
        "Provider reception metadata only; orbital estimates are not substituted for missing receptions"
    )

    async def fetch(self, http):
        data = await http.json(
            "GET", self.settings.tinygs_url, headers={"Authorization": "Bearer " + self.settings.tinygs_token}
        )
        return array(data if isinstance(data, list) else data.get("satellites"))

    def normalize(self, r):
        when = instant(r.get("lastSeen") or r.get("timestamp"))
        # Coordinates must refer to a reported reception station, never a propagated satellite.
        station = r.get("station") or {}
        return self.make(
            str(r.get("id") or r["name"]),
            f"TinyGS reception: {r['name']}",
            observed=when,
            lat=station.get("latitude"),
            lon=station.get("longitude"),
            tags=["satellite-reception"],
            sensor={
                "satellite": r["name"],
                "station": station.get("name"),
                "norad_id": r.get("noradId"),
                "packets": r.get("packets"),
                "freshness_seconds": 3600,
            },
        )


class Volcanoes(Feed):
    source_id, name = "volcanoes", "Smithsonian GVP Holocene volcano registry"
    homepage, reference = "https://volcano.si.edu/", True
    interval = 86400
    limitation = "Versioned volcano reference; a listed volcano is not a current eruption"

    async def fetch(self, http):
        data = await http.json(
            "GET",
            "https://webservices.volcano.si.edu/geoserver/GVP-VOTW/wfs",
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeName": "GVP-VOTW:E3WebApp_HoloceneVolcanoes",
                "outputFormat": "application/json",
            },
        )
        return array(data, "features")

    def normalize(self, r):
        p = r["properties"]
        lon, lat = r["geometry"]["coordinates"][:2]
        identity = p.get("Volcano_Number") or p.get("VolcanoNumber") or r["id"]
        return self.make(
            identity,
            p.get("Volcano_Name") or p.get("VolcanoName") or "Volcano",
            lat=lat,
            lon=lon,
            tags=["volcano"],
            sensor={
                "last_eruption_year": p.get("LastEruption") or p.get("Last_Eruption_Year"),
                "reference_version": stamp()[:10],
            },
        )


class RIPEAtlas(Feed):
    source_id, name = "ripe_atlas", "RIPE Atlas public probe connectivity states"
    homepage = "https://atlas.ripe.net/"
    interval = 900
    limitation = "Probe connectivity status, not a confirmed regional outage or its cause"

    async def fetch(self, http):
        return array(
            await http.json(
                "GET", "https://atlas.ripe.net/api/v2/probes/?status=2&page_size=500&format=json"
            ),
            "results",
        )

    def normalize(self, r):
        loc = r.get("geometry") or {}
        coords = loc.get("coordinates")
        when = instant(r["status"]["since"])
        return self.make(
            r["id"],
            f"RIPE Atlas probe {r['id']}: {r['status']['name']}",
            observed=utcnow(),
            lon=coords[0] if coords else None,
            lat=coords[1] if coords else None,
            tags=["connectivity"],
            url=f"https://atlas.ripe.net/probes/{int(r['id'])}/",
            sensor={
                "status": r["status"]["name"],
                "status_since": stamp(when),
                "asn_v4": r.get("asn_v4"),
                "asn_v6": r.get("asn_v6"),
                "freshness_seconds": 1800,
            },
        )


class OpenAQ(Feed):
    source_id, name = "openaq", "OpenAQ station pollutant measurements"
    homepage, requirement = "https://openaq.org/", "openaq_api_key"
    limitation = "Station measurement with provider units; no country-wide air-quality claim or derived AQI"

    def access(self):
        return super().access() or (
            None if self.settings.openaq_location_ids else "Configure OSINT_OPENAQ_LOCATION_IDS"
        )

    async def fetch(self, http):
        records = []
        headers = {"X-API-Key": self.settings.openaq_api_key}
        for loc in self.settings.openaq_location_ids[:20]:
            if type(loc) is not int or loc < 1:
                raise ValueError("Invalid OpenAQ location ID")
            base = f"https://api.openaq.org/v3/locations/{loc}"
            sensors = {
                r["id"]: r
                for r in array(await http.json("GET", base + "/sensors", headers=headers), "results")
            }
            for row in array(await http.json("GET", base + "/latest", headers=headers), "results"):
                records.append({**row, "_sensor": sensors.get(row["sensorsId"], {}), "_location": loc})
        return records

    def normalize(self, r):
        p = r["_sensor"]["parameter"]
        loc = r["coordinates"]
        return self.make(
            f"{r['_location']}:{r['sensorsId']}",
            f"OpenAQ {p['name']} at location {r['_location']}",
            observed=instant(r["datetime"]["utc"]),
            lat=loc["latitude"],
            lon=loc["longitude"],
            tags=["air-quality"],
            url=f"https://explore.openaq.org/locations/{int(r['_location'])}",
            sensor={
                "value": number(r["value"]),
                "unit": p["units"],
                "parameter": p["name"],
                "sensor_id": r["sensorsId"],
                "freshness_seconds": 7200,
            },
        )


class GFWEvents(Feed):
    source_id, name = "gfw_events", "Global Fishing Watch apparent vessel activity events"
    homepage, requirement = "https://globalfishingwatch.org/", "gfw_api_token"
    limitation = "Provider-derived apparent activity, possibly delayed; AIS gaps or encounters do not establish illegal conduct"
    license = "Global Fishing Watch API terms and dataset license; non-commercial access unless separately authorized"
    interval = 21600

    async def fetch(self, http):
        datasets = {
            "fishing": "public-global-fishing-events:latest",
            "encounter": "public-global-encounters-events:latest",
            "loitering": "public-global-loitering-events:latest",
            "port_visit": "public-global-port-visits-events:latest",
            "gap": "public-global-gaps-events:latest",
        }
        params = {
            "start-date": stamp(utcnow() - timedelta(days=7)),
            "end-date": stamp(),
            "limit": min(100, self.settings.max_records),
            "offset": 0,
        }
        for i, kind in enumerate(self.settings.gfw_event_types[:5]):
            if kind not in datasets:
                raise ValueError("Unknown GFW event type")
            params[f"datasets[{i}]"] = datasets[kind]
        data = await http.json(
            "GET",
            "https://gateway.api.globalfishingwatch.org/v3/events",
            params=params,
            headers={"Authorization": "Bearer " + self.settings.gfw_api_token},
        )
        return array(data, "entries")

    def normalize(self, r):
        pos = r.get("position") or {}
        vessel = r.get("vessel") or {}
        return self.make(
            r["id"],
            f"GFW apparent {r['type']}: {vessel.get('name') or vessel.get('id') or 'vessel'}",
            observed=instant(r["start"]),
            lat=pos.get("lat"),
            lon=pos.get("lon"),
            tags=["vessel-activity"],
            url=f"https://globalfishingwatch.org/map/?event={quote(str(r['id']), safe='')}",
            sensor={
                "event_type": r["type"],
                "period_start": r["start"],
                "period_end": r.get("end"),
                "vessel_id": vessel.get("id"),
                "mmsi": vessel.get("ssvid"),
                "freshness_seconds": 604800,
            },
        )


class ReferenceFeed(Feed):
    reference, interval = True, 86400
    limitation = "Versioned reference geometry; proximity alone does not establish damage, outage or supply-chain dependency"

    def __init__(self, settings, definition):
        super().__init__(settings)
        self.definition = definition
        for field in ["source_id", "name", "url", "license", "version", "kind"]:
            if not isinstance(definition.get(field), str) or not definition[field]:
                raise ValueError("Reference sources need source_id, name, url, license, version and kind")
        if not re.fullmatch(r"[a-z][a-z0-9_-]{1,70}", definition["source_id"]) or definition["kind"] not in {
            "power-plant",
            "data-center",
            "cable",
            "supplier",
        }:
            raise ValueError("Invalid reference source")
        self.source_id, self.name, self.homepage, self.license = (
            definition[k] for k in ["source_id", "name", "url", "license"]
        )

    @property
    def initial_enabled(self):
        return True

    async def fetch(self, http):
        return array(await http.json("GET", self.definition["url"]), "features")

    def normalize(self, r):
        p = r["properties"]
        g = geometry(r["geometry"])
        coord = g["coordinates"] if g["type"] == "Point" else None
        if p.get("allow_download") is False:
            raise ValueError("Provider prohibits downloading this record")
        return self.make(
            r.get("id") or p["id"],
            p["name"],
            lat=coord[1] if coord else None,
            lon=coord[0] if coord else None,
            shape=g,
            tags=[self.definition["kind"]],
            url=p.get("source_url") or self.homepage,
            sensor={
                "reference_version": self.definition["version"],
                "asset_kind": self.definition["kind"],
                "operator": str(p.get("operator", ""))[:250],
                "sector": str(p.get("sector", ""))[:100],
                "capacity_mw": number(p["capacity_mw"]) if p.get("capacity_mw") is not None else None,
                "country": str(p.get("country", ""))[:100],
            },
        )


class PowerPlants(Feed):
    source_id, name = "wri_power_plants", "WRI Global Power Plant Database references"
    homepage, reference, interval = "https://www.wri.org/research/global-database-power-plants", True, 604800
    license = "Creative Commons Attribution 4.0; WRI Global Power Plant Database"
    limitation = "Historical power-plant registry; version is the downloaded file hash; no live operating state or generation inference"

    async def fetch(self, http):
        payload = await http.request(
            "GET",
            "https://raw.githubusercontent.com/wri/global-power-plant-database/master/output_database/global_power_plant_database.csv",
            max_bytes=33_554_432,
        )
        version = "sha256:" + hashlib.sha256(payload).hexdigest()
        return [
            {**row, "_registry_version": version}
            for row in csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
        ]

    def normalize(self, r):
        return self.make(
            r["gppd_idnr"],
            r["name"],
            lat=number(r["latitude"]),
            lon=number(r["longitude"]),
            tags=["power-plant"],
            sensor={
                "reference_version": r["_registry_version"],
                "asset_kind": "power-plant",
                "capacity_mw": number(r["capacity_mw"]),
                "fuel": r["primary_fuel"],
                "operator": r.get("owner"),
                "freshness_seconds": 2592000,
            },
        )


class Wastewater(Feed):
    source_id, name = "wastewater_export", "Authorized wastewater sample export"
    homepage = "https://data.wastewaterscan.org/"
    requirement = "wastewater_url"
    limitation = "Authorized sample export; sample date, analyte, unit and quality belong to the original laboratory record"

    def access(self):
        return super().access() or (
            None if self.settings.wastewater_license else "Record OSINT_WASTEWATER_LICENSE permission basis"
        )

    async def fetch(self, http):
        if urlsplit(self.settings.wastewater_url).path.lower().endswith(".csv"):
            payload = await http.request("GET", self.settings.wastewater_url)
            return csv_records(
                payload.decode("utf-8-sig"), self.source_id, min(200, self.settings.max_records)
            )
        return array(await http.json("GET", self.settings.wastewater_url), "features")

    def normalize(self, r):
        p = r["properties"]
        if p.get("allow_download") is False:
            raise ValueError("Provider prohibits downloading this record")
        g = geometry(r.get("geometry"))
        c = g["coordinates"] if g and g["type"] == "Point" else None
        if not p.get("unit") or not p.get("analyte") or not p.get("sample_id"):
            raise ValueError("Incomplete laboratory sample evidence")
        return self.make(
            p["sample_id"],
            f"Wastewater sample: {p['analyte']} at {p.get('site', 'site not supplied')}",
            observed=instant(p["sampled_at"]),
            lat=c[1] if c else None,
            lon=c[0] if c else None,
            shape=g,
            tags=["wastewater"],
            url=p["source_url"],
            sensor={
                "value": number(p["value"]) if p.get("value") is not None else None,
                "unit": p["unit"],
                "analyte": p["analyte"],
                "quality": p.get("quality", "Not supplied"),
                "permission_basis": self.settings.wastewater_license,
                "freshness_seconds": 604800,
            },
        )


class ManualWorkflow(Feed):
    manual = True

    @property
    def initial_enabled(self):
        return True

    async def fetch(self, http):
        raise ProviderError("Use the protected monitoring investigation workflow")

    def normalize(self, record):
        raise ValueError("On-demand workflow records use their dedicated schema")


class ImageryCatalog(ManualWorkflow):
    source_id, name = "imagery_catalog", "Sentinel-2 and NASA OPERA catalogs (on demand)"
    homepage = "https://earth-search.aws.element84.com/"
    limitation = "Acquisition-dated catalog records; protected raster assets can require an Earthdata token"


class PassiveRecon(ManualWorkflow):
    source_id, name = "passive_recon", "Passive DNS, RDAP, CT, Wikidata and OFAC lookups (on demand)"
    homepage = "https://www.iana.org/"
    limitation = (
        "Third-party public records and candidate matches; no target scanning or ownership conclusion"
    )


class PublishedAssessments(Wastewater):
    source_id, name = (
        "published_assessments",
        "Authorized published flood, disturbance and emergency assessments",
    )
    homepage = "https://mapping.emergency.copernicus.eu/"
    requirement = "published_assessments_url"
    limitation = (
        "Published assessment geometry and stated method, not a locally detected event or damage estimate"
    )

    def access(self):
        return Feed.access(self) or (
            None
            if self.settings.published_assessments_license
            else "Record OSINT_PUBLISHED_ASSESSMENTS_LICENSE"
        )

    async def fetch(self, http):
        return array(await http.json("GET", self.settings.published_assessments_url), "features")

    def normalize(self, r):
        p = r["properties"]
        if not p.get("method") or not p.get("product_type"):
            raise ValueError("Assessments require product type and stated method")
        if p.get("allow_download") is False:
            raise ValueError("Provider prohibits downloading this record")
        return self.make(
            r.get("id") or p["id"],
            p["title"],
            observed=instant(p["acquired_at"]),
            shape=geometry(r["geometry"]),
            tags=["published-assessment"],
            url=p["source_url"],
            sensor={
                "product_type": p["product_type"],
                "method": p["method"],
                "permission_basis": self.settings.published_assessments_license,
                "freshness_seconds": 604800,
            },
        )


def expanded_feeds(settings):
    providers = [
        cls(settings)
        for cls in [
            Feodo,
            URLhaus,
            NWS,
            SWPC,
            Caltrans,
            NYCCameras,
            SingaporeCameras,
            Amtraker,
            Digitraffic,
            KiwiSDR,
            PSKReporter,
            TinyGS,
            Volcanoes,
            RIPEAtlas,
            OpenAQ,
            GFWEvents,
            PowerPlants,
            Wastewater,
            PublishedAssessments,
            ImageryCatalog,
            PassiveRecon,
        ]
    ]
    providers.extend(ReferenceFeed(settings, r) for r in settings.reference_feeds[:20])
    provider = RSS(
        settings,
        source_id="euvsdisinfo",
        name="EUvsDisinfo published narratives",
        category="geopolitical",
        url="https://euvsdisinfo.eu/feed/",
        publisher_country=None,
        usage_notes="EUvsDisinfo's editorial assessments; attributed reporting, not neutral truth labels",
    )
    provider.initial_enabled = "euvsdisinfo" in settings.expansion_enabled
    providers.append(provider)
    return providers
