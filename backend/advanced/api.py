"""Versioned investigation API; authenticated by the existing server access token."""

from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from ..geo import countries
from ..models import Report, stamp, utcnow
from . import media
from .geo import measure, validate_geojson
from .processing import candidates, normalize_indicator, stable
from .providers import routing_resource
from .repository import Repository, identifier, packed
from .schemas import (
    AnalyzeInput,
    CaseInput,
    CorrelationInput,
    DocumentInput,
    EnrichInput,
    EvidenceInput,
    ExternalInput,
    GeoInput,
    MeasureInput,
    NoteInput,
    RelationshipInput,
    ResolveInput,
    SavedSearch,
    SourcePatch,
    VerifyInput,
    WatchInput,
    WatchPatch,
)
from .threats import CATALOGS, catalog_profiles, edge_catalogs, report_graph
from .watch import validate_url


def router(database, settings, authorize, source_statuses):
    repo = Repository(database)

    def aware(value):
        try:
            return Report.aware(value)
        except ValueError:
            raise HTTPException(422, "Dates require an explicit timezone") from None

    def read_access(request: Request):
        route = request.scope.get("route")
        if route is not None and hasattr(route, "dependant"):

            def query_keys(dependency):
                result = {p.alias for p in dependency.query_params}
                for child in dependency.dependencies:
                    result.update(query_keys(child))
                return result

            allowed = query_keys(route.dependant)
            if set(request.query_params) - allowed:
                raise HTTPException(422, "Unsupported query parameter")
        public_path = (
            request.url.path.startswith(
                ("/api/v1/osint/", "/api/v1/cyber/", "/api/v1/narratives", "/api/v1/sources")
            )
            and request.method == "GET"
        )
        if not settings.advanced_public_read or not public_path:
            try:
                authorize(request.headers.get("authorization"))
            except HTTPException:
                repo.audit("authorization.denied", "investigation-api")
                raise

    api = APIRouter(prefix="/api/v1", dependencies=[Depends(read_access)])
    private = [Depends(authorize)]

    def output(data, **meta):
        return {"data": data, "meta": meta}

    def queue_lookup(provider, payload):
        current = repo.one("SELECT enabled FROM sources WHERE source_id=?", (provider,))
        if not current or not current["enabled"]:
            raise HTTPException(409, "Provider is disabled or not configured")
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            used = db.execute(
                "SELECT COUNT(*) FROM investigation_jobs WHERE kind='lookup' AND created_at>=?",
                (utcnow().date().isoformat(),),
            ).fetchone()[0]
            pending = db.execute(
                "SELECT COUNT(*) FROM investigation_jobs WHERE kind='lookup' AND state IN ('queued','running')"
            ).fetchone()[0]
            if used >= settings.advanced_lookup_daily_budget or pending >= 4:
                raise HTTPException(429, "Public lookup budget or queue limit reached")
            jid = identifier()
            db.execute(
                "INSERT INTO investigation_jobs(id,kind,state,payload,created_at,updated_at) VALUES(?,'lookup','queued',?,?,?)",
                (jid, packed({"provider_id": provider, **payload}), stamp(), stamp()),
            )
        repo.audit("provider.lookup", jid, {"provider": provider})
        return output({"job_id": jid, "state": "queued", "provider": provider})

    def page(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0, le=1000000),
        q: str = Query("", max_length=200),
    ):
        return limit, offset, q

    def listing(table, paging, where="1=1", args=(), order="rowid DESC"):
        limit, offset, _ = paging
        count = repo.one(f"SELECT COUNT(*) total FROM {table} WHERE {where}", args)["total"]
        return output(
            repo.rows(
                f"SELECT * FROM {table} WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
                (*args, limit, offset),
            ),
            total=count,
            limit=limit,
            offset=offset,
        )

    def source_list(paging, category=""):
        limit, offset, q = paging
        if category not in {
            "",
            "search",
            "geopolitical",
            "military",
            "aviation",
            "maritime",
            "sentiment",
            "cyber",
            "economic",
            "environment",
            "analysis",
            "documents",
            "geo",
            "media",
        }:
            raise HTTPException(422, "Unsupported resource category")
        statuses = {s["source_id"]: s for s in source_statuses()}
        result = listing(
            "sources",
            paging,
            "(name LIKE ? OR source_id LIKE ?) AND (?='' OR category=?)",
            (f"%{q}%", f"%{q}%", category, category),
            "name",
        )
        for source in result["data"]:
            source["health"] = statuses.get(source["source_id"], {"state": "manual_lookup", "stale": True})
            source["last_verified_at"] = source["health"].get("last_success") or source["last_verified_at"]
            if source["source_id"] in {"ripe", "ioda", "searxng", "sans"}:
                last = repo.one(
                    "SELECT * FROM investigation_jobs WHERE kind='lookup' AND json_extract(payload,'$.provider_id')=? ORDER BY created_at DESC LIMIT 1",
                    (source["source_id"],),
                )
                source["health"] = {
                    "state": "ok"
                    if last and last["state"] == "completed"
                    else last["state"]
                    if last
                    else "never_run",
                    "last_success": source["last_verified_at"],
                    "error": last.get("error") if last else None,
                    "stale": not source["last_verified_at"]
                    or source["last_verified_at"] < stamp(utcnow() - timedelta(hours=2)),
                }
            if source["source_id"] in CATALOGS:
                catalog = repo.one(
                    "SELECT * FROM threat_catalog_state WHERE source_id=?", (source["source_id"],)
                )
                source["health"] = {
                    **catalog,
                    "stale": not catalog["last_success"]
                    or catalog["last_success"] < stamp(utcnow() - timedelta(days=2)),
                }
            if not source["enabled"] and source["permissions_state"] == "existing_connector":
                source["health"] = {**source["health"], "state": "disabled"}
            source["capabilities"] = repo.one(
                "SELECT capabilities FROM source_capabilities WHERE source_id=?", (source["source_id"],)
            )["capabilities"]
        return result

    @api.get("/osint/search")
    def search(
        request: Request,
        paging=Depends(page),
        category: str = Query("", max_length=100),
        source: str = Query("", max_length=100),
        language: str = Query("", max_length=10),
        country: str | None = Query(None, pattern="^[A-Z]{2}$"),
        start: datetime | None = None,
        end: datetime | None = None,
        order: str = Query("date", pattern="^(date|relevance)$"),
    ):
        limit, offset, q = paging
        if category not in {
            "",
            "events",
            "news",
            "geopolitical",
            "military",
            "aviation",
            "maritime",
            "sentiment",
            "cyber",
            "economic",
            "environment",
            "analysis",
            "documents",
            "organizations",
            "locations",
            "cases",
            "resources",
            "indicators",
        }:
            raise HTTPException(422, "Unsupported search category")
        for value in [start, end]:
            if value is not None:
                aware(value)
        if start and end and start > end:
            raise HTTPException(422, "Start must be before end")
        if category in {"documents", "organizations", "locations", "cases", "resources", "indicators"}:
            table = {
                "documents": "document_records",
                "organizations": "entities",
                "locations": "entities",
                "cases": "investigation_cases",
                "resources": "sources",
                "indicators": "cyber_indicators",
            }[category]
            if category in {"cases", "documents", "locations", "organizations"}:
                authorize(request.headers.get("authorization"))
            field = (
                "name"
                if table in {"entities", "sources"}
                else "normalized_value"
                if table == "cyber_indicators"
                else "title"
            )
            conditions = f"{field} LIKE ?"
            if table == "investigation_cases":
                conditions += " AND deleted_at IS NULL"
            args = [f"%{q}%"]
            if table == "entities":
                conditions += (
                    " AND type IN ('country','location')"
                    if category == "locations"
                    else " AND type IN ('organization','institution')"
                )
            if category == "documents":
                for field, value in [("source_id", source), ("jurisdiction", country)]:
                    if value:
                        conditions += f" AND {field}=?"
                        args.append(value)
                for op, instant in [(">=", start), ("<=", end)]:
                    if instant:
                        conditions += f" AND published_at{op}?"
                        args.append(stamp(instant))
                if language:
                    raise HTTPException(422, "Document language filter is not supported")
            elif source or language or start or end or country:
                raise HTTPException(
                    422,
                    "Selected collection supports category and keyword filters; use record search for source/date/language/country",
                )
            return listing(table, paging, conditions, args)
        result = repo.search(
            q,
            category,
            source,
            language,
            stamp(start) if start else None,
            stamp(end) if end else None,
            country,
            limit,
            offset,
            order,
            public_only=settings.advanced_public_read and not request.headers.get("authorization"),
        )
        return output(
            result["items"], total=result["total"], limit=limit, offset=offset, external_queries_sent=0
        )

    @api.get("/osint/records/{record_id}")
    def record(request: Request, record_id: str):
        data = repo.record(record_id)
        if data["license_classification"] not in {"source_terms", "provider_terms", "public_domain"}:
            authorize(request.headers.get("authorization"))
        return output(data)

    @api.get("/osint/resources")
    @api.get("/sources")
    def sources(paging=Depends(page), category: str = Query("", max_length=100)):
        return source_list(paging, category)

    @api.get("/sources/validation-report")
    def validation_report():
        rows = source_list((200, 0, ""))["data"]
        return output(
            {
                "sources": rows,
                "generated_at": stamp(),
                "limitations": "Source freshness describes collection health, not truth or independent corroboration. Unverified lookup resources remain disabled.",
            }
        )

    @api.get("/sources/{source_id}")
    @api.get("/osint/resources/{source_id}")
    def source(source_id: str):
        data = repo.one("SELECT * FROM sources WHERE source_id=?", (source_id,), True)
        data["capabilities"] = repo.one(
            "SELECT capabilities FROM source_capabilities WHERE source_id=?", (source_id,)
        )["capabilities"]
        return output(data)

    @api.get("/sources/{source_id}/health")
    def health(source_id: str):
        source(source_id)
        return output(
            next(
                (s for s in source_statuses() if s["source_id"] == source_id),
                {"state": "manual_lookup", "last_success": None},
            )
        )

    @api.patch("/sources/{source_id}", dependencies=private)
    def change_source(source_id: str, body: SourcePatch):
        data = source(source_id)["data"]
        if body.enabled and data["permissions_state"] != "existing_connector":
            raise HTTPException(
                409, "Automated adapter and permissions must be verified in configuration before activation"
            )
        with database.connect() as db:
            db.execute("UPDATE sources SET enabled=? WHERE source_id=?", (int(body.enabled), source_id))
        repo.audit("source.configure", source_id, body.model_dump())
        return source(source_id)

    @api.post("/osint/search/external", dependencies=private)
    def external(body: ExternalInput):
        data = source(body.provider_id)["data"]
        if not body.confirmed:
            raise HTTPException(422, "Confirm the named external provider before opening its search")
        if body.provider_id == "searxng" and settings.searxng_url:
            return queue_lookup("searxng", {"query": body.query})
        template = data["details"].get("search_url")
        if not template:
            raise HTTPException(
                409, "No permitted search adapter configured; use the resource's official website"
            )
        repo.audit("external.lookup.prepare", body.provider_id)
        return output(
            {
                "provider": data["name"],
                "url": template.replace("{query}", quote(body.query, safe="")),
                "method": "analyst_lookup",
                "query_sent_by_server": False,
            }
        )

    @api.get("/osint/search/jobs/{job_id}", dependencies=private)
    @api.get("/jobs/{job_id}", dependencies=private)
    def job(job_id: str):
        data = repo.one("SELECT * FROM investigation_jobs WHERE id=?", (job_id,), True)
        data.pop("payload", None)
        return output(data)

    @api.post("/jobs/{job_id}/cancel", dependencies=private)
    def cancel(job_id: str):
        with database.connect() as db:
            changed = db.execute(
                "UPDATE investigation_jobs SET state='cancelled',updated_at=? WHERE id=? AND state='queued'",
                (stamp(), job_id),
            ).rowcount
        if not changed:
            raise HTTPException(409, "Only queued jobs can be cancelled")
        return job(job_id)

    @api.get("/cyber/indicators")
    @api.get("/cyber/vulnerabilities")
    def indicators(
        request: Request,
        paging=Depends(page),
        type: str = Query("", pattern="^(|ip|domain|url|hash|cve)$"),
        provider: str = Query("", max_length=100),
        country: str | None = Query(None, pattern="^[A-Z]{2}$"),
        confidence: str = Query("", max_length=50),
        start: datetime | None = None,
        end: datetime | None = None,
    ):
        if request.url.path.endswith("vulnerabilities"):
            type = "cve"
        for value in [start, end]:
            if value:
                aware(value)
        _, _, q = paging
        conditions = "normalized_value LIKE ? AND (?='' OR type=?) AND (? IS NULL OR last_seen_at>=?) AND (? IS NULL OR first_seen_at<=?) AND EXISTS(SELECT 1 FROM indicator_evidence e JOIN external_records r USING(record_id) WHERE e.indicator_id=cyber_indicators.indicator_id AND (?='' OR r.source_id=?) AND (? IS NULL OR r.country=?) AND (?='' OR e.confidence=?))"
        return listing(
            "cyber_indicators",
            paging,
            conditions,
            (
                f"%{q}%",
                type,
                type,
                stamp(start) if start else None,
                stamp(start) if start else None,
                stamp(end) if end else None,
                stamp(end) if end else None,
                provider,
                provider,
                country,
                country,
                confidence,
                confidence,
            ),
            "last_seen_at DESC",
        )

    @api.get("/cyber/indicators/{indicator_id}")
    def indicator(indicator_id: str):
        data = repo.one("SELECT * FROM cyber_indicators WHERE indicator_id=?", (indicator_id,), True)
        data["evidence"] = repo.rows(
            "SELECT e.classification,e.confidence,r.* FROM indicator_evidence e JOIN external_records r USING(record_id) WHERE indicator_id=? ORDER BY r.published_at DESC LIMIT 200",
            (indicator_id,),
        )
        data["attribution_status"] = "Reported reference; not a confirmed cyber incident"
        return output(data)

    @api.post("/cyber/enrich", dependencies=private)
    def enrich(body: EnrichInput):
        if body.provider_id == "sans":
            import ipaddress

            try:
                address = ipaddress.ip_address(body.indicator)
                if not address.is_global:
                    raise ValueError("SANS lookup requires a public IP address")
            except ValueError as error:
                raise HTTPException(422, str(error)) from None
            return queue_lookup("sans", {"query": str(address)})
        if body.provider_id == "ripe":
            try:
                routing_resource(body.indicator)
            except ValueError as error:
                raise HTTPException(422, str(error)) from None
            return queue_lookup("ripe", {"query": body.indicator})
        if body.provider_id != "local":
            raise HTTPException(409, "External enrichment provider is not configured")
        try:
            kind, value = normalize_indicator(body.indicator)
        except (ValueError, UnicodeError) as error:
            raise HTTPException(422, str(error)) from None
        iid = stable(kind, value)
        found = repo.one("SELECT * FROM cyber_indicators WHERE indicator_id=?", (iid,))
        repo.audit("indicator.local_enrich", iid)
        return (
            indicator(iid)
            if found
            else output(
                {
                    "type": kind,
                    "normalized_value": value,
                    "evidence": [],
                    "method": "Local normalized evidence lookup",
                    "classification": "unknown",
                    "external_requests": 0,
                }
            )
        )

    @api.get("/cyber/disruptions")
    def disruptions(paging=Depends(page), country: str | None = Query(None, pattern="^[A-Z]{2}$")):
        result = listing(
            "cyber_disruptions", paging, "(? IS NULL OR country=?)", (country, country), "start_at DESC"
        )
        last = repo.one(
            "SELECT retrieved_at,payload FROM advanced_provider_cache WHERE source_id='ioda' ORDER BY retrieved_at DESC LIMIT 1"
        )
        result["meta"].update(
            {
                "source_id": "ioda",
                "measurement_period": last["payload"].get("measurement_period") if last else None,
                "coverage": "IODA country aggregates; awaiting first collection"
                if not last
                else "Heuristic network availability observations, no precise incident coordinates",
                "last_success": last["retrieved_at"] if last else None,
                "truncated": last["payload"].get("truncated", False) if last else False,
            }
        )
        return result

    @api.post("/cyber/disruptions/refresh", dependencies=private)
    def refresh_disruptions(country: str | None = Query(None, pattern="^[A-Z]{2}$")):
        return queue_lookup("ioda", {"country": country or ""})

    @api.get("/cyber/infrastructure")
    def infrastructure(paging=Depends(page)):
        return listing("advanced_provider_cache", paging, "source_id='ripe'", order="retrieved_at DESC")

    @api.get("/cyber/catalogs")
    def threat_catalogs():
        rows = repo.rows(
            "SELECT t.*,s.name,s.enabled,s.details FROM threat_catalog_state t JOIN sources s USING(source_id) ORDER BY s.name"
        )
        for row in rows:
            profile = repo.one(
                "SELECT profile FROM threat_catalog_objects WHERE source_id=? AND active=1 LIMIT 1",
                (row["source_id"],),
            )
            row["validation_notes"] = profile["profile"].get("catalog_exclusions", []) if profile else []
        return output(rows)

    @api.post("/cyber/catalogs/{source_id}/refresh", dependencies=private)
    def refresh_threats(source_id: str):
        current = repo.one("SELECT enabled FROM sources WHERE source_id=?", (source_id,))
        if (
            source_id not in CATALOGS
            or not current
            or not current["enabled"]
            or not settings.threat_catalogs_enabled
        ):
            raise HTTPException(409, "Reference catalog is disabled")
        pending = repo.one(
            "SELECT id FROM investigation_jobs WHERE kind='threat_catalog' AND state IN ('queued','running') AND json_extract(payload,'$.source_id')=?",
            (source_id,),
        )
        if pending:
            return output({"job_id": pending["id"], "state": "queued"})
        recent = repo.one("SELECT last_attempt FROM threat_catalog_state WHERE source_id=?", (source_id,))
        if (
            recent
            and recent["last_attempt"]
            and recent["last_attempt"] > stamp(utcnow() - timedelta(minutes=15))
        ):
            raise HTTPException(429, "Catalog was checked recently; retry after fifteen minutes")
        return output(repo.enqueue("threat_catalog", {"source_id": source_id}))

    @api.get("/cyber/actors")
    def threat_actors(
        paging=Depends(page),
        type: str = Query("threat_actor", pattern="^(threat_actor|campaign|malware|tool|technique)$"),
        source: str = Query("", max_length=100),
    ):
        limit, offset, q = paging
        condition = "EXISTS(SELECT 1 FROM threat_catalog_objects o WHERE o.entity_id=e.entity_id AND o.active=1 AND o.type=? AND (?='' OR o.source_id=?) AND (o.name LIKE ? OR EXISTS(SELECT 1 FROM json_each(o.aliases) WHERE value LIKE ?)))"
        args = (type, source, source, f"%{q}%", f"%{q}%")
        data = repo.rows(
            "SELECT e.* FROM entities e WHERE " + condition + " ORDER BY e.name LIMIT ? OFFSET ?",
            (*args, limit, offset),
        )
        for item in data:
            profiles = catalog_profiles(repo, item["entity_id"])
            item["catalog_sources"] = sorted({p["source_id"] for p in profiles if p["active"]})
            item["description"] = next((p["description"] for p in profiles if p["active"]), "")
            item["report_count"] = repo.one(
                "SELECT COUNT(*) n FROM threat_report_matches WHERE entity_id=? AND status='explicit_name_mention'",
                (item["entity_id"],),
            )["n"]
        return output(
            data,
            total=repo.one("SELECT COUNT(*) n FROM entities e WHERE " + condition, args)["n"],
            limit=limit,
            offset=offset,
            classification="reference_knowledge",
        )

    @api.get("/cyber/actors/{entity_id}")
    def threat_actor(entity_id: str):
        data = repo.evidence("entity", entity_id)
        data["catalog_profiles"] = catalog_profiles(repo, entity_id)
        data["reports"] = report_graph(repo, entity_id)
        data["attribution_status"] = (
            "Catalog and report assertions; matching a name does not establish responsibility for an incident"
        )
        return output(data)

    @api.get("/cyber/activity")
    def cyber_activity(paging=Depends(page)):
        return listing(
            "advanced_provider_cache",
            paging,
            "source_id='sans' AND cache_key<>'sans:cooldown'",
            order="retrieved_at DESC",
        )

    @api.get("/narratives")
    def narratives(paging=Depends(page), language: str = Query("", max_length=10)):
        limit, offset, q = paging
        data = repo.rows(
            "SELECT c.*,COUNT(n.record_id) samples,COUNT(DISTINCT r.source_id) sources,MAX(r.published_at) latest FROM narrative_clusters c JOIN narrative_members n USING(cluster_id) JOIN external_records r USING(record_id) WHERE c.title LIKE ? AND (?='' OR c.language=?) GROUP BY c.cluster_id ORDER BY samples DESC,latest DESC LIMIT ? OFFSET ?",
            (f"%{q}%", language, language, limit, offset),
        )
        total = repo.one(
            "SELECT COUNT(DISTINCT c.cluster_id) total FROM narrative_clusters c JOIN narrative_members n USING(cluster_id) WHERE c.title LIKE ? AND (?='' OR c.language=?)",
            (f"%{q}%", language, language),
        )["total"]
        return output(
            data,
            total=total,
            limit=limit,
            offset=offset,
            limitations="Lexical title clusters; samples are not representative public opinion",
        )

    @api.get("/narratives/sentiment")
    def sentiment(
        q: str = Query("", max_length=200), start: datetime | None = None, end: datetime | None = None
    ):
        for value in [start, end]:
            if value:
                aware(value)
        data = repo.rows(
            "SELECT r.language,n.sentiment,COUNT(*) samples,AVG(n.score) mean_score,COUNT(DISTINCT r.source_id) sources FROM narrative_members n JOIN external_records r USING(record_id) WHERE (r.title LIKE ? OR r.text LIKE ?) AND (? IS NULL OR r.published_at>=?) AND (? IS NULL OR r.published_at<=?) GROUP BY 1,2",
            (
                f"%{q}%",
                f"%{q}%",
                stamp(start) if start else None,
                stamp(start) if start else None,
                stamp(end) if end else None,
                stamp(end) if end else None,
            ),
        )
        return output(
            data,
            topic=q or "All indexed narratives",
            method="VADER English wording within topic-filtered records; not target-specific stance",
            confidence="Uncalibrated",
            limitations="Unsupported languages unclassified. Country mentions do not establish author origin or national opinion.",
        )

    @api.get("/narratives/trends")
    def trends(q: str = Query("", max_length=200), days: int = Query(14, ge=2, le=90)):
        from datetime import timedelta

        data = repo.rows(
            "SELECT m.day,m.language,SUM(m.count) samples FROM narrative_metrics m JOIN narrative_clusters c USING(cluster_id) WHERE c.title LIKE ? AND m.day>=? GROUP BY 1,2 ORDER BY 1",
            (f"%{q}%", (utcnow() - timedelta(days=days)).date().isoformat()),
        )
        counts = {}
        for row in data:
            counts[row["day"]] = counts.get(row["day"], 0) + row["samples"]
        today = utcnow().date().isoformat()
        previous = [counts.get((utcnow() - timedelta(days=i)).date().isoformat(), 0) for i in range(1, days)]
        baseline = sum(previous) / max(1, len(previous))
        return output(
            data,
            baseline_daily=baseline,
            today_partial_count=counts.get(today, 0),
            volume_ratio=counts.get(today, 0) / baseline if baseline else None,
            comparison="Partial UTC day against prior complete days; coverage changes can affect volume",
        )

    @api.get("/narratives/sources")
    def narrative_sources():
        return output(
            repo.rows(
                "SELECT r.source_id,r.language,COUNT(*) samples FROM narrative_members n JOIN external_records r USING(record_id) GROUP BY 1,2 ORDER BY samples DESC LIMIT 200"
            )
        )

    @api.get("/narratives/saved", dependencies=private)
    def saved(paging=Depends(page)):
        return listing("saved_narrative_searches", paging)

    @api.post("/narratives/saved", dependencies=private)
    def save(body: SavedSearch):
        return output(
            repo.insert(
                "saved_narrative_searches", {"id": identifier(), **body.model_dump(), "created_at": stamp()}
            )
        )

    @api.get("/narratives/{cluster_id}")
    def narrative(cluster_id: str, paging=Depends(page)):
        data = repo.one("SELECT * FROM narrative_clusters WHERE cluster_id=?", (cluster_id,), True)
        limit, offset, _ = paging
        data["members"] = repo.rows(
            "SELECT r.*,n.sentiment,n.score,n.confidence classification_confidence FROM narrative_members n JOIN external_records r USING(record_id) WHERE cluster_id=? ORDER BY r.published_at DESC LIMIT ? OFFSET ?",
            (cluster_id, limit, offset),
        )
        return output(data, limit=limit, offset=offset)

    @api.get("/geo/search")
    def geo_search(q: str = Query("", max_length=200), bbox: str | None = Query(None, max_length=100)):
        if bbox:
            from ..connectors.base import box

            try:
                west, south, east, north = box(bbox)
            except ValueError:
                raise HTTPException(422, "Invalid bounding box") from None
            data = repo.rows(
                "SELECT * FROM external_records WHERE longitude BETWEEN ? AND ? AND latitude BETWEEN ? AND ? ORDER BY published_at DESC LIMIT 200",
                (west, east, south, north),
            )
            return output(data, coverage="Reported coordinates and explicitly labeled regional context")
        try:
            parts = [float(x) for x in q.split(",")]
            if len(parts) == 2:
                from .geo import coordinate

                coordinate(parts)
                return output(
                    [
                        {
                            "longitude": parts[0],
                            "latitude": parts[1],
                            "precision": "unresolved",
                            "basis": "Analyst coordinate input; not independently substantiated",
                        }
                    ]
                )
        except ValueError:
            if "," in q:
                raise HTTPException(422, "Use valid longitude, latitude") from None
        data = [
            {
                "id": stable("country", f["properties"]["code"]),
                **f["properties"],
                "precision": "country",
                "basis": "Natural Earth country centroid",
                "historical_imagery_url": "https://worldview.earthdata.nasa.gov/",
            }
            for f in countries()["features"]
            if q.casefold() in f["properties"]["name"].casefold() or q.upper() == f["properties"]["code"]
        ]
        return output(
            data[:200], geocoder="Local Natural Earth country names; city geocoder is not configured"
        )

    @api.get("/geo/locations/{location_id}")
    def location(location_id: str):
        for feature in countries()["features"]:
            if stable("country", feature["properties"]["code"]) == location_id:
                return output({**feature, "precision": "country", "source": "Natural Earth, public domain"})
        raise HTTPException(404, "Location not found")

    @api.post("/geo/measure", dependencies=private)
    def measurement(body: MeasureInput):
        try:
            return output(measure(body.operation, body.coordinates))
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

    @api.post("/geo/import", dependencies=private)
    def geo_import(body: GeoInput):
        try:
            validate_geojson(body.geojson)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        data = body.model_dump(mode="json")
        result = repo.insert("geographic_evidence", {"id": identifier(), **data, "retrieved_at": stamp()})
        repo.audit("geo.import", result["id"])
        return output(result)

    @api.get("/geo/evidence", dependencies=private)
    def geo_evidence(paging=Depends(page)):
        return listing("geographic_evidence", paging, "title LIKE ?", (f"%{paging[2]}%",))

    @api.get("/media/evidence", dependencies=private)
    def media_list(paging=Depends(page)):
        return listing("media_evidence", paging, "deleted_at IS NULL")

    @api.post("/media/evidence", dependencies=private)
    async def media_upload(
        request: Request,
        filename: str = Query(..., min_length=1, max_length=200),
        original_url: str = Query("", max_length=2048),
    ):
        return output(await media.upload(request, repo, settings, filename, original_url))

    @api.get("/media/evidence/{media_id}/metadata", dependencies=private)
    @api.get("/media/evidence/{media_id}", dependencies=private)
    def media_detail(media_id: str):
        data = repo.evidence("media", media_id)
        data["verification_steps"] = repo.rows(
            "SELECT * FROM media_verifications WHERE media_id=? ORDER BY created_at,id LIMIT 200", (media_id,)
        )
        return output(data)

    @api.get("/media/evidence/{media_id}/file", dependencies=private)
    def media_file(media_id: str):
        data = repo.evidence("media", media_id)
        # Use stored internal identifier, never the URL or original filename as a path.
        path = settings.evidence_directory / (data["id"] + ".bin")
        if not path.exists():
            raise HTTPException(410, "Evidence file is no longer retained")
        return FileResponse(
            path,
            media_type="application/octet-stream",
            filename=data["filename"],
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @api.post("/media/evidence/{media_id}/verify", dependencies=private)
    def verification(media_id: str, body: VerifyInput):
        repo.evidence("media", media_id)
        data = repo.insert(
            "media_verifications",
            {"id": identifier(), "media_id": media_id, **body.model_dump(), "created_at": stamp()},
        )
        repo.audit("media.verify", media_id, {"step_id": data["id"]})
        return output(data)

    @api.delete("/media/evidence/{media_id}", dependencies=private)
    def media_delete(media_id: str):
        repo.evidence("media", media_id)
        with database.connect() as db:
            db.execute("UPDATE media_evidence SET deleted_at=? WHERE id=?", (stamp(), media_id))
        repo.audit("media.delete", media_id)
        return output({"deleted": True, "file_retention_days": settings.evidence_retention_days})

    @api.get("/graph/entities")
    def entities(paging=Depends(page), type: str = Query("", max_length=30)):
        return listing(
            "entities",
            paging,
            "(name LIKE ? OR entity_id IN (SELECT entity_id FROM entity_aliases WHERE alias LIKE ?)) AND (?='' OR type=?)",
            (f"%{paging[2]}%", f"%{paging[2]}%", type, type),
            "name,entity_id",
        )

    @api.get("/graph/entities/{entity_id}")
    def entity(entity_id: str):
        data = repo.evidence("entity", entity_id)
        data["aliases"] = repo.rows("SELECT alias FROM entity_aliases WHERE entity_id=?", (entity_id,))
        data["mentions"] = repo.rows(
            "SELECT r.* FROM entity_source_mentions m JOIN external_records r USING(record_id) WHERE entity_id=? ORDER BY r.published_at DESC LIMIT 200",
            (entity_id,),
        )
        data["catalog_profiles"] = catalog_profiles(repo, entity_id)
        data["cyber_reports"] = report_graph(repo, entity_id)
        return output(data)

    @api.get("/graph/relationships")
    def relationships(paging=Depends(page), status: str = Query("", pattern="^(|reported|inferred)$")):
        result = listing(
            "relationships",
            paging,
            "(EXISTS(SELECT 1 FROM relationship_evidence e WHERE e.relationship_id=relationships.relationship_id) OR EXISTS(SELECT 1 FROM threat_catalog_relations c WHERE c.relationship_id=relationships.relationship_id AND c.active=1)) AND (?='' OR status=?)",
            (status, status),
        )
        for edge in result["data"]:
            edge["catalog_evidence"] = edge_catalogs(repo, edge["relationship_id"])
            edge["evidence_ids"] = [
                r["record_id"]
                for r in repo.rows(
                    "SELECT record_id FROM relationship_evidence WHERE relationship_id=? LIMIT 200",
                    (edge["relationship_id"],),
                )
            ]
        return result

    @api.post("/graph/relationships", dependencies=private)
    def relationship(body: RelationshipInput):
        if body.from_id == body.to_id or (
            body.valid_from and body.valid_to and body.valid_from > body.valid_to
        ):
            raise HTTPException(422, "Invalid self-reference or validity interval")
        repo.evidence("entity", body.from_id)
        repo.evidence("entity", body.to_id)
        for rid in body.evidence_ids:
            repo.record(rid)
        row = {"relationship_id": identifier(), **body.model_dump(mode="json", exclude={"evidence_ids"})}
        repo.insert("relationships", row)
        with database.connect() as db:
            for rid in body.evidence_ids:
                db.execute(
                    "INSERT OR IGNORE INTO relationship_evidence VALUES(?,?)", (row["relationship_id"], rid)
                )
        repo.audit("relationship.create", row["relationship_id"], {"evidence_ids": body.evidence_ids})
        return output({**row, "evidence_ids": body.evidence_ids})

    @api.get("/graph/neighborhood/{entity_id}")
    def neighborhood(
        entity_id: str,
        nodes: int = Query(80, ge=1, le=120),
        edges: int = Query(150, ge=1, le=300),
        status: str = Query("", pattern="^(|reported|inferred)$"),
    ):
        entity(entity_id)
        data = repo.rows(
            "SELECT r.* FROM relationships r WHERE (from_id=? OR to_id=?) AND (EXISTS(SELECT 1 FROM relationship_evidence e WHERE e.relationship_id=r.relationship_id) OR EXISTS(SELECT 1 FROM threat_catalog_relations c WHERE c.relationship_id=r.relationship_id AND c.active=1)) AND (?='' OR status=?) ORDER BY CASE WHEN r.type='catalog_uses' THEN 0 ELSE 1 END,relationship_id LIMIT ?",
            (entity_id, entity_id, status, status, edges + 1),
        )
        ids, selected = {entity_id}, []
        for edge in data[:edges]:
            possible = ids | {edge["from_id"], edge["to_id"]}
            if len(possible) > nodes:
                continue
            ids = possible
            edge["catalog_evidence"] = edge_catalogs(repo, edge["relationship_id"])
            edge["evidence_ids"] = [
                r["record_id"]
                for r in repo.rows(
                    "SELECT record_id FROM relationship_evidence WHERE relationship_id=? LIMIT 50",
                    (edge["relationship_id"],),
                )
            ]
            selected.append(edge)
        return output(
            {"nodes": [repo.evidence("entity", eid) for eid in sorted(ids)], "edges": selected},
            depth=1,
            node_limit=nodes,
            edge_limit=edges,
            truncated=len(data) > len(selected),
        )

    @api.post("/graph/resolve", dependencies=private)
    def resolve(body: ResolveInput):
        for rid in body.evidence_ids:
            repo.record(rid)
        eid = body.entity_id or identifier()
        if body.entity_id:
            existing = repo.evidence("entity", eid)
            if existing["type"] != body.type:
                raise HTTPException(422, "Entity type must match the existing identity")
        else:
            repo.insert(
                "entities",
                {
                    "entity_id": eid,
                    "type": body.type,
                    "name": body.name,
                    "normalized_name": body.name.casefold(),
                    "ambiguity": "analyst-created; no automatic same-name merge",
                    "created_at": stamp(),
                },
            )
        with database.connect() as db:
            if body.alias:
                db.execute("INSERT OR IGNORE INTO entity_aliases VALUES(?,?)", (eid, body.alias))
            for rid in body.evidence_ids:
                db.execute("INSERT OR IGNORE INTO entity_source_mentions VALUES(?,?)", (eid, rid))
        repo.audit("entity.resolve", eid, {"evidence_ids": body.evidence_ids})
        return entity(eid)

    @api.get("/watch/sources", dependencies=private)
    def watch_sources(paging=Depends(page)):
        return listing("watch_sources", paging)

    @api.post("/watch/sources", dependencies=private)
    def watch_create(body: WatchInput):
        try:
            validate_url(body.url, settings.watch_allowed_hosts)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        row = repo.insert("watch_sources", {"id": identifier(), **body.model_dump(), "enabled": 1})
        repo.audit("watch.register", row["id"], {"permission_basis": body.permission_basis})
        return output(row)

    @api.patch("/watch/sources/{watch_id}", dependencies=private)
    def watch_update(watch_id: str, body: WatchPatch):
        repo.one("SELECT id FROM watch_sources WHERE id=?", (watch_id,), True)
        with database.connect() as db:
            for key, value in body.model_dump(exclude_none=True).items():
                db.execute(f"UPDATE watch_sources SET {key}=? WHERE id=?", (value, watch_id))
        repo.audit("watch.configure", watch_id, body.model_dump(exclude_none=True))
        return output(repo.one("SELECT * FROM watch_sources WHERE id=?", (watch_id,)))

    @api.get("/watch/sources/{watch_id}/changes", dependencies=private)
    def changes(watch_id: str, paging=Depends(page)):
        return listing("source_changes", paging, "watch_id=?", (watch_id,))

    @api.get("/watch/changes/{change_id}", dependencies=private)
    def change(change_id: str):
        data = repo.evidence("change", change_id)
        data["current"] = repo.one("SELECT * FROM webpage_snapshots WHERE id=?", (data["current_id"],), True)
        data["previous"] = (
            repo.one("SELECT * FROM webpage_snapshots WHERE id=?", (data["previous_id"],))
            if data["previous_id"]
            else None
        )
        return output(data)

    @api.get("/documents", dependencies=private)
    def documents(
        paging=Depends(page),
        organization: str = Query("", max_length=200),
        jurisdiction: str | None = Query(None, pattern="^[A-Z]{2}$"),
        source: str = Query("", max_length=100),
        start: datetime | None = None,
        end: datetime | None = None,
    ):
        for value in [start, end]:
            if value:
                aware(value)
        return listing(
            "document_records",
            paging,
            "title LIKE ? AND organization LIKE ? AND (? IS NULL OR jurisdiction=?) AND (?='' OR source_id=?) AND (? IS NULL OR published_at>=?) AND (? IS NULL OR published_at<=?)",
            (
                f"%{paging[2]}%",
                f"%{organization}%",
                jurisdiction,
                jurisdiction,
                source,
                source,
                stamp(start) if start else None,
                stamp(start) if start else None,
                stamp(end) if end else None,
                stamp(end) if end else None,
            ),
        )

    @api.post("/documents", dependencies=private)
    def document_import(body: DocumentInput):
        if body.license_classification == "metadata_only" and body.text:
            raise HTTPException(422, "Metadata-only documents cannot store text")
        source(body.source_id)
        result = repo.insert(
            "document_records", {"id": identifier(), **body.model_dump(mode="json"), "retrieved_at": stamp()}
        )
        repo.audit("document.import", result["id"])
        return output(result)

    @api.get("/documents/sources")
    def document_sources(paging=Depends(page)):
        return source_list(paging, "documents")

    @api.get("/documents/{document_id}", dependencies=private)
    def document(document_id: str):
        return output(repo.evidence("document", document_id))

    @api.post("/correlation/candidates", dependencies=private)
    def correlation(body: CorrelationInput):
        return output(
            candidates(repo, body.record_ids, body.weights),
            method="weighted-association-v1; not causal probability",
        )

    @api.get("/correlation/events/{record_id}")
    def event_correlations(record_id: str, paging=Depends(page)):
        return listing(
            "correlations",
            paging,
            "EXISTS(SELECT 1 FROM json_each(correlations.event_ids) WHERE value=?)",
            (record_id,),
        )

    @api.post("/correlation/analyze", dependencies=private)
    @api.post("/narratives/analyze", dependencies=private)
    @api.post("/documents/analyze", dependencies=private)
    def analyze(request: Request, body: AnalyzeInput):
        kind = "document" if "/documents/" in request.url.path else "record"
        for rid in body.record_ids:
            repo.evidence(kind, rid)
        if not settings.openrouter_api_key:
            raise HTTPException(503, "OpenRouter is not configured")
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            used = db.execute(
                "SELECT COUNT(*) FROM advanced_ai_usage WHERE principal=? AND requested_at>=?",
                ("local-administrator", utcnow().date().isoformat()),
            ).fetchone()[0]
            if used >= settings.advanced_ai_daily_budget:
                raise HTTPException(429, "Administrator daily investigation AI budget exhausted")
            pending = db.execute(
                "SELECT COUNT(*) FROM investigation_jobs WHERE kind='analysis' AND state IN ('queued','running')"
            ).fetchone()[0]
            if pending >= 4:
                raise HTTPException(429, "Investigation analysis queue is full")
            jid = identifier()
            db.execute(
                "INSERT INTO advanced_ai_usage(principal,requested_at,job_id) VALUES(?,?,?)",
                ("local-administrator", stamp(), jid),
            )
            db.execute(
                "INSERT INTO investigation_jobs(id,kind,state,payload,created_at,updated_at) VALUES(?,'analysis','queued',?,?,?)",
                (
                    jid,
                    packed(
                        {
                            **body.model_dump(),
                            "evidence_kind": kind,
                            "assessment_type": request.url.path.split("/")[3],
                        }
                    ),
                    stamp(),
                    stamp(),
                ),
            )
        repo.audit("analysis.enqueue", jid)
        return output({"job_id": jid, "state": "queued"})

    @api.get("/correlation/analyses/{analysis_id}", dependencies=private)
    def analysis(analysis_id: str):
        return output(repo.evidence("analysis", analysis_id))

    @api.get("/ai/usage", dependencies=private)
    def usage(request: Request):
        used = repo.one(
            "SELECT COUNT(*) used FROM advanced_ai_usage WHERE principal=? AND requested_at>=?",
            ("local-administrator", utcnow().date().isoformat()),
        )["used"]
        return output(
            {
                "provider": request.app.state.ai.usage(),
                "principal": "local-administrator",
                "investigation_daily_budget": settings.advanced_ai_daily_budget,
                "investigation_used": used,
                "remaining": max(0, settings.advanced_ai_daily_budget - used),
            }
        )

    @api.get("/cases", dependencies=private)
    def cases(paging=Depends(page)):
        return listing(
            "investigation_cases",
            paging,
            "deleted_at IS NULL AND title LIKE ?",
            (f"%{paging[2]}%",),
            "updated_at DESC",
        )

    @api.post("/cases", dependencies=private)
    def create_case(body: CaseInput):
        row = repo.insert(
            "investigation_cases",
            {"id": identifier(), **body.model_dump(), "created_at": stamp(), "updated_at": stamp()},
        )
        repo.audit("case.create", row["id"])
        return output(row)

    @api.get("/cases/{case_id}", dependencies=private)
    def case(case_id: str):
        return output(repo.case(case_id))

    @api.patch("/cases/{case_id}", dependencies=private)
    def update_case(case_id: str, body: CaseInput):
        repo.case(case_id)
        with database.connect() as db:
            db.execute(
                "UPDATE investigation_cases SET title=?,description=?,status=?,tags=?,updated_at=?,deleted_at=? WHERE id=?",
                (
                    body.title,
                    body.description,
                    body.status,
                    packed(body.tags),
                    stamp(),
                    stamp() if body.status == "deleted" else None,
                    case_id,
                ),
            )
        repo.audit("case.update", case_id, {"status": body.status})
        return output({"id": case_id, **body.model_dump(), "updated_at": stamp()})

    @api.post("/cases/{case_id}/evidence", dependencies=private)
    def attach(case_id: str, body: EvidenceInput):
        return output(repo.attach(case_id, body.kind, body.reference_id))

    @api.post("/cases/{case_id}/notes", dependencies=private)
    def note(case_id: str, body: NoteInput):
        repo.case(case_id)
        row = repo.insert(
            "case_notes", {"id": identifier(), "case_id": case_id, "text": body.text, "created_at": stamp()}
        )
        repo.audit("case.note.add", case_id, {"note_id": row["id"]})
        return output(row)

    @api.get("/cases/{case_id}/timeline", dependencies=private)
    def case_timeline(case_id: str):
        data = repo.case(case_id)
        rows = (
            [{"kind": "evidence", "timestamp": r["added_at"], **r} for r in data["evidence"]]
            + [{"kind": "note", "timestamp": r["created_at"], **r} for r in data["notes"]]
            + [{"kind": "audit", "timestamp": r["created_at"], **r} for r in data["history"]]
        )
        return output(sorted(rows, key=lambda r: r["timestamp"]))

    @api.get("/cases/{case_id}/graph", dependencies=private)
    def case_graph(case_id: str):
        case = repo.case(case_id)
        root = {"entity_id": case_id, "name": case["title"], "type": "case"}
        children = [
            {
                "entity_id": e["id"],
                "name": e["snapshot"].get("title", e["snapshot"].get("name", e["kind"])),
                "type": e["kind"],
            }
            for e in case["evidence"][:100]
        ]
        edges = [
            {
                "relationship_id": e["id"],
                "from_id": case_id,
                "to_id": e["id"],
                "type": "saved_evidence",
                "status": "analyst_saved",
                "evidence_ids": [e["reference_id"]] if e["kind"] == "record" else [],
                "snapshot": e["snapshot"],
                "sha256": e["sha256"],
            }
            for e in case["evidence"][:100]
        ]
        return output(
            {"nodes": [root, *children], "edges": edges},
            node_limit=101,
            truncated=len(case["evidence"]) > 100,
        )

    @api.post("/cases/{case_id}/export", dependencies=private)
    def export(case_id: str, format: str = Query("json", pattern="^(json|markdown)$")):
        data = repo.case(case_id)
        for item in data["evidence"]:
            snapshot = item["snapshot"]
            if snapshot.get("license_classification") in {
                "restricted",
                "metadata_only",
                "source_terms",
                "provider_terms",
            }:
                for key in ["text", "raw", "metadata", "description", "diff", "geojson"]:
                    snapshot.pop(key, None)
                item["export_content"] = "Reference metadata only; stored original snapshot hash retained"
        repo.audit("case.export", case_id, {"format": format})
        if format == "json":
            return output(data, exported_at=stamp())
        lines = [
            "# " + data["title"],
            data["description"],
            "Status: " + data["status"],
            "Created: " + data["created_at"],
            "## Evidence",
        ]
        for item in data["evidence"]:
            s = item["snapshot"]
            lines += [
                "- " + s.get("title", s.get("filename", item["kind"])),
                "  Source: " + str(s.get("original_url", s.get("source_url", "Local evidence"))),
                "  Saved: " + item["added_at"],
                "  Original snapshot SHA-256: " + item["sha256"],
            ]
        lines += ["## Analyst notes", *[n["created_at"] + " — " + n["text"] for n in data["notes"]]]
        return output({"format": "markdown", "text": "\n\n".join(lines)}, exported_at=stamp())

    return api
