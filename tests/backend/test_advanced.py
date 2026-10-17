import hashlib
import io
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.advanced.analysis import analyze
from backend.advanced.backup import backup, restore
from backend.advanced.geo import measure, validate_geojson
from backend.advanced.processing import index_batch, normalize_indicator
from backend.advanced.repository import Repository
from backend.advanced.tasks import tick
from backend.advanced.watch import normalized_text, pinned_get, save_snapshot, validate_url
from backend.config import ROOT, Settings
from backend.database import Database
from backend.main import create_app
from backend.models import Report, utcnow

# Derived from the migration files so adding a migration cannot leave a test
# asserting a stale schema version.
SCHEMA_VERSION = len(list((ROOT / "backend/migrations").glob("*.sql")))


@pytest.fixture
def workspace(tmp_path):
    settings = Settings(
        _env_file=None,
        database=tmp_path / "test.sqlite3",
        admin_token="test-access",
        evidence_directory=tmp_path / "evidence",
        openrouter_api_key="",
        watch_allowed_hosts=["example.org"],
    )
    app = create_app(settings)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer test-access"
        database = app.state.database
        for i, (title, category) in enumerate(
            [
                ("France and Germany announce successful defence cooperation", "geopolitical"),
                ("France and Germany warn of escalating defence conflict", "military"),
                ("CVE-2026-12345 affects example.org and 8.8.8.8", "cyber"),
                ("CVE-2026-12345 requires urgent remediation", "cyber"),
                ("La France et l'Allemagne annoncent un accord pour la sécurité européenne", "geopolitical"),
            ]
        ):
            database.ingest(
                Report(
                    source_id="bbc" if i != 3 else "ncsc",
                    external_id=str(i),
                    source_url=f"https://example.org/{i}",
                    title=title,
                    description="Public report for bounded evidence processing.",
                    category=category,
                    published_at=utcnow() - timedelta(hours=i),
                    sentiment_kind="news" if category != "cyber" else "official",
                    language="en",
                )
            )
        index_batch(database)
        yield client, app, Repository(database), settings


def test_projection_search_and_request_envelope(workspace):
    client, app, repo, _ = workspace
    response = client.get("/api/v1/osint/search?q=France&order=relevance&limit=1")
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 3
    assert len(data["data"]) == 1
    assert data["request_id"] == response.headers["x-request-id"]
    assert data["data"][0]["original_url"].startswith("https://example.org/")
    assert client.get("/api/v1/osint/search?limit=201").status_code == 422
    assert client.get("/api/v1/osint/search?q=%22%29%20OR%201%3D1%20--").status_code == 200
    records = repo.rows("SELECT * FROM external_records")
    assert all(r["published_at"] and r["content_hash"] for r in records)
    with app.state.database.connect() as db:
        db.execute("UPDATE reports SET title='Replacement evidence title' WHERE external_id='0'")
    assert repo.search("Replacement")["total"] == 1
    assert repo.search("successful")["total"] == 0


@pytest.mark.parametrize(
    "path",
    [
        "/osint/search",
        "/cyber/indicators",
        "/narratives",
        "/graph/entities",
        "/cases",
        "/sources",
        "/media/evidence",
        "/documents",
        "/watch/sources",
    ],
)
def test_investigation_read_access_is_private_by_default(workspace, path):
    client, _, _, _ = workspace
    client.headers.pop("Authorization")
    response = client.get("/api/v1" + path)
    assert response.status_code == 401
    assert response.json()["error_code"] == "HTTP_401"
    assert "test-access" not in response.text


