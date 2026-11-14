# MCP and HTTP API integration

Signal Atlas has one data and authorization boundary: its FastAPI service. The MCP adapter in `backend/mcp_server.py` calls that service through documented routes. It does not read SQLite, run collectors, or bypass API validation. Start the API before starting MCP.

The adapter uses the [official Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk) 2.3.0 over local **stdio**. It exposes nine public read tools, plus seven protected investigation tools when `OSINT_MCP_API_TOKEN` is set. For network clients, use the existing HTTP API and its OpenAPI schema. This release does not expose an MCP HTTP listener.

## Install and start

From the repository root, install the optional dependency set into the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-mcp.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

On Linux or macOS, use `.venv/bin/python` in place of `.venv\Scripts\python.exe`. Keep the API process running. It applies database migrations at startup; the worker is a separate process if fresh provider collection is needed. Check `http://127.0.0.1:8000/api/health` before connecting a client.

If pip cannot use the Windows certificate store in your environment, the equivalent install is `uv pip install --python .\.venv\Scripts\python.exe --system-certs -r requirements-mcp.txt`.

In another terminal, start MCP:

```powershell
.\.venv\Scripts\python.exe scripts\mcp_server.py
```

Stdio is a protocol stream, so the command appears idle when run directly. Normally an MCP host launches it. Set `OSINT_MCP_API_URL` if the FastAPI service is at a different URL. The default is `http://127.0.0.1:8000`. Do not put credentials in that URL.

### MCP host configuration

Use absolute paths. This example is for a Windows checkout; escape backslashes in JSON:

```json
{
  "mcpServers": {
    "signal-atlas": {
      "command": "E:\\path\\to\\signal-atlas-osint\\.venv\\Scripts\\python.exe",
      "args": ["E:\\path\\to\\signal-atlas-osint\\scripts\\mcp_server.py"],
      "env": {
        "OSINT_MCP_API_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

For protected case and investigation tools, configure `OSINT_ADMIN_TOKEN` on the FastAPI service and pass the same value to the MCP process as `OSINT_MCP_API_TOKEN`. Store it in the host's secret or environment configuration, not in a checked-in file. The adapter sends the bearer token only on protected API calls. Without this variable, the protected tools are absent from `tools/list`. A non-loopback API URL must use HTTPS when a token is configured.

### Verify from an MCP client

To launch the stdio server, discover tools and search through the SDK:

```python
import asyncio
import sys
from mcp import Client, StdioServerParameters

async def main():
    server = StdioServerParameters(
        command=sys.executable,
        args=[r"E:\path\to\signal-atlas-osint\scripts\mcp_server.py"],
    )
    async with Client(server) as client:
        print([tool.name for tool in (await client.list_tools()).tools])
        result = await client.call_tool("search_events", {
            "categories": ["infrastructure"],
            "source_id": "dshield",
            "limit": 10,
        })
        print(result.structured_content)

