import json
from pathlib import Path

import pytest

from scripts.collection_status import write_status


def test_status_retries_reader_lock_then_replaces_atomically(tmp_path, monkeypatch):
    path = tmp_path / "status.json"
    path.write_text('{"old": true}', encoding="utf-8")
    original = Path.replace
    calls = []

    def replace(temporary, destination):
        calls.append(temporary)
        if len(calls) < 3:
            assert json.loads(path.read_text()) == {"old": True}
            raise PermissionError("synthetic Windows reader lock")
        return original(temporary, destination)

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr("scripts.collection_status.time.sleep", lambda delay: None)
    write_status(path, {"new": True})
    assert json.loads(path.read_text()) == {"new": True}
    assert len(calls) == 3
    assert not list(tmp_path.glob("*.tmp"))


def test_status_permanent_lock_preserves_previous_file_and_cleans_temp(tmp_path, monkeypatch):
    path = tmp_path / "status.json"
    path.write_text('{"old": true}', encoding="utf-8")

    def blocked(*args):
        raise PermissionError("synthetic permanent lock")

    monkeypatch.setattr(Path, "replace", blocked)
    monkeypatch.setattr("scripts.collection_status.time.sleep", lambda delay: None)
    with pytest.raises(PermissionError):
        write_status(path, {"new": True})
    assert json.loads(path.read_text()) == {"old": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_disposable_bridge_can_update_with_windows_delete_lock(tmp_path, monkeypatch):
    path = tmp_path / "bridge.json"
    path.write_text('{"old": true}', encoding="utf-8")

    def blocked(*args):
        raise PermissionError("synthetic persistent Windows delete lock")

    monkeypatch.setattr(Path, "replace", blocked)
    monkeypatch.setattr("scripts.collection_status.time.sleep", lambda delay: None)
    write_status(path, {"new": True}, allow_inplace=True)
    assert json.loads(path.read_text()) == {"new": True}
    assert not list(tmp_path.glob("*.tmp"))