def test_indicator_deduplication_and_conflicting_evidence(workspace):
    client, _, _, _ = workspace
    result = client.post("/api/v1/cyber/enrich", json={"indicator": "cve-2026-12345"}).json()["data"]
    assert result["normalized_value"] == "CVE-2026-12345"
    assert len(result["evidence"]) == 2
    assert {r["source_id"] for r in result["evidence"]} == {"bbc", "ncsc"}
    assert result["attribution_status"].startswith("Reported")
    assert client.post("/api/v1/cyber/enrich", json={"indicator": "nonsense"}).status_code == 422
    assert (
        client.post("/api/v1/cyber/enrich", json={"indicator": "8.8.8.8", "provider_id": "otx"}).status_code
        == 409
    )
    assert client.get("/api/v1/cyber/disruptions").json()["meta"]["measurement_period"] is None


@pytest.mark.parametrize(
    "value,expected",
    [
        ("CVE-2025-1234", ("cve", "CVE-2025-1234")),
        ("EXAMPLE.ORG", ("domain", "example.org")),
        ("2001:4860:4860::8888", ("ip", "2001:4860:4860::8888")),
        ("A" * 64, ("hash", "a" * 64)),
        ("HTTPS://Example.Org/x#fragment", ("url", "https://example.org/x")),
    ],
)
def test_indicator_normalization(value, expected):
    assert normalize_indicator(value) == expected


def test_narrative_language_and_membership(workspace):
    client, _, repo, _ = workspace
    data = client.get("/api/v1/narratives/sentiment").json()
    assert any(r["language"] == "fr" and r["sentiment"] == "unclassified" for r in data["data"])
    assert sum(r["samples"] for r in data["data"]) == 5
    assert "not target-specific stance" in data["meta"]["method"]
    cluster = client.get("/api/v1/narratives").json()["data"][0]
    members = client.get("/api/v1/narratives/" + cluster["cluster_id"]).json()["data"]["members"]
    assert members and all(r["record_id"] and r["original_url"] for r in members)
    before = repo.rows("SELECT * FROM narrative_metrics")
    assert index_batch(repo.database) == 0
    assert repo.rows("SELECT * FROM narrative_metrics") == before


def test_graph_evidence_and_limits_and_ambiguity(workspace):
    client, _, _, _ = workspace
    france = next(r for r in client.get("/api/v1/graph/entities").json()["data"] if r["name"] == "France")
    graph = client.get(f"/api/v1/graph/neighborhood/{france['entity_id']}?nodes=2&edges=2").json()["data"]
    assert len(graph["nodes"]) <= 2 and len(graph["edges"]) <= 2
    assert graph["edges"] and all(r["evidence_ids"] and r["status"] == "reported" for r in graph["edges"])
    assert client.get(f"/api/v1/graph/neighborhood/{france['entity_id']}?nodes=121").status_code == 422
    a = client.post(
        "/api/v1/graph/resolve", json={"name": "Example Institute", "type": "institution"}
    ).json()["data"]
    b = client.post(
        "/api/v1/graph/resolve", json={"name": "Example Institute", "type": "institution"}
    ).json()["data"]
    assert a["entity_id"] != b["entity_id"]


def test_case_immutable_evidence_notes_export_and_soft_deletion(workspace):
    client, _, repo, _ = workspace
    case = client.post("/api/v1/cases", json={"title": "Public research", "tags": ["France"]}).json()["data"]
    record = repo.search("France")["items"][0]
    evidence = client.post(
        f"/api/v1/cases/{case['id']}/evidence", json={"kind": "record", "reference_id": record["record_id"]}
    ).json()["data"]
    with repo.database.connect() as db:
        db.execute(
            "UPDATE external_records SET title='Changed source text' WHERE record_id=?",
            (record["record_id"],),
        )
    saved = client.get(f"/api/v1/cases/{case['id']}").json()["data"]
    assert saved["evidence"][0]["snapshot"]["title"] == record["title"]
    assert evidence["sha256"] == saved["evidence"][0]["sha256"]
    assert (
        client.post(f"/api/v1/cases/{case['id']}/notes", json={"text": "Private analyst note"}).status_code
        == 200
    )
    exported = client.post(f"/api/v1/cases/{case['id']}/export").json()["data"]
    assert "text" not in exported["evidence"][0]["snapshot"]
    assert exported["evidence"][0]["snapshot"]["original_url"] == record["original_url"]
    assert (
        client.post(f"/api/v1/cases/{case['id']}/export?format=markdown")
        .json()["data"]["text"]
        .startswith("# Public research")
    )
    assert client.get(f"/api/v1/cases/{case['id']}/timeline").json()["data"]
    assert (
        client.patch(
            f"/api/v1/cases/{case['id']}", json={"title": "Public research", "status": "deleted"}
        ).status_code
        == 200
    )
    assert client.get(f"/api/v1/cases/{case['id']}").status_code == 404


