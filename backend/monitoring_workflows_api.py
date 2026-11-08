"""Protected investigation workflows shared with the monitoring dashboard."""

import asyncio
import hashlib
import importlib.util
import io
import json
import uuid
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from PIL import Image, UnidentifiedImageError
from pydantic import Field, model_validator

from .advanced.repository import Repository, packed
from .connectors.base import ProviderError, SafeHTTP
from .connectors.expanded import PublishedAssessments, ReferenceFeed, TinyGS, Wastewater
from .models import Report, stamp
from .monitoring import save_directory
from .monitoring_imagery import RasterComparison, SceneSearch, asset_bytes, scene, search_scenes
from .monitoring_imports import csv_records
from .monitoring_recon import Lookup, finish, lookup, reserve
from .monitoring_workflows import (
    AssetImport,
    Input,
    Watch,
    assets,
    create_watch,
    entity_history,
    evaluate_watches,
    exposure,
)
from .tls import outbound_tls

CAPABILITIES = [
    ("c2", "C2 and malicious-URL feeds", ["feodo", "urlhaus"], "layers"),
    ("weather", "Official weather warnings", ["nws_alerts"], "layers"),
    ("space-weather", "Space-weather timelines", ["swpc"], "layers"),
    (
        "cameras",
        "Regional public cameras",
        ["caltrans_cameras", "nyc_cameras", "singapore_cameras"],
        "layers",
    ),
    ("references", "Versioned infrastructure assets", ["wri_power_plants"], "assets"),
    ("watches", "Spatial and entity watch rules", [], "watches"),
    ("gfw", "Apparent vessel activity", ["gfw_events"], "layers"),
    ("radio", "Receiver discovery and radio receptions", ["kiwisdr", "psk_reporter"], "layers"),
    ("tinygs", "Satellite reception metadata", ["tinygs"], "layers"),
    ("rail", "Regional train tracking", ["amtraker", "digitraffic"], "layers"),
    ("environment", "Air quality and volcano references", ["openaq", "volcanoes"], "layers"),
    ("imagery", "Acquisition-dated imagery catalogs", ["imagery_catalog"], "imagery"),
    ("products", "Published assessments and raster comparisons", ["published_assessments"], "imagery"),
    ("enrichment", "Passive recon and candidate entity links", ["passive_recon"], "recon"),
    (
        "exposure",
        "Supplier exposure, narratives and wastewater",
        ["euvsdisinfo", "wastewater_export"],
        "exposure",
    ),
]


def capabilities():
    return [
        {"id": key, "name": name, "sources": sources, "workflow": workflow}
        for key, name, sources, workflow in CAPABILITIES
    ]


class Toggle(Input):
    enabled: bool


class Exposure(Input):
    kind: str = Field("supplier", pattern="^(supplier|power-plant|data-center|cable)$")
    radius_km: float = Field(50, ge=0.1, le=500, allow_inf_nan=False)
    hours: int = Field(24, ge=1, le=168)


class Evidence(Input):
    case_id: str = Field(pattern="^[a-f0-9]{32}$")
    kind: str = Field(pattern="^(observation|scene|analysis|alert|asset|lookup)$")
    reference_id: str = Field(pattern="^[a-f0-9]{32,64}$")


class ObservationImport(Input):
    kind: str = Field(pattern="^(wastewater_export|published_assessments|tinygs)$")
    permission_basis: str = Field(min_length=10, max_length=500)
    records: list[dict] = Field(default_factory=list, max_length=200)
    csv_text: str = Field("", max_length=60000)

    @model_validator(mode="after")
    def format(self):
        if bool(self.records) == bool(self.csv_text):
            raise ValueError("Supply records or CSV text")
        return self


class Candidate(Input):
    lookup_id: str = Field(pattern="^[a-f0-9]{32}$")
    candidate_id: str = Field(pattern="^Q[1-9][0-9]{0,15}$")
    case_id: str | None = Field(None, pattern="^[a-f0-9]{32}$")


def archive_analysis(database, kind, payload):
    identifier = uuid.uuid4().hex
    with database.connect() as db:
        db.execute(
            "INSERT INTO monitoring_analyses VALUES(?,?,?,?)",
            (identifier, kind, stamp(), json.dumps(payload)),
        )
    return {"id": identifier, "kind": kind, **payload}


