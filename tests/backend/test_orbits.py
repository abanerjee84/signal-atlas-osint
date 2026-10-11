import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.collect_orbits import collect_orbits, collect_orbits_locked, parse_tle
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
    assert download.call_count == 2  # One attempt per provider, never a per-satellite request.
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
