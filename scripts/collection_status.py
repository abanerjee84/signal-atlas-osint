"""Atomic aggregate status files, tolerating short Windows reader locks."""

import json
import time
import uuid


def write_status(path, payload, *, allow_inplace=False):
    temporary = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
    text = json.dumps(payload, indent=2)
    try:
        temporary.write_text(text, encoding="utf-8")
        for attempt in range(10):
            try:
                temporary.replace(path)
                return
            except PermissionError:
                if attempt == 9:
                    if allow_inplace:
                        # An existing Windows reader may permit writes but deny deletion.
                        # Only the disposable public bridge opts in. A concurrent JSON
                        # parse can fail briefly; the UI handles that as unavailable.
                        path.write_text(text, encoding="utf-8")
                        return
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)
