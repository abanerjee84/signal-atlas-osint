"""Read-only, redacted verification against the running local services."""

import asyncio
import json
from pathlib import Path

import httpx

from backend.config import Settings
from backend.database import Database
from backend.models import stamp


async def main():
    settings = Settings()
    result = {
        "verified_at": stamp(),
        "environment": "Windows local development",
        "ubuntu_8gb_acceptance": "not executed",
    }
    async with httpx.AsyncClient(base_url="http://127.0.0.1:5173", timeout=20) as client:
        result["workspace_status"] = (await client.get("/advanced.html")).status_code
        result["anonymous_private_case_status"] = (await client.get("/api/v1/cases")).status_code
        result["development_private_file_status"] = {}
        for path in ["/.env", "/data/osint.sqlite3", "/backend/config.py"]:
            result["development_private_file_status"][path] = (await client.get(path)).status_code
        headers = {"Authorization": "Bearer " + settings.admin_token}
        sources = (await client.get("/api/v1/sources?limit=200", headers=headers)).json()
        result["registry_count"] = sources["meta"]["total"]
        result["added_news_feeds"] = [
            {"source": s["source_id"], "health": s["health"]}
            for s in sources["data"]
            if s["source_id"]
            in {
                "un_news",
                "africanews",
                "mercopress",
                "buenos_aires_herald",
                "cna_world",
                "cna_asia",
                "rfi",
                "abc_world",
                "euronews",
                "guardian_africa",
                "guardian_americas",
                "guardian_asia",
            }
        ]
        result["country_outage_observations"] = (
            await client.get("/api/v1/cyber/disruptions?limit=1", headers=headers)
        ).json()["meta"]
    with Database(settings.database).connect() as db:
        result["schema_version"] = db.execute("PRAGMA user_version").fetchone()[0]
        result["storage_counts"] = {
            table: db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
            for table in [
                "external_records",
                "entities",
                "relationships",
                "narrative_clusters",
                "investigation_cases",
                "case_evidence",
                "media_evidence",
            ]
        }
        result["unindexed_text_records"] = db.execute(
            "SELECT COUNT(*) FROM external_records WHERE indexed_at IS NULL AND category NOT IN ('aviation','maritime') AND source_id NOT LIKE 'watch_%'"
        ).fetchone()[0]
        result["geopolitical_report_sources"] = db.execute(
            "SELECT COUNT(DISTINCT source_id) FROM external_records WHERE category='geopolitical'"
        ).fetchone()[0]
        result["geopolitical_context_countries"] = db.execute(
            "SELECT COUNT(DISTINCT country) FROM external_records WHERE category='geopolitical' AND country IS NOT NULL"
        ).fetchone()[0]
    assets = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in Path("dist").rglob("*")
        if p.is_file() and p.suffix in {".js", ".html", ".css"}
    )
    secret_names = [
        "admin_token",
        "openrouter_api_key",
        "acled_password",
        "opensky_client_secret",
        "firms_map_key",
        "maritime_token",
        "aisstream_api_key",
    ]
    result["configured_secrets_found_in_frontend"] = sum(
        1 for name in secret_names if (value := getattr(settings, name)) and value in assets
    )
    Path("docs/advanced-live-verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
