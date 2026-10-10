import asyncio
import gzip
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from backend.ai import AIError, AIService
from backend.models import AnalyzeRequest


def configured(settings):
    settings.openrouter_api_key = "synthetic-api-key"
    settings.openrouter_model = "test/model:free"
    return settings


def model_catalog():
    return {"data": [{"id": "test/model:free", "pricing": {"prompt": "0", "completion": "0"}}]}


def completion(event, report):
    return {
        "model": "test/model:free",
        "usage": {"prompt_tokens": 25, "completion_tokens": 12},
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "claims": [
                                {
                                    "text": "Synthetic source-grounded statement",
                                    "kind": "sourced_fact",
                                    "citations": [{"event_id": event, "report_id": report}],
                                }
                            ],
                            "limitations": ["Synthetic test evidence only"],
                        }
                    )
                }
            }
        ],
    }


async def test_cached_grounded_result_and_usage(settings, database, report):
    configured(settings)
    event = database.ingest(report)
    rid = database.detail(event)["reports"][0]["report_id"]
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(
            200, json=model_catalog() if request.url.path.endswith("models") else completion(event, rid)
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = AIService(settings, database, client)
        question = AnalyzeRequest(question="Summarize synthetic evidence", event_ids=[event])
        first, second = await service.analyze(question), await service.analyze(question)
        assert not first["cached"] and second["cached"]
        assert first["references"][0]["source_url"] == report.source_url
        assert calls.count("/api/v1/chat/completions") == 1
        assert service.usage()["requests"] == 1
        assert service.usage()["prompt_tokens"] == 25


async def test_plain_text_is_available_as_unvalidated_draft(settings, database, report):
    configured(settings)
    event = database.ingest(report)
    text = "The available reports describe an agreement. Independent confirmation is limited."
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=model_catalog()
                if request.url.path.endswith("models")
                else {"choices": [{"message": {"content": text}}]},
            )
        )
    ) as client:
        service = AIService(settings, database, client)
        request = AnalyzeRequest(question="Summarize", event_ids=[event])
        result = await service.analyze(request)
        cached = await service.analyze(request)
        assert cached["cached"] and service.usage()["requests"] == 1
        assert service.usage()["statuses"] == {"draft": 1}
    assert result["output_mode"] == "draft"
    assert result["draft_text"] == text
    assert result["claims"] == []
    assert result["citation_validation"] == "not_validated"


@pytest.mark.parametrize(
    "text",
    ['{"answer":"unstructured"}', '{"claims": [truncated', [{"type": "text", "text": "A plain answer."}]],
)
async def test_schema_mismatches_and_text_parts_remain_drafts(settings, database, report, text):
    configured(settings)
    event = database.ingest(report)

    def handler(request):
        if request.url.path.endswith("models"):
            return httpx.Response(200, json=model_catalog())
        assert "response_format" not in json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await AIService(settings, database, client).analyze(
            AnalyzeRequest(question="Summarize", event_ids=[event])
        )
    assert result["output_mode"] == "draft" and not result["claims"]


async def test_markdown_fenced_json_is_recovered(settings, database, report):
    configured(settings)
    event = database.ingest(report)
    rid = database.detail(event)["reports"][0]["report_id"]
    payload = completion(event, rid)
    content = payload["choices"][0]["message"]["content"]
    payload["choices"][0]["message"]["content"] = "Here is the assessment:\n```json\n" + content + "\n```"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json=model_catalog() if request.url.path.endswith("models") else payload
            )
        )
    ) as client:
        result = await AIService(settings, database, client).analyze(
            AnalyzeRequest(question="Summarize", event_ids=[event])
        )
    assert result["output_mode"] == "structured"
    assert result["claims"][0]["citations"][0]["report_id"] == rid


async def test_compressed_provider_response_is_decoded_once(settings, database, report):
    configured(settings)
    event = database.ingest(report)
    rid = database.detail(event)["reports"][0]["report_id"]
    compressed = gzip.compress(json.dumps(completion(event, rid)).encode())

    def handler(request):
        if request.url.path.endswith("models"):
            return httpx.Response(200, json=model_catalog())
        return httpx.Response(
            200,
            headers={
                "Content-Type": "application/json",
                "Content-Encoding": "gzip",
                "Content-Length": str(len(compressed)),
            },
            stream=httpx.ByteStream(compressed),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = AIService(settings, database, client)
        result = await service.analyze(AnalyzeRequest(question="Summarize", event_ids=[event]))
        assert result["claims"][0]["citations"] == [{"event_id": event, "report_id": rid}]
        assert service.usage()["statuses"] == {"ok": 1}


@pytest.mark.parametrize("invalid", ["citation"])
async def test_rejects_fabricated_citations_and_schema(settings, database, report, invalid):
    configured(settings)
    event = database.ingest(report)
    payload = (
        completion(event, "fabricated-id")
        if invalid == "citation"
        else {"choices": [{"message": {"content": '{"answer":"unstructured"}'}}]}
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json=model_catalog() if request.url.path.endswith("models") else payload
            )
        )
    ) as client:
        service = AIService(settings, database, client)
        with pytest.raises(AIError) as error:
            await service.analyze(AnalyzeRequest(question="Summarize", event_ids=[event]))
        assert error.value.status == 502
        with database.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM ai_cache").fetchone()[0] == 0


