import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.config import Settings
from backend.database import Database

settings = Settings()
print(json.dumps(Database(settings.database).maintenance(settings)))
