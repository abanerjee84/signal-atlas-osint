"""Consistent database + immutable media bundle, with a verified restore operation."""

import hashlib
import json
import re
import shutil
import sqlite3
from contextlib import closing

from ..models import stamp
from ..operations import backup_database


def digest_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup(database, evidence, destination, keep=7):
    root = destination.resolve()
    dbcopy = backup_database(database, root, keep)
    bundle = root / dbcopy.stem
    bundle.mkdir()
    media = bundle / "evidence"
    media.mkdir()
    shutil.copy2(dbcopy, bundle / "database.sqlite3")
    files = {"database.sqlite3": digest_file(bundle / "database.sqlite3")}
    with closing(sqlite3.connect(bundle / "database.sqlite3")) as db:
        if db.execute("SELECT name FROM sqlite_master WHERE name='media_evidence'").fetchone():
            for media_id, sha256 in db.execute(
                "SELECT id,sha256 FROM media_evidence WHERE deleted_at IS NULL"
            ):
                if not re.fullmatch(r"[a-f0-9]{32}", media_id):
                    raise ValueError("Invalid stored media identifier")
                source = evidence / (media_id + ".bin")
                if not source.is_file() or digest_file(source) != sha256:
                    raise ValueError("Active media missing or hash mismatch; bundle is incomplete")
                target = media / source.name
                shutil.copy2(source, target)
                files["evidence/" + source.name] = digest_file(target)
    manifest = {
        "version": 1,
        "created_at": stamp(),
        "files": files,
        "notes": "Database includes source snapshots and private cases. Public discussion snapshots are excluded by dashboard backup policy. Selected case evidence follows analyst case retention policy.",
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (bundle / "manifest.json").chmod(0o600)
    for path in files:
        (bundle / path).chmod(0o600)
    old = sorted(
        [p for p in root.glob("osint-*") if p.is_dir() and (p / "manifest.json").is_file()], reverse=True
    )[keep:]
    for folder in old:
        if folder.resolve().parent == root:
            shutil.rmtree(folder)
    return bundle


def restore(bundle, destination):
    bundle, destination = bundle.resolve(), destination.resolve()
    if destination.exists():
        raise ValueError("Restore destination must be a new directory")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if (
        manifest.get("version") != 1
        or not isinstance(manifest.get("files"), dict)
        or "database.sqlite3" not in manifest["files"]
    ):
        raise ValueError("Unsupported backup manifest")
    for filename, expected in manifest["files"].items():
        if filename != "database.sqlite3" and not re.fullmatch(r"evidence/[a-f0-9]{32}\.bin", filename):
            raise ValueError("Unsafe bundle path")
        source = bundle / filename
        if (
            source.is_symlink()
            or source.resolve().parent not in {bundle, bundle / "evidence"}
            or digest_file(source) != expected
        ):
            raise ValueError("Backup hash or path validation failed")
    with closing(sqlite3.connect(f"file:{bundle / 'database.sqlite3'}?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Backup database integrity failed")
    destination.mkdir(parents=True)
    (destination / "evidence").mkdir()
    for filename in manifest["files"]:
        shutil.copy2(bundle / filename, destination / filename)
    return {"restored_to": str(destination), "files_verified": len(manifest["files"]), "integrity": "ok"}
