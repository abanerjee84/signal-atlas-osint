"""Synthetic fixtures verify attribution boundaries; never load live credentials or feeds."""

import hashlib
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.advanced.processing import index_batch, stable
from backend.advanced.providers import lookup
from backend.advanced.repository import Repository
from backend.advanced.threats import match_reports, refresh_catalog, schedule, store_catalog
from backend.config import Settings
from backend.connectors.base import ProviderError
from backend.connectors.cyber_feeds import cyber_feeds
from backend.main import create_app
from backend.models import Report, utcnow

ACTOR = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
STIX = "33333333-3333-4333-8333-333333333333"
MALWARE = "44444444-4444-4444-8444-444444444444"


def galaxy(version=1, extra=False):
    values = [
        {
            "uuid": ACTOR,
            "value": "Fixture Group",
            "description": "Synthetic actor reference",
            "meta": {
                "synonyms": ["Fixture APT", "Shared Alias"],
                "refs": ["https://attack.mitre.org/groups/G9999/"],
            },
        }
    ]
    if extra:
        values.append({"uuid": OTHER, "value": "Separate Fixture", "meta": {"synonyms": ["Shared Alias"]}})
    return {"version": version, "values": values}


def bundle(revoked=False):
    actor = {
        "id": "intrusion-set--" + STIX,
        "type": "intrusion-set",
        "name": "Fixture APT",
        "aliases": ["Fixture Group"],
        "external_references": [
            {
                "source_name": "mitre-attack",
                "external_id": "G9999",
                "url": "https://attack.mitre.org/groups/G9999/",
            }
        ],
    }
    malware = {"id": "malware--" + MALWARE, "type": "malware", "name": "Fixture Malware", "revoked": revoked}
    relation = {
        "id": "relationship--" + OTHER,
        "type": "relationship",
        "source_ref": actor["id"],
        "target_ref": malware["id"],
        "relationship_type": "uses",
        "description": "Synthetic documented usage, historical reference",
        "external_references": [{"url": "https://example.org/fixture-report"}],
    }
    return {"type": "bundle", "objects": [actor, malware, relation]}