def test_media_validation_reproducible_hash_and_private_download(workspace):
    client, _, _, settings = workspace
    buffer = io.BytesIO()
    Image.new("RGB", (20, 10), "yellow").save(buffer, format="PNG")
    payload = buffer.getvalue()
    response = client.post(
        "/api/v1/media/evidence?filename=evidence.png", content=payload, headers={"Content-Type": "image/png"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["sha256"] == hashlib.sha256(payload).hexdigest()
    assert data["metadata"]["width"] == 20
    assert data["metadata"]["c2pa"]["status"] == "unsupported"
    assert (settings.evidence_directory / (data["id"] + ".bin")).exists()
    assert client.get(f"/api/v1/media/evidence/{data['id']}/file").content == payload
    assert (
        client.post(
            "/api/v1/media/evidence?filename=fake.jpg",
            content=payload,
            headers={"Content-Type": "image/jpeg"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/media/evidence?filename=../file.png",
            content=payload,
            headers={"Content-Type": "image/png"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/media/evidence?filename=file.exe",
            content=b"MZ",
            headers={"Content-Type": "application/octet-stream"},
        ).status_code
        == 415
    )
    assert client.delete(f"/api/v1/media/evidence/{data['id']}").status_code == 200
    assert client.get(f"/api/v1/media/evidence/{data['id']}").status_code == 410


@pytest.mark.parametrize(
    "value",
    [
        {"type": "Point", "coordinates": [181, 2]},
        {"type": "Point", "coordinates": [1, float("inf")]},
        {"type": "Point", "coordinates": [True, 2]},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [2, 2]]]},
        {"type": "Point", "coordinates": [1, 2], "crs": {"name": "EPSG:3857"}},
        {"type": "LineString", "coordinates": [[0, 0]]},
    ],
)
def test_geojson_rejects_invalid_coordinates_and_structure(value):
    with pytest.raises(ValueError):
        validate_geojson(value)


def test_measurement_and_geo_evidence(workspace):
    client, _, _, _ = workspace
    assert abs(measure("distance", [[0, 0], [1, 0]])["value"] - 111195) < 1
    assert measure("area", [[0, 0], [1, 0], [1, 1], [0, 0]])["value"] > 6e9
    body = {
        "title": "Authorized overlay",
        "geojson": {"type": "Point", "coordinates": [2, 48]},
        "precision": "approximate",
        "basis": "Analyst supplied coordinate reference",
        "source_url": "https://example.org/map",
        "license_classification": "authorized",
    }
    result = client.post("/api/v1/geo/import", json=body).json()["data"]
    assert result["acquired_at"] is None and result["retrieved_at"]
    assert client.get("/api/v1/geo/search?q=France").json()["data"][0]["precision"] == "country"
    assert client.get("/api/v1/geo/search?q=181,0").status_code == 422


def test_watch_policy_and_versioned_changes(workspace):
    client, _, repo, _ = workspace
    assert (
        client.post(
            "/api/v1/watch/sources",
            json={
                "url": "https://127.0.0.1/",
                "title": "Private",
                "permission_basis": "Not permitted because it targets a private network",
            },
        ).status_code
        == 422
    )
    data = client.post(
        "/api/v1/watch/sources",
        json={
            "url": "https://example.org/report",
            "title": "Public page",
            "permission_basis": "Administrator authorized published research page monitoring",
        },
    ).json()["data"]
    watch = repo.one("SELECT * FROM watch_sources WHERE id=?", (data["id"],))
    assert save_snapshot(repo, watch, "First text", {})["changed"]
    assert not save_snapshot(repo, watch, "First text", {})["changed"]
    assert save_snapshot(repo, watch, "Updated text", {})["changed"]
    assert len(repo.rows("SELECT * FROM source_changes")) == 2
    assert client.get(f"/api/v1/watch/sources/{watch['id']}/changes").json()["meta"]["total"] == 2
    original = repo.one("SELECT * FROM webpage_snapshots WHERE text='First text'")
    assert save_snapshot(repo, watch, "First text", {})["changed"]
    assert not save_snapshot(repo, watch, "First text", {})["changed"]
    assert (
        repo.one("SELECT * FROM webpage_snapshots WHERE text='First text'")["retrieved_at"]
        == original["retrieved_at"]
    )
    assert len(repo.rows("SELECT * FROM source_changes")) == 3
    assert (
        repo.one("SELECT * FROM external_records WHERE source_id=?", ("watch_" + watch["id"],))[
            "published_at"
        ]
        is None
    )
    assert normalized_text(b"<p> A  B </p><script>malicious</script>", "text/html") == "A B"


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/",
        "https://169.254.169.254/",
        "https://[::1]/",
        "http://example.org/",
        "https://user:pass@example.org/",
        "https://example.org:444/",
        "https://other.example/",
        "https://example.org/#fragment",
    ],
)
def test_watch_rejects_unsafe_destinations(url):
    with pytest.raises(ValueError):
        validate_url(url, ["example.org", "127.0.0.1", "169.254.169.254", "::1"])