asyncio.run(main())
```

## Tool catalog

MCP names and arguments are discoverable through `tools/list`. All read results retain the HTTP API's source IDs, evidence basis, timestamps, limits and coverage fields. Dictionary results use MCP structured output. `list_layers` returns an array wrapped by the SDK in `structured_content.result`.

| MCP tool | HTTP route | Main arguments and bound | Access |
| --- | --- | --- | --- |
| `health` | `GET /api/health` | None | Public |
| `source_status` | `GET /api/status` | None | Public |
| `list_layers` | `GET /api/layers` | None | Public |
| `search_events` | `GET /api/events` | Categories, literal `q`, country, timezone-aware `start`/`end`, source ID, `limit` 1–100, `offset` 0–100,000, latest/balanced order | Public |
| `get_event` | `GET /api/events/{event_id}` | 32-character lowercase hex event ID | Public |
| `event_timeline` | `GET /api/timeline` | UTC lookback 1–90 days, optional categories, hour/day interval | Public |
| `cyber_relations` | `GET /api/cyber/relations` | UTC lookback 1–90 days | Public |
| `monitoring_catalog` | `GET /api/monitoring/catalog` | None | Public |
| `monitoring_frame` | `GET /api/monitoring/frame` | Lookback 1–168 hours, layer IDs, `limit` 1–200 | Public |
| `investigation_search` | `GET /api/v1/osint/search` | Keyword, category, `limit` 1–50, offset | Stdio with token |
| `get_investigation_record` | `GET /api/v1/osint/records/{record_id}` | 32-character lowercase hex record ID | Stdio with token |
| `list_cases` | `GET /api/v1/cases` | Keyword, `limit` 1–50, offset | Stdio with token |
| `get_case` | `GET /api/v1/cases/{case_id}` | 32-character lowercase hex case ID | Stdio with token |
| `create_case` | `POST /api/v1/cases` | Title 1–200 chars, description up to 4,000 chars, up to 20 tags; creates an open case | Stdio with token |
| `attach_case_evidence` | `POST /api/v1/cases/{case_id}/evidence` | Case ID, evidence kind and existing reference ID | Stdio with token |
| `add_case_note` | `POST /api/v1/cases/{case_id}/notes` | Case ID and note text 1–10,000 chars | Stdio with token |

The three case action tools persist data and are marked as non-idempotent additions. The API validates the referenced evidence and records the change. MCP does not expose collector refresh, passive host lookups, AI analysis, file import, deletion, or arbitrary URL/SQL execution. Use the documented HTTP API for workflows outside this tool set.

## HTTP API examples

FastAPI publishes its full OpenAPI schema at `/api/openapi.json` and an interactive reference at `/api/docs`. MCP uses that API rather than replacing it.

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/events?categories=infrastructure&source_id=dshield&limit=10'
Invoke-RestMethod 'http://127.0.0.1:8000/api/monitoring/frame?layers=aircraft&hours=24&limit=100'
```

For a protected request:

```powershell
$headers = @{ Authorization = "Bearer $env:OSINT_ADMIN_TOKEN" }
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/cases?limit=20' -Headers $headers
```

`source_id` selects one exact source ID on event queries. It can be combined with category, literal search, date, country, bounding box and pagination. Dates must include a timezone, for example `2026-11-14T00:00:00Z`. The event API caps pages at 1,000; MCP deliberately caps its own event pages at 100. API event pages report `total`, `located_total`, `has_more`, category counts and the selection method. The investigation API returns `data` and `meta` envelopes with a request ID.

## Errors, limits and deployment

The adapter preserves API status meaning in MCP tool errors: 401 for a bad administrator token, 404 for an absent ID, 422 for invalid filters, 429 for a rate or quota limit, and 503 for a disabled protected function. Invalid MCP argument shapes are rejected before an API request. A connection failure reports that the API is unavailable; check `OSINT_MCP_API_URL` and `/api/health`.

FastAPI limits request bodies and per-peer request rates. MCP adds tighter page sizes but does not increase provider quotas or start background collection. Its 30-second HTTP timeout applies to each adapter call. Stale provider data stays labeled in the API response. An empty result can mean a date, source or location filter, missing access, or delayed collection.

The MCP server runs as a local child process and relies on the trust boundary of the host that launches it. Protected MCP tools are available only when that process has the administrator token. Keep the API's bearer token and provider credentials outside source control. The HTTP API remains available to network integrations under its existing access rules; see [API reference](API.md), [deployment](DEPLOYMENT.md) and [operations](OPERATIONS.md).

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest tests\backend\test_mcp_server.py -q --basetemp=.pytest_mcp
.\.venv\Scripts\python.exe -m ruff check backend\mcp_server.py scripts\mcp_server.py tests\backend\test_mcp_server.py
```

The MCP tests connect an official SDK client to the server in process and send its HTTP calls to the actual FastAPI app through an in-memory ASGI transport. They cover discovery, source filtering, a retained event lookup, case creation and a saved note.
