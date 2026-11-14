import asyncio
import json
import urllib.error

import pytest

from backend.aircraft_details import CALLS, DB, AircraftLookup, photo_details


def test_callsign_join_rejects_namesakes_and_keeps_only_identity(tmp_path):
    client = AircraftLookup(tmp_path)
    sources = {
        CALLS + "TEST123": {"ac": [
            {"hex": "aaaaaa", "flight": "TEST123", "r": "WRONG", "lat": 90},
            {"hex": "abcdef", "flight": " OTHER ", "r": "WRONG"},
            {"hex": "abcdef", "flight": " TEST123 ", "r": "N123", "t": "P8", "desc": "Poseidon", "dbFlags": 1, "lat": 80, "lon": 20},
        ]},
        DB + "A.js": {"BCDEF": ["N123", "P8", "10", "Poseidon"]},
        DB + "icao_aircraft_types2.js": {"P8": ["Boeing P-8", "L2J"]},
        DB + "operators.js": {},
    }
    client.json = lambda url, _: sources[url]
    resolved = client.resolve([("abcdef", "TEST123")])
    details = client.metadata("abcdef", "TEST123", resolved["abcdef"])
    assert details["registration"] == "N123" and details["military"] is True
    assert details["identity_basis"] == "callsign_and_icao"
    assert not {"latitude", "longitude", "lat", "lon", "altitude", "speed", "time_key"} & details.keys()
    assert client.resolve([("bbbbbb", "TEST123")]) == {}


def test_registry_children_and_no_unknown_operator_inference(tmp_path):
    client = AircraftLookup(tmp_path)
    sources = {
        DB + "7.js": {"children": ["7C"]},
        DB + "7C.js": {"F9CD": ["A47-003", "P8", "10", "Boeing P-8A Poseidon"]},
        DB + "icao_aircraft_types2.js": {}, DB + "operators.js": {},
    }
    client.json = lambda url, _: sources[url]
    details = client.metadata("7cf9cd", "BFLO76")
    assert details["registration"] == "A47-003" and details["operator"] is None
    assert details["identity_basis"] == "opensky_icao_registry"


def test_access_rejection_backs_off_entire_host(tmp_path):
    client = AircraftLookup(tmp_path, now=lambda: 1000)
    requests = []
    def denied(request, **_):
        requests.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)
    client.opener.open = denied
    assert client.json(CALLS + "ONE1", 300) == {}
    assert client.json(CALLS + "TWO2", 300) == {}
    assert len(requests) == 1
    assert json.loads((tmp_path / "api.airplanes.live.json").read_text())["retry_at"] == 87400


def test_photos_require_exact_source_and_credit():
    photo = {"thumbnail_large": {"src": "https://t.plnspttrs.net/123/example_280.jpg"},
             "link": "https://www.planespotters.net/photo/123/aircraft", "photographer": "Test Photographer"}
    assert photo_details({"photos": [photo]})["credit"] == "Test Photographer"
    for changed in [{"photographer": ""}, {"link": "javascript:alert(1)"},
                    {"thumbnail_large": {"src": "https://t.plnspttrs.net.attacker.example/picture"}}]:
        assert photo_details({"photos": [{**photo, **changed}]}) is None
    assert photo_details({"photos": []}) is None


@pytest.mark.parametrize("active", [False, True])
async def test_enrichment_lane_obeys_visible_layer_demand(database, monkeypatch, active):
    from backend import aircraft_details, aviation_demand
    stopped = asyncio.Event()
    collections = []

    def requested(_):
        if not active:
            stopped.set()
        return active

    def collect(_):
        collections.append(1)
        stopped.set()

    monkeypatch.setattr(aviation_demand, "aviation_requested", requested)
    monkeypatch.setattr(aircraft_details, "collect_details", collect)
    await asyncio.wait_for(aircraft_details.details_loop(database, stopped, require_viewer=True), timeout=2)
    assert len(collections) == int(active)
