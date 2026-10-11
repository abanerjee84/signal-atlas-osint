import gzip
from datetime import datetime, timezone

import pytest

from backend.connectors.imperva_map import ImpervaMap, dataset_rows
from backend.connectors.threat_maps import BitdefenderMap, BunkerWebMap, table_attacks


def test_bottom_table_attacks_only_direction_and_repeated_snapshot_identity(settings, database):
    rows = [
        ["Sun 11 Oct 9:01:12 AM", "n/a", "attack", "Germany", "United States"],
        ["Sun 11 Oct 9:00:56 AM", "n/a", "ATTACK", "Bulgaria", "United States"],
        ["Sun 11 Oct 9:01:33 AM", "Win32.Test", "infection", "Sudan", "n/a"],
        ["Sun 11 Oct 9:01:34 AM", "n/a", "spam", "United States", "n/a"],
        ["Sun 11 Oct 9:01:35 AM", "n/a", "attack", "Unknown", "United States"],
    ]
    records = table_attacks(rows)
    assert len(records) == 2
    assert [r["observation_id"] for r in records] == [r["observation_id"] for r in table_attacks(rows)]
    item = BitdefenderMap(settings).normalize(records[0])
    assert (item.threat.traffic_origin_country, item.threat.traffic_target_country) == ("DE", "US")
    assert item.threat.provider_time == rows[0][0]
    assert item.occurred_at is None
    assert item.threat.actor == "Unknown actor"
    from backend.models import Filters

    for _ in range(2):
        for record in records:
            database.ingest(BitdefenderMap(settings).normalize(record))
    assert database.events(Filters(categories=["threat"]))["total"] == 2
    assert BunkerWebMap(settings).interval == 10 and BunkerWebMap(settings).sample_seconds < 10


def test_imperva_preserves_reporting_period_requests_and_pair_diversity(settings):
    data = b"US,US,Business,OWASP,RCE,Bot,50000,3\nUS,US,Business,OWASP,RCE,Bot,50000,3\nSG,IE,Retail,Automated Threat,Business Logic,Bot,81,3\nDE,CO,,OWASP,Data Leakage,Bot,7,3\n"
    rows = dataset_rows(gzip.compress(data), "2026-10-09", 3, 3)
    assert len(rows) == 3
    assert {row["attacker"] for row in rows} == {"US", "SG", "DE"}
    assert (
        rows[1]["observation_id"]
        == dataset_rows(gzip.compress(data), "2026-10-09", 3, 3)[1]["observation_id"]
    )
    item = ImpervaMap(settings).normalize(rows[1])
    assert item.published_at == datetime(2026, 10, 9, tzinfo=timezone.utc)
    assert item.occurred_at is None
    assert "2026-10-08 to 2026-10-09" in item.description
    assert "81 provider attack requests" in item.description
    assert "provider-requests:81" in item.tags
    assert item.threat.traffic_origin_country == "SG"
    assert item.threat.traffic_target_country == "IE"


def test_compressed_dataset_cannot_expand_without_bound():
    with pytest.raises(ValueError, match="Oversized"):
        dataset_rows(gzip.compress(b"x" * 8_388_609), "2026-10-09", 3)
    with pytest.raises(ValueError):
        dataset_rows(gzip.compress(b"US,US\n")[:-4], "2026-10-09", 3)
