"""Explicit live verification using public news and a public routing lookup."""

import asyncio
import json
import time
from pathlib import Path

import httpx

from backend.config import Settings
from backend.models import stamp


async def main():
    settings = Settings()
    result = {
        "verified_at": stamp(),
        "inputs": "Two public geopolitical records; RIPEstat routing for 8.8.8.8",
        "private_case_content_sent": False,
    }
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000/api/v1",
        headers={"Authorization": "Bearer " + settings.admin_token},
        timeout=20,
    ) as client:
        public = (await client.get("/osint/search?category=geopolitical&limit=2")).json()["data"]
        requests = {
            "ripe": ("/cyber/enrich", {"indicator": "8.8.8.8", "provider_id": "ripe"}),
            "openrouter": (
                "/correlation/analyze",
                {
                    "record_ids": [r["record_id"] for r in public],
                    "question": "Summarize only what these public source records report, cite their evidence IDs, and describe limits. Do not invent a relationship between unrelated reports.",
                },
            ),
        }
        jobs = {}
        for name, (path, body) in requests.items():
            response = await client.post(path, json=body)
            data = response.json()
            result[name] = {"enqueue_status": response.status_code}
            if response.is_success:
                jobs[name] = data["data"]["job_id"]
                result[name]["job_id"] = jobs[name]
            else:
                result[name]["error"] = data.get("error", data.get("detail"))
        began = time.monotonic()
        while jobs and time.monotonic() - began < 210:
            for name, job_id in list(jobs.items()):
                response = await client.get("/jobs/" + job_id)
                if not response.is_success:
                    continue
                job = response.json()["data"]
                result[name]["state"] = job["state"]
                if job["state"] in {"completed", "failed", "cancelled"}:
                    result[name]["elapsed_seconds_including_queue"] = round(time.monotonic() - began, 2)
                    result[name]["result"] = job["result"]
                    result[name]["error"] = job.get("error")
                    del jobs[name]
            if jobs:
                await asyncio.sleep(7)
    Path("docs/advanced-provider-verification.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                name: {k: v for k, v in value.items() if k != "result"} if isinstance(value, dict) else value
                for name, value in result.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
