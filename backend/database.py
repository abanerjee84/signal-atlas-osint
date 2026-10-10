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
                            db.execute(statement)
                            statement = ""
                    if statement.strip():
                        raise RuntimeError("Incomplete migration statement")
                    db.execute(f"PRAGMA user_version={target}")
                    version = target

    def ingest(self, report: Report, connection: sqlite3.Connection | None = None) -> str:
        """One transaction preserves report provenance and bounded conservative clustering."""
        now = stamp()
        report_id = hashlib.sha256(f"{report.source_id}:{report.external_id}".encode()).hexdigest()[:32]
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
            existing = db.execute("SELECT event_id FROM reports WHERE report_id=?", (report_id,)).fetchone()
            event_id = existing[0] if existing else None
            if not event_id:
                # Cross-collector copies of the same source URL join the same event.
                same_url = (
                    None
                    if report.category in {"environment", "aviation", "maritime", "cyber", "sentiment"}
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
                tags,ai_summary,time_key,aircraft_track_deg,aircraft_callsign,aircraft_category)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                    ),
                )
            elif existing:
                # Refresh primary-source revisions without overwriting other supporting reports.
                db.execute(
                    """UPDATE events SET title=?,description=?,latitude=?,longitude=?,country_code=?,
                location_precision=?,location_basis=?,occurred_at=?,published_at=?,time_key=?,
                confidence=?,evidence_basis=?,severity=?,severity_basis=?,tags=?,updated_at=?,
                aircraft_track_deg=?,aircraft_callsign=?,aircraft_category=?
                WHERE event_id=? AND source_id=? AND source_url=?""",
                    (
                        report.title,
                        report.description,
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
        if report.category in {"aviation", "maritime", "environment", "cyber", "sentiment"}:
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
        return result

    def with_aircraft_metadata(self, rows):
        items = [self.event_dict(row) for row in rows]
        ids = [item["event_id"] for item in items if item["category"] == "aviation"]
        metadata = {}
        if ids:
            with self.connect() as db:
                for row in db.execute(
                    f"SELECT event_id,metadata FROM reports WHERE event_id IN ({','.join('?' for _ in ids)})",
                    ids,
                ):
                    data = json.loads(row["metadata"]).get("aircraft")
                    if data:
                        metadata[row["event_id"]] = data
        for item in items:
            if item["category"] == "aviation":
                item["aircraft"] = metadata.get(item["event_id"])
        return items

    def statuses(self) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM connector_status ORDER BY source_id")]

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

    def unlock(self, name: str, owner: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM job_locks WHERE name=? AND owner=?", (name, owner))

    def maintenance(self, settings: Settings) -> dict:
        with self.connect() as db:
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
