import logging
import secrets
import sqlite3
import ssl
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .ai import AIError, AIService
from .analytics import anomalies, cross_category, regional_anomalies, sentiment, timeline
from .config import Settings
from .connectors.reddit_browser import BrowserCapture, RedditBrowser
from .connectors.registry import connectors
from .country_activity import country_activity
from .database import Database
from .geo import countries
from .military import military_brief
from .models import AnalyzeRequest, Category, EvidenceReview, Filters, stamp, utcnow
from .relations import cyber_relations, news_relations
from .security import RequestLimits
from .social_analytics import social_sentiment

log = logging.getLogger("osint.api")


def parse_filters(
    categories: str = Query("", max_length=200),
    q: str = Query("", max_length=200),
    country: str | None = Query(None, pattern="^[A-Z]{2}$"),
    start: datetime | None = None,
    end: datetime | None = None,
    bbox: str | None = Query(None, max_length=100),
    time_basis: str = Query("event", pattern="^(event|published|ingested)$"),
    aircraft_categories: str = Query("", max_length=50),
) -> Filters:
    try:
        values = tuple(float(part) for part in bbox.split(",")) if bbox else None
        return Filters(
            categories=[Category(value) for value in categories.split(",") if value],
            q=q,
            country=country,
            start=start,
            end=end,
            bbox=values,
            time_basis=time_basis,
            aircraft_categories=[int(value) for value in aircraft_categories.split(",") if value],
        )
    except (ValueError, ValidationError):
        raise HTTPException(
            422, "Invalid category, bounding box or date range; dates require timezone"
        ) from None