def router(database, settings, authorize):
    api = APIRouter(
        prefix="/api/monitoring", tags=["Monitoring investigations"], dependencies=[Depends(authorize)]
    )

    def permitted(source_id, check_enabled=True):
        from types import SimpleNamespace

        from .worker import permission_refusal

        source = SimpleNamespace(source_id=source_id, settings=settings)
        if permission_refusal(database, source):
            raise HTTPException(403, "Collection is blocked by the deployment's recorded source permissions")
        with database.connect() as db:
            row = db.execute("SELECT enabled FROM sources WHERE source_id=?", (source_id,)).fetchone()
        if check_enabled and row and not row[0]:
            raise HTTPException(403, "This source is disabled by the administrator")

    def failure(error):
        return (
            HTTPException(502, "Provider request failed; inspect source access and retry later")
            if isinstance(error, (ProviderError, httpx.HTTPError))
            else HTTPException(422, str(error))
        )

    @api.get("/watches")
    def watches():
        with database.connect() as db:
            rows = db.execute("SELECT * FROM monitoring_rules ORDER BY created_at DESC LIMIT 100").fetchall()
        return {"items": [{**dict(r), "config": json.loads(r["config"])} for r in rows]}

    @api.post("/watches")
    def add_watch(body: Watch):
        try:
            identifier = create_watch(database, body)
        except ValueError as e:
            raise failure(e) from None
        Repository(database).audit("monitoring.watch.create", identifier, {"name": body.name})
        return {"id": identifier, **body.model_dump()}

    @api.post("/watches/{identifier}/enabled")
    def toggle_watch(identifier: str, body: Toggle):
        with database.connect() as db:
            if not db.execute(
                "UPDATE monitoring_rules SET enabled=? WHERE id=?", (int(body.enabled), identifier)
            ).rowcount:
                raise HTTPException(404, "Watch not found")
        return {"id": identifier, "enabled": body.enabled}

    @api.post("/watches/evaluate")
    def tick():
        return evaluate_watches(database)

    @api.get("/alerts")
    def alerts(limit: int = Query(100, ge=1, le=500)):
        with database.connect() as db:
            rows = db.execute(
                "SELECT a.*,r.name FROM monitoring_alerts a JOIN monitoring_rules r ON r.id=a.rule_id ORDER BY triggered_at DESC LIMIT ?",
                (limit + 1,),
            ).fetchall()
        return {
            "items": [{**dict(r), "snapshot": json.loads(r["snapshot"])} for r in rows[:limit]],
            "truncated": len(rows) > limit,
        }

    @api.post("/alerts/{identifier}/acknowledge")
    def acknowledge(identifier: str):
        with database.connect() as db:
            if not db.execute(
                "UPDATE monitoring_alerts SET acknowledged_at=COALESCE(acknowledged_at,?) WHERE id=?",
                (stamp(), identifier),
            ).rowcount:
                raise HTTPException(404, "Alert not found")
        return {"id": identifier, "acknowledged": True}

    @api.get("/assets")
    def asset_list(
        kind: str = Query("", pattern="^(|power-plant|data-center|cable|supplier)$"),
        limit: int = Query(2000, ge=1, le=5000),
    ):
        return assets(database, kind, limit)

    @api.post("/assets/import")
    def import_assets(body: AssetImport):
        permitted(body.source_id, check_enabled=False)
        try:
            Report.safe_url(body.source_url)
            provider = ReferenceFeed(
                settings,
                {
                    "source_id": body.source_id,
                    "name": body.name,
                    "kind": body.kind,
                    "license": body.license,
                    "version": body.version,
                    "url": body.source_url,
                },
            )
            reports = [provider.normalize(r) for r in body.features]
            stored = save_directory(database, reports)
        except (ValueError, KeyError, TypeError) as e:
            raise HTTPException(
                422,
                "Invalid reference import; provide feature IDs, names, valid geometry and source/version/license",
            ) from e
        Repository(database).audit(
            "monitoring.assets.import",
            body.source_id,
            {"stored": stored, "version": body.version, "license": body.license},
        )
        return {"stored": stored, "source_id": body.source_id, "classification": "reference"}

    @api.post("/exposure")
    def asset_exposure(body: Exposure):
        result = exposure(database, body.kind, body.radius_km, body.hours)
        return archive_analysis(database, "asset_exposure", result)

    @api.post("/observations/import")
    def import_observations(body: ObservationImport):
        permitted(body.kind, check_enabled=False)
        config = settings.model_copy(
            update={
                "wastewater_license": body.permission_basis,
                "published_assessments_license": body.permission_basis,
            }
        )
        provider = {
            "wastewater_export": Wastewater,
            "published_assessments": PublishedAssessments,
            "tinygs": TinyGS,
        }[body.kind](config)
        try:
            records = csv_records(body.csv_text, body.kind) if body.csv_text else body.records
            reports = [provider.normalize(r) for r in records]
            for report in reports:
                report.raw["monitoring"]["permission_basis"] = body.permission_basis
            stored = save_directory(database, reports)
        except (ValueError, KeyError, TypeError) as e:
            raise HTTPException(
                422,
                "Invalid authorized export; check provider record IDs, times, units, source links and geometry",
            ) from e
        Repository(database).audit(
            "monitoring.observations.import",
            body.kind,
            {"stored": stored, "permission_basis": body.permission_basis},
        )
        return {"stored": stored, "source_id": body.kind}

    @api.get("/entity-history")
    def history(
        source_id: str = Query(max_length=100),
        entity_id: str = Query(max_length=512),
        hours: int = Query(24, ge=1, le=168),
        at: datetime | None = None,
    ):
        from .monitoring_api import moment

        end = moment(at)
        return entity_history(database, source_id, entity_id, end - timedelta(hours=hours), end)

    @api.post("/scenes/search")
    async def imagery_search(body: SceneSearch):
        permitted("imagery_catalog")
        try:
            target = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
            key, cached = reserve(database, settings, "imagery", target)
            if cached is not None:
                return {**cached, "cached": True}
            async with httpx.AsyncClient(timeout=settings.http_timeout, verify=outbound_tls()) as client:
                result = await search_scenes(database, settings, SafeHTTP(settings, client), body)
            finish(database, key, result, hours=1)
            return {**result, "cached": False}
        except (ValueError, ProviderError, httpx.HTTPError) as e:
            raise failure(e) from None
        except (KeyError, TypeError, OverflowError):
            raise HTTPException(502, "Provider returned an unsupported catalog record") from None

    @api.get("/scenes")
    def scenes(limit: int = Query(50, ge=1, le=100)):
        with database.connect() as db:
            rows = db.execute(
                "SELECT id FROM monitoring_scenes ORDER BY acquired_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return {"items": [scene(database, r["id"]) for r in rows]}

    @api.get("/scenes/{identifier}/preview")
    async def preview(identifier: str):
        permitted("imagery_catalog")
        try:
            item = scene(database, identifier)
            async with httpx.AsyncClient(timeout=settings.http_timeout, verify=outbound_tls()) as client:
                payload = await asset_bytes(settings, SafeHTTP(settings, client), item, "thumbnail")
            with Image.open(io.BytesIO(payload)) as image:
                fmt = image.format
                if (
                    fmt not in {"JPEG", "PNG", "WEBP"}
                    or image.width * image.height > 16_000_000
                    or len(payload) > 8_388_608
                ):
                    raise ValueError("Preview exceeds safe image limits")
                image.verify()
            return Response(
                payload,
                media_type={"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[fmt],
                headers={"Cache-Control": "private, max-age=300"},
            )
        except (ValueError, KeyError, ProviderError, httpx.HTTPError, UnidentifiedImageError) as e:
            raise HTTPException(422, "Preview unavailable; use the original scene reference") from e

    @api.post("/scenes/compare")
    async def comparison(body: RasterComparison):
        permitted("imagery_catalog")
        if importlib.util.find_spec("rasterio") is None:
            raise HTTPException(503, "Install requirements-geo.txt to enable raster comparisons")
        from .monitoring_rasters import compare_rasters

        try:
            before, after = scene(database, body.before_id), scene(database, body.after_id)
            if (
                before["provider"] != after["provider"]
                or before["collection"] != after["collection"]
                or before["acquired_at"] >= after["acquired_at"]
            ):
                raise ValueError("Choose ordered acquisitions from the same provider and product collection")
            if (
                body.kind == "water"
                and before["provider"] != "opera-water"
                or body.kind == "ndvi"
                and before["provider"] != "sentinel2"
            ):
                raise ValueError(
                    "Water comparisons need OPERA water products; NDVI needs Sentinel-2 reflectance and SCL"
                )
            target = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
            key, cached = reserve(database, settings, "raster", target)
            if cached is not None:
                return {**cached, "cached": True}
            keys = ["water"] if body.kind == "water" else ["red", "nir", "scl"]
            payloads = {}
            async with httpx.AsyncClient(timeout=settings.http_timeout, verify=outbound_tls()) as client:
                http = SafeHTTP(settings, client)
                for label, item in [("before", before), ("after", after)]:
                    for asset in keys:
                        payloads[f"{label}.{asset}"] = await asset_bytes(settings, http, item, asset)
            result = await asyncio.to_thread(
                compare_rasters, settings, body, {"before": before, "after": after}, payloads
            )
            result["provenance"] = [
                {"id": r["id"], "acquired_at": r["acquired_at"], "source_url": r["metadata"]["source_url"]}
                for r in [before, after]
            ]
            archived = archive_analysis(database, body.kind, result)
            finish(database, key, archived)
            return archived
        except (ValueError, ProviderError, httpx.HTTPError) as e:
            raise failure(e) from None

    @api.post("/recon")
    async def recon(body: Lookup):
        permitted("passive_recon")
        try:
            key, cached = reserve(database, settings, body.kind, body.target.strip().casefold())
            if cached is not None:
                return {**cached, "cached": True}
            async with httpx.AsyncClient(timeout=settings.http_timeout, verify=outbound_tls()) as client:
                result = await lookup(SafeHTTP(settings, client), body)
            result.update(received_at=stamp(), kind=body.kind, target=body.target, lookup_id=key)
            finish(database, key, result)
            Repository(database).audit("monitoring.recon.read", key, {"kind": body.kind})
            return {**result, "cached": False}
        except (ValueError, ProviderError, httpx.HTTPError) as e:
            raise failure(e) from None

    @api.get("/analyses/{identifier}")
    def analysis(identifier: str):
        with database.connect() as db:
            row = db.execute("SELECT * FROM monitoring_analyses WHERE id=?", (identifier,)).fetchone()
        if not row:
            raise HTTPException(404, "Analysis not found")
        return {**dict(row), "payload": json.loads(row["payload"])}

    @api.post("/enrichment/retain")
    def retain_candidate(body: Candidate):
        repo = Repository(database)
        if body.case_id:
            repo.case(body.case_id)
        with database.connect() as db:
            row = db.execute(
                "SELECT payload FROM monitoring_lookup_calls WHERE id=? AND kind='wikidata'",
                (body.lookup_id,),
            ).fetchone()
        if not row or not row[0]:
            raise HTTPException(404, "Retained Wikidata lookup not found")
        payload = json.loads(row[0])
        candidate = next((r for r in payload.get("candidates", []) if r["id"] == body.candidate_id), None)
        if not candidate:
            raise HTTPException(422, "Candidate was not returned by this lookup")
        eid = hashlib.sha256(("wikidata:" + body.candidate_id).encode()).hexdigest()[:32]
        rid = hashlib.sha256(("wikidata-lookup:" + body.lookup_id).encode()).hexdigest()[:32]
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT OR IGNORE INTO external_records(record_id,source_id,external_record_id,original_url,title,text,language,kind,category,ingested_at,updated_at,precision,confidence,metadata,license_classification) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    rid,
                    "passive_recon",
                    body.lookup_id,
                    candidate["source_url"],
                    f"Wikidata candidate {body.candidate_id}",
                    packed(candidate),
                    "en",
                    "candidate_enrichment",
                    "reference",
                    stamp(),
                    stamp(),
                    "unknown",
                    "Single-source",
                    packed({"candidate": candidate, "retrieved_at": payload.get("received_at")}),
                    "metadata_only",
                ),
            )
            db.execute(
                "INSERT OR IGNORE INTO entities VALUES(?,?,?,?,?,?)",
                (
                    eid,
                    "organization",
                    candidate.get("label") or body.candidate_id,
                    (candidate.get("label") or body.candidate_id).casefold(),
                    "Wikidata candidate; not a verified identity match",
                    stamp(),
                ),
            )
            db.execute("INSERT OR IGNORE INTO entity_source_mentions VALUES(?,?)", (eid, rid))
            relationships = []
            for claim in candidate.get("relations", []):
                value = claim.get("value")
                if (
                    claim.get("property") not in {"P127", "P749", "P159", "P17"}
                    or not isinstance(value, dict)
                    or not str(value.get("id", "")).startswith("Q")
                ):
                    continue
                target = hashlib.sha256(("wikidata:" + value["id"]).encode()).hexdigest()[:32]
                db.execute(
                    "INSERT OR IGNORE INTO entities VALUES(?,?,?,?,?,?)",
                    (
                        target,
                        "reference",
                        value["id"],
                        value["id"].casefold(),
                        "Source knowledge-base claim; label unresolved",
                        stamp(),
                    ),
                )
                relationship = hashlib.sha256(
                    f"{eid}:{claim['property']}:{target}:{rid}".encode()
                ).hexdigest()[:32]
                db.execute(
                    "INSERT OR IGNORE INTO relationships VALUES(?,?,?,?,?,?,?,?)",
                    (
                        relationship,
                        eid,
                        target,
                        claim["relation"],
                        "source_claim",
                        None,
                        None,
                        packed(
                            {
                                "claim": claim,
                                "source_url": candidate["source_url"],
                                "retrieved_at": payload.get("received_at"),
                            }
                        ),
                    ),
                )
                db.execute("INSERT OR IGNORE INTO entity_source_mentions VALUES(?,?)", (target, rid))
                db.execute("INSERT OR IGNORE INTO relationship_evidence VALUES(?,?)", (relationship, rid))
                relationships.append(relationship)
        if body.case_id:
            repo.attach(body.case_id, "record", rid)
            repo.attach(body.case_id, "entity", eid)
        repo.audit(
            "monitoring.enrichment.retain",
            eid,
            {"lookup_id": body.lookup_id, "candidate_id": body.candidate_id},
        )
        return {
            "entity_id": eid,
            "relationship_ids": relationships,
            "status": "source_claim",
            "basis": "Analyst retained a sourced candidate; not an automatic verified identity merge",
        }

    @api.post("/evidence")
    def evidence(body: Evidence):
        repo = Repository(database)
        repo.case(body.case_id)
        tables = {
            "observation": ("monitoring_history", "observation_id", "payload"),
            "scene": ("monitoring_scenes", "id", None),
            "analysis": ("monitoring_analyses", "id", "payload"),
            "alert": ("monitoring_alerts", "id", "snapshot"),
            "asset": ("monitoring_assets", "id", "payload"),
            "lookup": ("monitoring_lookup_calls", "id", "payload"),
        }
        table, column, payload_field = tables[body.kind]
        with database.connect() as db:
            row = db.execute(f"SELECT * FROM {table} WHERE {column}=?", (body.reference_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Retained evidence not found")
        if payload_field and not row[payload_field]:
            raise HTTPException(422, "This lookup has no completed result to attach")
        snapshot = (
            scene(database, body.reference_id) if body.kind == "scene" else json.loads(row[payload_field])
        )
        original = (
            snapshot.get("source_url")
            or snapshot.get("metadata", {}).get("source_url")
            or snapshot.get("observation", {}).get("source_url")
            or "https://github.com/abanerjee84/signal-atlas-osint"
        )
        rid = hashlib.sha256(f"monitoring:{body.kind}:{body.reference_id}".encode()).hexdigest()[:32]
        packed_snapshot = packed(snapshot)
        with database.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO external_records(record_id,source_id,external_record_id,original_url,title,text,language,kind,category,ingested_at,updated_at,content_hash,precision,confidence,metadata,license_classification) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    rid,
                    str(snapshot.get("source_id") or "monitoring"),
                    body.reference_id,
                    original,
                    str(snapshot.get("title") or f"Monitoring {body.kind} evidence")[:500],
                    packed_snapshot[:40000],
                    "en",
                    "monitoring_evidence",
                    "geo",
                    stamp(),
                    stamp(),
                    hashlib.sha256(packed_snapshot.encode()).hexdigest(),
                    "source-defined",
                    "Single-source",
                    packed(
                        {
                            "monitoring_snapshot": snapshot,
                            "monitoring_reference": {
                                "kind": body.kind,
                                "id": body.reference_id,
                                "received_at": dict(row).get("received_at"),
                            },
                            "classification": "source_observation_or_derived_analysis",
                        }
                    ),
                    "metadata_only",
                ),
            )
        return repo.attach(body.case_id, "record", rid)

    return api