async def test_quota_atomic(settings, database):
    settings.ai_daily_budget = 3
    async with httpx.AsyncClient() as client:
        service = AIService(settings, database, client)

        def reserve(_):
            try:
                service.reserve("test")
                return True
            except AIError:
                return False

        with ThreadPoolExecutor(max_workers=8) as pool:
            assert sum(pool.map(reserve, range(10))) == 3
        assert service.usage()["remaining"] == 0


async def test_timeout_retry_and_quota_consumption(monkeypatch, settings, database, report):
    configured(settings)
    event = database.ingest(report)

    async def no_sleep(seconds):
        pass

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    def handler(request):
        if request.url.path.endswith("models"):
            return httpx.Response(200, json=model_catalog())
        raise httpx.ReadTimeout("synthetic timeout")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = AIService(settings, database, client)
        with pytest.raises(AIError, match="timeout"):
            await service.analyze(AnalyzeRequest(question="Summarize", event_ids=[event]))
        assert service.usage()["requests"] == 2
        assert service.usage()["statuses"]["timeout"] == 2


async def test_rate_limit_preserves_non_ai(monkeypatch, settings, database, report):
    configured(settings)
    event = database.ingest(report)

    async def no_sleep(seconds):
        pass

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: (
                httpx.Response(200, json=model_catalog())
                if request.url.path.endswith("models")
                else httpx.Response(429)
            )
        )
    ) as client:
        service = AIService(settings, database, client)
        with pytest.raises(AIError) as error:
            await service.analyze(AnalyzeRequest(question="Summarize", event_ids=[event]))
        assert error.value.status == 429
        assert database.detail(event) is not None


async def test_paid_model_rejected(settings, database, report):
    configured(settings)
    event = database.ingest(report)
    catalogue = model_catalog()
    catalogue["data"][0]["pricing"]["prompt"] = "0.01"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=catalogue))
    ) as client:
        service = AIService(settings, database, client)
        with pytest.raises(AIError, match="not priced as free"):
            await service.analyze(AnalyzeRequest(question="Summarize", event_ids=[event]))
        assert service.usage()["requests"] == 0


async def test_available_free_fallback(settings, database, report):
    configured(settings)
    settings.openrouter_fallback = "test/fallback:free"
    event = database.ingest(report)
    rid = database.detail(event)["reports"][0]["report_id"]
    catalogue = model_catalog()
    catalogue["data"].append(
        {"id": settings.openrouter_fallback, "pricing": {"prompt": "0", "completion": "0"}}
    )

    def handler(request):
        if request.url.path.endswith("models"):
            return httpx.Response(200, json=catalogue)
        if json.loads(request.content)["model"] == settings.openrouter_model:
            return httpx.Response(404)
        result = completion(event, rid)
        result["model"] = settings.openrouter_fallback
        return httpx.Response(200, json=result)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = AIService(settings, database, client)
        result = await service.analyze(
            AnalyzeRequest(question="Summarize synthetic evidence", event_ids=[event])
        )
        assert result["model"] == settings.openrouter_fallback
        assert service.usage()["requests"] == 2


async def test_non_ai_request_remains_responsive_during_inference(settings, report):
    from backend.main import create_app

    configured(settings)
    started, release = asyncio.Event(), asyncio.Event()
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        event = app.state.database.ingest(report)
        rid = app.state.database.detail(event)["reports"][0]["report_id"]

        async def handler(request):
            if request.url.path.endswith("models"):
                return httpx.Response(200, json=model_catalog())
            started.set()
            await release.wait()
            return httpx.Response(200, json=completion(event, rid))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as provider:
            app.state.ai = AIService(settings, app.state.database, provider)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                task = asyncio.create_task(
                    client.post(
                        "/api/ai/analyze",
                        headers={"Authorization": "Bearer test-access-token"},
                        json={"question": "Summarize", "event_ids": [event]},
                    )
                )
                await asyncio.wait_for(started.wait(), timeout=2)
                response = await asyncio.wait_for(client.get("/api/health"), timeout=0.5)
                assert response.status_code == 200
                release.set()
                assert (await task).status_code == 200
