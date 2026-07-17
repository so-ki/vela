from __future__ import annotations

import json
import stat
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core import secure_json_store
from app.core.secure_json_store import atomic_write_json
from app.services import cold_start_service, user_preference_service


def test_atomic_json_replace_is_private_and_failure_preserves_previous_file(tmp_path, monkeypatch):
    path = tmp_path / "state" / "preferences.json"
    atomic_write_json(path, {"revision": 1})

    assert json.loads(path.read_text(encoding="utf-8")) == {"revision": 1}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700

    def fail_replace(*_args, **_kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(secure_json_store.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        atomic_write_json(path, {"revision": 2})

    assert json.loads(path.read_text(encoding="utf-8")) == {"revision": 1}
    assert list(path.parent.glob(f".{path.name}.*.tmp")) == []


def test_concurrent_preference_updates_do_not_drop_events(tmp_path, monkeypatch):
    monkeypatch.setattr(user_preference_service, "PREFS_DIR", tmp_path / "preferences")

    def record(index: int) -> None:
        user_preference_service.record_review_decision(
            17,
            code=f"CASE-{index:03d}",
            decision="rejected",
            comment="concurrency regression",
        )

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(record, range(80)))

    persisted = user_preference_service.load_user_preferences(17)
    assert len(persisted["events"]) == 80
    assert len(persisted["reject_counts"]) == 80
    assert stat.S_IMODE((tmp_path / "preferences" / "user_17.json").stat().st_mode) == 0o600


def test_attachment_merge_keeps_uploaded_metadata_and_parsed_answer(tmp_path, monkeypatch):
    sessions = tmp_path / "sessions"
    templates = tmp_path / "templates"
    monkeypatch.setattr(cold_start_service, "SESSIONS_DIR", sessions)
    monkeypatch.setattr(cold_start_service, "TEMPLATES_DIR", templates)

    session_id = "11111111-1111-4111-8111-111111111111"
    atomic_write_json(
        sessions / f"{session_id}.json",
        {
            "session_id": session_id,
            "user_id": 9,
            "answers": {},
            "uploaded_templates": [],
            "uploaded_files": [],
            "status": "in_progress",
        },
    )

    cold_start_service.upload_interview_attachment(
        session_id,
        9,
        purpose="contract_house_rules",
        filename="sample.txt",
        content="受控试点模板内容".encode("utf-8"),
        parse=True,
        parse_into="contract_house_rules",
    )

    persisted = json.loads((sessions / f"{session_id}.json").read_text(encoding="utf-8"))
    assert len(persisted["uploaded_templates"]) == 1
    assert len(persisted["uploaded_files"]) == 1
    assert persisted["answers"]["contract_house_rules"] == "受控试点模板内容"
    stored_path = templates / "user_9" / persisted["uploaded_files"][0]["id"]
    assert stat.S_IMODE(stored_path.stat().st_mode) == 0o600
