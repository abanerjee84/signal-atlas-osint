import json
import urllib.error

from backend.vessel_details import (
    DETAIL,
    SEARCH,
    RegistryLookup,
    identity_from_values,
    safe_mmsi,
)


def test_identity_flattens_registry_entry():
    payload = {
        "registryInfo": [
            {"shipname": "FIRST SHIP", "flag": "GB", "transmissionDateTo": "2020-01-01"},
            {"shipname": "SECOND SHIP", "imo": "1234567", "lengthM": 150,
             "tonnageGt": 20000, "callsign": "TESTFX",
             "transmissionDateTo": "2025-06-01"},
        ],
        "registryOwners": [
            {"name": "Example Shipping Ltd", "flag": "GB", "yearFrom": 2020,
             "yearTo": None},
        ],
        "shiptypes": [{"name": "Tanker"}],
        "mmsis": ["232035583"],
    }
    identity = identity_from_values(payload)
    assert identity["shipname"] == "SECOND SHIP"
    assert identity["imo"] == "1234567"
    assert identity["callsign"] == "TESTFX"
    assert identity["length_m"] == 150
    assert identity["tonnage_gt"] == 20000
    assert identity["types"] == ["Tanker"]
    assert identity["owners"][0]["name"] == "Example Shipping Ltd"
    assert identity["identity_basis"] == "registry_and_ais"


def test_identity_ignores_malformed_payload():
    assert identity_from_values({"registryInfo": []}) is None
    assert identity_from_values({}) is None
    assert identity_from_values(None) is None


def test_mmsi_validation():
    assert safe_mmsi("232035583") == "232035583"
    assert safe_mmsi("0") is None
    assert safe_mmsi("abc") is None
    assert safe_mmsi("") is None


def test_resolve_rejects_unmatched_and_namesakes(tmp_path):
    client = RegistryLookup(tmp_path, "token")
    sources = {
        SEARCH + "232035583": {"entries": [{"mmsi": 232035583, "id": "abc123"}]},
        DETAIL + "abc123": {"vessels": [
            {"mmsi": 111111111, "registryInfo": [{"shipname": "OTHER"}]},
            {"mmsi": 232035583, "registryInfo": [{"shipname": "MATCH"}]},
        ]},
    }
    client.json = lambda url, ttl: sources[url]
    result = client.resolve("232035583")
    assert result["shipname"] == "MATCH"


def test_resolve_returns_unavailable_when_no_match(tmp_path):
    client = RegistryLookup(tmp_path, "token")
    client.json = lambda url, ttl: {"entries": [{"mmsi": 999999999, "id": "x"}]}
    result = client.resolve("232035583")
    assert result["available"] is False
    assert result["mmsi"] == "232035583"


def test_access_rejection_backs_off_host(tmp_path):
    client = RegistryLookup(tmp_path, "token", now=lambda: 1000)
    requests = []

    def denied(request, **_):
        requests.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

    client.opener.open = denied
    assert client.json(SEARCH + "232035583", 300) == {}
    assert len(requests) == 1
    assert (
        json.loads((tmp_path / "gateway.api.globalfishingwatch.org.json").read_text())[
            "retry_at"
        ]
        == 87400
    )
