"""Monitoring read APIs and authenticated, quota-bounded passive host enrichment."""

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import ROOT
from .connectors.base import ProviderError, SafeHTTP
from .indicators import public_ip
from .models import Report, stamp, utcnow
from .monitoring import LAYER_IDS, LAYERS, frame, gnss_cells
from .tls import outbound_tls


def moment(value):
    value = value or utcnow()
    if value.tzinfo is None or value > utcnow() + timedelta(seconds=5):
        raise HTTPException(422, "Use a timezone-aware UTC time at or before now")
    return value.astimezone(timezone.utc)


class HostLookup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ip: str = Field(min_length=3, max_length=45)

    @field_validator("ip")
    @classmethod
    def valid_ip(cls, value):
        return public_ip(value)


def router(database, settings, authorize, source_statuses):
    api = APIRouter(prefix="/api/monitoring", tags=["Monitoring"])

    @api.get("/catalog")
    def catalog():
        sources = source_statuses()
        with database.connect() as db:
            bounds = db.execute(
                "SELECT MIN(received_at),MAX(received_at),COUNT(*) FROM monitoring_history"
            ).fetchone()
        return dict(
            layers=LAYERS,
            layer_count=len(LAYERS),
            sources=sources,
            source_count=len(sources),
            healthy_source_count=sum(row.get("state") == "ok" and not row.get("stale") for row in sources),
            history=dict(
                first=bounds[0],
                last=bounds[1],
                observations=bounds[2],
                retention_days=settings.monitoring_retention_days,
                max_rows=settings.monitoring_max_rows,
            ),
            shodan_configured=bool(settings.shodan_api_key),
            limitation="Sublayers overlap. Registered feeds are not necessarily enabled, accessible or healthy.",
        )

    @api.get("/frame")
    def observations(
        at: datetime | None = None,
        hours: int = Query(24, ge=1, le=168),
        layers: str = Query("", max_length=1000),
        limit: int = Query(2000, ge=1, le=5000),
    ):
        point = moment(at)
        selected = set(filter(None, layers.split(",")))
        if selected - LAYER_IDS:
            raise HTTPException(422, "Unknown monitoring layer")
        # Interference needs all recent aircraft, even if only GNSS cells are selected.
        base = frame(
            database,
            point,
            hours,
            selected - {"gnss"} | {"aircraft"} if "gnss" in selected else selected,
            limit,
        )
        base["gnss"] = gnss_cells(base["items"])
        if selected:
            base["items"] = [item for item in base["items"] if selected.intersection(item["layers"])]
        base["gnss_sample_truncated"] = base["truncated"]
        return base

    @api.get("/orbits")
    def orbits(at: datetime | None = None):
        point = moment(at)
        with database.connect() as db:
            row = db.execute(
                "SELECT payload FROM monitoring_orbits WHERE collected_at<=? "
                "ORDER BY collected_at DESC LIMIT 1",
                (stamp(point),),
            ).fetchone()
        if row:
            return dict(snapshot=json.loads(row[0]), basis="SGP4 estimates from retained orbital elements")
        if at is None:
            path = ROOT / "public/orbital-elements.json"
            if path.exists():
                return dict(
                    snapshot=json.loads(path.read_text(encoding="utf-8")),
                    basis="SGP4 estimates from current orbital elements",
                )
        return dict(snapshot=None, basis="No orbital elements retained at this time")

    @api.post("/shodan", dependencies=[Depends(authorize)])
    async def shodan(body: HostLookup):
        if not settings.shodan_api_key:
            raise HTTPException(503, "Configure OSINT_SHODAN_API_KEY on the server")
        from .worker import permission_refusal

        class ShodanSource:
            source_id = "shodan"

        source = ShodanSource()
        source.settings = settings
        if permission_refusal(database, source):
            raise HTTPException(403, "Shodan collection blocked by this deployment's source permissions")
        with database.connect() as db:
            enabled = db.execute("SELECT enabled FROM sources WHERE source_id='shodan'").fetchone()
        if enabled and not enabled[0]:
            raise HTTPException(403, "Shodan lookup disabled by administrator")
        now = utcnow()
        prefix = hashlib.sha256(body.ip.encode()).hexdigest() + ":"
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cached = db.execute(
                "SELECT payload FROM monitoring_lookups WHERE cache_key LIKE ? AND payload IS NOT NULL "
                "AND requested_at>? ORDER BY requested_at DESC LIMIT 1",
                (prefix + "%", stamp(now - timedelta(hours=24))),
            ).fetchone()
            if cached:
                return {**json.loads(cached[0]), "cached": True}
            pending = db.execute(
                "SELECT 1 FROM monitoring_lookups WHERE cache_key LIKE ? AND requested_at>?",
                (prefix + "%", stamp(now - timedelta(minutes=1))),
            ).fetchone()
            if pending:
                raise HTTPException(429, "Host lookup recently requested; retry in one minute")
            count = db.execute(
                "SELECT COUNT(*) FROM monitoring_lookups WHERE requested_at>=?",
                (stamp(now.replace(hour=0, minute=0, second=0, microsecond=0)),),
            ).fetchone()[0]
            if count >= settings.shodan_daily_budget:
                raise HTTPException(429, "Local Shodan daily budget exhausted")
            key = prefix + uuid.uuid4().hex
            db.execute("INSERT INTO monitoring_lookups VALUES(?,?,NULL)", (key, stamp(now)))
        try:
            async with httpx.AsyncClient(timeout=settings.http_timeout, verify=outbound_tls()) as client:
                data = await SafeHTTP(settings, client).json(
                    "GET",
                    f"https://api.shodan.io/shodan/host/{body.ip}",
                    attempts=1,
                    params={"key": settings.shodan_api_key, "minify": "true"},
                )
            if not isinstance(data, dict) or data.get("ip_str") != body.ip:
                raise ValueError("Mismatched host response")
            result = dict(
                ip=body.ip,
                organization=str(data.get("org", "Unknown"))[:250],
                ports=[p for p in data.get("ports", []) if type(p) is int and 1 <= p <= 65535][:100],
                provider_updated_at=str(data.get("last_update", ""))[:50],
                received_at=stamp(),
                source_url=f"https://www.shodan.io/host/{body.ip}",
                basis="Passive Shodan host record; exposed service does not establish compromise",
                cached=False,
            )
            report = Report(
                external_id=body.ip,
                source_id="shodan",
                source_url=result["source_url"],
                title=f"Shodan host {body.ip}",
                description=f"{result['organization']}; ports {result['ports']}. {result['basis']}",
                category="infrastructure",
                latitude=data.get("latitude"),
                longitude=data.get("longitude"),
                location_precision="approximate",
                location_basis="Shodan IP geolocation, not a surveyed device position",
                published_at=utcnow(),
                tags=["shodan"],
                raw={"monitoring": result},
            )
            database.ingest(report)
            database.set_status(
                "shodan",
                state="ok",
                last_attempt=stamp(now),
                last_success=stamp(),
                error=None,
                fetched=1,
                stored=1,
            )
            with database.connect() as db:
                db.execute(
                    "UPDATE monitoring_lookups SET payload=? WHERE cache_key=?", (json.dumps(result), key)
                )
            return result
        except (ProviderError, ValueError, TypeError, KeyError):
            database.set_status(
                "shodan",
                state="error",
                last_attempt=stamp(now),
                error="Passive host lookup failed; check provider access",
            )
            raise HTTPException(502, "Shodan lookup failed; check provider access and retry later") from None

    return api
