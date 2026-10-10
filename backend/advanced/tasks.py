import asyncio
import uuid
from datetime import timedelta

from ..ai import AIError
from ..models import stamp, utcnow
from .analysis import analyze
from .processing import index_batch
from .providers import lookup
from .repository import Repository, packed
from .threats import match_reports, refresh_catalog, schedule
from .watch import poll


async def tick(database, settings, client):
    repo = Repository(database)
    owner = uuid.uuid4().hex
    if not await asyncio.to_thread(database.lock, "advanced:worker", owner, 600):
        return
    try:
        # Recover work abandoned by a process crash after its bounded lease has expired.
        with database.connect() as db:
            db.execute(
                "UPDATE investigation_jobs SET state='failed',error='Worker interrupted; submit again',updated_at=? WHERE state='running' AND updated_at<?",
                (stamp(), stamp(utcnow() - timedelta(seconds=600))),
            )
        await asyncio.to_thread(index_batch, database, 200)
        await asyncio.to_thread(match_reports, repo, 100)
        jobs = repo.rows(
            "SELECT * FROM investigation_jobs WHERE state='queued' ORDER BY created_at,id LIMIT 2"
        )
        for job in jobs:
            with database.connect() as db:
                db.execute(
                    "UPDATE investigation_jobs SET state='running',updated_at=? WHERE id=?",
                    (stamp(), job["id"]),
                )
            try:
                async with asyncio.timeout(180):
                    if job["kind"] == "analysis":
                        result = await analyze(repo, settings, client, job["payload"])
                    elif job["kind"] == "watch":
                        watch = repo.one(
                            "SELECT * FROM watch_sources WHERE id=?", (job["payload"]["watch_id"],), True
                        )
                        if not watch["enabled"]:
                            raise ValueError("Monitor is paused")
                        result = await poll(repo, settings, watch)
                    elif job["kind"] == "lookup":
                        result = await lookup(repo, settings, client, job["payload"])
                    elif job["kind"] == "threat_catalog":
                        result = await refresh_catalog(repo, settings, client, job["payload"]["source_id"])
                    else:
                        raise ValueError("Unsupported job type")
                with database.connect() as db:
                    db.execute(
                        "UPDATE investigation_jobs SET state='completed',result=?,updated_at=? WHERE id=?",
                        (packed(result), stamp(), job["id"]),
                    )
            except Exception as error:
                message = (
                    error.message
                    if isinstance(error, AIError)
                    else str(error)
                    if isinstance(error, ValueError)
                    else "Job failed (" + type(error).__name__ + ")"
                )
                with database.connect() as db:
                    db.execute(
                        "UPDATE investigation_jobs SET state='failed',error=?,updated_at=? WHERE id=?",
                        (message[:300], stamp(), job["id"]),
                    )
            repo.audit("job.finished", job["id"], {"kind": job["kind"]})
        schedule(repo, settings)
        # Schedules create at most two pending monitor jobs per tick, without overlap.
        with database.connect() as db:
            for watch in db.execute(
                "SELECT * FROM watch_sources WHERE enabled=1 AND (next_run IS NULL OR next_run<=?) ORDER BY next_run LIMIT 2",
                (stamp(),),
            ).fetchall():
                active = db.execute(
                    "SELECT 1 FROM investigation_jobs WHERE kind='watch' AND state IN ('queued','running') AND json_extract(payload,'$.watch_id')=?",
                    (watch["id"],),
                ).fetchone()
                if not active:
                    db.execute(
                        "INSERT INTO investigation_jobs(id,kind,state,payload,created_at,updated_at) VALUES(?,'watch','queued',?,?,?)",
                        (uuid.uuid4().hex, packed({"watch_id": watch["id"]}), stamp(), stamp()),
                    )
        cleanup(repo, settings)
        # Public country aggregates, hourly; never individual-device or precise IP geolocation.
        with database.connect() as db:
            enabled = db.execute("SELECT enabled FROM sources WHERE source_id='ioda'").fetchone()
            cached = db.execute(
                "SELECT 1 FROM advanced_provider_cache WHERE source_id='ioda' AND expires_at>?", (stamp(),)
            ).fetchone()
            pending = db.execute(
                "SELECT 1 FROM investigation_jobs WHERE kind='lookup' AND state IN ('queued','running') AND json_extract(payload,'$.provider_id')='ioda'"
            ).fetchone()
            recent_failure = db.execute(
                "SELECT 1 FROM investigation_jobs WHERE kind='lookup' AND state='failed' AND json_extract(payload,'$.provider_id')='ioda' AND updated_at>?",
                (stamp(utcnow() - timedelta(hours=1)),),
            ).fetchone()
            if enabled and enabled[0] and not cached and not pending and not recent_failure:
                db.execute(
                    "INSERT INTO investigation_jobs(id,kind,state,payload,created_at,updated_at) VALUES(?,'lookup','queued',?,?,?)",
                    (uuid.uuid4().hex, packed({"provider_id": "ioda"}), stamp(), stamp()),
                )
    finally:
        await asyncio.to_thread(database.unlock, "advanced:worker", owner)


def cleanup(repo, settings):
    cutoff = stamp(utcnow() - timedelta(days=settings.evidence_retention_days))
    for row in repo.rows("SELECT id FROM media_evidence WHERE deleted_at<? LIMIT 20", (cutoff,)):
        (settings.evidence_directory / (row["id"] + ".bin")).unlink(missing_ok=True)
    with repo.database.connect() as db:
        # Explicit case deletion clears private notes/evidence after retention; audit remains.
        deleted = db.execute(
            "SELECT id FROM investigation_cases WHERE deleted_at<? LIMIT 20", (cutoff,)
        ).fetchall()
        for row in deleted:
            db.execute("DELETE FROM case_evidence WHERE case_id=?", (row[0],))
            db.execute("DELETE FROM case_notes WHERE case_id=?", (row[0],))
            db.execute("DELETE FROM investigation_cases WHERE id=?", (row[0],))
        db.execute(
            "DELETE FROM investigation_jobs WHERE updated_at<? AND state IN ('completed','failed','cancelled')",
            (cutoff,),
        )
