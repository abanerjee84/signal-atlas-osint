import json

import pytest
import websockets

from backend.connectors import maritime as maritime_module
from backend.connectors.maritime import AISSTREAM, OPEN_SEAFEED, OPEN_WATERS, Maritime
from backend.models import Filters, utcnow


def ws_record(**overrides):
    record = {
        "mmsi": 232035583,
        "name": "Synthetic Ferry",
        "latitude": 50.9,
        "longitude": -1.3,
        "speed_kn": 12.5,
        "course_deg": 217.8,
        "type": 79,
        "upstream": "aisstream",
        "region": "North Atlantic / English Channel",
        "provider": "Open Waters AIS",
        "source_url": "https://openwaters.io/ais/",
        "observed_at": utcnow().isoformat(),
    }
    record.update(overrides)
    return record


def test_normalize_ws_record(settings):
    report = Maritime(settings).normalize(ws_record())
    assert report.external_id == "mmsi:232035583"
    assert report.title == "Vessel Synthetic Ferry"
    assert (report.latitude, report.longitude) == (50.9, -1.3)
    assert report.category == "maritime"
    assert "ais" in report.tags and "232035583" in report.tags
    assert report.vessel_course_deg == 217.8
    assert report.vessel_speed_kn == 12.5
    assert report.vessel_type == 79
    # MID 232 is a United Kingdom prefix in the ITU table.
    assert report.vessel_flag == "GB"


def test_normalize_flags_follow_the_mmsi_prefix(settings):
    provider = Maritime(settings)
    assert provider.normalize(ws_record(mmsi=355817000)).vessel_flag == "PA"
    assert provider.normalize(ws_record(mmsi=419001234)).vessel_flag == "IN"
    # An unassigned prefix stays unavailable rather than implying a country.
    assert provider.normalize(ws_record(mmsi=999999999)).vessel_flag is None
    # An unset type code is not silently relabelled as a reported type.
    assert provider.normalize(ws_record(type=None)).vessel_type is None


def test_normalize_ws_record_without_name(settings):
    report = Maritime(settings).normalize(ws_record(name=None))
    assert report.title == "Vessel 232035583"


def test_normalize_licensed_record_keeps_legacy_shape(settings):
    record = {
        "mmsi": 123,
        "name": None,
        "latitude": 1.0,
        "longitude": 2.0,
        "observed_at": "2026-10-17T10:00:00+00:00",
        "source_url": "https://example.org/feed",
    }
    report = Maritime(settings).normalize(record)
    assert report.external_id == "123:2026-10-17T10:00:00+00:00"


def test_access_is_open_for_free_sources(settings):
    assert Maritime(settings).access() is None
    metadata = Maritime(settings).metadata()
    assert len(metadata["world_strips"]) == 3
    assert len(metadata["fallback_regions"]) == 9
    assert metadata["per_cycle_cap"] == 1000


def test_parse_open_waters_position():
    frame = {
        "type": "event",
        "mmsi": 249651000,
        "msg_type": "PositionReport",
        "lat": 51.89,
        "lon": 4.33,
        "ship_type": 79,
        "source": "aisstream",
    }
    record = Maritime._parse_open_waters(frame)
    assert record["mmsi"] == 249651000
    assert (record["latitude"], record["longitude"]) == (51.89, 4.33)
    assert record["upstream"] == "aisstream"
    assert record["type"] == 79
    # The region stream documents no type field, so an absent one stays absent.
    assert Maritime._parse_open_waters({"type": "event", "mmsi": 1, "lat": 1.0, "lon": 2.0})["type"] is None


def test_parse_open_waters_ignores_control_frames():
    assert Maritime._parse_open_waters({"type": "welcome", "sub": "anon:x"}) is None
    assert Maritime._parse_open_waters({"type": "error", "error": "bbox not allowed"}) is None
    assert Maritime._parse_open_waters({"type": "event", "mmsi": -1, "lat": 1.0, "lon": 2.0}) is None