async def test_watch_dns_rebinding_is_blocked(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(ValueError, match="non-public"):
        await pinned_get("https://example.org/report", ["example.org"])


def test_document_licenses_publication_and_case_link(workspace):
    client, _, _, _ = workspace
    body = {
        "title": "Public document",
        "organization": "Example Institution",
        "source_id": "documentcloud",
        "original_url": "https://example.org/doc",
        "text": "Authorized original document passage",
        "license_classification": "metadata_only",
    }
    assert client.post("/api/v1/documents", json=body).status_code == 422
    body["license_classification"] = "authorized"
    data = client.post("/api/v1/documents", json=body).json()["data"]
    assert data["published_at"] is None and data["retrieved_at"]
    assert client.get("/api/v1/documents?organization=Example").json()["meta"]["total"] == 1
    assert (
        client.post(
            "/api/v1/documents/analyze",
            json={"question": "Summarize the cited evidence", "record_ids": [data["id"]]},
        ).status_code
        == 503
    )


def test_deterministic_correlation_works_without_ai(workspace):
    client, _, repo, _ = workspace
    ids = [r["record_id"] for r in repo.search("France")["items"]]
    result = client.post("/api/v1/correlation/candidates", json={"record_ids": ids}).json()
    assert result["data"] and 0 <= result["data"][0]["score"] <= 1
    assert "not causation" in result["data"][0]["basis"]["limitations"]
    assert (
        client.post(
            "/api/v1/correlation/candidates",
            json={"record_ids": ids, "weights": {"time": 1, "country": 1, "topics": 1}},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/correlation/analyze", json={"question": "Explain the sources", "record_ids": ids}
        ).status_code
        == 503
    )


def test_source_disable_and_restricted_provider_activation(workspace):
    client, _, _, _ = workspace
    body = {"enabled": False, "permission_basis": "Administrator temporarily pauses this public feed"}
    assert client.patch("/api/v1/sources/bbc", json=body).json()["data"]["enabled"] == 0
    assert client.patch("/api/v1/sources/otx", json={**body, "enabled": True}).status_code == 409
    assert (
        client.post(
            "/api/v1/osint/search/external",
            json={"provider_id": "archive", "query": "France", "confirmed": False},
        ).status_code
        == 422
    )
    result = client.post(
        "/api/v1/osint/search/external",
        json={"provider_id": "archive", "query": "France & Germany", "confirmed": True},
    ).json()["data"]
    assert result["query_sent_by_server"] is False
    assert "%26" in result["url"]


async def test_worker_jobs_fail_independently_and_recover(workspace):
    _, _, repo, settings = workspace
    job = repo.enqueue("unknown", {})
    async with httpx.AsyncClient() as client:
        await tick(repo.database, settings, client)
    result = repo.one("SELECT * FROM investigation_jobs WHERE id=?", (job["job_id"],))
    assert result["state"] == "failed"
    assert "Unsupported job" in result["error"]
    assert repo.search("France")["total"] == 3


def test_concurrent_first_start_migrations_are_serialized(tmp_path):
    with ThreadPoolExecutor(max_workers=2) as pool:
        for attempt in range(20):
            path = tmp_path / f"concurrent-{attempt}.sqlite3"
            list(pool.map(lambda _: Database(path).initialize(), range(2)))
            with sqlite3.connect(path) as db:
                assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
                assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_bundle_restore_includes_case_snapshots_and_media(workspace, tmp_path):
    client, _, repo, settings = workspace
    buffer = io.BytesIO()
    Image.new("RGB", (3, 3), "blue").save(buffer, format="PNG")
    media = client.post(
        "/api/v1/media/evidence?filename=sample.png",
        content=buffer.getvalue(),
        headers={"Content-Type": "image/png"},
    ).json()["data"]
    case = client.post("/api/v1/cases", json={"title": "Restore verification"}).json()["data"]
    client.post(f"/api/v1/cases/{case['id']}/evidence", json={"kind": "media", "reference_id": media["id"]})
    bundle = backup(settings.database, settings.evidence_directory, tmp_path / "backups")
    target = tmp_path / "restored"
    result = restore(bundle, target)
    assert result["files_verified"] == 2
    assert (target / "evidence" / (media["id"] + ".bin")).read_bytes() == buffer.getvalue()
    restored = Repository(Database(target / "database.sqlite3"))
    assert restored.case(case["id"])["evidence"][0]["snapshot"]["sha256"] == media["sha256"]
    assert not (bundle / ".env").exists()
    (bundle / "evidence" / (media["id"] + ".bin")).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="validation failed"):
        restore(bundle, tmp_path / "invalid-restore")


