from __future__ import annotations

import json
from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.schemas.onboarding import (
    InterviewAnswerRequest,
    InterviewCompleteRequest,
    InterviewSyncRequest,
)
from app.services import cold_start_service


@pytest.fixture()
def isolated_onboarding_store(tmp_path, monkeypatch):
    monkeypatch.setattr(cold_start_service, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(cold_start_service, "TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr(cold_start_service, "PROFILES_DIR", tmp_path / "profiles")
    return tmp_path


def test_onboarding_request_models_reject_unstructured_or_oversized_state():
    session_id = "11111111-1111-4111-8111-111111111111"
    assert InterviewCompleteRequest(session_id=session_id).session_id == session_id
    assert InterviewAnswerRequest(question_id="org_name", answer="Vela Legal").answer == "Vela Legal"

    for payload in (
        {"question_id": "org_name", "answer": {"nested": "object"}},
        {"question_id": "../profile", "answer": "x"},
        {"question_id": "org_name", "answer": 123},
        {"question_id": "org_name", "answer": "x", "unexpected": True},
        {"question_id": "org_name", "answer": "x" * 20_001},
    ):
        with pytest.raises(ValidationError):
            InterviewAnswerRequest.model_validate(payload)

    with pytest.raises(ValidationError):
        InterviewCompleteRequest(session_id="../../playbook_profiles/user_1")
    with pytest.raises(ValidationError):
        InterviewSyncRequest(
            answers={f"question_{index}": "x" * 17_000 for index in range(4)}
        )


def test_service_whitelists_questions_and_validates_sync_atomically(isolated_onboarding_store):
    started = cold_start_service.start_interview(7)
    session_id = started["session_id"]
    path = cold_start_service.SESSIONS_DIR / f"{session_id}.json"

    with pytest.raises(ValueError, match="未知访谈问题"):
        cold_start_service.submit_interview_answer(session_id, 7, "invented_field", "x")
    with pytest.raises(ValueError, match="未知选项"):
        cold_start_service.submit_interview_answer(
            session_id,
            7,
            "primary_jurisdiction",
            "attacker-controlled",
        )
    with pytest.raises(ValueError, match="未知访谈问题"):
        cold_start_service.sync_interview_answers(
            session_id,
            7,
            {"org_name": "Should not persist", "invented_field": "x"},
        )

    assert json.loads(path.read_text(encoding="utf-8"))["answers"] == {}
    result = cold_start_service.sync_interview_answers(
        session_id,
        7,
        {
            "org_name": "Vela Legal",
            "industry_focus": ["new_energy", "other"],
            "industry_focus_other": "物流仓储",
        },
    )
    assert result["saved_keys"] == ["org_name", "industry_focus", "industry_focus_other"]


def test_session_ids_cannot_escape_the_session_directory(isolated_onboarding_store):
    with pytest.raises(ValueError, match="会话 ID"):
        cold_start_service.sync_interview_answers(
            "../../playbook_profiles/user_1",
            1,
            {"org_name": "overwrite"},
        )


def test_active_user_and_instance_session_quotas_are_enforced(
    isolated_onboarding_store,
    monkeypatch,
):
    first = cold_start_service.start_interview(1)
    resumed = cold_start_service.start_interview(1)
    assert resumed["session_id"] == first["session_id"]
    assert len(list(cold_start_service.SESSIONS_DIR.glob("*.json"))) == 1

    legacy_extra_id = "22222222-2222-4222-8222-222222222222"
    slightly_newer = (cold_start_service._utcnow() + timedelta(seconds=1)).isoformat()
    cold_start_service.atomic_write_json(
        cold_start_service.SESSIONS_DIR / f"{legacy_extra_id}.json",
        {
            "session_id": legacy_extra_id,
            "user_id": 1,
            "started_at": slightly_newer,
            "answers": {},
            "uploaded_templates": [],
            "status": "in_progress",
        },
    )
    pruned = cold_start_service.start_interview(1)
    assert pruned["session_id"] == legacy_extra_id
    assert len(list(cold_start_service.SESSIONS_DIR.glob("*.json"))) == 1

    monkeypatch.setattr(cold_start_service, "MAX_SESSIONS_INSTANCE", 1)
    with pytest.raises(ValueError, match="本实例"):
        cold_start_service.start_interview(2)


def test_expired_sessions_are_removed_before_instance_quota_check(
    isolated_onboarding_store,
    monkeypatch,
):
    monkeypatch.setattr(cold_start_service, "MAX_SESSIONS_INSTANCE", 1)
    monkeypatch.setattr(cold_start_service, "SESSION_TTL", timedelta(seconds=1))
    started = cold_start_service.start_interview(1)
    path = cold_start_service.SESSIONS_DIR / f"{started['session_id']}.json"
    session = json.loads(path.read_text(encoding="utf-8"))
    session["started_at"] = "2000-01-01T00:00:00+00:00"
    path.write_text(json.dumps(session), encoding="utf-8")

    replacement = cold_start_service.start_interview(2)
    assert replacement["session_id"] != started["session_id"]
    assert not path.exists()


def test_session_serialization_has_a_hard_ceiling(isolated_onboarding_store, monkeypatch):
    started = cold_start_service.start_interview(5)
    path = cold_start_service.SESSIONS_DIR / f"{started['session_id']}.json"
    before = path.read_bytes()
    monkeypatch.setattr(cold_start_service, "MAX_SESSION_JSON_BYTES", len(before) + 100)

    with pytest.raises(ValueError, match="状态超过安全上限"):
        cold_start_service.submit_interview_answer(
            started["session_id"],
            5,
            "contract_house_rules",
            "x" * 500,
        )
    assert path.read_bytes() == before


def test_template_file_count_user_bytes_and_instance_bytes_are_bounded(
    isolated_onboarding_store,
    monkeypatch,
):
    with pytest.raises(ValueError, match="文件名不安全"):
        cold_start_service.save_playbook_template(
            1,
            session_id=None,
            filename="../escape.txt",
            content=b"1",
        )

    monkeypatch.setattr(cold_start_service, "MAX_TEMPLATE_FILE_BYTES", 4)
    with pytest.raises(ValueError, match="单个模板"):
        cold_start_service.save_playbook_template(
            1,
            session_id=None,
            filename="too-large.txt",
            content=b"12345",
        )

    monkeypatch.setattr(cold_start_service, "MAX_TEMPLATE_FILE_BYTES", 100)
    monkeypatch.setattr(cold_start_service, "MAX_TEMPLATES_PER_USER", 1)
    cold_start_service.save_playbook_template(
        1,
        session_id=None,
        filename="first.txt",
        content=b"123",
    )
    with pytest.raises(ValueError, match="最多保存 1"):
        cold_start_service.save_playbook_template(
            1,
            session_id=None,
            filename="second.txt",
            content=b"1",
        )

    monkeypatch.setattr(cold_start_service, "MAX_TEMPLATES_PER_USER", 10)
    monkeypatch.setattr(cold_start_service, "MAX_TEMPLATE_BYTES_PER_USER", 5)
    cold_start_service.save_playbook_template(
        2,
        session_id=None,
        filename="first.txt",
        content=b"123",
    )
    with pytest.raises(ValueError, match="合计不能超过"):
        cold_start_service.save_playbook_template(
            2,
            session_id=None,
            filename="second.txt",
            content=b"123",
        )

    monkeypatch.setattr(cold_start_service, "MAX_TEMPLATE_BYTES_PER_USER", 100)
    monkeypatch.setattr(cold_start_service, "MAX_TEMPLATES_INSTANCE", 2)
    with pytest.raises(ValueError, match="数量已达上限"):
        cold_start_service.save_playbook_template(
            3,
            session_id=None,
            filename="instance-count.txt",
            content=b"1",
        )

    monkeypatch.setattr(cold_start_service, "MAX_TEMPLATES_INSTANCE", 100)
    monkeypatch.setattr(cold_start_service, "MAX_TEMPLATE_BYTES_INSTANCE", 7)
    with pytest.raises(ValueError, match="本实例.*总量"):
        cold_start_service.save_playbook_template(
            3,
            session_id=None,
            filename="instance-limit.txt",
            content=b"12",
        )


def test_attachment_purpose_cannot_write_an_unrelated_answer(isolated_onboarding_store):
    session_id = cold_start_service.start_interview(9)["session_id"]
    with pytest.raises(ValueError, match="用途与解析目标不匹配"):
        cold_start_service.upload_interview_attachment(
            session_id,
            9,
            purpose="brief_template_sample",
            filename="sample.txt",
            content="受控试点模板内容".encode("utf-8"),
            parse=True,
            parse_into="contract_house_rules",
        )
    assert list(cold_start_service.TEMPLATES_DIR.rglob("*")) == []