def test_parse_openseafeed_position():
    frame = {
        "Message": {
            "PositionReport": {
                "Latitude": 50.88,
                "Longitude": -1.30,
                "Sog": 2.8,
                "Cog": 217.8,
                "UserID": 232035583,
            }
        },
        "Metadata": {},
    }
    record = Maritime._parse_openseafeed(frame)
    assert record["mmsi"] == 232035583
    assert record["speed_kn"] == 2.8
    assert record["course_deg"] == 217.8
    assert record["type"] is None


def test_parse_openseafeed_static_report_carries_the_type():
    frame = {
        "Message": {"ShipStaticData": {"UserID": 232035583, "Type": 69, "Valid": True}},
        "Metadata": {},
    }
    record = Maritime._parse_openseafeed(frame)
    assert record["type"] == 69


def test_parse_openseafeed_rejects_invalid_mmsi():
    frame = {"Message": {"PositionReport": {"Latitude": 1.0, "Longitude": 2.0, "UserID": -5}}}
    assert Maritime._parse_openseafeed(frame) is None


def test_merge_keeps_name_and_latest_position():
    vessels = {}
    maritime_module.Maritime._merge(
        vessels,
        {
            "mmsi": 1,
            "name": None,
            "latitude": 10.0,
            "longitude": 20.0,
            "speed_kn": None,
            "course_deg": None,
            "upstream": None,
        },
    )
    maritime_module.Maritime._merge(
        vessels,
        {
            "mmsi": 1,
            "name": "Named Ship",
            "latitude": 11.0,
            "longitude": 21.0,
            "speed_kn": 5.0,
            "course_deg": 90.0,
            "type": 79,
            "upstream": None,
        },
    )
    vessel = vessels[1]
    assert vessel["name"] == "Named Ship"
    assert (vessel["latitude"], vessel["longitude"]) == (11.0, 21.0)
    assert vessel["speed_kn"] == 5.0
    assert vessel["type"] == 79


def test_select_records_caps_with_geographic_sample(settings):
    settings.max_records = 10
    coordinates = [(78 + index % 3, 20.0) for index in range(50)] + [(-120.0, 40.0), (150.0, -30.0)]
    records = [ws_record(mmsi=index, longitude=longitude, latitude=latitude) for index, (longitude, latitude) in enumerate(coordinates)]
    selected = Maritime(settings).select_records(records)
    assert len(selected) == 10
    assert len({record["mmsi"] for record in selected}) == 10


class FakeSocket:
    def __init__(self, frames):
        self.frames = list(frames)
        self.sent = []

    async def send(self, data):
        self.sent.append(json.loads(data))

    async def recv(self):
        if not self.frames:
            raise websockets.exceptions.ConnectionClosedOK(None, None)
        return self.frames.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def fake_connect(frames_by_url):
    """frames_by_url maps a URL to one frame queue per connection."""
    created = {}
    counters = {}

    def factory(url, **kwargs):
        queues = frames_by_url.get(url, [])
        index = counters.get(url, 0)
        counters[url] = index + 1
        socket = FakeSocket(queues[index] if index < len(queues) else [])
        created.setdefault(url, []).append(socket)
        return socket

    return factory, created


def seafeed_position(mmsi, lat, lon):
    return json.dumps(
        {
            "Message": {
                "PositionReport": {
                    "Latitude": lat,
                    "Longitude": lon,
                    "Sog": 6.0,
                    "Cog": 90.0,
                    "UserID": mmsi,
                }
            },
            "Metadata": {},
        }
    )


def aisstream_position(mmsi, lat, lon, ship_name=None, sog=None, cog=None):
    frame = {
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": mmsi, "ShipName": ship_name, "Latitude": lat, "Longitude": lon},
        "Message": {
            "PositionReport": {"UserID": mmsi, "Sog": sog, "Cog": cog, "Valid": True}
        },
    }
    # The service sends binary frames carrying UTF-8 JSON, so the parser has to
    # take bytes as well as str.
    return json.dumps(frame).encode()


def aisstream_static(mmsi, ship_name, ship_type=None):
    body = {"UserID": mmsi, "Name": ship_name}
    if ship_type is not None:
        body["Type"] = ship_type
    return json.dumps(
        {
            "MessageType": "ShipStaticData",
            "MetaData": {"MMSI": mmsi, "ShipName": ship_name},
            "Message": {"ShipStaticData": body},
        }
    )


