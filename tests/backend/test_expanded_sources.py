from datetime import timedelta

import pytest

from backend.connectors.expanded import (
    NWS,
    Caltrans,
    Digitraffic,
    Feodo,
    GFWEvents,
    KiwiSDR,
    OpenAQ,
    PSKReporter,
    PublishedAssessments,
    ReferenceFeed,
    SingaporeCameras,
    TinyGS,
    URLhaus,
    Wastewater,
    maidenhead,
)
from backend.connectors.registry import connectors
from backend.models import Filters, stamp, utcnow
from backend.monitoring import frame
from backend.worker import collect


class HTTP:
    def __init__(self, data):
        self.data = data
        self.calls = []

    async def json(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.data

    async def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.data


def test_registry_and_access_requirements(settings):
    providers = {p.source_id: p for p in connectors(settings)}
    assert {
        "feodo",
        "urlhaus",
        "nws_alerts",
        "swpc",
        "caltrans_cameras",
        "nyc_cameras",
        "singapore_cameras",
        "amtraker",
        "digitraffic",
        "kiwisdr",
        "psk_reporter",
        "tinygs",
        "volcanoes",
        "ripe_atlas",
        "openaq",
        "gfw_events",
        "wri_power_plants",
        "wastewater_export",
        "published_assessments",
        "imagery_catalog",
        "passive_recon",
        "euvsdisinfo",
    } <= set(providers)
    assert providers["feodo"].initial_enabled
    for source in [
        "urlhaus",
        "openaq",
        "gfw_events",
        "tinygs",
        "psk_reporter",
        "wastewater_export",
        "published_assessments",
    ]:
        assert providers[source].access()
    assert providers["imagery_catalog"].manual and providers["passive_recon"].manual


def test_feodo_uses_current_port_schema_preserves_times_and_never_invents_geography(settings):
    r = Feodo(settings).normalize(
        {
            "ip_address": "8.8.8.8",
            "port": 443,
            "malware": "Synthetic fixture",
            "first_seen": "2026-01-01 00:00:00",
            "last_online": "2026-01-02 00:00:00",
            "country": "US",
            "status": "offline",
        }
    )
    assert r.cyber_observation.port == 443 and r.cyber_observation.first_seen.year == 2026
    assert r.latitude is None and r.country_code is None and r.threat is None
    assert r.raw["monitoring"]["provider_status"] == "offline"
    assert "c2" in r.tags
    assert r.occurred_at > utcnow() - timedelta(minutes=1)
    with pytest.raises(ValueError):
        Feodo(settings).normalize({"ip_address": "127.0.0.1", "port": 443})


async def test_urlhaus_credentials_stay_in_provider_header(settings):
    settings.urlhaus_auth_key = "synthetic-auth-secret"
    http = HTTP(
        {
            "urls": [
                {
                    "id": 12,
                    "url": "https://example.org/malware",
                    "dateadded": "2026-01-01 00:00:00",
                    "threat": "malware_download",
                }
            ]
        }
    )
    feed = URLhaus(settings)
    rows = await feed.fetch(http)
    r = feed.normalize(rows[0])
    assert http.calls[0][1]["headers"] == {"Auth-Key": "synthetic-auth-secret"}
    assert "synthetic-auth-secret" not in r.model_dump_json()
    assert r.cyber_observation.indicator_type == "url" and r.latitude is None


def test_nws_warning_retains_geometry_and_validity_without_a_fake_centroid(settings):
    now = utcnow()
    g = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    r = NWS(settings).normalize(
        {
            "id": "urn:synthetic:alert",
            "geometry": g,
            "properties": {
                "sent": stamp(now),
                "expires": stamp(now + timedelta(hours=1)),
                "event": "Flood Warning",
                "headline": "Synthetic official warning fixture",
                "description": "Test only",
                "severity": "Severe",
                "certainty": "Observed",
            },
        }
    )
    assert r.latitude is None and r.raw["monitoring"]["geometry"] == g
    assert r.raw["monitoring"]["expires_at"] > stamp(now)
    assert r.category == "environment"


async def test_camera_snapshots_are_reference_history_not_incident_counts(settings, database):
    http = HTTP(
        {
            "items": [
                {
                    "timestamp": stamp(),
                    "cameras": [
                        {
                            "camera_id": "fixture",
                            "image": "https://example.org/camera.jpg",
                            "timestamp": stamp(),
                            "location": {"latitude": 1.4, "longitude": 103.7},
                        }
                    ],
                }
            ]
        }
    )
    result = await collect(SingaporeCameras(settings), database, http)
    assert result["stored"] == 1 and result["state"] == "ok"
    assert database.events(Filters())["total"] == 0
    r = frame(database, utcnow())["items"][0]
    assert r["sensor"]["reference"] and r["sensor"]["media_url"] == "https://example.org/camera.jpg"


async def test_caltrans_ids_include_the_district_and_bad_districts_are_rejected(settings):
    settings.caltrans_districts = [4]
    http = HTTP(
        {
            "data": [
                {
                    "cctv": {
                        "index": "1",
                        "location": {"locationName": "Fixture", "latitude": "37", "longitude": "-122"},
                        "imageData": {"static": {"currentImageURL": "https://example.org/camera.jpg"}},
                    }
                }
            ]
        }
    )
    rows = await Caltrans(settings).fetch(http)
    assert rows[0]["id"] == "d4:1"
    assert Caltrans(settings).normalize(rows[0]).latitude == 37
    settings.caltrans_districts = [99]
    with pytest.raises(ValueError):
        await Caltrans(settings).fetch(http)


async def test_digitraffic_retains_official_time_and_units(settings):
    http = HTTP(
        [
            {
                "departureDate": "2026-01-01",
                "trainNumber": 99,
                "timestamp": stamp(),
                "speed": 62,
                "location": {"coordinates": [24.9, 60.2]},
            }
        ]
    )
    row = (await Digitraffic(settings).fetch(http))[0]
    r = Digitraffic(settings).normalize(row)
    assert r.raw["monitoring"]["speed_unit"] == "km/h" and r.longitude == 24.9
    assert Digitraffic(settings).fast_monitoring


@pytest.mark.parametrize(
    "grid,expected", [("AA00", (-179, -89.5)), ("JJ00", (1, 0.5)), ("FM19EC", (-77.625, 39.104166666666664))]
)
def test_maidenhead_is_a_grid_centre(grid, expected):
    assert maidenhead(grid) == pytest.approx(expected)


async def test_psk_xml_is_bounded_and_preserves_reception_time(settings):
    settings.psk_callsign = "TEST/1"
    http = HTTP(
        b'<receptionReports><receptionReport receiverLocator="JJ00" senderCallsign="TEST/1" receiverCallsign="TEST/2" frequency="14074000" flowStartSeconds="1794000000" mode="FT8" sNR="-10" /></receptionReports>'
    )
    feed = PSKReporter(settings)
    row = (await feed.fetch(http))[0]
    r = feed.normalize(row)
    assert r.raw["monitoring"]["snr_db"] == -10 and r.raw["monitoring"]["frequency_hz"] == 14074000
    assert r.longitude == 1 and r.latitude == 0.5
    with pytest.raises(ValueError):
        maidenhead("not-a-grid")


def test_satellite_receptions_require_provider_time_and_do_not_propagate_a_position(settings):
    feed = TinyGS(settings)
    r = feed.normalize({"id": "fixture", "name": "Fixture satellite", "timestamp": stamp(), "noradId": 123})
    assert r.latitude is None and r.raw["monitoring"]["norad_id"] == 123
    with pytest.raises(ValueError):
        feed.normalize({"name": "no timestamp"})


async def test_kiwi_directory_is_parsed_as_json_without_executing_javascript(settings):
    http = HTTP(
        b'var receivers = [{"gps":"(30.1, -110.2)","url":"https://example.org/receiver","name":"Fixture"}];'
    )
    feed = KiwiSDR(settings)
    r = feed.normalize((await feed.fetch(http))[0])
    assert r.latitude == 30.1 and r.longitude == -110.2 and "radio" in r.tags


async def test_openaq_uses_latest_measurements_not_location_lastvalue(settings):
    settings.openaq_api_key = "synthetic-key"
    settings.openaq_location_ids = [7]

    class AQ:
        async def json(self, method, url, **kwargs):
            assert kwargs["headers"]["X-API-Key"] == "synthetic-key"
            if url.endswith("/sensors"):
                return {"results": [{"id": 8, "parameter": {"name": "pm25", "units": "µg/m³"}}]}
            return {
                "results": [
                    {
                        "sensorsId": 8,
                        "value": 14.2,
                        "datetime": {"utc": stamp()},
                        "coordinates": {"latitude": 10, "longitude": 20},
                    }
                ]
            }

    feed = OpenAQ(settings)
    r = feed.normalize((await feed.fetch(AQ()))[0])
    assert r.raw["monitoring"]["value"] == 14.2 and r.raw["monitoring"]["unit"] == "µg/m³"
    assert r.external_id == "7:8" and "synthetic-key" not in r.model_dump_json()


def test_gfw_events_keep_apparent_activity_and_avoid_attribution(settings):
    r = GFWEvents(settings).normalize(
        {
            "id": "fixture",
            "type": "ENCOUNTER",
            "start": stamp(utcnow() - timedelta(days=3)),
            "end": stamp(utcnow() - timedelta(days=2)),
            "position": {"lat": 10, "lon": 20},
            "vessel": {"id": "vessel1", "ssvid": "123456789"},
        }
    )
    assert r.raw["monitoring"]["mmsi"] == "123456789" and "vessel-activity" in r.tags
    assert r.threat is None and "do not establish illegal" in r.description


def test_reference_import_keeps_geometry_version_and_rights(settings):
    feed = ReferenceFeed(
        settings,
        {
            "source_id": "fixture_assets",
            "name": "Fixture assets",
            "url": "https://example.org/assets",
            "license": "Authorized fixture",
            "version": "2026-01",
            "kind": "cable",
        },
    )
    shape = {"type": "LineString", "coordinates": [[1, 2], [3, 4]]}
    r = feed.normalize({"id": "cable-1", "geometry": shape, "properties": {"name": "Fixture cable"}})
    assert r.latitude is None and r.raw["monitoring"]["geometry"] == shape
    assert r.raw["monitoring"]["reference_version"] == "2026-01"
    with pytest.raises(ValueError):
        feed.normalize(
            {"id": "x", "geometry": shape, "properties": {"name": "Restricted", "allow_download": False}}
        )


def test_wastewater_requires_sample_evidence_and_respects_download_restrictions(settings):
    settings.wastewater_license = "Synthetic authorized export"
    row = {
        "geometry": {"type": "Point", "coordinates": [1, 2]},
        "properties": {
            "sample_id": "sample-1",
            "analyte": "Synthetic analyte",
            "sampled_at": stamp(),
            "value": None,
            "unit": "copies/g",
            "quality": "non-detect",
            "source_url": "https://example.org/lab",
        },
    }
    r = Wastewater(settings).normalize(row)
    assert r.raw["monitoring"]["value"] is None and r.raw["monitoring"]["quality"] == "non-detect"
    row["properties"]["allow_download"] = False
    with pytest.raises(ValueError):
        Wastewater(settings).normalize(row)


def test_published_assessments_require_a_method_and_are_not_fake_local_detections(settings):
    row = {
        "id": "product1",
        "geometry": {"type": "Point", "coordinates": [10, 20]},
        "properties": {
            "id": "product1",
            "title": "Synthetic published assessment",
            "acquired_at": stamp(),
            "source_url": "https://example.org/product",
            "product_type": "water_extent",
            "method": "Published classification",
        },
    }
    r = PublishedAssessments(settings).normalize(row)
    assert r.raw["monitoring"]["method"] == "Published classification"
    assert r.latitude is None
    row["properties"].pop("method")
    with pytest.raises(ValueError):
        PublishedAssessments(settings).normalize(row)
