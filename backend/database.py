import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager, nullcontext
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .config import ROOT, Settings
from .geo import country_at
from .models import Filters, Report, stamp, utcnow
from .sentiment import score, social_score, tokens


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query)
        if not k.lower().startswith("utm_") and k not in {"fbclid", "gclid"}
    ]
    return urlunsplit(
        (parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), urlencode(sorted(query)), "")
    )


def report_identifier(source_id: str, external_id: str) -> str:
    """Stored identity for a report; one row per source and external id."""
    return hashlib.sha256(f"{source_id}:{external_id}".encode()).hexdigest()[:32]


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            # SQLite's journal-mode transition can return BUSY without invoking
            # busy_timeout when two processes initialize a new file together.
            deadline = time.monotonic() + 10
            while True:
                try:
                    db.execute("PRAGMA journal_mode=WAL")
                    break
                except sqlite3.OperationalError as error:
                    if (
                        error.sqlite_errorcode not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
                        or time.monotonic() >= deadline
                    ):
                        raise
                    time.sleep(0.05)
            # Serialize version inspection as well as DDL. The API and worker may
            # start together; executescript would implicitly commit this lock.
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            migrations = sorted((ROOT / "backend/migrations").glob("*.sql"))
            # Derived from the migration files, so adding one cannot leave the
            # guard behind and reject the very schema it just created.
            newest = max(int(path.name.split("_")[0]) for path in migrations)
            if version > newest:
                raise RuntimeError("Database schema newer than application")
            for path in migrations:
                target = int(path.name.split("_")[0])
                if target > version:
                    statement = ""
                    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
                        statement += line
                        if sqlite3.complete_statement(statement):
                            try:
                                db.execute(statement)
                            except sqlite3.OperationalError as error:
                                # A rolled-back version may re-run an upgrade whose columns already exist.
                                if "duplicate column name" not in str(error):
                                    raise
                            statement = ""
                    if statement.strip():
                        raise RuntimeError("Incomplete migration statement")
                    db.execute(f"PRAGMA user_version={target}")
                    version = target

    def ingest(self, report: Report, connection: sqlite3.Connection | None = None) -> str:
        """One transaction preserves report provenance and bounded conservative clustering."""
        now = stamp()
        report_id = report_identifier(report.source_id, report.external_id)
        source_url = canonical_url(report.source_url)
        label, value = (
            social_score(report.description or report.title, report.language)
            if report.social
            else score(report.title, report.language)
            if report.sentiment_kind
            else (None, None)
        )
        country = report.country_code
        if not country and report.longitude is not None:
            country = country_at(report.longitude, report.latitude)
        metadata = report.model_dump(mode="json", exclude={"raw", "title", "description"})
        metadata["country_code"] = country
        with nullcontext(connection) if connection is not None else self.connect() as db:
            if connection is None:
                db.execute("BEGIN IMMEDIATE")
            if report.cyber_observation:
                from .infrastructure_geo import apply_cached_location

                apply_cached_location(db, report)
                country = report.country_code
                metadata = report.model_dump(mode="json", exclude={"raw", "title", "description"})
            existing = db.execute("SELECT event_id FROM reports WHERE report_id=?", (report_id,)).fetchone()
            event_id = existing[0] if existing else None
            if not event_id:
                # Cross-collector copies of the same source URL join the same event.
                same_url = (
                    None
                    if report.category
                    in {
                        "environment",
                        "aviation",
                        "maritime",
                        "cyber",
                        "infrastructure",
                        "sentiment",
                        "threat",
                    }
                    else db.execute(
                        "SELECT r.event_id FROM reports r JOIN events e ON e.event_id=r.event_id WHERE r.source_url=? AND e.category=? LIMIT 1",
                        (source_url, report.category),
                    ).fetchone()
                )
                event_id = same_url[0] if same_url else self._cluster(db, report, country)
            if not event_id:
                event_id = uuid.uuid4().hex
                db.execute(
                    """INSERT INTO events (event_id,title,description,category,latitude,longitude,
                location_precision,location_basis,country_code,occurred_at,published_at,ingested_at,
                updated_at,source_id,source_url,confidence,evidence_basis,severity,severity_basis,
                tags,ai_summary,time_key,aircraft_track_deg,aircraft_callsign,aircraft_category,
                vessel_course_deg,vessel_speed_kn,vessel_type,vessel_flag)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        event_id,
                        report.title,
                        report.description,
                        report.category,
                        report.latitude,
                        report.longitude,
                        report.location_precision,
                        report.location_basis,
                        country,
                        stamp(report.occurred_at) if report.occurred_at else None,
                        stamp(report.published_at),
                        now,
                        now,
                        report.source_id,
                        source_url,
                        report.confidence,
                        report.evidence_basis,
                        report.severity,
                        report.severity_basis,
                        json.dumps(report.tags),
                        None,
                        stamp(report.occurred_at or report.published_at),
                        report.aircraft_track_deg,
                        report.aircraft_callsign or None,
                        report.aircraft_category,
                        report.vessel_course_deg,
                        report.vessel_speed_kn,
                        report.vessel_type,
                        report.vessel_flag,
                    ),
                )
            elif existing:
                # Refresh primary-source revisions without overwriting other supporting reports.
                # vessel_type is preserved across refreshes: position reports carry no
                # ship type, and wiping the column on every positional update would
                # discard the last self-reported static value from earlier cycles.
                db.execute(
                    """UPDATE events SET title=?,description=?,category=?,latitude=?,longitude=?,country_code=?,
                location_precision=?,location_basis=?,occurred_at=?,published_at=?,time_key=?,
                confidence=?,evidence_basis=?,severity=?,severity_basis=?,tags=?,updated_at=?,
                aircraft_track_deg=?,aircraft_callsign=?,aircraft_category=?,
                vessel_course_deg=?,vessel_speed_kn=?,vessel_type=COALESCE(?,vessel_type),vessel_flag=?
                WHERE event_id=? AND source_id=? AND source_url=?""",
                    (
                        report.title,
                        report.description,
                        report.category,
                        report.latitude,
                        report.longitude,
                        country,
                        report.location_precision,
                        report.location_basis,
                        stamp(report.occurred_at) if report.occurred_at else None,
                        stamp(report.published_at),
                        stamp(report.occurred_at or report.published_at),
                        report.confidence,
                        report.evidence_basis,
                        report.severity,
                        report.severity_basis,
                        json.dumps(report.tags),
                        now,
                        report.aircraft_track_deg,
                        report.aircraft_callsign or None,
                        report.aircraft_category,
                        report.vessel_course_deg,
                        report.vessel_speed_kn,
                        report.vessel_type,
                        report.vessel_flag,
                        event_id,
                        report.source_id,
                        source_url,
                    ),
                )
            db.execute(
                """INSERT INTO reports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(report_id) DO UPDATE SET title=excluded.title,description=excluded.description,
                published_at=excluded.published_at,occurred_at=excluded.occurred_at,updated_at=excluded.updated_at,
                language=excluded.language,sentiment_kind=excluded.sentiment_kind,sentiment_label=excluded.sentiment_label,
                sentiment_score=excluded.sentiment_score,metadata=excluded.metadata""",
                (
                    report_id,
                    event_id,
                    report.source_id,
                    report.external_id,
                    source_url,
                    report.title,
                    report.description,
                    stamp(report.published_at),
                    stamp(report.occurred_at) if report.occurred_at else None,
                    now,
                    now,
                    report.language,
                    report.sentiment_kind,
                    label,
                    value,
                    json.dumps(metadata),
                ),
            )
            db.execute(
                "INSERT INTO raw_records VALUES (?,?,?) ON CONFLICT(report_id) DO UPDATE SET payload=excluded.payload,ingested_at=excluded.ingested_at",
                (report_id, json.dumps(report.raw), now),
            )
            db.execute("UPDATE events SET updated_at=? WHERE event_id=?", (now, event_id))
            if report.cyber_observation:
                from .cyber_observations import index_observation

                index_observation(
                    db, report_id, report.source_id, report.cyber_observation, report.confidence
                )
            review = db.execute(
                "SELECT confidence,basis FROM evidence_reviews WHERE event_id=? ORDER BY id DESC LIMIT 1",
                (event_id,),
            ).fetchone()
            if review:
                db.execute(
                    "UPDATE events SET confidence=?,evidence_basis=? WHERE event_id=?",
                    (review[0], review[1], event_id),
                )
        return event_id

    def ingest_many(self, reports: list[Report]) -> list[str]:
        """Commit at most 100 reports together, keeping writes short and reducing disk flushes."""
        if len(reports) > 100:
            raise ValueError("Batch size exceeds 100 reports")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            return [self.ingest(report, db) for report in reports]

    def _cluster(self, db, report: Report, country: str | None) -> str | None:
        # Position observations and measured hazards remain separate observations.
        if report.category in {
            "aviation",
            "maritime",
            "environment",
            "cyber",
            "infrastructure",
            "sentiment",
            "threat",
        }:
            return None
        instant = report.occurred_at or report.published_at
        candidates = db.execute(
            """SELECT * FROM events WHERE category=? AND time_key BETWEEN ? AND ?
            AND country_code IS ? ORDER BY time_key DESC LIMIT 150""",
            (
                report.category,
                stamp(instant - timedelta(hours=12)),
                stamp(instant + timedelta(hours=12)),
                country,
            ),
        ).fetchall()
        words = tokens(report.title)
        for event in candidates:
            other = tokens(event["title"])
            overlap = len(words & other) / max(1, len(words | other))
            if len(words & other) < 4 or overlap < 0.8:
                continue
            if report.latitude is not None and event["latitude"] is not None:
                if (
                    abs(report.latitude - event["latitude"]) > 0.5
                    or abs(report.longitude - event["longitude"]) > 0.5
                ):
                    continue
            # Unknown occurrence times require stricter matching to reduce unrelated repeated headlines.
            if report.occurred_at is None and overlap < 0.95:
                continue
            return event["event_id"]
        return None

    @staticmethod
    def where(filters: Filters, alias: str = "") -> tuple[str, list]:
        prefix = f"{alias}." if alias else ""
        terms, values = ["1=1"], []
        if filters.categories:
            terms.append(f"{prefix}category IN ({','.join('?' for _ in filters.categories)})")
            values.extend(filters.categories)
        if filters.aircraft_categories:
            terms.append(
                f"({prefix}category!='aviation' OR ({prefix}aircraft_category IN "
                f"({','.join('?' for _ in filters.aircraft_categories)}) "
                f"AND {prefix}aircraft_track_deg>=0 AND {prefix}aircraft_track_deg<360 "
                f"AND {prefix}latitude IS NOT NULL AND {prefix}longitude IS NOT NULL))"
            )
            values.extend(filters.aircraft_categories)
        if filters.infrastructure_provider:
            terms.append(f"({prefix}category!='infrastructure' OR {prefix}source_id=?)")
            values.append(filters.infrastructure_provider)
        if filters.q:
            query = filters.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            terms.append(
                f"({prefix}title LIKE ? ESCAPE '\\' OR {prefix}description LIKE ? ESCAPE '\\' OR {prefix}tags LIKE ? ESCAPE '\\')"
            )
            values.extend([f"%{query}%"] * 3)
        if filters.country:
            terms.append(f"{prefix}country_code=?")
            values.append(filters.country)
        column = {"event": "time_key", "published": "published_at", "ingested": "ingested_at"}[
            filters.time_basis
        ]
        for value, operator in ((filters.start, ">="), (filters.end, "<=")):
            if value:
                terms.append(f"{prefix}{column}{operator}?")
                values.append(stamp(value))
        if filters.bbox:
            west, south, east, north = filters.bbox
            join = "AND" if west <= east else "OR"
            terms.append(
                f"({prefix}longitude>=? {join} {prefix}longitude<=?) AND {prefix}latitude BETWEEN ? AND ?"
            )
            values.extend([west, east, south, north])
        return " AND ".join(terms), values

    @staticmethod
    def event_dict(row) -> dict:
        event = dict(row)
        event["tags"] = json.loads(event["tags"])
        return event

    def events(self, filters: Filters, limit: int = 500, offset: int = 0, balanced: bool = False) -> dict:
        where, values = self.where(filters)
        count_where, count_values = self.where(filters.model_copy(update={"categories": []}))
        column = {"event": "time_key", "published": "published_at", "ingested": "ingested_at"}[
            filters.time_basis
        ]
        with self.connect() as db:
            total = db.execute(f"SELECT COUNT(*) FROM events WHERE {where}", values).fetchone()[0]
            if balanced:
                # Round-robin categories and geographic cells, so frequent position snapshots
                # cannot consume the whole first page and hide older source reports.
                rows = db.execute(
                    f"""WITH cells AS (
                        SELECT event_id,category,{column} AS sort_time,
                        ROW_NUMBER() OVER (
                            PARTITION BY category,CAST((longitude+180)/30 AS INTEGER),
                            CAST((latitude+90)/30 AS INTEGER)
                            ORDER BY {column} DESC,event_id
                        ) AS cell_rank FROM events WHERE {where}
                    ), ranked AS (
                        SELECT *,ROW_NUMBER() OVER (
                            PARTITION BY category ORDER BY cell_rank,sort_time DESC,event_id
                        ) AS category_rank FROM cells
                    ) SELECT e.* FROM ranked r JOIN events e ON e.event_id=r.event_id
                    ORDER BY r.category_rank,r.category LIMIT ? OFFSET ?""",
                    [*values, limit, offset],
                ).fetchall()
            else:
                rows = db.execute(
                    f"SELECT * FROM events WHERE {where} ORDER BY {column} DESC,event_id LIMIT ? OFFSET ?",
                    [*values, limit, offset],
                ).fetchall()
            located = db.execute(
                f"SELECT COUNT(*) FROM events WHERE {where} AND latitude IS NOT NULL", values
            ).fetchone()[0]
            category_counts = {
                row["category"]: row["count"]
                for row in db.execute(
                    f"SELECT category,COUNT(*) AS count FROM events WHERE {count_where} GROUP BY category",
                    count_values,
                )
            }
        return {
            "items": self.with_aircraft_metadata(rows),
            "total": total,
            "located_total": located,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(rows) < total,
            "category_counts": category_counts,
            "selection": "layers_and_regions" if balanced else "latest",
        }

    def detail(self, event_id: str) -> dict | None:
        with self.connect() as db:
            event = db.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
            if not event:
                return None
            rows = db.execute(
                "SELECT * FROM reports WHERE event_id=? ORDER BY published_at LIMIT 100", (event_id,)
            ).fetchall()
            total = db.execute("SELECT COUNT(*) FROM reports WHERE event_id=?", (event_id,)).fetchone()[0]
            reviews = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM evidence_reviews WHERE event_id=? ORDER BY id DESC LIMIT 50", (event_id,)
                )
            ]
        result = self.event_dict(event)
        result["reports"] = [{**dict(row), "metadata": json.loads(row["metadata"])} for row in rows]
        result["report_count"] = total
        result["evidence_reviews"] = reviews
        if result["category"] == "aviation" and result["reports"]:
            result["aircraft"] = result["reports"][0]["metadata"].get("aircraft")
        if result["category"] == "threat" and result["reports"]:
            result["threat"] = result["reports"][0]["metadata"].get("threat")
        if result["category"] == "infrastructure" and result["reports"]:
            for field in ("cyber_observation", "infrastructure_geo"):
                result[field] = result["reports"][0]["metadata"].get(field)
        return result

    def with_aircraft_metadata(self, rows):
        items = [self.event_dict(row) for row in rows]
        ids = [
            item["event_id"] for item in items if item["category"] in {"aviation", "threat", "infrastructure"}
        ]
        metadata = {}
        if ids:
            with self.connect() as db:
                for row in db.execute(
                    f"SELECT event_id,metadata FROM reports WHERE event_id IN ({','.join('?' for _ in ids)})",
                    ids,
                ):
                    data = json.loads(row["metadata"])
                    if data:
                        metadata[row["event_id"]] = data
        for item in items:
            if item["category"] == "aviation":
                item["aircraft"] = metadata.get(item["event_id"], {}).get("aircraft")
            if item["category"] == "threat":
                item["threat"] = metadata.get(item["event_id"], {}).get("threat")
            if item["category"] == "infrastructure":
                for field in ("cyber_observation", "infrastructure_geo"):
                    item[field] = metadata.get(item["event_id"], {}).get(field)
        return items

    def statuses(self) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM connector_status ORDER BY source_id")]

    def permission(self, source_id: str) -> dict | None:
        """Recorded redistribution decision for a source, or None when undecided.

        An absent row means the decision was never made, which is not the same as
        permission granted.
        """
        with self.connect() as db:
            row = db.execute("SELECT * FROM source_permissions WHERE source_id=?", (source_id,)).fetchone()
        return dict(row) if row else None

    def permissions(self) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM source_permissions ORDER BY source_id")]

    def set_permission(self, source_id: str, **fields) -> None:
        allowed = {
            "display_class",
            "commercial_use",
            "retention_allowed",
            "export_allowed",
            "derivative_allowed",
            "basis",
            "reviewed_at",
            "reviewer",
        }
        if not fields or not set(fields) <= allowed:
            raise ValueError("Invalid permission fields")
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO source_permissions(source_id) VALUES (?)", (source_id,))
            db.execute(
                f"UPDATE source_permissions SET {','.join(key + '=?' for key in fields)} WHERE source_id=?",
                [*fields.values(), source_id],
            )

    def set_status(self, source_id: str, **fields) -> None:
        allowed = {
            "state",
            "last_attempt",
            "last_success",
            "error",
            "fetched",
            "stored",
            "rejected",
            "truncated",
            "next_run",
            "duration_ms",
        }
        if not fields or not set(fields) <= allowed:
            raise ValueError("Invalid status fields")
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO connector_status(source_id) VALUES (?)", (source_id,))
            db.execute(
                f"UPDATE connector_status SET {','.join(key + '=?' for key in fields)} WHERE source_id=?",
                [*fields.values(), source_id],
            )

    def lock(self, name: str, owner: str, seconds: int) -> bool:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM job_locks WHERE expires_at<?", (stamp(),))
            try:
                db.execute(
                    "INSERT INTO job_locks VALUES (?,?,?)",
                    (name, owner, stamp(utcnow() + timedelta(seconds=seconds))),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def renew_lock(self, name: str, owner: str, seconds: int) -> bool:
        with self.connect() as db:
            return (
                db.execute(
                    "UPDATE job_locks SET expires_at=? WHERE name=? AND owner=? AND expires_at>=?",
                    (stamp(utcnow() + timedelta(seconds=seconds)), name, owner, stamp()),
                ).rowcount
                == 1
            )

    def unlock(self, name: str, owner: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM job_locks WHERE name=? AND owner=?", (name, owner))

    def maintenance(self, settings: Settings) -> dict:
        from .cyber_observations import prune_observations

        prune_observations(self, settings.cyber_observation_retention_days)
        with self.connect() as db:
            db.execute(
                "DELETE FROM cyber_ddos_series WHERE start_at<?", (stamp(utcnow() - timedelta(days=30)),)
            )
            db.execute(
                "DELETE FROM events WHERE category='sentiment' AND ingested_at<?",
                (stamp(utcnow() - timedelta(hours=24)),),
            )
            db.execute("""INSERT INTO daily_stats SELECT substr(time_key,1,10),category,COUNT(*) FROM events
             GROUP BY substr(time_key,1,10),category HAVING 1
             ON CONFLICT(day,category) DO UPDATE SET count=excluded.count""")
            deleted = {}
            for table, column, days in [
                ("raw_records", "ingested_at", settings.raw_retention_days),
                ("events", "time_key", settings.event_retention_days),
                ("daily_stats", "day", settings.stats_retention_days),
            ]:
                deleted[table] = db.execute(
                    f"DELETE FROM {table} WHERE {column}<?", (stamp(utcnow() - timedelta(days=days)),)
                ).rowcount
            db.execute("DELETE FROM ai_cache WHERE expires_at<?", (stamp(),))
            db.execute(
                "DELETE FROM ai_calls WHERE requested_at<?",
                (stamp(utcnow() - timedelta(days=settings.stats_retention_days)),),
            )
        with self.connect() as db:
            db.execute("PRAGMA wal_checkpoint(PASSIVE)")
            db.execute("PRAGMA optimize")
        return deleted

    def replace_social_snapshot(self, source_id: str, reports: list[Report]) -> int:
        """Current bounded collection replaces previous content, including absent/deleted posts."""
        if len(reports) > 5000 or any(
            report.source_id != source_id or not report.social or report.category != "sentiment"
            for report in reports
        ):
            raise ValueError("Invalid social snapshot")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM events WHERE category='sentiment' AND source_id=?", (source_id,))
            for report in reports:
                self.ingest(report, db)
        return len(reports)

    def replace_vessel_snapshot(self, source_id: str, reports: list[Report]) -> int:
        """Current AIS fleet replaces the previous one.

        Vessel rows are keyed by MMSI and updated in place, so without this a
        vessel that stops reporting keeps its last position on the map
        indefinitely, presented as a current fix. Only vessels present in this
        cycle are kept.

        Positions are written first through the ordinary chunked path and the
        retired rows are deleted afterwards in short statements. Wrapping all of
        it in one transaction would hold the database write lock for a thousand
        upserts and stall the concurrent aircraft snapshot, which is what turns
        a live dashboard into a 503.
        """
        if len(reports) > 5000 or any(
            report.source_id != source_id or report.category != "maritime"
            for report in reports
        ):
            raise ValueError("Invalid vessel snapshot")
        report_ids = [report_identifier(source_id, report.external_id) for report in reports]
        for start in range(0, len(reports), 100):
            self.ingest_many(reports[start : start + 100])
        # A stored event keeps its own id, so the surviving set is resolved
        # through the reports that reference it rather than assumed.
        event_ids: list[str] = []
        with self.connect() as db:
            # SQLite caps host parameters per statement, so the lookup reads
            # report ids in chunks, while the surviving set is stated through a
            # temp table: a chunked NOT IN list would delete rows whose ids
            # belong to a later chunk.
            db.execute("CREATE TEMP TABLE keep_events (event_id TEXT PRIMARY KEY)")
            for start in range(0, len(report_ids), 400):
                chunk = report_ids[start : start + 400]
                event_ids += [
                    row[0]
                    for row in db.execute(
                        f"SELECT event_id FROM reports WHERE report_id IN ({','.join('?' * len(chunk))})",
                        chunk,
                    )
                ]
            for start in range(0, len(event_ids), 400):
                db.executemany(
                    "INSERT OR IGNORE INTO keep_events VALUES (?)",
                    [(event_id,) for event_id in event_ids[start : start + 400]],
                )
            db.execute(
                "DELETE FROM events WHERE category='maritime' AND source_id=? "
                "AND event_id NOT IN (SELECT event_id FROM keep_events)",
                (source_id,),
            )
        return len(reports)

    def prune_threat_telemetry(self, source_id: str) -> int:
        """Bound vendor samples independently of published reports, in a short transaction."""
        if source_id not in {
            "bitdefender_threatmap",
            "bunkerweb_threatmap",
            "imperva_threatmap",
            "radware_threatmap",
        }:
            raise ValueError("Unknown threat telemetry source")
        with self.connect() as db:
            return db.execute(
                """DELETE FROM events WHERE category='threat' AND source_id=? AND (
                ingested_at<? OR event_id NOT IN (
                SELECT event_id FROM events WHERE category='threat' AND source_id=?
                ORDER BY ingested_at DESC,event_id LIMIT 2000))""",
                (source_id, stamp(utcnow() - timedelta(days=7)), source_id),
            ).rowcount
