"""Shared evidence interface. Modules never read the dashboard's private tables."""

import hashlib
import json
import re
import uuid

from fastapi import HTTPException

from ..models import stamp


def identifier():
    return uuid.uuid4().hex


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


JSON_FIELDS = {
    "aliases",
    "profile",
    "refs",
    "metadata",
    "details",
    "capabilities",
    "geojson",
    "tags",
    "snapshot",
    "response",
    "basis",
    "event_ids",
    "payload",
    "result",
}


def decoded(row):
    if row is None:
        return None
    result = dict(row)
    for key in JSON_FIELDS & result.keys():
        if result[key] is not None:
            try:
                result[key] = json.loads(result[key])
            except (ValueError, TypeError):
                pass
    if "record_id" in result and "original_url" in result:
        result["source_confidence"] = result.get("confidence")
        result["verification_status"] = result.get("metadata", {}).get("verification_status", "reported")
    return result


class Repository:
    def __init__(self, database):
        self.database = database

    def rows(self, sql, parameters=()):
        with self.database.connect() as db:
            return [decoded(row) for row in db.execute(sql, parameters)]

    def one(self, sql, parameters=(), required=False):
        rows = self.rows(sql, parameters)
        if not rows and required:
            raise HTTPException(404, "Evidence or resource not found")
        return rows[0] if rows else None

    def insert(self, table, values):
        # Table and column names come exclusively from module code, never API inputs.
        with self.database.connect() as db:
            db.execute(
                f"INSERT INTO {table}({','.join(values)}) VALUES({','.join('?' for _ in values)})",
                tuple(packed(v) if isinstance(v, (dict, list)) else v for v in values.values()),
            )
        return values

    def audit(self, action, resource_id, details=None):
        self.insert(
            "audit_log",
            {
                "action": action,
                "resource_id": resource_id,
                "principal": "local-administrator",
                "created_at": stamp(),
                "details": details or {},
            },
        )

    def record(self, record_id):
        return self.one("SELECT * FROM external_records WHERE record_id=?", (record_id,), True)

    def search(
        self,
        q="",
        category="",
        source="",
        language="",
        start=None,
        end=None,
        country=None,
        limit=50,
        offset=0,
        order="date",
        public_only=False,
    ):
        clauses, args = [], []
        if public_only:
            clauses.append("r.license_classification IN ('source_terms','provider_terms','public_domain')")
        join = ""
        if q:
            terms = re.findall(r"[\w.-]+", q, re.UNICODE)[:12]
            if not terms:
                return {"items": [], "total": 0}
            join = " JOIN aos_search f ON f.record_id=r.record_id"
            clauses.append("aos_search MATCH ?")
            args.append(" AND ".join('"' + term.replace('"', '""') + '"' for term in terms))
        for field, value in [
            ("category", category),
            ("source_id", source),
            ("language", language),
            ("country", country),
        ]:
            if value:
                if field == "category" and value in {"events", "news"}:
                    clauses.append(
                        "r.event_id IS NOT NULL" if value == "events" else "r.kind IN ('news','official')"
                    )
                else:
                    clauses.append(f"r.{field}=?")
                    args.append(value)
        for operator, value in [(">=", start), ("<=", end)]:
            if value:
                clauses.append(f"r.published_at{operator}?")
                args.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        sorting = (
            "bm25(aos_search),r.record_id"
            if q and order == "relevance"
            else "r.published_at DESC,r.record_id"
        )
        with self.database.connect() as db:
            total = db.execute("SELECT COUNT(*) FROM external_records r" + join + where, args).fetchone()[0]
            items = [
                decoded(row)
                for row in db.execute(
                    "SELECT r.* FROM external_records r"
                    + join
                    + where
                    + " ORDER BY "
                    + sorting
                    + " LIMIT ? OFFSET ?",
                    [*args, limit, offset],
                )
            ]
        return {"items": items, "total": total}

    def evidence(self, kind, reference_id):
        tables = {
            "record": ("external_records", "record_id"),
            "media": ("media_evidence", "id"),
            "geo": ("geographic_evidence", "id"),
            "document": ("document_records", "id"),
            "analysis": ("ai_analyses", "id"),
            "change": ("source_changes", "id"),
            "entity": ("entities", "entity_id"),
        }
        table, key = tables[kind]
        result = self.one(f"SELECT * FROM {table} WHERE {key}=?", (reference_id,), True)
        if result.get("deleted_at"):
            raise HTTPException(410, "Evidence has been deleted")
        return result

    def case(self, case_id):
        case = self.one(
            "SELECT * FROM investigation_cases WHERE id=? AND deleted_at IS NULL", (case_id,), True
        )
        case["evidence"] = self.rows(
            "SELECT * FROM case_evidence WHERE case_id=? ORDER BY added_at DESC,id LIMIT 200", (case_id,)
        )
        case["notes"] = self.rows(
            "SELECT * FROM case_notes WHERE case_id=? ORDER BY created_at DESC,id LIMIT 200", (case_id,)
        )
        case["history"] = self.rows(
            "SELECT * FROM audit_log WHERE resource_id=? ORDER BY id DESC LIMIT 200", (case_id,)
        )
        case["counts"] = self.one(
            "SELECT (SELECT COUNT(*) FROM case_evidence WHERE case_id=?) evidence,(SELECT COUNT(*) FROM case_notes WHERE case_id=?) notes,(SELECT COUNT(*) FROM audit_log WHERE resource_id=?) history",
            (case_id, case_id, case_id),
        )
        case["truncated"] = any(case["counts"][key] > 200 for key in ("evidence", "notes", "history"))
        return case

    def attach(self, case_id, kind, reference_id):
        self.case(case_id)
        snapshot = self.evidence(kind, reference_id)
        if kind == "entity":
            from .threats import catalog_profiles

            profiles = catalog_profiles(self, reference_id)
            if profiles:
                snapshot["catalog_profiles"] = profiles
                snapshot["classification"] = "reference_knowledge"
        digest = hashlib.sha256(packed(snapshot).encode()).hexdigest()
        row = self.insert(
            "case_evidence",
            {
                "id": identifier(),
                "case_id": case_id,
                "kind": kind,
                "reference_id": reference_id,
                "snapshot": snapshot,
                "sha256": digest,
                "added_at": stamp(),
            },
        )
        self.audit("case.evidence.add", case_id, {"evidence_id": row["id"], "sha256": digest})
        return row

    def enqueue(self, kind, payload):
        row = self.insert(
            "investigation_jobs",
            {
                "id": identifier(),
                "kind": kind,
                "state": "queued",
                "payload": payload,
                "created_at": stamp(),
                "updated_at": stamp(),
            },
        )
        self.audit("job.enqueue", row["id"], {"kind": kind})
        return {"job_id": row["id"], "state": "queued"}

    def register(self, providers):
        with self.database.connect() as db:
            for provider in providers:
                metadata = provider.metadata()
                feed = metadata.get("delivery") == "RSS/Atom"
                scraper = any(
                    word in metadata.get("delivery", "").lower()
                    for word in ("scrap", "renderer", "html", "public compressed csv")
                )
                access = "registration_required" if provider.access() else "free"
                db.execute(
                    "INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET name=excluded.name,details=excluded.details,official_url=excluded.official_url,integration=excluded.integration,category=excluded.category",
                    (
                        provider.source_id,
                        provider.name,
                        provider.name,
                        str(provider.category),
                        provider.homepage,
                        "feed" if feed else "scraper" if scraper else "api",
                        access,
                        metadata.get("license", "source_terms"),
                        "existing_connector",
                        int(getattr(provider, "initial_enabled", True)),
                        None,
                        packed(metadata),
                    ),
                )
                db.execute(
                    "INSERT OR REPLACE INTO source_capabilities VALUES(?,?)",
                    (
                        provider.source_id,
                        packed(
                            {
                                "collection": True,
                                "frequency_seconds": provider.interval,
                                "format": "RSS/Atom"
                                if feed
                                else "public website scrape"
                                if scraper
                                else "provider structured data",
                                "limitations": provider.limitation,
                                "automation": "existing dashboard adapter",
                            }
                        ),
                    ),
                )
            for source_id, name, url, category, integration, access, template in RESOURCES:
                db.execute(
                    "INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        source_id,
                        name,
                        name,
                        category,
                        url,
                        integration,
                        access,
                        "provider_terms",
                        "manual_only",
                        0,
                        None,
                        packed(
                            {
                                "search_url": template,
                                "limitation": "Analyst lookup only; programmatic access has not been configured or verified.",
                            }
                        ),
                    ),
                )
                db.execute(
                    "INSERT OR IGNORE INTO source_capabilities VALUES(?,?)",
                    (source_id, packed({"collection": False, "manual_lookup": bool(template)})),
                )
        from .providers import register_public

        if providers:
            register_public(self, providers[0].settings)
            from .threats import register as register_threats

            register_threats(self, providers[0].settings)


