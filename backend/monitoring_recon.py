"""Passive third-party lookups with a shared local budget and no target connections."""

import csv
import io
import ipaddress
import json
import uuid
from datetime import timedelta
from urllib.parse import urlsplit

from pydantic import Field

from .connectors.base import ProviderError, SafeHTTP
from .indicators import domain, public_ip
from .models import stamp, utcnow
from .monitoring_workflows import Input


class Lookup(Input):
    kind: str = Field(pattern="^(dns|rdap|certificates|wikidata|sanctions)$")
    target: str = Field(min_length=2, max_length=200)


def reserve(database, settings, kind, target):
    now = utcnow()
    with database.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        cached = db.execute(
            "SELECT payload FROM monitoring_lookup_calls WHERE kind=? AND target=? AND expires_at>? AND payload IS NOT NULL ORDER BY requested_at DESC LIMIT 1",
            (kind, target, stamp(now)),
        ).fetchone()
        if cached:
            return None, json.loads(cached[0])
        if db.execute(
            "SELECT 1 FROM monitoring_lookup_calls WHERE kind=? AND target=? AND requested_at>? AND payload IS NULL",
            (kind, target, stamp(now - timedelta(minutes=2))),
        ).fetchone():
            raise ValueError("This lookup is already pending or recently failed; retry in two minutes")
        count = db.execute(
            "SELECT COUNT(*) FROM monitoring_lookup_calls WHERE requested_at>=?",
            (stamp(now.replace(hour=0, minute=0, second=0, microsecond=0)),),
        ).fetchone()[0]
        if count >= settings.expansion_lookup_daily_budget:
            raise ValueError("Local expansion lookup daily budget exhausted")
        key = uuid.uuid4().hex
        db.execute(
            "INSERT INTO monitoring_lookup_calls VALUES(?,?,?,?,NULL,NULL)", (key, kind, target, stamp(now))
        )
    return key, None


def finish(database, key, payload, hours=24):
    with database.connect() as db:
        db.execute(
            "UPDATE monitoring_lookup_calls SET payload=?,expires_at=? WHERE id=?",
            (json.dumps(payload), stamp(utcnow() + timedelta(hours=hours)), key),
        )


async def rdap(http, target):
    try:
        address = ipaddress.ip_address(public_ip(target))
    except ValueError:
        target = domain(target)
        category = "dns"
        address = None
    else:
        category = "ipv4" if address.version == 4 else "ipv6"
    registry = await http.json("GET", f"https://data.iana.org/rdap/{category}.json")
    candidates = []
    for selectors, urls in registry.get("services", []):
        for selector in selectors:
            if address:
                net = ipaddress.ip_network(selector)
                if address in net:
                    candidates.append((net.prefixlen, urls[0]))
            elif selector == target.rsplit(".", 1)[-1]:
                candidates.append((1, urls[0]))
    if not candidates:
        raise ValueError("IANA does not list an RDAP service for this target")
    base = max(candidates)[1]
    parsed = urlsplit(base)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        raise ValueError("Registry does not provide an approved HTTPS service")
    # Trust the IANA bootstrap service, then validate the exact public registry host.
    scoped = SafeHTTP(
        http.settings.model_copy(
            update={"extra_allowed_hosts": [*http.settings.extra_allowed_hosts, parsed.hostname]}
        ),
        http.client,
    )
    data = await scoped.json("GET", base.rstrip("/") + ("/ip/" if address else "/domain/") + target)
    return {
        "handle": data.get("handle"),
        "name": data.get("ldhName") or data.get("name"),
        "status": data.get("status", [])[:20],
        "events": data.get("events", [])[:30],
        "entities": [
            {"handle": e.get("handle"), "roles": e.get("roles", [])} for e in data.get("entities", [])[:30]
        ],
        "source_url": base,
        "basis": "Registry registration context; redaction and registry terms apply",
    }


async def lookup(http, body):
    target = body.target.strip()
    if body.kind == "dns":
        target = domain(target)
        data = await http.json("GET", "https://dns.google/resolve", params={"name": target, "type": "A"})
        return {
            "target": target,
            "status": data.get("Status"),
            "answers": data.get("Answer", [])[:50],
            "source_url": "https://dns.google/",
            "basis": "Public resolver response; not an active connection to the target",
        }
    if body.kind == "rdap":
        return await rdap(http, target)
    if body.kind == "certificates":
        target = domain(target)
        data = await http.json("GET", "https://crt.sh/", params={"q": "%." + target, "output": "json"})
        if not isinstance(data, list):
            raise ProviderError("Certificate transparency response unsupported")
        return {
            "target": target,
            "certificates": [
                {
                    k: r.get(k)
                    for k in [
                        "id",
                        "issuer_name",
                        "common_name",
                        "name_value",
                        "not_before",
                        "not_after",
                        "entry_timestamp",
                    ]
                }
                for r in data[:100]
            ],
            "truncated": len(data) > 100,
            "source_url": "https://crt.sh/",
            "basis": "Certificate log assertions; not evidence that a service is currently reachable",
        }
    if body.kind == "wikidata":
        matches = await http.json(
            "GET",
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbsearchentities",
                "search": target,
                "language": "en",
                "format": "json",
                "limit": 5,
            },
        )
        entries = matches.get("search", [])
        ids = [
            r["id"] for r in entries if str(r.get("id", "")).startswith("Q") and str(r["id"])[1:].isdigit()
        ]
        claims = {}
        if ids:
            raw = await http.json(
                "GET",
                "https://www.wikidata.org/w/api.php",
                params={"action": "wbgetentities", "ids": "|".join(ids), "props": "claims", "format": "json"},
            )
            claims = raw.get("entities", {})
        results = []
        for r in entries:
            relations = []
            for prop, label in [
                ("P127", "owned by"),
                ("P749", "parent organization"),
                ("P159", "headquarters"),
                ("P17", "country"),
                ("P856", "official website"),
            ]:
                for claim in claims.get(r["id"], {}).get("claims", {}).get(prop, [])[:10]:
                    snak = claim.get("mainsnak", {})
                    if snak.get("snaktype") != "value":
                        continue
                    relations.append(
                        {
                            "property": prop,
                            "relation": label,
                            "value": snak.get("datavalue", {}).get("value"),
                            "references": claim.get("references", [])[:3],
                            "rank": claim.get("rank"),
                        }
                    )
            results.append(
                {
                    "id": r["id"],
                    "label": r.get("label"),
                    "description": r.get("description"),
                    "source_url": f"https://www.wikidata.org/wiki/{r['id']}",
                    "relations": relations,
                    "match": "candidate; analyst verification required",
                }
            )
        return {
            "candidates": results,
            "basis": "Public knowledge-base claims; a name match is not verified ownership or identity",
        }
    payload = await http.request(
        "GET",
        "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV",
        max_bytes=16_777_216,
    )
    rows = []
    for row in csv.reader(io.StringIO(payload.decode("utf-8-sig"))):
        if len(row) > 3 and target.casefold() in row[1].casefold():
            rows.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "type": row[2],
                    "programs": row[3],
                    "match": "text candidate; not identity verification",
                }
            )
            if len(rows) > 100:
                break
    return {
        "candidates": rows[:100],
        "truncated": len(rows) > 100,
        "source_url": "https://ofac.treasury.gov/sanctions-list-service",
        "basis": "OFAC SDN text matches; legal/identity conclusions require independent review",
    }
