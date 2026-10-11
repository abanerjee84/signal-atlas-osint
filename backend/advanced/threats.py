"""Versioned reference catalogs and literal report matches, separate from dated incidents."""

import hashlib
import json
import re
from collections import defaultdict
from datetime import timedelta
from urllib.parse import urlsplit

from ..config import ROOT
from ..connectors.base import SafeHTTP, clean
from ..models import stamp, utcnow
from .processing import stable
from .repository import packed

CATALOGS = {
    "misp_galaxy": {
        "name": "MISP Galaxy threat actors",
        "url": "https://raw.githubusercontent.com/MISP/misp-galaxy/main/clusters/threat-actor.json",
        "home": "https://www.misp-galaxy.org/threat-actor/",
        "license": "CC0 / BSD dual license",
        "format": "MISP Galaxy JSON",
    },
    "malpedia_actors": {
        "name": "Malpedia public actor metadata",
        "url": "https://malpedia.caad.fkie.fraunhofer.de/api/get/actors",
        "home": "https://malpedia.caad.fkie.fraunhofer.de/usage/api",
        "license": "CC BY-NC-SA 3.0",
        "format": "Public actor JSON",
    },
    "etda_actors": {
        "name": "ETDA / ThaiCERT Threat Group Cards",
        "url": "https://apt.etda.or.th/cgi-bin/getcard.cgi?g=all&o=j",
        "home": "https://apt.etda.or.th/cgi-bin/listgroups.cgi",
        "license": "CC BY-NC-SA 4.0",
        "format": "Official actor JSON export",
    },
    "mitre_attack": {
        "name": "MITRE ATT&CK Enterprise knowledge base",
        "url": "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json",
        "home": "https://attack.mitre.org/",
        "license": "MITRE ATT&CK license; retain copyright and license",
        "format": "STIX 2.1 JSON",
    },
}
KINDS = {
    "intrusion-set": "threat_actor",
    "campaign": "campaign",
    "malware": "malware",
    "tool": "tool",
    "attack-pattern": "technique",
}
MITRE_LICENSE = (ROOT / "docs/licenses/MITRE-ATTACK.txt").read_text(encoding="utf-8")
_MATCH_CACHE = {}


def register(repo, settings):
    with repo.database.connect() as db:
        for sid, spec in CATALOGS.items():
            details = {
                "authentication": "None",
                "frequency_seconds": 86400,
                "format": spec["format"],
                "license": spec["license"],
                "license_url": "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/LICENSE.txt"
                if sid == "mitre_attack"
                else "https://raw.githubusercontent.com/MISP/misp-galaxy/main/LICENSE.md"
                if sid == "misp_galaxy"
                else "https://malpedia.caad.fkie.fraunhofer.de/usage/tos"
                if sid == "malpedia_actors"
                else spec["url"],
                "geographic_coverage": "Reference knowledge; no incident coordinates",
                "collection": True,
                "limitations": "Historical source assertions; catalog revisions are not new attacks. Shared catalogs do not independently corroborate attribution.",
            }
            db.execute(
                "INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET details=excluded.details,name=excluded.name",
                (
                    sid,
                    spec["name"],
                    spec["name"],
                    "cyber",
                    spec["home"],
                    "reference_catalog",
                    "free",
                    spec["license"],
                    "existing_connector",
                    int(settings.threat_catalogs_enabled),
                    None,
                    packed(details),
                ),
            )
            db.execute("INSERT OR REPLACE INTO source_capabilities VALUES(?,?)", (sid, packed(details)))
            db.execute("INSERT OR IGNORE INTO threat_catalog_state(source_id) VALUES(?)", (sid,))


def names(values):
    if isinstance(values, str):
        values = [values]
    return sorted(
        {clean(v, 200) for v in (values or []) if isinstance(v, str) and 3 <= len(v.strip()) <= 200}
    )[:100]


