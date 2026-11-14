"""Short per-viewer leases: collect only while a live layer is visible."""

from datetime import timedelta

from .models import stamp, utcnow

PREFIX = "view:aviation:"
LEASE_SECONDS = 35


def set_demand(database, viewer, active):
    with database.connect() as connection:
        connection.execute("DELETE FROM job_locks WHERE name LIKE ? AND expires_at<=?", (PREFIX + "%", stamp()))
        if active:
            connection.execute(
                "INSERT INTO job_locks VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET expires_at=excluded.expires_at",
                (PREFIX + viewer, viewer, stamp(utcnow() + timedelta(seconds=LEASE_SECONDS))),
            )
        else:
            connection.execute("DELETE FROM job_locks WHERE name=? AND owner=?", (PREFIX + viewer, viewer))


def aviation_requested(database):
    with database.connect() as connection:
        return bool(connection.execute(
            "SELECT 1 FROM job_locks WHERE name LIKE ? AND expires_at>? LIMIT 1", (PREFIX + "%", stamp())
        ).fetchone())