RESOURCES = [
    ("searxng", "SearXNG", "https://docs.searxng.org/", "search", "api", "unverified", None),
    (
        "aleph",
        "OCCRP Aleph",
        "https://aleph.occrp.org/",
        "documents",
        "analyst_lookup",
        "registration_required",
        "https://aleph.occrp.org/entities?q={query}",
    ),
    (
        "documentcloud",
        "DocumentCloud",
        "https://www.documentcloud.org/",
        "documents",
        "analyst_lookup",
        "free",
        "https://www.documentcloud.org/app?q={query}",
    ),
    (
        "archive",
        "Internet Archive",
        "https://archive.org/",
        "documents",
        "analyst_lookup",
        "free",
        "https://archive.org/search?query={query}",
    ),
    (
        "geonames",
        "GeoNames",
        "https://www.geonames.org/",
        "geo",
        "analyst_lookup",
        "registration_required",
        "https://www.geonames.org/search.html?q={query}",
    ),
    (
        "ct",
        "Certificate Transparency search",
        "https://crt.sh/",
        "cyber",
        "analyst_lookup",
        "free",
        "https://crt.sh/?q={query}",
    ),
    (
        "radar",
        "Cloudflare Radar",
        "https://radar.cloudflare.com/",
        "cyber",
        "restricted",
        "registration_required",
        None,
    ),
    (
        "otx",
        "AlienVault OTX",
        "https://otx.alienvault.com/",
        "cyber",
        "restricted",
        "registration_required",
        None,
    ),
    (
        "abuseipdb",
        "AbuseIPDB",
        "https://www.abuseipdb.com/",
        "cyber",
        "restricted",
        "registration_required",
        None,
    ),
    (
        "greynoise",
        "GreyNoise",
        "https://www.greynoise.io/",
        "cyber",
        "restricted",
        "registration_required",
        None,
    ),
    (
        "shadowserver",
        "Shadowserver",
        "https://www.shadowserver.org/",
        "cyber",
        "restricted",
        "registration_required",
        None,
    ),
    (
        "bgptools",
        "BGP.tools",
        "https://bgp.tools/",
        "cyber",
        "analyst_lookup",
        "free",
        "https://bgp.tools/search?q={query}",
    ),
    ("censys", "Censys", "https://search.censys.io/", "cyber", "restricted", "registration_required", None),
    (
        "forensically",
        "Forensically",
        "https://29a.ch/photo-forensics/",
        "media",
        "analyst_lookup",
        "free",
        None,
    ),
    (
        "filmot",
        "Filmot",
        "https://filmot.com/",
        "media",
        "analyst_lookup",
        "unverified",
        "https://filmot.com/search/{query}/1",
    ),
    (
        "exif",
        "Local image metadata inspection",
        "https://pillow.readthedocs.io/",
        "media",
        "local_utility",
        "free",
        None,
    ),
    (
        "imagery",
        "NASA Worldview",
        "https://worldview.earthdata.nasa.gov/",
        "geo",
        "analyst_lookup",
        "free",
        None,
    ),
]