@pytest.fixture
def threat_workspace(tmp_path):
    settings = Settings(
        _env_file=None,
        database=tmp_path / "threat.sqlite3",
        admin_token="fixture-token",
        threat_catalogs_enabled=False,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer fixture-token"
        yield client, Repository(app.state.database), settings


def store(repo, sid, data):
    return store_catalog(repo, sid, data, hashlib.sha256(json.dumps(data).encode()).hexdigest())


def test_shared_catalog_ids_deduplicate_without_creating_events(threat_workspace):
    client, repo, _ = threat_workspace
    data = galaxy()
    store(repo, "misp_galaxy", data)
    store(repo, "malpedia_actors", {"Fixture Group": data["values"][0]})
    actors = client.get("/api/v1/cyber/actors").json()
    assert actors["meta"]["total"] == 1
    assert set(actors["data"][0]["catalog_sources"]) == {"misp_galaxy", "malpedia_actors"}
    assert repo.one("SELECT COUNT(*) n FROM external_records")["n"] == 0
    assert repo.one("SELECT COUNT(*) n FROM events")["n"] == 0
    assert client.get("/api/v1/cyber/actors?q=Fixture%20APT").json()["meta"]["total"] == 1


def test_documented_mitre_id_resolves_and_edges_keep_catalog_evidence(threat_workspace):
    client, repo, _ = threat_workspace
    store(repo, "misp_galaxy", galaxy())
    store(repo, "mitre_attack", bundle())
    eid = stable("threat-reference", ACTOR)
    result = client.get(f"/api/v1/graph/neighborhood/{eid}").json()["data"]
    assert len(result["nodes"]) == 2
    edge = result["edges"][0]
    assert edge["type"] == "catalog_uses" and edge["status"] == "reported"
    assert edge["evidence_ids"] == []
    assert edge["catalog_evidence"][0]["refs"] == ["https://example.org/fixture-report"]
    assert client.get("/api/v1/cyber/actors").json()["meta"]["total"] == 1


def test_alias_alone_never_merges_identities(threat_workspace):
    client, repo, _ = threat_workspace
    store(repo, "misp_galaxy", galaxy(extra=True))
    assert client.get("/api/v1/cyber/actors?q=Shared%20Alias").json()["meta"]["total"] == 2


def test_case_snapshot_keeps_catalog_version_and_provenance(threat_workspace):
    client, repo, _ = threat_workspace
    store(repo, "misp_galaxy", galaxy(version=1))
    case_id = client.post(
        "/api/v1/cases", json={"title": "Actor reference review", "description": "Fixture"}
    ).json()["data"]["id"]
    saved = repo.attach(case_id, "entity", stable("threat-reference", ACTOR))
    store(repo, "misp_galaxy", galaxy(version=2))
    frozen = repo.one("SELECT snapshot FROM case_evidence WHERE id=?", (saved["id"],))["snapshot"]
    assert frozen["catalog_profiles"][0]["version"] == "1"
    assert frozen["catalog_profiles"][0]["original_url"] and frozen["classification"] == "reference_knowledge"


def test_broad_catalog_group_cannot_merge_distinct_mitre_groups(threat_workspace):
    client, repo, _ = threat_workspace
    data = galaxy()
    data["values"][0]["meta"]["refs"].append("https://attack.mitre.org/groups/G9998/")
    store(repo, "misp_galaxy", data)
    stix = bundle()
    stix["objects"].append(
        {
            "id": "intrusion-set--" + OTHER,
            "type": "intrusion-set",
            "name": "Separate subgroup",
            "external_references": [{"source_name": "mitre-attack", "external_id": "G9998"}],
        }
    )
    store(repo, "mitre_attack", stix)
    assert client.get("/api/v1/cyber/actors").json()["meta"]["total"] == 3
    # Simulate a previously over-broad stored identity, then reconcile it on refresh.
    with repo.database.connect() as db:
        db.execute(
            "UPDATE threat_catalog_objects SET entity_id=? WHERE source_id='mitre_attack' AND type='threat_actor'",
            (stable("threat-reference", ACTOR),),
        )
    store(repo, "mitre_attack", stix)
    assert client.get("/api/v1/cyber/actors").json()["meta"]["total"] == 3
    edge = repo.one("SELECT * FROM relationships WHERE type='catalog_uses'")
    assert edge["from_id"] == stable("threat-reference", STIX)


def test_revoked_objects_and_removed_relations_leave_active_graph(threat_workspace):
    client, repo, _ = threat_workspace
    store(repo, "mitre_attack", bundle())
    store(repo, "mitre_attack", bundle(revoked=True))
    assert client.get("/api/v1/cyber/actors?type=malware").json()["meta"]["total"] == 0
    assert client.get("/api/v1/graph/relationships").json()["data"] == []
    assert repo.one("SELECT active FROM threat_catalog_objects WHERE type='malware'")["active"] == 0


def test_invalid_revision_retains_last_valid_snapshot(threat_workspace):
    _, repo, _ = threat_workspace
    store(repo, "misp_galaxy", galaxy())
    with pytest.raises(ValueError):
        store(repo, "misp_galaxy", {"values": [{"value": "Missing identity"}]})
    assert (
        repo.one("SELECT object_count FROM threat_catalog_state WHERE source_id='misp_galaxy'")[
            "object_count"
        ]
        == 1
    )
    assert repo.one("SELECT COUNT(*) n FROM threat_catalog_objects WHERE active=1")["n"] == 1


def test_name_mentions_word_boundaries_ambiguity_and_reprocessing(threat_workspace):
    _, repo, _ = threat_workspace
    store(repo, "misp_galaxy", galaxy(extra=True))
    for i, title in enumerate(
        [
            "Fixture APT and France appear in a public advisory",
            "Shared Alias mentioned in Germany",
            "Fixture APTExtra is a different string",
        ]
    ):
        repo.database.ingest(
            Report(
                source_id="ncsc",
                external_id=str(i),
                source_url=f"https://example.org/{i}",
                title=title,
                category="cyber",
                published_at=utcnow(),
                sentiment_kind="official",
            )
        )
    index_batch(repo.database)
    assert match_reports(repo) == 3
    assert match_reports(repo) == 0
    matches = repo.rows("SELECT * FROM threat_report_matches")
    assert len(matches) == 3
    assert sum(m["status"] == "ambiguous_alias" for m in matches) == 2
    edges = repo.rows("SELECT * FROM relationships WHERE type='actor_report_context'")
    assert len(edges) == 1 and "Does not establish actor responsibility" in edges[0]["basis"]
    store(repo, "misp_galaxy", galaxy(version=2))
    assert match_reports(repo) == 3
    assert not repo.rows("SELECT * FROM threat_report_matches WHERE status='ambiguous_alias'")


def test_disabled_catalogs_and_scheduling_are_explicit(threat_workspace):
    client, repo, settings = threat_workspace
    schedule(repo, settings)
    assert not repo.rows("SELECT * FROM investigation_jobs WHERE kind='threat_catalog'")
    assert client.post("/api/v1/cyber/catalogs/misp_galaxy/refresh").status_code == 409
    settings.threat_catalogs_enabled = True
    with repo.database.connect() as db:
        db.execute("UPDATE sources SET enabled=1 WHERE source_id='misp_galaxy'")
    schedule(repo, settings)
    schedule(repo, settings)
    assert len(repo.rows("SELECT * FROM investigation_jobs WHERE kind='threat_catalog'")) == 1
    client.headers.pop("Authorization")
    assert client.get("/api/v1/cyber/actors").status_code == 401
    assert client.post("/api/v1/cyber/catalogs/misp_galaxy/refresh").status_code == 401


async def test_failed_fetch_keeps_data_and_visible_error(threat_workspace):
    _, repo, settings = threat_workspace
    settings.threat_catalogs_enabled = True
    with repo.database.connect() as db:
        db.execute("UPDATE sources SET enabled=1 WHERE source_id='misp_galaxy'")
    store(repo, "misp_galaxy", galaxy())
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(403))
    ) as client:
        with pytest.raises(ProviderError):
            await refresh_catalog(repo, settings, client, "misp_galaxy")
    state = repo.one("SELECT * FROM threat_catalog_state WHERE source_id='misp_galaxy'")
    assert state["state"] == "error" and state["last_success"] and state["next_run"]
    assert repo.one("SELECT COUNT(*) n FROM threat_catalog_objects WHERE active=1")["n"] == 1


