from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.models import utcnow


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        yield client


def test_api_contract(client, report):
    event = client.app.state.database.ingest(report)
    for path in [
        "health",
        "status",
        "layers",
        "sources",
        "events",
        "events/" + event,
        "countries/IN",
        "country-activity",
        "sentiment",
        "relations",
        "military",
        "timeline",
        "ai/usage",
        "anomalies",
        "statistics",
        "openapi.json",
    ]:
        response = client.get("/api/" + path)
        assert response.status_code == 200, (path, response.text)
    detail = client.get("/api/events/" + event).json()
    source = client.get("/api/reports/" + detail["reports"][0]["report_id"]).json()
    assert source["raw"] == {"test": True}
    layers = client.get("/api/layers").json()
    assert len(layers) == 10
    cyber = next(layer for layer in layers if layer["id"] == "cyber")
    assert cyber["categories"] == ["cyber", "threat"]
    assert {"bitdefender_threatmap", "bunkerweb_threatmap", "cisa"} <= set(cyber["sources"])
    assert client.get("/api/events?format=geojson").json()["features"][0]["geometry"]["type"] == "Point"


@pytest.mark.parametrize(
    "query",
    [
        "limit=1001",
        "offset=-1",
        "bbox=0,0",
        "bbox=0,50,10,20",
        "categories=invalid",
        "country=BAD",
        "start=2026-01-01",
        "start=2026-10-11T00:00:00Z&end=2026-10-10T00:00:00Z",
        "q=" + "a" * 201,
    ],
)
def test_invalid_parameters(client, query):
    assert client.get("/api/events?" + query).status_code == 422


def test_sentiment_separate_samples_and_languages(client, report):
    db = client.app.state.database
    db.ingest(report)
    db.ingest(report.model_copy(update={"external_id": "other", "source_id": "copy"}))
    db.ingest(
        report.model_copy(
            update={"external_id": "es", "source_url": "https://example.org/es", "language": "es"}
        )
    )
    result = client.get("/api/sentiment?kind=news&q=peace").json()
    assert result["sample_count"] == 1
    assert result["dataset_count"] == 2
    assert result["excluded_language_count"] == 1
    assert result["distribution"]["positive"] == 1
    assert client.get("/api/sentiment?kind=public").json()["sample_count"] == 0


def test_ai_authorization_and_body_limit(client):
    body = {"question": "Summarize the evidence"}
    assert client.post("/api/ai/analyze", json=body).status_code == 401
    assert (
        client.post(
            "/api/ai/analyze", json=body, headers={"Authorization": "Bearer test-access-token"}
        ).status_code
        == 503
    )
    assert client.post("/api/ai/analyze", content=b"x" * 65537).status_code == 413
    response = client.post(
        "/api/ai/analyze",
        json={"question": "valid", "event_ids": ["../../"]},
        headers={"Authorization": "Bearer test-access-token"},
    )
    assert response.status_code == 422


def test_not_found_and_admin_protection(client):
    assert client.get("/api/events/" + "0" * 32).status_code == 404
    assert client.get("/api/countries/XX").status_code == 404
    assert client.post("/api/admin/maintenance").status_code == 401
    assert (
        client.post(
            "/api/admin/maintenance", headers={"Authorization": "Bearer test-access-token"}
        ).status_code
        == 200
    )


def test_rate_limit(client):
    for _ in range(120):
        assert client.get("/api/health").status_code == 200
    assert client.get("/api/health").status_code == 429


def test_evidence_review_requires_supported_records_and_independence(client, report):
    database = client.app.state.database
    event = database.ingest(report)
    rid = database.detail(event)["reports"][0]["report_id"]
    headers = {"Authorization": "Bearer test-access-token"}
    body = {
        "confidence": "Corroborated",
        "basis": "Synthetic review of independently reported source material.",
        "report_ids": [rid],
        "independent_sources_confirmed": True,
    }
    path = f"/api/admin/events/{event}/evidence"
    assert client.post(path, json=body).status_code == 401
    assert client.post(path, json=body, headers=headers).status_code == 422
    other = report.model_copy(
        update={
            "source_id": "independent",
            "external_id": "second",
            "source_url": "https://another.example.org/report",
        }
    )
    database.ingest(other)
    body["report_ids"] = [item["report_id"] for item in database.detail(event)["reports"]]
    assert client.post(path, json=body, headers=headers).status_code == 200
    database.ingest(report)
    assert database.detail(event)["confidence"] == "Corroborated"
    body["confidence"] = "Disputed"
    assert client.post(path, json=body, headers=headers).status_code == 422
    body["contradiction_confirmed"] = True
    assert client.post(path, json=body, headers=headers).status_code == 200
    body["confidence"] = "Verified"
    assert client.post(path, json=body, headers=headers).status_code == 422
    assert len(database.detail(event)["evidence_reviews"]) == 2