def test_parse_aisstream_position_from_binary_frame():
    frame = aisstream_position(368207620, 25.7617, -80.1918, "EXAMPLE VESSEL", 12.4, 86.7)
    record = Maritime._parse_aisstream(frame)
    assert record["mmsi"] == 368207620
    assert record["name"] == "EXAMPLE VESSEL"
    assert (record["latitude"], record["longitude"]) == (25.7617, -80.1918)
    assert record["speed_kn"] == 12.4
    assert record["course_deg"] == 86.7


def test_parse_aisstream_trims_padded_ship_name():
    record = Maritime._parse_aisstream(aisstream_position(1, 1.0, 2.0, "ADELINE MARIE       "))
    assert record["name"] == "ADELINE MARIE"


def test_parse_aisstream_ignores_confirmation_and_other_types():
    confirmation = json.dumps(
        {"MessageType": "SubscriptionConfirmation", "Message": {"CompressionEnabled": True}}
    )
    assert Maritime._parse_aisstream(confirmation) is None
    assert (
        Maritime._parse_aisstream(
            json.dumps(
                {"MessageType": "BaseStationReport", "MetaData": {"MMSI": 1},
                 "Message": {"BaseStationReport": {"UserID": 1}}}
            )
        )
        is None
    )
    assert Maritime._parse_aisstream(b"not json") is None


def test_parse_aisstream_rejects_invalid_mmsi():
    assert Maritime._parse_aisstream(aisstream_position(0, 1.0, 2.0)) is None
    assert Maritime._parse_aisstream(aisstream_position(-5, 1.0, 2.0)) is None
    assert (
        Maritime._parse_aisstream(
            aisstream_position(1, 1.0, 2.0).replace(b'"MMSI": 1', b'"MMSI": "1"')
        )
        is None
    )


def test_parse_aisstream_captures_the_ship_type_static_report():
    record = Maritime._parse_aisstream(aisstream_static(368207620, "EXAMPLE VESSEL", 80))
    assert record["type"] == 80


def test_ship_type_codes_stay_in_the_reportable_ais_range():
    # 0 means "not available" in AIS, so it must not become a stored type.
    assert maritime_module._ship_type(0) is None
    assert maritime_module._ship_type(79) == 79
    assert maritime_module._ship_type(79.0) == 79
    assert maritime_module._ship_type(255) == 255
    assert maritime_module._ship_type(256) is None
    assert maritime_module._ship_type("79") is None
    assert maritime_module._ship_type(True) is None
    assert maritime_module._ship_type(None) is None


def test_aisstream_static_message_names_a_vessel_already_positioned():
    """A static report carries no position but still supplies the vessel name."""
    vessels = {}
    Maritime._merge(vessels, Maritime._parse_aisstream(aisstream_position(1, 10.0, 20.0)))
    assert vessels[1]["name"] is None
    assert vessels[1]["type"] is None
    Maritime._merge(vessels, Maritime._parse_aisstream(aisstream_static(1, "ZWERVER", 79)))
    assert vessels[1]["name"] == "ZWERVER"
    assert vessels[1]["type"] == 79
    assert (vessels[1]["latitude"], vessels[1]["longitude"]) == (10.0, 20.0)


def test_vessel_snapshot_retires_vessels_that_stopped_reporting(settings, database):
    """A vessel absent from the next cycle must not keep its last position."""
    provider = Maritime(settings)

    def titles():
        rows = database.events(Filters(categories=["maritime"]), limit=50)["items"]
        return sorted(event["title"] for event in rows)

    database.replace_vessel_snapshot(
        provider.source_id,
        [provider.normalize(ws_record(mmsi=111)), provider.normalize(ws_record(mmsi=222))],
    )
    # Both vessels share one MMSI-keyed identity per report, so each is distinct.
    assert len(titles()) == 2

    # Only one vessel reports in the next cycle.
    database.replace_vessel_snapshot(provider.source_id, [provider.normalize(ws_record(mmsi=111))])
    assert titles() == ["Vessel Synthetic Ferry"]

    rows = database.events(Filters(categories=["maritime"]), limit=50)
    assert rows["total"] == 1