FilterDependency = Annotated[Filters, Depends(parse_filters)]


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    database = Database(config.database)
    providers = connectors(config)

    @asynccontextmanager
    async def lifespan(app):
        database.initialize()
        from .advanced.repository import Repository

        Repository(database).register(providers)
        async with httpx.AsyncClient(
            timeout=config.ai_timeout,
            verify=ssl.create_default_context(),
            limits=httpx.Limits(max_connections=4),
        ) as client:
            app.state.ai = AIService(config, database, client)
            yield

    app = FastAPI(
        title="Global OSINT Intelligence API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    app.state.database, app.state.settings = database, config
    app.add_middleware(RequestLimits)

    @app.middleware("http")
    async def versioned_envelope(request, call_next):
        import json
        import uuid

        response = await call_next(request)
        if not request.url.path.startswith("/api/v1/"):
            return response
        request_id = uuid.uuid4().hex
        response.headers["X-Request-ID"] = request_id
        response.headers["Cache-Control"] = "no-store"
        if "application/json" in response.headers.get("content-type", ""):
            body = b"".join([chunk async for chunk in response.body_iterator])
            value = json.loads(body)
            if response.status_code >= 400:
                value = {
                    "error_code": f"HTTP_{response.status_code}",
                    "message": value.get("detail", "Request failed"),
                    "request_id": request_id,
                }
            else:
                value["request_id"] = request_id
            headers = dict(response.headers)
            headers.pop("content-length", None)
            return JSONResponse(value, status_code=response.status_code, headers=headers)
        return response

    @app.exception_handler(sqlite3.Error)
    async def database_error(request, error):
        log.error("Database operation failed", extra={"error_type": type(error).__name__})
        return JSONResponse({"detail": "Database unavailable; retry shortly"}, status_code=503)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Avoid reflecting arbitrary user input or authorization fields in errors.
        return JSONResponse(
            {
                "detail": "Invalid request parameters or body",
                "fields": [list(item["loc"]) for item in error.errors()],
            },
            status_code=422,
        )

    def authorize(authorization: str | None = Header(None)):
        if not config.admin_token:
            raise HTTPException(
                503, "Protected functions disabled until an administrator token is configured"
            )
        expected = "Bearer " + config.admin_token
        if not authorization or not secrets.compare_digest(authorization.encode(), expected.encode()):
            raise HTTPException(
                401, "Administrator authorization required", headers={"WWW-Authenticate": "Bearer"}
            )

    @app.get("/api/health")
    def health():
        with database.connect() as db:
            db.execute("SELECT 1")
        return {"status": "ok", "version": "0.1.0", "timestamp": stamp(), "database": "sqlite-wal"}

    def source_statuses():
        persisted = {item["source_id"]: item for item in database.statuses()}
        from .advanced.repository import Repository

        disabled = {
            item["source_id"]
            for item in Repository(database).rows(
                "SELECT source_id FROM sources WHERE enabled=0 AND permissions_state='existing_connector'"
            )
        }
        result = []
        for provider in providers:
            current = persisted.get(
                provider.source_id, {"state": "never_run", "last_success": None, "error": None}
            )
            if provider.access():
                current = {**current, "state": "access_required", "error": provider.access()}
            if provider.source_id in disabled:
                current = {**current, "state": "disabled", "error": "Collection disabled by administrator"}
            last = current.get("last_success")
            stale = not last or last < stamp(
                utcnow()
                - timedelta(seconds=86400 if getattr(provider, "manual", False) else provider.interval * 2)
            )
            result.append({**provider.metadata(), **current, "stale": stale})
        return result

    from .advanced.api import router as investigation_router

    app.include_router(investigation_router(database, config, authorize, source_statuses))

    @app.get("/api/status")
    def status():
        with database.connect() as db:
            heartbeat = db.execute("SELECT heartbeat FROM worker_state WHERE id=1").fetchone()
            count = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return {
            "timestamp": stamp(),
            "connectors": source_statuses(),
            "event_count": count,
            "worker_heartbeat": heartbeat[0] if heartbeat else None,
            "worker_alive": bool(heartbeat and heartbeat[0] > stamp(utcnow() - timedelta(minutes=10))),
            "storage_bytes": sum(
                path.stat().st_size
                for path in (config.database, config.database.with_name(config.database.name + "-wal"))
                if path.exists()
            ),
        }

    @app.get("/api/layers")
    def layers():
        statuses = {item["source_id"]: item for item in source_statuses()}
        result = []
        for category in Category:
            if category == Category.threat:
                continue
            categories = {"cyber", "threat"} if category == Category.cyber else {category.value}
            own = [
                provider
                for provider in providers
                if provider.category in categories
                or categories.intersection(provider.metadata().get("categories", []))
            ]
            states = [statuses.get(provider.source_id, {}) for provider in own]
            current = [item for item in states if item.get("state") == "ok" and not item.get("stale")]
            needs_access = [item for item in states if item.get("state") == "access_required"]
            failing = [
                item
                for item in states
                if item.get("state") not in {"ok", "access_required"}
                or (item.get("state") == "ok" and item.get("stale"))
            ]
            result.append(
                {
                    "id": category.value,
                    "categories": sorted(categories),
                    "name": {
                        "geopolitical": "Geopolitical events",
                        "military": "Military OSINT",
                        "aviation": "Aviation",
                        "maritime": "Maritime",
                        "sentiment": "Global sentiment",
                        "cyber": "Cyber: Threat Actors",
                        "threat": "Threat Actor",
                        "economic": "Economic and energy",
                        "environment": "Environment and humanitarian",
                        "analysis": "Reporting signals & alerts",
                    }[category.value],
                    "sources": [provider.source_id for provider in own],
                    "health": {
                        "total": len(own),
                        "current": len(current),
                        "needs_access": len(needs_access),
                        "failing": len(failing),
                        "stale": sum(
                            item.get("state") == "ok" and item.get("stale", False) for item in states
                        ),
                        # A layer with sources but none currently working renders
                        # near-empty for reasons that have nothing to do with the
                        # world. Surface that instead of a bare zero.
                        "coverage": (
                            "no_sources"
                            if not own
                            else "none_current"
                            if not current
                            else "degraded"
                            if len(current) < len(own)
                            else "current"
                        ),
                        "detail": [
                            {
                                "source_id": provider.source_id,
                                "name": provider.name,
                                "state": statuses.get(provider.source_id, {}).get("state", "unknown"),
                                "stale": statuses.get(provider.source_id, {}).get("stale", True),
                                "error": statuses.get(provider.source_id, {}).get("error"),
                                "access_requirement": provider.access(),
                            }
                            for provider in own
                            if statuses.get(provider.source_id, {}).get("state") != "ok"
                            or statuses.get(provider.source_id, {}).get("stale")
                        ],
                    },
                }
            )
        return result

    @app.get("/api/events")
    def events(
        filters: FilterDependency,
        limit: int = Query(500, ge=1, le=1000),
        offset: int = Query(0, ge=0, le=100000),
        format: str = Query("json", pattern="^(json|geojson)$"),
        order: str = Query("latest", pattern="^(latest|balanced)$"),
    ):
        result = database.events(filters, limit, offset, balanced=order == "balanced")
        if format == "geojson":
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": event["event_id"],
                        "geometry": {"type": "Point", "coordinates": [event["longitude"], event["latitude"]]},
                        "properties": event,
                    }
                    for event in result["items"]
                    if event["latitude"] is not None
                ],
                "total": result["total"],
                "located_total": result["located_total"],
                "has_more": result["has_more"],
                "limit": limit,
                "offset": offset,
                "category_counts": result["category_counts"],
                "selection": result["selection"],
            }
        return result

    @app.get("/api/aviation/live")
    def aviation_live(
        filters: FilterDependency,
        viewer: Annotated[str | None, Query(pattern=r"^[a-f0-9]{32}$")] = None,
        active: bool = True,
    ):
        from .aviation import current_aircraft
        from .aviation_demand import set_demand

        if viewer:
            set_demand(database, viewer, active)

        result = current_aircraft(database, filters)
        source = next(item for item in source_statuses() if item["source_id"] == "opensky")
        if source["state"] in {"disabled", "access_required"}:
            result["items"] = []
        return {**result, "source_state": source["state"], "poll_seconds": config.opensky_poll_seconds}

    @app.get("/api/events/{event_id}")
    def event_detail(event_id: str):
        if len(event_id) != 32:
            raise HTTPException(404, "Event not found")
        detail = database.detail(event_id)
        if not detail:
            raise HTTPException(404, "Event not found")
        return detail

    @app.get("/api/reports/{report_id}")
    def report_detail(report_id: str):
        with database.connect() as db:
            report = db.execute("SELECT * FROM reports WHERE report_id=?", (report_id,)).fetchone()
            raw = db.execute("SELECT payload FROM raw_records WHERE report_id=?", (report_id,)).fetchone()
        if not report:
            raise HTTPException(404, "Report not found")
        import json

        return {
            **dict(report),
            "metadata": json.loads(report["metadata"]),
            "raw": json.loads(raw[0]) if raw else None,
            "raw_retained": bool(raw),
        }

    @app.get("/api/country-activity")
    def country_comparison(
        filters: FilterDependency,
        kind: str = Query("news", pattern="^(news|public|official)$"),
        platform: str = Query("all", pattern="^(all|reddit|youtube|x|mastodon|lemmy|telegram)$"),
        geography: str = Query("mentions", pattern="^(mentions|origin)$"),
    ):
        return country_activity(database, filters, kind, platform, geography)

    @app.get("/api/countries/{code}")
    def country_overview(code: str, filters: FilterDependency):
        match = next(
            (
                feature["properties"]
                for feature in countries()["features"]
                if feature["properties"]["code"] == code
            ),
            None,
        )
        if not match:
            raise HTTPException(404, "Country not found")
        selected = filters.model_copy(update={"country": code})
        result = database.events(selected, 50)
        return {
            "country": match,
            "events": result,
            "sentiment": sentiment(database, selected, "news"),
            "limitation": "Illustrative Natural Earth borders; regional news mentions do not locate an incident. Empty results do not imply absence of activity.",
        }

    @app.get("/api/sentiment")
    def sentiment_aggregates(
        filters: FilterDependency,
        kind: str = Query("news", pattern="^(news|public|official)$"),
        platform: str = Query("all", pattern="^(all|reddit|youtube|x|mastodon|lemmy|telegram)$"),
        geography: str = Query("mentions", pattern="^(mentions|origin)$"),
    ):
        if kind == "public" or platform != "all":
            return social_sentiment(database, filters, kind, platform, geography)
        return sentiment(database, filters, kind)

    @app.get("/api/relations")
    def report_connections(filters: FilterDependency):
        return news_relations(database, filters)

    @app.get("/api/cyber/relations")
    def cyber_network(filters: FilterDependency):
        return cyber_relations(database, filters)

    @app.get("/api/military")
    def military_evidence(filters: FilterDependency):
        return military_brief(database, filters)

    @app.get("/api/timeline")
    def historical(filters: FilterDependency, interval: str = Query("hour", pattern="^(hour|day)$")):
        return {
            "items": timeline(database, filters, interval),
            "time_basis": filters.time_basis,
            "limit": 3000,
            "limitation": "Retained normalized events; occurrence time falls back to publication when unknown. Playback is observation history, not interpolated trajectories.",
        }

    @app.get("/api/statistics")
    def daily_statistics():
        with database.connect() as db:
            rows = db.execute("SELECT * FROM daily_stats ORDER BY day DESC LIMIT 3300").fetchall()
        return {"items": [dict(row) for row in rows], "retention_days": config.stats_retention_days}

    @app.get("/api/sources")
    def sources():
        return [provider.metadata() for provider in providers]

    @app.get("/api/anomalies")
    def alerts():
        return {
            "items": anomalies(database),
            "method": "Deterministic event-volume comparison; no LLM inference",
        }

    @app.get("/api/anomalies/regional")
    def regional_alerts(filters: FilterDependency):
        return {
            "items": regional_anomalies(database, filters),
            "method": "Per-region cell volume against the region's own 72h baseline; no LLM inference",
        }

    @app.get("/api/cross-category")
    def cross_category_alerts(filters: FilterDependency):
        return cross_category(database, filters)

    @app.post("/api/ai/analyze", dependencies=[Depends(authorize)])
    async def analyze(request: Request, body: AnalyzeRequest):
        try:
            return await request.app.state.ai.analyze(body)
        except AIError as error:
            raise HTTPException(error.status, error.message) from None

    @app.get("/api/ai/usage")
    def ai_usage(request: Request):
        return request.app.state.ai.usage()

    @app.post("/api/admin/maintenance", dependencies=[Depends(authorize)])
    def maintenance():
        return database.maintenance(config)

    @app.post("/api/admin/social/reddit-browser", dependencies=[Depends(authorize)])
    def import_reddit_browser(body: BrowserCapture):
        provider = RedditBrowser(config)
        try:
            records = [
                provider.normalize_capture(record)
                for record in body.records
                if record.text not in {"[removed]", "[deleted]"} and record.author != "[deleted]"
            ]
        except (ValueError, TypeError, KeyError, IndexError):
            raise HTTPException(
                422, "Browser records failed public reference or timestamp validation"
            ) from None
        if not records:
            raise HTTPException(422, "Capture contains no usable public wording")
        database.replace_social_snapshot(provider.source_id, records)
        database.set_status(
            provider.source_id,
            state="ok",
            last_success=stamp(),
            error=None,
            fetched=len(body.records),
            stored=len(records),
            rejected=len(body.records) - len(records),
        )
        return {
            "source_id": provider.source_id,
            "stored": len(records),
            "delivery": "Explicit public browser capture; manual refresh, no API key",
            "expires_after_hours": 24,
        }

    @app.post("/api/admin/connectors/{source_id}/refresh", dependencies=[Depends(authorize)])
    def refresh_connector(source_id: str):
        provider = next((provider for provider in providers if provider.source_id == source_id), None)
        if not provider:
            raise HTTPException(404, "Source not found")
        if getattr(provider, "manual", False):
            raise HTTPException(
                409, "This source requires a fresh public browser capture; it is not an unattended collector"
            )
        if provider.access():
            raise HTTPException(409, provider.access())
        database.set_status(source_id, next_run=stamp())
        return {
            "source_id": source_id,
            "state": "scheduled",
            "note": "The separate worker picks up this job on its next scheduler pass",
        }

    @app.post("/api/admin/events/{event_id}/evidence", dependencies=[Depends(authorize)])
    def review_evidence(event_id: str, body: EvidenceReview):
        import json
        from urllib.parse import urlsplit

        event = database.detail(event_id)
        if not event:
            raise HTTPException(404, "Event not found")
        selected = [report for report in event["reports"] if report["report_id"] in body.report_ids]
        if len(selected) != len(body.report_ids):
            raise HTTPException(422, "Evidence must reference reports belonging to this event")
        if body.confidence == "Corroborated":
            hosts = {urlsplit(report["source_url"]).hostname for report in selected}
            if len(hosts) < 2 or not body.independent_sources_confirmed:
                raise HTTPException(
                    422,
                    "Corroboration requires distinct publisher hosts and explicit analyst confirmation of source independence",
                )
        if body.confidence == "Disputed" and (len(selected) < 2 or not body.contradiction_confirmed):
            raise HTTPException(
                422,
                "Disputed classification requires two cited reports and analyst confirmation of conflicting evidence",
            )
        if body.confidence == "Verified" and not any(
            report["metadata"]["confidence"] == "Verified" for report in selected
        ):
            raise HTTPException(
                422, "Verified requires a provider-reviewed observation or authoritative catalog record"
            )
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO evidence_reviews(event_id,confidence,basis,report_ids,independent_sources_confirmed,contradiction_confirmed,reviewed_at) VALUES (?,?,?,?,?,?,?)",
                (
                    event_id,
                    body.confidence,
                    body.basis,
                    json.dumps(body.report_ids),
                    body.independent_sources_confirmed,
                    body.contradiction_confirmed,
                    stamp(),
                ),
            )
            db.execute(
                "UPDATE events SET confidence=?,evidence_basis=?,updated_at=? WHERE event_id=?",
                (body.confidence, body.basis, stamp(), event_id),
            )
        return database.detail(event_id)

    return app


app = create_app()