# Actor identifiers must not be ordinary words. APT41 is also tracked as
# "Lead" and Earth Lusca as "Chromium", so those aliases appear constantly in
# unrelated reporting and would otherwise merge distinct groups and confirm
# false matches. This list is deliberately short and evidence-led: it holds
# only vocabulary observed to collide, and every hit is surfaced rather than
# silently dropped, so it can be extended from real collisions.
ORDINARY_ALIASES = frozenset(
    {
        "lead",
        "leads",
        "leader",
        "chromium",
        "chrome",
        "water",
        "sand",
        "iron",
        "steel",
        "gold",
        "silver",
        "copper",
        "acid",
        "miner",
        "operator",
        "system",
        "target",
        "threat",
        "actor",
        "group",
        "report",
        "update",
    }
)


def distinctive(alias):
    """Whether an alias may identify an actor on its own."""
    folded = clean(alias, 200).casefold()
    return len(folded) >= 4 and folded not in ORDINARY_ALIASES


# The two catalogs that publish identical object identifiers, and so already
# agree on identity. Everything else reconciles onto them.
CANONICAL_ACTOR_SOURCES = ("misp_galaxy", "malpedia_actors")
# Sources that resolve identity by their own explicit rules instead.
MITRE_SOURCES = frozenset({"mitre_attack"})


def urls(values):
    result = []
    for value in values or []:
        if isinstance(value, dict):
            value = value.get("url")
        if not isinstance(value, str):
            continue
        try:
            parsed = urlsplit(value)
            if (
                len(value) <= 2048
                and parsed.scheme in {"https", "http"}
                and parsed.hostname
                and not parsed.username
                and not parsed.password
            ):
                result.append(value)
        except ValueError:
            pass
    return list(dict.fromkeys(result))[:100]