def test_per_source_refresh_auth_and_access_requirement(client):
    headers = {"Authorization": "Bearer test-access-token"}
    assert client.post("/api/admin/connectors/usgs/refresh").status_code == 401
    assert client.post("/api/admin/connectors/usgs/refresh", headers=headers).json()["state"] == "scheduled"
    assert client.post("/api/admin/connectors/firms/refresh", headers=headers).status_code == 409
    assert client.post("/api/admin/connectors/missing/refresh", headers=headers).status_code == 404


def test_sentiment_uses_each_report_publication_time(client, report):
    database = client.app.state.database
    old = report.model_copy(update={"published_at": utcnow() - timedelta(days=10)})
    database.ingest(old)
    recent = report.model_copy(update={"source_id": "recent", "external_id": "second"})
    database.ingest(recent)  # Same URL, same event, newer source report.
    result = client.get(
        "/api/sentiment", params={"start": (utcnow() - timedelta(days=1)).isoformat(), "kind": "news"}
    ).json()
    assert result["sample_count"] == 1
    assert result["period_basis"] == "source_publication"


def browser_record(**updates):
    return {
        "post_id": "t1_abc",
        "title": "Comment on a public thread",
        "text": "France and Germany have signed a successful peace agreement.",
        "url": "https://www.reddit.com/r/worldnews/comments/xyz/comment/abc/",
        "published_at": utcnow().isoformat(),
        "author": "public_example",
        "community": "worldnews",
        "content_type": "comment",
        "thread_title": "France and Germany discuss defence cooperation",
        **updates,
    }


def test_public_browser_capture_is_protected_and_replaces_snapshot(client):
    body = {"records": [browser_record()]}
    assert client.post("/api/admin/social/reddit-browser", json=body).status_code == 401
    headers = {"Authorization": "Bearer test-access-token"}
    response = client.post("/api/admin/social/reddit-browser", json=body, headers=headers)
    assert response.status_code == 200
    result = client.get("/api/sentiment?kind=public").json()
    assert result["dataset_count"] == 1 and result["known_origin_count"] == 0
    assert (
        result["posts"][0]["relations"][0]["target_url"] == "https://www.reddit.com/r/worldnews/comments/xyz/"
    )
    assert result["discussion_network"]["edges"][0]["kind"] == "comment_on"
    second = {
        "records": [
            browser_record(
                post_id="t1_def", url="https://www.reddit.com/r/worldnews/comments/xyz/comment/def/"
            )
        ]
    }
    assert client.post("/api/admin/social/reddit-browser", json=second, headers=headers).status_code == 200
    assert client.get("/api/sentiment?kind=public").json()["posts"][0]["post_id"] == "t1_def"
    assert (
        client.post("/api/admin/connectors/reddit_browser/refresh", json={}, headers=headers).status_code
        == 409
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"url": "https://example.org/r/worldnews/comments/xyz/comment/abc/"},
        {"url": "https://www.reddit.com/r/worldnews/comments/"},
        {"published_at": "2026-10-10T12:00:00"},
        {"published_at": (utcnow() + timedelta(days=1)).isoformat()},
        {
            "community": "private_example",
            "url": "https://www.reddit.com/r/private_example/comments/xyz/comment/abc/",
        },
    ],
)
def test_browser_capture_rejects_invalid_scope_and_dates(client, changes):
    response = client.post(
        "/api/admin/social/reddit-browser",
        json={"records": [browser_record(**changes)]},
        headers={"Authorization": "Bearer test-access-token"},
    )
    assert response.status_code == 422
    assert client.get("/api/sentiment?kind=public").json()["dataset_count"] == 0