def test_etda_excludes_malformed_uuid_without_rewriting_identity(threat_workspace):
    client, repo, _ = threat_workspace
    data = {
        "last-db-change": "2025-08-16",
        "values": [
            {"uuid": ACTOR, "actor": "Fixture Group"},
            {"uuid": "d2fd8a6e-0f59-4f61-b42c-17b66cc17c9 1", "actor": "UNC2891"},
        ],
    }
    result = store_catalog(repo, "etda_actors", data, "fixture")
    assert result["rejected"] == 1
    rows = client.get("/api/v1/cyber/catalogs").json()["data"]
    state = next(row for row in rows if row["source_id"] == "etda_actors")
    assert state["object_count"] == 1 and state["state"] == "ok"
    assert state["validation_notes"][0]["name"] == "UNC2891"
    assert not repo.one("SELECT 1 FROM threat_catalog_objects WHERE name='UNC2891'")


async def test_sans_lookup_cache_and_rate_limit_pause(threat_workspace):
    _, repo, settings = threat_workspace
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={"ip": {"number": "8.8.8.8", "count": 5}})
        return httpx.Response(429, headers={"Retry-After": "900"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        first = await lookup(repo, settings, client, {"provider_id": "sans", "query": "8.8.8.8"})
        assert first["classification"] == "reported_network_activity"
        assert (await lookup(repo, settings, client, {"provider_id": "sans", "query": "8.8.8.8"}))["cached"]
        with pytest.raises(ProviderError):
            await lookup(repo, settings, client, {"provider_id": "sans", "query": "1.1.1.1"})
        with pytest.raises(ValueError, match="requested a pause"):
            await lookup(repo, settings, client, {"provider_id": "sans", "query": "9.9.9.9"})
    assert len(calls) == 2


def test_cyber_feed_context_and_secondary_analysis(threat_workspace):
    client, repo, settings = threat_workspace
    feeds = {feed.source_id: feed for feed in cyber_feeds(settings)}
    payload = {
        "title": "Spyware report",
        "description": "France and Germany discussed in the report",
        "link": "https://citizenlab.ca/fixture",
        "pubDate": "Sat, 10 Oct 2026 10:00:00 GMT",
    }
    report = feeds["citizen_lab"].normalize(payload)
    assert report.latitude is None and set(report.news.mentioned_countries) == {"FR", "DE"}
    repo.database.ingest(report)
    network = client.get("/api/cyber/relations").json()
    assert network["report_count"] == 1 and network["edges"]
    assert all(edge["event_ids"] and edge["urls"] for edge in network["edges"])
    assert "automated-secondary-analysis" in feeds["defend_network"].normalize(payload).tags
    assert (
        client.post(
            "/api/v1/cyber/enrich", json={"provider_id": "sans", "indicator": "127.0.0.1"}
        ).status_code
        == 422
    )