def parse_catalog(sid, data):
    objects, relations = [], []
    if not isinstance(data, dict):
        raise ValueError("Catalog must be a JSON object")
    version = str(data.get("version") or data.get("last-db-change") or "unversioned")
    if sid == "mitre_attack":
        rows = data.get("objects")
        if data.get("type") != "bundle" or not isinstance(rows, list) or len(rows) > 100000:
            raise ValueError("Invalid or oversized MITRE STIX bundle")
        # A bundle may contain several versions of an object. Select its newest version.
        latest = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                continue
            previous = latest.get(row["id"])
            if previous is None or str(row.get("modified", "")) > str(previous.get("modified", "")):
                latest[row["id"]] = row
        for row in latest.values():
            if row.get("type") == "x-mitre-collection":
                version = str(row.get("x_mitre_version") or row.get("name") or version)
            active = not row.get("revoked", False) and not row.get("x_mitre_deprecated", False)
            if row.get("type") == "relationship":
                if active:
                    relations.append(
                        {
                            "id": row["id"],
                            "from": row.get("source_ref"),
                            "to": row.get("target_ref"),
                            "type": clean(row.get("relationship_type", "related-to"), 60),
                            "basis": clean(
                                row.get("description", "Documented MITRE relationship; historical reference"),
                                4000,
                            ),
                            "refs": urls(row.get("external_references", [])),
                            "modified": row.get("modified"),
                        }
                    )
                continue
            kind = KINDS.get(row.get("type"))
            if kind:
                refs = urls(row.get("external_references", []))
                primary = next(
                    (u for u in refs if urlsplit(u).hostname == "attack.mitre.org"), CATALOGS[sid]["home"]
                )
                objects.append(
                    {
                        "id": row["id"],
                        "uuid": row["id"].split("--")[-1],
                        "type": kind,
                        "name": clean(row.get("name", ""), 200),
                        "description": clean(row.get("description", ""), 20000),
                        "aliases": names(row.get("aliases", [])),
                        "profile": {
                            "copyright_and_license": MITRE_LICENSE,
                            "refs": refs,
                            "external_references": row.get("external_references", []),
                            "version": row.get("x_mitre_version"),
                            "revoked": row.get("revoked", False),
                            "deprecated": row.get("x_mitre_deprecated", False),
                        },
                        "url": primary,
                        "modified": row.get("modified"),
                        "active": active,
                    }
                )
    else:
        values = list(data.values()) if sid == "malpedia_actors" else data.get("values")
        if not isinstance(values, list) or not values or len(values) > 20000:
            raise ValueError("Invalid or oversized actor catalog")
        excluded = []
        for row in values:
            if not isinstance(row, dict):
                raise ValueError("Malformed actor entry")
            uid = row.get("uuid")
            name = clean(row.get("value") or row.get("actor") or "", 200)
            if (
                not isinstance(uid, str)
                or not re.fullmatch(
                    r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}", uid
                )
                or not name
            ):
                if sid == "etda_actors" and name:
                    excluded.append({"name": name, "reason": "Invalid provider UUID; identity not rewritten"})
                    continue
                raise ValueError("Actor identity missing")
            profile = dict(row.get("meta") or {})
            if sid == "etda_actors":
                profile = {
                    "country": row.get("country", []),
                    "refs": urls(row.get("information", [])),
                    "last_db_change": data.get("last-db-change"),
                }
                aliases = names(
                    [item.get("name", "") for item in row.get("names", []) if isinstance(item, dict)]
                )
            else:
                aliases = names(profile.get("synonyms", []))
            profile["refs"] = urls(profile.get("refs", []))
            origin = CATALOGS[sid]["home"]
            if sid == "malpedia_actors":
                # Human-readable API names are not the actor-page slug identifiers.
                origin = CATALOGS[sid]["url"]
            objects.append(
                {
                    "id": uid.lower(),
                    "uuid": uid.lower(),
                    "type": "threat_actor",
                    "name": name,
                    "description": clean(row.get("description", ""), 20000),
                    "aliases": aliases,
                    "profile": profile,
                    "url": origin,
                    "modified": row.get("last-card-change"),
                    "active": True,
                }
            )
        if excluded:
            if len(excluded) > max(1, len(values) // 100):
                raise ValueError("Too many malformed catalog identities")
            for obj in objects:
                obj["profile"]["catalog_exclusions"] = excluded
    if not objects or any(not obj["name"] for obj in objects):
        raise ValueError("Catalog has no valid named objects")
    return version, objects, relations


def mitre_group_ids(profile):
    ids = set()
    for value in profile.get("refs", []):
        match = re.search(r"https?://attack\.mitre\.org/groups/(G\d{4})", value)
        if match:
            ids.add(match[1])
    for ref in profile.get("external_references", []):
        if ref.get("source_name") == "mitre-attack" and re.fullmatch(r"G\d{4}", ref.get("external_id", "")):
            ids.add(ref["external_id"])
    return ids


def store_catalog(repo, sid, data, checksum=""):
    version, objects, relations = parse_catalog(sid, data)
    now = stamp()
    with repo.database.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        # Explicit cited MITRE group identifiers permit cross-catalog identity resolution.
        group_map = defaultdict(set)
        for row in db.execute(
            "SELECT entity_id,profile FROM threat_catalog_objects WHERE active=1 AND type='threat_actor' AND source_id<>'mitre_attack'"
        ):
            ids = mitre_group_ids(json.loads(row["profile"]))
            if len(ids) == 1:
                group_map[next(iter(ids))].add(row["entity_id"])
        db.execute("UPDATE threat_catalog_objects SET active=0 WHERE source_id=?", (sid,))
        db.execute("UPDATE threat_catalog_relations SET active=0 WHERE source_id=?", (sid,))
        # Reconcile an incoming actor against the canonical catalog pair only.
        # Those two share object identifiers already, so they form the base set
        # of distinct groups. Including etda or MITRE here would be circular:
        # the duplicates being reconciled are exactly what makes an alias look
        # ambiguous, so the candidate set would never fall to one.
        alias_index = defaultdict(set)
        # MITRE is excluded by policy, not by omission: a broad group reference
        # is deliberately never allowed to collapse distinct intrusion sets, so
        # it resolves only through its own cited group identifiers.
        if sid not in MITRE_SOURCES:
            placeholders = ",".join("?" for _ in CANONICAL_ACTOR_SOURCES)
            for row in db.execute(
                "SELECT entity_id,name,aliases FROM threat_catalog_objects "
                f"WHERE active=1 AND type='threat_actor' AND source_id IN ({placeholders})",
                CANONICAL_ACTOR_SOURCES,
            ):
                try:
                    prior = json.loads(row["aliases"] or "[]")
                except ValueError:
                    prior = []
                for alias in names([row["name"], *prior]):
                    if distinctive(alias):
                        alias_index[alias.casefold()].add(row["entity_id"])
        id_map = {}
        for obj in objects:
            existing = db.execute(
                "SELECT entity_id FROM threat_catalog_objects WHERE source_id=? AND external_id=?",
                (sid, obj["id"]),
            ).fetchone()
            eid = existing[0] if existing else stable("threat-reference", obj["uuid"])
            # Resolve against the canonical catalogs by a distinctive shared alias.
            # Never merge identities on a similar name or a shared informal
            # alias; a single candidate is a merge and several stay separate.
            def alias_candidate(obj):
                if not alias_index:
                    return None
                mapped = set()
                for alias in names([obj["name"], *obj["aliases"]]):
                    if distinctive(alias):
                        mapped |= alias_index.get(alias.casefold(), set())
                return next(iter(mapped)) if len(mapped) == 1 else None

            if sid in MITRE_SOURCES and obj["type"] == "threat_actor":
                # Reconcile earlier broad groupings as well as first imports.
                eid = stable("threat-reference", obj["uuid"])
                mapped = set().union(*(group_map[gid] for gid in mitre_group_ids(obj["profile"])))
                if len(mapped) == 1:
                    eid = mapped.pop()
            elif obj["type"] == "threat_actor":
                eid = alias_candidate(obj) or eid
            id_map[obj["id"]] = eid
            db.execute(
                "INSERT OR IGNORE INTO entities VALUES(?,?,?,?,?,?)",
                (
                    eid,
                    obj["type"],
                    obj["name"],
                    obj["name"].casefold(),
                    "Source catalog identity; attribution is reported, not independently verified",
                    now,
                ),
            )
            db.execute(
                "INSERT INTO threat_catalog_objects VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id,external_id) DO UPDATE SET entity_id=excluded.entity_id,name=excluded.name,description=excluded.description,aliases=excluded.aliases,profile=excluded.profile,original_url=excluded.original_url,version=excluded.version,modified_at=excluded.modified_at,retrieved_at=excluded.retrieved_at,active=excluded.active",
                (
                    sid,
                    obj["id"],
                    eid,
                    obj["type"],
                    obj["name"],
                    obj["description"],
                    packed(obj["aliases"]),
                    packed(obj["profile"]),
                    obj["url"],
                    version,
                    obj["modified"],
                    now,
                    int(obj["active"]),
                    CATALOGS[sid]["license"],
                ),
            )
            for alias in names([obj["name"], *obj["aliases"]]):
                db.execute("INSERT OR IGNORE INTO entity_aliases VALUES(?,?)", (eid, alias))
        active = {obj["id"] for obj in objects if obj["active"]}
        edge_count = 0
        for relation in relations:
            if relation["from"] not in active or relation["to"] not in active:
                continue
            left, right = id_map[relation["from"]], id_map[relation["to"]]
            if left == right:
                continue
            edge = stable(sid, relation["id"])
            db.execute(
                "INSERT INTO relationships VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(relationship_id) DO UPDATE SET from_id=excluded.from_id,to_id=excluded.to_id,basis=excluded.basis,type=excluded.type",
                (edge, left, right, "catalog_" + relation["type"], "reported", None, None, relation["basis"]),
            )
            origin = next(
                (u for u in relation["refs"] if urlsplit(u).hostname == "attack.mitre.org"),
                CATALOGS[sid]["home"],
            )
            db.execute(
                "INSERT INTO threat_catalog_relations VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(source_id,external_id) DO UPDATE SET active=excluded.active,refs=excluded.refs,modified_at=excluded.modified_at,retrieved_at=excluded.retrieved_at",
                (sid, relation["id"], edge, origin, packed(relation["refs"]), relation["modified"], now, 1),
            )
            edge_count += 1
        db.execute(
            "UPDATE threat_catalog_state SET state='ok',version=?,last_success=?,next_run=?,error=NULL,checksum=?,object_count=?,relation_count=? WHERE source_id=?",
            (
                version,
                now,
                stamp(utcnow() + timedelta(days=1)),
                checksum,
                sum(obj["active"] for obj in objects),
                edge_count,
                sid,
            ),
        )
        db.execute("UPDATE sources SET last_verified_at=? WHERE source_id=?", (now, sid))
    return {
        "source_id": sid,
        "objects": len(objects),
        "relations": edge_count,
        "version": version,
        "rejected": len(data["values"]) - len(objects) if sid == "etda_actors" else 0,
        "classification": "reference_knowledge",
    }


async def refresh_catalog(repo, settings, client, sid):
    spec = CATALOGS.get(sid)
    if (
        not spec
        or not settings.threat_catalogs_enabled
        or not repo.one("SELECT 1 FROM sources WHERE source_id=? AND enabled=1", (sid,))
    ):
        raise ValueError("Catalog is disabled")
    with repo.database.connect() as db:
        db.execute(
            "UPDATE threat_catalog_state SET state='fetching',last_attempt=? WHERE source_id=?",
            (stamp(), sid),
        )
    try:
        raw = await SafeHTTP(settings, client).request(
            "GET", spec["url"], attempts=1, max_bytes=96_000_000 if sid == "mitre_attack" else 6_000_000
        )
        checksum = hashlib.sha256(raw).hexdigest()
        import asyncio

        return await asyncio.to_thread(store_catalog, repo, sid, json.loads(raw), checksum)
    except Exception:
        with repo.database.connect() as db:
            db.execute(
                "UPDATE threat_catalog_state SET state='error',error='Catalog fetch or validation failed; last successful snapshot retained',next_run=? WHERE source_id=?",
                (stamp(utcnow() + timedelta(hours=1)), sid),
            )
        raise


def schedule(repo, settings):
    if not settings.threat_catalogs_enabled:
        return
    with repo.database.connect() as db:
        for sid in CATALOGS:
            due = db.execute(
                "SELECT 1 FROM threat_catalog_state t JOIN sources s USING(source_id) WHERE source_id=? AND s.enabled=1 AND (next_run IS NULL OR next_run<=?)",
                (sid, stamp()),
            ).fetchone()
            pending = db.execute(
                "SELECT 1 FROM investigation_jobs WHERE kind='threat_catalog' AND state IN ('queued','running') AND json_extract(payload,'$.source_id')=?",
                (sid,),
            ).fetchone()
            if due and not pending:
                from .repository import identifier

                db.execute(
                    "INSERT INTO investigation_jobs(id,kind,state,payload,created_at,updated_at) VALUES(?,'threat_catalog','queued',?,?,?)",
                    (identifier(), packed({"source_id": sid}), stamp(), stamp()),
                )
                db.execute(
                    "UPDATE threat_catalog_state SET next_run=? WHERE source_id=?",
                    (stamp(utcnow() + timedelta(hours=1)), sid),
                )
                break


def catalog_profiles(repo, eid):
    return repo.rows(
        "SELECT * FROM threat_catalog_objects WHERE entity_id=? ORDER BY active DESC,source_id", (eid,)
    )


def edge_catalogs(repo, edge):
    return repo.rows(
        "SELECT source_id,external_id,original_url,refs,modified_at,retrieved_at FROM threat_catalog_relations WHERE relationship_id=? AND active=1",
        (edge,),
    )


def match_reports(repo, limit=200):
    signatures = repo.rows(
        "SELECT source_id,checksum FROM threat_catalog_state WHERE last_success IS NOT NULL ORDER BY source_id"
    )
    if not signatures:
        return 0
    signature = stable("literal-alias-v4-distinctive-actor-malware-campaign", packed(signatures))
    rows = repo.rows(
        "SELECT r.* FROM external_records r LEFT JOIN threat_match_state m USING(record_id) WHERE r.category IN ('cyber','threat') AND (m.record_id IS NULL OR m.catalog_signature<>? OR m.content_hash<>COALESCE(r.content_hash,'')) ORDER BY r.ingested_at DESC LIMIT ?",
        (signature, limit),
    )
    key = (str(repo.database.path), signature)
    if _MATCH_CACHE.get("key") != key:
        alias_ids = defaultdict(set)
        # Malware, tools and campaigns are proper nouns and can be matched by
        # name. ATT&CK techniques are deliberately excluded: their names are
        # ordinary English ("Cloud Accounts", "Virtual Private Server") and a
        # literal match would attribute technique reports to nothing and
        # technique articles to whatever they happen to discuss. A report
        # names its malware or its campaign, not its technique.
        for profile in repo.rows(
            "SELECT entity_id,name,aliases FROM threat_catalog_objects "
            "WHERE active=1 AND type IN ('threat_actor','malware','tool','campaign')"
        ):
            for alias in names([profile["name"], *profile["aliases"]]):
                if distinctive(alias):
                    alias_ids[alias.casefold()].add(profile["entity_id"])
        pattern = (
            re.compile(
                r"(?<!\w)(?:"
                + "|".join(re.escape(alias) for alias in sorted(alias_ids, key=len, reverse=True))
                + r")(?!\w)",
                re.I,
            )
            if alias_ids
            else None
        )
        _MATCH_CACHE.update(key=key, ids=alias_ids, pattern=pattern)
    alias_ids, pattern = _MATCH_CACHE["ids"], _MATCH_CACHE["pattern"]
    # Collect first, then decide. An alias appearing across a large share of
    # the corpus is not an identifier: ATT&CK calls a tool "route", and that
    # single word matched two thousand unrelated reports. Such aliases are
    # demoted rather than trusted, which is evidence about the alias rather
    # than an assumption about a fixed list of words.
    resolved = []
    alias_documents = defaultdict(int)
    for record in rows:
        text = record["title"] + " " + record["text"]
        matched = {}
        for match in pattern.finditer(text) if pattern else []:
            alias = match.group().casefold()
            ids = alias_ids[alias]
            for eid in ids:
                state = "explicit_name_mention" if len(ids) == 1 else "ambiguous_alias"
                if eid not in matched or state == "explicit_name_mention":
                    matched[eid] = (alias, state)
        for alias, _ in matched.values():
            alias_documents[alias] += 1
        resolved.append((record, matched))
    ceiling = max(3, len(rows) // 50)
    for record, matched in resolved:
        with repo.database.connect() as db:
            db.execute("DELETE FROM threat_report_matches WHERE record_id=?", (record["record_id"],))
            db.execute(
                "DELETE FROM relationship_evidence WHERE record_id=? AND relationship_id IN (SELECT relationship_id FROM relationships WHERE type='actor_report_context')",
                (record["record_id"],),
            )
            for eid, (alias, status) in matched.items():
                if status == "explicit_name_mention" and alias_documents[alias] > ceiling:
                    status = "ambiguous_alias"
                db.execute(
                    "INSERT INTO threat_report_matches VALUES(?,?,?,?)",
                    (record["record_id"], eid, alias, status),
                )
                if status == "explicit_name_mention":
                    places = db.execute(
                        "SELECT e.entity_id FROM entities e JOIN entity_source_mentions m USING(entity_id) WHERE m.record_id=? AND e.type='country' LIMIT 8",
                        (record["record_id"],),
                    ).fetchall()
                    for place in places:
                        edge = stable("actor-report-context", eid, place[0])
                        db.execute(
                            "INSERT OR IGNORE INTO relationships VALUES(?,?,?,?,?,?,?,?)",
                            (
                                edge,
                                eid,
                                place[0],
                                "actor_report_context",
                                "reported",
                                None,
                                None,
                                "Actor name and country both explicitly mentioned in a cyber report. Does not establish actor responsibility, sponsor or victim location.",
                            ),
                        )
                        db.execute(
                            "INSERT OR IGNORE INTO relationship_evidence VALUES(?,?)",
                            (edge, record["record_id"]),
                        )
            db.execute(
                "INSERT OR REPLACE INTO threat_match_state VALUES(?,?,?)",
                (record["record_id"], signature, record["content_hash"] or ""),
            )
    return len(rows)


def report_graph(repo, eid):
    return repo.rows(
        "SELECT r.*,m.alias,m.status AS match_status FROM threat_report_matches m JOIN external_records r USING(record_id) WHERE m.entity_id=? ORDER BY r.published_at DESC LIMIT 50",
        (eid,),
    )