def test_unknown_filters_naive_dates_and_hypothesis_relationships(workspace):
    client, _, repo, _ = workspace
    assert client.get("/api/v1/osint/search?unsupported=value").status_code == 422
    assert client.get("/api/v1/osint/search?start=2026-10-10").status_code == 422
    nodes = repo.rows("SELECT * FROM entities WHERE type='country' LIMIT 2")
    rid = repo.search("France")["items"][0]["record_id"]
    body = {
        "from_id": nodes[0]["entity_id"],
        "to_id": nodes[1]["entity_id"],
        "type": "analyst_hypothesis",
        "status": "inferred",
        "basis": "Analyst association proposed from this specific source record",
        "evidence_ids": [rid],
    }
    response = client.post("/api/v1/graph/relationships", json=body)
    assert response.status_code == 200
    inferred = client.get("/api/v1/graph/relationships?status=inferred").json()["data"]
    assert len(inferred) == 1 and inferred[0]["evidence_ids"] == [rid]
    body["evidence_ids"] = ["a" * 32]
    assert client.post("/api/v1/graph/relationships", json=body).status_code == 404


async def test_ai_validates_citations_and_reuses_cache(workspace, monkeypatch):
    _, _, repo, settings = workspace
    from backend.ai import AIError

    settings.openrouter_api_key = "temporary-test-key"
    settings.openrouter_model = "test/free"

    async def catalog(self):
        return {"test/free": {"pricing": {"prompt": "0", "completion": "0"}}}

    monkeypatch.setattr("backend.ai.AIService.models", catalog)
    rid = repo.search("France")["items"][0]["record_id"]
    output = {
        "observations": [{"text": "The report mentions France.", "evidence_ids": ["unsupported"]}],
        "supporting_evidence_ids": [rid],
        "contradictory_evidence_ids": [],
        "hypotheses": [],
        "limitations": ["Single source text, not independently confirmed."],
    }
    calls = []

    async def completion(self, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(output)}}]})

    monkeypatch.setattr("backend.ai.AIService.completion", completion)
    payload = {"question": "Explain the source evidence", "record_ids": [rid]}
    async with httpx.AsyncClient() as client:
        with pytest.raises(AIError, match="Unsupported AI citation"):
            await analyze(repo, settings, client, payload)
        assert not repo.rows("SELECT * FROM ai_analyses")
        output["observations"][0]["evidence_ids"] = [rid]
        first = await analyze(repo, settings, client, payload)
        cached = await analyze(repo, settings, client, payload)
    assert first["analysis_id"] == cached["analysis_id"]
    assert cached["cached"] is True and len(calls) == 2
    assert "untrusted data" in calls[0]["messages"][0]["content"]


