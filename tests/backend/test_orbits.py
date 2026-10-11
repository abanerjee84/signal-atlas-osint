import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from backend.orbital_catalog import mission_metadata
from scripts.collect_orbits import SOURCES, collect_orbits, collect_orbits_locked, parse_omm, parse_tle
from scripts.collection_status import write_status

FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "orbital-elements.json").read_text())


def test_elements_are_checked_for_checksum_epoch_and_catalogue():
    item = FIXTURE["items"][0]
    now = datetime.fromisoformat(item["epoch"]) + timedelta(hours=1)
    text = f"{item['name']}\n\n{item['tle1']}\n{item['tle2']}\n"
    assert parse_tle(text, "CelesTrak", now)[0]["catalog_id"] == item["catalog_id"]
    assert not parse_tle(text, "CelesTrak", now + timedelta(days=30))
    broken = item["tle1"][:68] + str((int(item["tle1"][68]) + 1) % 10)
    assert not parse_tle(text.replace(item["tle1"], broken), "CelesTrak", now)
    assert not parse_tle("<html>Unavailable</html>", "CelesTrak", now)


def test_download_failure_preserves_good_elements_and_throttles_retries(tmp_path):
    (tmp_path / "public").mkdir()
    cache = tmp_path / "data" / "run"
    cache.mkdir(parents=True)
    now = datetime.fromisoformat(FIXTURE["items"][0]["epoch"]) + timedelta(hours=1)
    write_status(cache / "orbital-sources.json", {"CelesTrak": {"items": FIXTURE["items"]}})
    with patch("scripts.collect_orbits.urllib.request.urlopen", side_effect=OSError("offline")) as download:
        first = collect_orbits(tmp_path, now)
        second = collect_orbits(tmp_path, now + timedelta(minutes=1))
    assert download.call_count == len(SOURCES)  # One attempt per feed; second pass makes no requests.
    assert len(first["items"]) == len(FIXTURE["items"]) == len(second["items"])
    assert all(row["state"] == "unavailable" for row in second["sources"])


def test_workers_share_a_lease_and_release_it_on_failure():
    database = Mock()
    database.lock.return_value = False
    with patch("scripts.collect_orbits.collect_orbits") as download:
        assert collect_orbits_locked(database) is None
        download.assert_not_called()
    database.lock.return_value = True
    with patch("scripts.collect_orbits.collect_orbits", side_effect=OSError("locked file")):
        import pytest

        with pytest.raises(OSError):
            collect_orbits_locked(database)
    database.unlock.assert_called_once()
    assert database.unlock.call_args.args == database.lock.call_args.args[:2]


MILITARY = json.loads((Path(__file__).parents[1] / "fixtures" / "military-elements.json").read_text())


def test_omm_supports_new_catalogue_ids_and_rejects_impossible_or_stale_elements():
    sample = MILITARY["items"][0]["omm"]
    now = datetime.fromisoformat(sample["EPOCH"]).replace(
        tzinfo=datetime.fromisoformat(FIXTURE["items"][0]["epoch"]).tzinfo
    )
    six_digit = {**sample, "NORAD_CAT_ID": 100123, "OBJECT_NAME": "Synthetic military payload"}
    parsed = parse_omm(json.dumps([six_digit]), "CelesTrak Military", now)
    assert parsed[0]["catalog_id"] == 100123
    assert parsed[0]["role"] == "military"
    assert parsed[0]["operator"] == "Not specified"
    for change in [
        {"MEAN_MOTION": float("nan")},
        {"ECCENTRICITY": 1},
        {"NORAD_CAT_ID": True},
        {"OBJECT_NAME": "Synthetic payload R/B"},
        {"INCLINATION": 181},
    ]:
        assert not parse_omm(json.dumps([{**six_digit, **change}]), "CelesTrak Military", now)
    assert not parse_omm(json.dumps([six_digit]), "CelesTrak Military", now + timedelta(days=30))
    assert not parse_omm(json.dumps([six_digit]), "CelesTrak Military", now - timedelta(days=3))


def test_observer_payloads_retain_attribution_and_exclude_rocket_bodies():
    item = next(row for row in MILITARY["items"] if row["source"] == "McCants observers")
    now = datetime.fromisoformat(item["epoch"]) + timedelta(hours=1)
    text = f"{item['name']}\n{item['tle1']}\n{item['tle2']}\n"
    parsed = parse_tle(text, item["source"], now)[0]
    assert parsed["role"] == "military"
    assert parsed["element_basis"] == "Observer-derived elements"
    assert parsed["mission_basis"] == "Observer identification"
    assert parsed["operator_country"] == "US"
    assert not parse_tle(text.replace(item["name"], item["name"] + " r"), item["source"], now)


def test_origin_belongs_to_operator_not_ground_position_or_launch_site():
    assert mission_metadata("25544", "ISS", "CelesTrak")["operator_country"] == "INT"
    assert mission_metadata("48274", "Tiangong", "CelesTrak")["operator_country"] == "CN"
    assert mission_metadata("100123", "PRAETORIAN SDA_601", "CelesTrak Military")["operator_country"] == "US"
    unknown = mission_metadata("100123", "Unidentified military payload", "CelesTrak Military")
    assert "operator_country" not in unknown


def test_http_rejection_stops_future_queries_until_intervention(tmp_path):
    import urllib.error

    now = datetime.fromisoformat(FIXTURE["items"][0]["epoch"])
    with patch(
        "scripts.collect_orbits.urllib.request.urlopen",
        side_effect=urllib.error.HTTPError("https://example.org", 403, "blocked", {}, None),
    ) as download:
        collect_orbits(tmp_path, now)
        collect_orbits(tmp_path, now + timedelta(days=1))
    assert download.call_count == len(SOURCES)