def test_vessel_snapshot_refuses_foreign_records(settings, database):
    provider = Maritime(settings)
    foreign = provider.normalize(ws_record()).model_copy(update={"source_id": "other"})
    with pytest.raises(ValueError):
        database.replace_vessel_snapshot(provider.source_id, [foreign])


def test_vessel_snapshot_keeps_fleet_larger_than_one_statement(settings, database):
    """Deletes are chunk-bounded, so the surviving set must stay whole across chunks."""
    provider = Maritime(settings)
    fleet = [provider.normalize(ws_record(mmsi=304000000 + i)) for i in range(450)]
    database.replace_vessel_snapshot(provider.source_id, fleet)
    rows = database.events(Filters(categories=["maritime"]), limit=500)
    assert rows["total"] == 450
    flags = {event["vessel_flag"] for event in rows["items"]}
    assert flags == {"AG"}


def test_vessel_flag_and_type_are_stored_and_served(settings, database):
    provider = Maritime(settings)
    database.replace_vessel_snapshot(provider.source_id, [provider.normalize(ws_record())])
    row = database.events(Filters(categories=["maritime"]), limit=10)["items"][0]
    assert row["vessel_type"] == 79
    assert row["vessel_flag"] == "GB"
    # A later position-only refresh of the same vessel carries no type: the
    # stored observation keeps the last self-reported value instead of
    # forgetting it, while the flag state follows the current MMSI.
    positions_only = provider.normalize(ws_record(type=None, course_deg=5.0))
    database.replace_vessel_snapshot(provider.source_id, [positions_only])
    row = database.events(Filters(categories=["maritime"]), limit=10)["items"][0]
    assert row["vessel_type"] == 79
    assert row["vessel_flag"] == "GB"
    # A known vessel that re-appears under a different MMSI-flag combination
    # (unknown flag) is still stored as it reports.
    unknown = provider.normalize(ws_record(mmsi=999999999, type=None))
    database.replace_vessel_snapshot(provider.source_id, [unknown])
    row = database.events(Filters(categories=["maritime"]), limit=10)["items"][0]
    assert row["vessel_type"] is None
    assert row["vessel_flag"] is None


async def test_fetch_prefers_aisstream_when_a_key_is_configured(settings, monkeypatch):
    settings.aisstream_api_key = "synthetic-key"
    provider = Maritime(settings)
    provider._collect_seconds = 1
    factory, created = fake_connect(
        {
            AISSTREAM["url"]: [
                [aisstream_position(368207620, 25.7, -80.1, "EXAMPLE VESSEL", 12.4, 86.7)],
                [aisstream_position(232035583, 30.0, 10.0, "FERRY", 5.0, 90.0)],
                [aisstream_position(252012345, 10.0, 110.0, "TANKER", 1.0, 12.0)],
            ]
        }
    )
    monkeypatch.setattr(maritime_module.websockets, "connect", factory)
    records = await provider.fetch(None)
    assert {record["mmsi"] for record in records} == {368207620, 232035583, 252012345}
    assert all(record["provider"] == "AIS Stream" for record in records)
    assert all(record["region"] == "worldwide" for record in records)
    # The anonymous streams are not touched while the keyed primary works.
    assert OPEN_SEAFEED["url"] not in created
    subscription = created[AISSTREAM["url"]][0].sent[0]
    assert subscription["APIKey"] == "synthetic-key"
    assert subscription["FilterMessageTypes"] == ["PositionReport", "ShipStaticData"]
    assert created[AISSTREAM["url"]][0].sent[0]["BoundingBoxes"][0] == [[-90, -180], [90, -60]]


async def test_fetch_falls_back_to_openseafeed_when_aisstream_is_unavailable(settings, monkeypatch):
    settings.aisstream_api_key = "synthetic-key"
    provider = Maritime(settings)
    provider._collect_seconds = 1
    factory, created = fake_connect(
        {
            AISSTREAM["url"]: [[], [], []],
            OPEN_SEAFEED["url"]: [
                [seafeed_position(244650598, 51.0, -2.0)],
                [seafeed_position(232035583, 30.0, 10.0)],
                [seafeed_position(252012345, 10.0, 110.0)],
            ],
        }
    )
    monkeypatch.setattr(maritime_module.websockets, "connect", factory)
    records = await provider.fetch(None)
    assert len(records) == 3
    assert all(record["provider"] == "OpenSeaFeed" for record in records)
    assert AISSTREAM["url"] in created


