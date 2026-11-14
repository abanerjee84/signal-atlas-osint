"""MCP adapter for the existing Signal Atlas HTTP API.

Run with ``python -m backend.mcp_server``. The stdio transport exposes private
case tools only when OSINT_MCP_API_TOKEN is configured.
"""

import os
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from .models import Category


class AtlasAPIError(ToolError):
    """A bounded, caller-facing error from the Signal Atlas API."""


class AtlasAPI:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        token: str = "",
        client: httpx.AsyncClient | None = None,
    ):
        parsed = urlsplit(base_url)
        if (parsed.scheme not in {"http", "https"} or not parsed.netloc
                or parsed.username is not None or parsed.password is not None):
            raise ValueError("OSINT_MCP_API_URL must be an HTTP(S) URL without credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("OSINT_MCP_API_URL cannot contain a query or fragment")
        hostname = parsed.hostname or ""
        try:
            loopback = ip_address(hostname).is_loopback
        except ValueError:
            loopback = hostname == "localhost"
        if token and parsed.scheme == "http" and not loopback:
            raise ValueError("OSINT_MCP_API_URL must use HTTPS when forwarding an administrator token remotely")
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.client = client

    async def request(
        self,
        method: Literal["GET", "POST"],
        path: str,
        *,
        params: dict | None = None,
        body: dict | None = None,
        private: bool = False,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        if private and not self.token:
            raise AtlasAPIError("Set OSINT_MCP_API_TOKEN to use protected investigation tools")
        headers = {"Authorization": f"Bearer {self.token}"} if private else {}
        try:
            if self.client is None:
                async with httpx.AsyncClient(base_url=self.base_url, timeout=30, follow_redirects=False) as client:
                    response = await client.request(method, path, params=params, json=body, headers=headers)
            else:
                response = await self.client.request(method, path, params=params, json=body, headers=headers)
        except httpx.RequestError as error:
            raise AtlasAPIError("Signal Atlas API is unavailable; check OSINT_MCP_API_URL") from error
        if not response.is_success:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            detail = payload.get("message") or payload.get("detail") or response.reason_phrase
            if not isinstance(detail, str):
                detail = "Request failed"
            raise AtlasAPIError(f"Signal Atlas API returned {response.status_code}: {detail[:300]}")
        try:
            return response.json()
        except ValueError as error:
            raise AtlasAPIError("Signal Atlas API returned invalid JSON") from error


def _window(days: int) -> dict[str, str]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return {"start": start.isoformat(), "end": end.isoformat()}


def _filters(
    categories: list[Category] | None = None,
    q: str = "",
    country: str | None = None,
    start: str | None = None,
    end: str | None = None,
    source_id: str = "",
) -> dict[str, Any]:
    values = {
        "categories": ",".join(item.value for item in categories or []),
        "q": q,
        "country": country,
        "start": start,
        "end": end,
        "source_id": source_id,
    }
    return {key: value for key, value in values.items() if value is not None and value != ""}


READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False)


def create_mcp_server(api: AtlasAPI, *, include_private: bool = False) -> MCPServer:
    server = MCPServer(
        "signal-atlas-osint",
        title="Signal Atlas OSINT",
        version="0.1.0",
        instructions=(
            "Use retained source evidence and disclose coverage limits. Country mentions do not locate incidents; "
            "IP infrastructure geography does not identify an actor. Empty results are not proof of inactivity."
        ),
    )

    @server.tool(annotations=READ, structured_output=True)
    async def health() -> dict[str, Any]:
        """Check API and database availability, version and UTC timestamp."""
        return await api.request("GET", "api/health")

    @server.tool(annotations=READ, structured_output=True)
    async def source_status() -> dict[str, Any]:
        """Get worker heartbeat and per-provider availability, access and staleness."""
        return await api.request("GET", "api/status")

    @server.tool(annotations=READ, structured_output=True)
    async def list_layers() -> list[dict[str, Any]]:
        """List event layers, source IDs and their current coverage state."""
        return await api.request("GET", "api/layers")

    @server.tool(annotations=READ, structured_output=True)
    async def search_events(
        categories: list[Category] | None = None,
        q: Annotated[str, Field(max_length=200)] = "",
        country: Annotated[str | None, Field(pattern=r"^[A-Z]{2}$")] = None,
        start: str | None = None,
        end: str | None = None,
        source_id: Annotated[str, Field(pattern=r"^[a-z0-9_]{0,80}$")] = "",
        limit: Annotated[int, Field(ge=1, le=100)] = 50,
        offset: Annotated[int, Field(ge=0, le=100000)] = 0,
        order: Literal["latest", "balanced"] = "latest",
    ) -> dict[str, Any]:
        """Search retained events with bounded pagination. Dates require timezone offsets; location may be unknown."""
        params = _filters(categories, q, country, start, end, source_id)
        params.update(limit=limit, offset=offset, order=order)
        return await api.request("GET", "api/events", params=params)

    @server.tool(annotations=READ, structured_output=True)
    async def get_event(event_id: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]) -> dict[str, Any]:
        """Get one retained event with its supporting reports and review history."""
        return await api.request("GET", f"api/events/{event_id}")

    @server.tool(annotations=READ, structured_output=True)
    async def event_timeline(
        days: Annotated[int, Field(ge=1, le=90)] = 7,
        categories: list[Category] | None = None,
        interval: Literal["hour", "day"] = "day",
    ) -> dict[str, Any]:
        """Count retained events over a UTC lookback window, by hour or day."""
        params = _filters(categories)
        params.update(_window(days))
        params["interval"] = interval
        return await api.request("GET", "api/timeline", params=params)

    @server.tool(annotations=READ, structured_output=True)
    async def cyber_relations(days: Annotated[int, Field(ge=1, le=90)] = 7) -> dict[str, Any]:
        """Get source-backed cyber country context links for a UTC lookback window."""
        return await api.request("GET", "api/cyber/relations", params=_window(days))

    @server.tool(annotations=READ, structured_output=True)
    async def monitoring_catalog() -> dict[str, Any]:
        """List monitoring sublayers, retention, source health and workflow capabilities."""
        return await api.request("GET", "api/monitoring/catalog")

    @server.tool(annotations=READ, structured_output=True)
    async def monitoring_frame(
        hours: Annotated[int, Field(ge=1, le=168)] = 24,
        layers: list[str] | None = None,
        limit: Annotated[int, Field(ge=1, le=200)] = 100,
    ) -> dict[str, Any]:
        """Read a bounded monitoring snapshot. Sublayers overlap and the response reports truncation."""
        return await api.request(
            "GET", "api/monitoring/frame", params={"hours": hours, "layers": ",".join(layers or []), "limit": limit}
        )

    if include_private:
        if not api.token:
            raise ValueError("Protected MCP tools require OSINT_MCP_API_TOKEN")

        @server.tool(annotations=READ, structured_output=True)
        async def investigation_search(
            q: Annotated[str, Field(max_length=200)] = "",
            category: str = "",
            limit: Annotated[int, Field(ge=1, le=50)] = 20,
            offset: Annotated[int, Field(ge=0, le=1000000)] = 0,
        ) -> dict[str, Any]:
            """Search protected investigation records and return the API's data/meta envelope."""
            return await api.request(
                "GET", "api/v1/osint/search", params={"q": q, "category": category, "limit": limit, "offset": offset},
                private=True,
            )

        @server.tool(annotations=READ, structured_output=True)
        async def get_investigation_record(
            record_id: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")],
        ) -> dict[str, Any]:
            """Get a protected investigation record and its provenance."""
            return await api.request("GET", f"api/v1/osint/records/{record_id}", private=True)

        @server.tool(annotations=READ, structured_output=True)
        async def list_cases(
            q: Annotated[str, Field(max_length=200)] = "",
            limit: Annotated[int, Field(ge=1, le=50)] = 20,
            offset: Annotated[int, Field(ge=0, le=1000000)] = 0,
        ) -> dict[str, Any]:
            """List saved investigation cases. Requires the administrator token."""
            return await api.request(
                "GET", "api/v1/cases", params={"q": q, "limit": limit, "offset": offset}, private=True
            )

        @server.tool(annotations=READ, structured_output=True)
        async def get_case(case_id: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]) -> dict[str, Any]:
            """Get a case, including saved evidence and notes. Requires the administrator token."""
            return await api.request("GET", f"api/v1/cases/{case_id}", private=True)

        @server.tool(annotations=WRITE, structured_output=True)
        async def create_case(
            title: Annotated[str, Field(min_length=1, max_length=200)],
            description: Annotated[str, Field(max_length=4000)] = "",
            tags: Annotated[list[str] | None, Field(max_length=20)] = None,
        ) -> dict[str, Any]:
            """Create a persistent investigation case. Requires the administrator token."""
            return await api.request(
                "POST", "api/v1/cases", body={"title": title, "description": description, "tags": tags or []},
                private=True,
            )

        @server.tool(annotations=WRITE, structured_output=True)
        async def attach_case_evidence(
            case_id: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")],
            kind: Literal["record", "media", "geo", "document", "analysis", "change", "entity"],
            reference_id: Annotated[str, Field(pattern=r"^[a-f0-9-]{32,36}$")],
        ) -> dict[str, Any]:
            """Save an existing evidence reference into a case. Requires the administrator token."""
            return await api.request(
                "POST", f"api/v1/cases/{case_id}/evidence", body={"kind": kind, "reference_id": reference_id},
                private=True,
            )

        @server.tool(annotations=WRITE, structured_output=True)
        async def add_case_note(
            case_id: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")],
            text: Annotated[str, Field(min_length=1, max_length=10000)],
        ) -> dict[str, Any]:
            """Append a persistent note to a case. Requires the administrator token."""
            return await api.request("POST", f"api/v1/cases/{case_id}/notes", body={"text": text}, private=True)

    return server


def main() -> None:
    api = AtlasAPI(
        base_url=os.getenv("OSINT_MCP_API_URL", "http://127.0.0.1:8000"),
        token=os.getenv("OSINT_MCP_API_TOKEN", ""),
    )
    create_mcp_server(api, include_private=bool(api.token)).run()


if __name__ == "__main__":
    main()
