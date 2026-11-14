"""Exercise the MCP protocol against the real FastAPI app in memory."""

import httpx
import pytest
from mcp import Client

from backend.main import create_app
from backend.mcp_server import AtlasAPI, create_mcp_server


@pytest.mark.asyncio
async def test_public_mcp_tools_forward_filters_and_keep_private_tools_hidden(settings, report):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        event_id = app.state.database.ingest(report)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            server = create_mcp_server(AtlasAPI("http://test", client=http))
            async with Client(server) as client:
                names = {tool.name for tool in (await client.list_tools()).tools}
                assert {"health", "search_events", "get_event", "monitoring_frame"} <= names
                assert "create_case" not in names
                result = await client.call_tool(
                    "search_events", {"categories": ["geopolitical"], "source_id": "synthetic", "limit": 10}
                )
                assert not result.is_error
                assert result.structured_content["total"] == 1
                assert result.structured_content["items"][0]["event_id"] == event_id
                detail = await client.call_tool("get_event", {"event_id": event_id})
                assert not detail.is_error
                assert detail.structured_content["event_id"] == event_id
                invalid = await client.call_tool("search_events", {"start": "not-a-date"})
                assert invalid.is_error
                assert "422" in invalid.content[0].text


@pytest.mark.asyncio
async def test_private_case_tools_use_admin_token_and_persist(settings):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as http:
            api = AtlasAPI("http://127.0.0.1", token=settings.admin_token, client=http)
            server = create_mcp_server(api, include_private=True)
            async with Client(server) as client:
                names = {tool.name for tool in (await client.list_tools()).tools}
                assert {"create_case", "list_cases", "get_case", "add_case_note"} <= names
                created = await client.call_tool("create_case", {"title": "Synthetic MCP case"})
                assert not created.is_error
                case_id = created.structured_content["data"]["id"]
                noted = await client.call_tool("add_case_note", {"case_id": case_id, "text": "Source pending review"})
                assert not noted.is_error
                result = await client.call_tool("get_case", {"case_id": case_id})
                assert not result.is_error
                assert result.structured_content["data"]["notes"][0]["text"] == "Source pending review"


def test_private_tools_require_explicit_token():
    with pytest.raises(ValueError, match="OSINT_MCP_API_TOKEN"):
        create_mcp_server(AtlasAPI(), include_private=True)


@pytest.mark.asyncio
async def test_api_adapter_forwards_token_only_to_protected_routes():
    seen = []

    def respond(request):
        seen.append((request.url.path, request.headers.get("authorization")))
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="http://127.0.0.1") as http:
        api = AtlasAPI("http://127.0.0.1", token="private-test-token", client=http)
        await api.request("GET", "api/health")
        await api.request("GET", "api/v1/cases", private=True)
    assert seen == [("/api/health", None), ("/api/v1/cases", "Bearer private-test-token")]


def test_remote_token_requires_https():
    with pytest.raises(ValueError, match="HTTPS"):
        AtlasAPI("http://example.org", token="private-test-token")
