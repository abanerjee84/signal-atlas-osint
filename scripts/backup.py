"""Consistent online SQLite backup; never copy a live WAL database with filesystem tools."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.advanced.backup import backup, restore
from backend.config import Settings

parser = argparse.ArgumentParser()
parser.add_argument("--destination", type=Path, default=Path("data/backups"))
parser.add_argument("--keep", type=int, default=7)
parser.add_argument(
    "--restore", type=Path, help="Verified bundle to restore into a new --destination directory"
)
arguments = parser.parse_args()
if not 1 <= arguments.keep <= 365:
    parser.error("keep must be between 1 and 365")
if arguments.restore:
    print(json.dumps(restore(arguments.restore, arguments.destination)))
else:
    settings = Settings()
    result = backup(settings.database, settings.evidence_directory, arguments.destination, arguments.keep)
    manifest = json.loads((result / "manifest.json").read_text(encoding="utf-8"))
    print(json.dumps({"backup": str(result), "integrity": "ok", "files": len(manifest["files"])}))