async def test_advanced_ai_accepts_cached_plain_draft(workspace, monkeypatch):
    _, _, repo, settings = workspace
    settings.openrouter_api_key = "synthetic"
    settings.openrouter_model = "test/free"

    async def catalog(self):
        return {"test/free": {"pricing": {"prompt": "0", "completion": "0"}}}

    async def completion(self, **kwargs):
        assert "response_format" not in kwargs["json"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "An incomplete assessment without machine-readable claims."}}
                ]
            },
        )

    monkeypatch.setattr("backend.ai.AIService.models", catalog)
    monkeypatch.setattr("backend.ai.AIService.completion", completion)
    rid = repo.search("France")["items"][0]["record_id"]
    payload = {"question": "Explain this report", "record_ids": [rid]}
    async with httpx.AsyncClient() as client:
        result = await analyze(repo, settings, client, payload)
        cached = await analyze(repo, settings, client, payload)
    assert result["output_mode"] == "draft" and result["citation_validation"] == "not_validated"
    assert result["observations"] == [] and len(result["references"]) == 1
    assert cached["cached"]


def test_mixed_news_selection_and_registered_free_providers(workspace):
    _, _, _, settings = workspace
    from backend.connectors.registry import connectors
    from backend.connectors.rss import RSS

    provider = next(c for c in connectors(settings) if c.source_id == "abc_world")
    assert isinstance(provider, RSS)
    records = [
        {"title": "Singer releases album", "category": "Music"},
        {"title": "President announces diplomatic agreement", "category": "Politics"},
        {"title": "Aircraft carrier returns after deployment", "category": "News"},
        {"title": "Candidate wins local vote in Peru", "category": "News"},
        {"title": "Houthis claim attacks on Saudi airports", "category": "News"},
    ]
    assert len(provider.select_records(records)) == 4
    assert len([c for c in connectors(settings) if c.category == "geopolitical"]) >= 27


async def test_ripe_lookup_is_bounded_cached_and_does_not_scan(workspace, monkeypatch):
    _, _, repo, settings = workspace
    from backend.advanced.providers import lookup, routing_resource

    calls = []

    async def response(self, method, url, **kwargs):
        calls.append(url)
        return {"status": "ok", "data": {"prefix": "8.8.8.0/24", "asns": ["15169"]}}

    monkeypatch.setattr("backend.connectors.base.SafeHTTP.json", response)
    payload = {"provider_id": "ripe", "query": "8.8.8.8"}
    async with httpx.AsyncClient() as client:
        first = await lookup(repo, settings, client, payload)
        cached = await lookup(repo, settings, client, payload)
    assert first["source_id"] == "ripe" and cached["cached"]
    assert len(calls) == 1 and calls[0].startswith("https://stat.ripe.net/")
    with pytest.raises(ValueError):
        routing_resource("127.0.0.1")
    assert routing_resource("AS15169") == ("as-overview", "AS15169")