async def test_fetch_never_opens_a_keyed_connection_without_a_key(settings, monkeypatch):
    provider = Maritime(settings)
    provider._collect_seconds = 1
    factory, created = fake_connect(
        {
            OPEN_SEAFEED["url"]: [
                [seafeed_position(244650598, 51.0, -2.0)],
                [seafeed_position(232035583, 30.0, 10.0)],
                [seafeed_position(252012345, 10.0, 110.0)],
            ]
        }
    )
    monkeypatch.setattr(maritime_module.websockets, "connect", factory)
    records = await provider.fetch(None)
    assert AISSTREAM["url"] not in created
    assert all(record["provider"] == "OpenSeaFeed" for record in records)


async def test_fetch_uses_openseafeed_worldwide_when_available(settings, monkeypatch):
    provider = Maritime(settings)
    provider._collect_seconds = 1
    factory, created = fake_connect(
        {
            OPEN_SEAFEED["url"]: [
                [seafeed_position(244650598, 51.0, -2.0)],
                [seafeed_position(232035583, 30.0, 10.0)],
                [seafeed_position(252012345, 10.0, 110.0)],
            ]
        }
    )
    monkeypatch.setattr(maritime_module.websockets, "connect", factory)
    records = await provider.fetch(None)
    assert {record["mmsi"] for record in records} == {244650598, 232035583, 252012345}
    assert all(record["provider"] == "OpenSeaFeed" for record in records)
    assert all(record["region"] == "worldwide" for record in records)
    assert OPEN_WATERS["url"] not in created
    boxes = [socket.sent[0]["BoundingBoxes"][0] for socket in created[OPEN_SEAFEED["url"]]]
    assert boxes == [
        [[-90, -180], [90, -60]],
        [[-90, -60], [90, 60]],
        [[-90, 60], [90, 180]],
    ]


async def test_fetch_worldwide_survives_one_failed_strip(settings, monkeypatch):
    provider = Maritime(settings)
    provider._collect_seconds = 1
    factory, _ = fake_connect(
        {
            OPEN_SEAFEED["url"]: [
                [],
                [seafeed_position(232035583, 30.0, 10.0)],
                [seafeed_position(252012345, 10.0, 110.0)],
            ]
        }
    )
    monkeypatch.setattr(maritime_module.websockets, "connect", factory)
    records = await provider.fetch(None)
    assert {record["mmsi"] for record in records} == {232035583, 252012345}


async def test_fetch_falls_back_to_open_waters(settings, monkeypatch):
    frames = [
        json.dumps(
            {
                "type": "event",
                "mmsi": 249651000,
                "msg_type": "PositionReport",
                "lat": 51.89,
                "lon": 4.33,
                "source": "aisstream",
            }
        )
    ]
    provider = Maritime(settings)
    provider._collect_seconds = 1
    factory, created = fake_connect(
        {OPEN_SEAFEED["url"]: [[], [], []], OPEN_WATERS["url"]: [frames]}
    )
    monkeypatch.setattr(maritime_module.websockets, "connect", factory)
    records = await provider.fetch(None)
    assert len(records) == 1
    assert records[0]["provider"] == "Open Waters AIS"
    assert created[OPEN_WATERS["url"]][0].sent[0]["type"] == "subscribe"


async def test_fetch_raises_when_both_streams_fail(settings, monkeypatch):
    provider = Maritime(settings)
    provider._collect_seconds = 1
    factory, _ = fake_connect(
        {OPEN_SEAFEED["url"]: [[], [], []], OPEN_WATERS["url"]: [[]]}
    )
    monkeypatch.setattr(maritime_module.websockets, "connect", factory)
    with pytest.raises(Exception, match="AIS stream"):
        await provider.fetch(None)
