"""Back up or restore investigations; restore always targets a new directory."""

import argparse
import json
from pathlib import Path

from backend.advanced.backup import backup, restore
from backend.config import Settings

parser = argparse.ArgumentParser()
parser.add_argument("--destination", type=Path, default=Path("data/backups"))
parser.add_argument("--restore", type=Path)
parser.add_argument("--keep", type=int, default=7)
args = parser.parse_args()
if not 1 <= args.keep <= 365:
    parser.error("keep must be 1–365")
if args.restore:
    print(json.dumps(restore(args.restore, args.destination)))
else:
    settings = Settings()
    bundle = backup(settings.database, settings.evidence_directory, args.destination, args.keep)
    print(json.dumps({"bundle": str(bundle), "manifest": str(bundle / "manifest.json")}))
