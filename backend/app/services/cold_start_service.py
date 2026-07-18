"""Cold-start interview + playbook profile (Claude for Legal pattern)."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.secure_json_store import (
    atomic_write_bytes,
    atomic_write_json,
    synchronized_json_store,
)

INTERVIEW_PATH = Path(__file__).resolve().parents[1] / "data" / "cold_start_interview.json"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PROFILES_DIR = DATA_DIR / "playbook_profiles"
TEMPLATES_DIR = DATA_DIR / "playbook_templates"
PLAYBOOK_PROFILE_SCHEMA_VERSION = "1.0"
PLAYBOOK_OWNER_BINDING_VERSION = "1.0"

# Auxiliary onboarding state is intentionally bounded because it lives on the
# persistent application volume rather than in the transactional database.  The
# production pilot runs one worker, so the shared JSON-store lock below makes
# these quota checks and writes atomic within the supported deployment boundary.
SESSION_TTL = timedelta(days=7)
COMPLETED_SESSION_RETENTION = timedelta(days=1)
MAX_ACTIVE_SESSIONS_PER_USER = 1
MAX_SESSIONS_INSTANCE = 1_000
MAX_SESSION_JSON_BYTES = 128 * 1024
MAX_INTERVIEW_ANSWER_KEYS = 16
MAX_INTERVIEW_ANSWER_CHARS = 20_000
MAX_SHORT_ANSWER_CHARS = 500
MAX_INTERVIEW_LIST_ITEMS = 16
MAX_INTERVIEW_LIST_ITEM_CHARS = 256
MAX_INTERVIEW_SYNC_BYTES = 64 * 1024
MAX_TEMPLATE_FILE_BYTES = 25 * 1024 * 1024
MAX_TEMPLATES_PER_USER = 20
MAX_TEMPLATE_BYTES_PER_USER = 100 * 1024 * 1024
MAX_TEMPLATES_INSTANCE = 1_000
MAX_TEMPLATE_BYTES_INSTANCE = 1024 * 1024 * 1024

SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
QUESTION_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

# Playbook profile → default scope (does NOT modify rules JSON)
INDUSTRY_FOCUS_DEFAULT_DIMENSIONS: dict[str, list[str]] = {
    "new_energy": ["labor", "foreign_investment", "tax", "environment", "industry_access"],
    "mining": ["foreign_investment", "tax", "environment", "industry_access"],
    "cross_border_ecommerce": ["foreign_investment", "tax", "industry_access", "data_compliance"],
}

INDUSTRY_FOCUS_SUGGESTED_CODES: dict[str, list[str]] = {
    "new_energy": [
        "LAB-001",
        "LAB-002",
        "FOR-001",
        "FOR-002",
        "FOR-003",
        "TAX-001",
        "TAX-002",
        "ENV-001",
        "ENV-004",
        "IND-001",
        "IND-002",
    ],
    "mining": ["FOR-001", "FOR-002", "ENV-001", "TAX-001", "IND-001"],
    "cross_border_ecommerce": ["FOR-001", "TAX-001", "TAX-004", "IND-002", "DAT-001"],
}

VALID_SCOPE_DIMENSIONS = frozenset(
    {"labor", "foreign_investment", "tax", "environment", "industry_access", "data_compliance"}
)
SESSIONS_DIR = DATA_DIR / "interview_sessions"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().isoformat()


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w.\-]", "_", name or "template")[:120]


def _validate_template_filename(filename: str) -> None:
    try:
        encoded_length = len(filename.encode("utf-8")) if isinstance(filename, str) else 0
    except UnicodeEncodeError as exc:
        raise ValueError("模板文件名不安全或过长") from exc
    if (
        not isinstance(filename, str)
        or not filename
        or encoded_length > 512
        or Path(filename).name != filename
        or "\\" in filename
        or any(ord(char) < 32 or ord(char) == 127 for char in filename)
    ):
        raise ValueError("模板文件名不安全或过长")


def load_interview_script() -> dict[str, Any]:
    with open(INTERVIEW_PATH, encoding="utf-8") as f:
        return json.load(f)


def _profile_path(user_id: int) -> Path:
    return PROFILES_DIR / f"user_{user_id}.json"


def _profile_unavailable(user_id: int, message: str) -> dict[str, Any]:
    return {
        "completed": False,
        "user_id": user_id,
        "message": message,
    }


def _owner_binding(
    user_id: int,
    *,
    owner_email: Optional[str],
    owner_auth_provider: Optional[str],
    owner_external_subject: Optional[str],
) -> Optional[dict[str, Any]]:
    """Return a canonical account binding, or None when identity cannot be verified."""
    email = str(owner_email or "").strip().lower()
    auth_provider = str(owner_auth_provider or "").strip().lower()
    external_subject = str(owner_external_subject or "").strip() or None
    if user_id <= 0 or not email or not auth_provider:
        return None
    if auth_provider != "local" and not external_subject:
        return None
    return {
        "binding_version": PLAYBOOK_OWNER_BINDING_VERSION,
        "user_id": user_id,
        "email": email,
        "auth_provider": auth_provider,
        "external_subject": external_subject,
    }


@synchronized_json_store
def save_playbook_profile(
    user_id: int,
    profile: dict[str, Any],
    *,
    owner_email: str,
    owner_auth_provider: str,
    owner_external_subject: Optional[str],
) -> dict[str, Any]:
    """Persist a profile bound to the authenticated account, not only a reusable DB id."""
    if user_id <= 0:
        raise ValueError("用户 ID 无效")
    binding = _owner_binding(
        user_id,
        owner_email=owner_email,
        owner_auth_provider=owner_auth_provider,
        owner_external_subject=owner_external_subject,
    )
    if binding is None:
        raise ValueError("无法验证 Playbook 所属账号身份")
    payload = dict(profile)
    payload["user_id"] = user_id
    payload["owner_binding"] = binding
    payload.setdefault("profile_schema_version", PLAYBOOK_PROFILE_SCHEMA_VERSION)
    atomic_write_json(_profile_path(user_id), payload, sort_keys=True)
    return payload


def _canonical_session_id(session_id: str) -> str:
    candidate = str(session_id or "")
    if not SESSION_ID_RE.fullmatch(candidate):
        raise ValueError("访谈会话 ID 格式无效")
    try:
        parsed = uuid.UUID(candidate)
    except ValueError as exc:
        raise ValueError("访谈会话 ID 格式无效") from exc
    if parsed.version != 4 or str(parsed) != candidate:
        raise ValueError("访谈会话 ID 格式无效")
    return candidate


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{_canonical_session_id(session_id)}.json"


def _serialized_json_size(payload: Any, *, pretty: bool = False) -> int:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("访谈答案必须是文本或文本列表") from exc
    if pretty:
        encoded += "\n"
    return len(encoded.encode("utf-8"))


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _session_activity(session: dict[str, Any], path: Path) -> datetime:
    for key in ("completed_at", "updated_at", "started_at"):
        parsed = _parse_timestamp(session.get(key))
        if parsed is not None:
            return parsed
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _session_expired(session: dict[str, Any], path: Path, now: datetime) -> bool:
    retention = (
        COMPLETED_SESSION_RETENTION
        if session.get("status") == "completed"
        else SESSION_TTL
    )
    activity = _session_activity(session, path)
    if activity > now + timedelta(minutes=5):
        return True
    return now - activity > retention


def _remove_session(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _read_session_file(path: Path) -> dict[str, Any]:
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("访谈会话文件无效")
        if path.stat().st_size > MAX_SESSION_JSON_BYTES:
            raise ValueError("访谈会话状态超过安全上限")
        with open(path, encoding="utf-8") as stream:
            session = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("访谈会话状态损坏或不可读取") from exc
    if not isinstance(session, dict):
        raise ValueError("访谈会话状态无效")
    if not isinstance(session.get("answers", {}), dict):
        raise ValueError("访谈会话答案结构无效")
    for key in ("uploaded_templates", "uploaded_files"):
        if key in session and not isinstance(session[key], list):
            raise ValueError("访谈会话附件结构无效")
    return session


def _cleanup_expired_sessions(*, now: Optional[datetime] = None) -> list[tuple[Path, dict[str, Any]]]:
    """Remove expired/corrupt session files and return retained bounded records."""

    now = now or _utcnow()
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    retained: list[tuple[Path, dict[str, Any]]] = []
    for path in SESSIONS_DIR.glob("*.json"):
        try:
            session_id = _canonical_session_id(path.stem)
            session = _read_session_file(path)
            if session.get("session_id") != session_id:
                raise ValueError("访谈会话标识不匹配")
            if type(session.get("user_id")) is not int or session["user_id"] <= 0:
                raise ValueError("访谈会话用户无效")
            if _session_expired(session, path, now):
                _remove_session(path)
                continue
        except ValueError:
            _remove_session(path)
            continue
        retained.append((path, session))
    return retained


def _load_session(
    session_id: str,
    user_id: int,
    *,
    require_in_progress: bool = True,
) -> tuple[Path, dict[str, Any]]:
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("用户 ID 无效")
    path = _session_path(session_id)
    if not path.exists():
        raise ValueError("访谈会话不存在或已过期")
    session = _read_session_file(path)
    if session.get("session_id") != session_id:
        raise ValueError("访谈会话状态无效")
    if session.get("user_id") != user_id:
        raise ValueError("无权访问该访谈会话")
    if _session_expired(session, path, _utcnow()):
        _remove_session(path)
        raise ValueError("访谈会话不存在或已过期")
    if require_in_progress and session.get("status") != "in_progress":
        raise ValueError("访谈会话已完成或不可修改")
    return path, session


def _assert_session_size(session: dict[str, Any]) -> None:
    if _serialized_json_size(session, pretty=True) > MAX_SESSION_JSON_BYTES:
        raise ValueError("访谈会话状态超过安全上限，请缩短答案或减少附件")


def _question_specs(script: Optional[dict[str, Any]] = None) -> dict[str, dict[str, Any]]:
    script = script or load_interview_script()
    specs: dict[str, dict[str, Any]] = {}
    for raw_question in script.get("questions") or []:
        if not isinstance(raw_question, dict):
            continue
        question_id = raw_question.get("id")
        if isinstance(question_id, str) and QUESTION_ID_RE.fullmatch(question_id):
            specs[question_id] = raw_question
        other = raw_question.get("other_field")
        if isinstance(other, dict):
            other_id = other.get("id")
            if isinstance(other_id, str) and QUESTION_ID_RE.fullmatch(other_id):
                specs[other_id] = {
                    "id": other_id,
                    "type": "text",
                    "is_other_field": True,
                }
    return specs


def _choice_values(question: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for option in question.get("options") or []:
        value = option.get("value") if isinstance(option, dict) else option
        if isinstance(value, str):
            values.add(value)
    return values


def _normalize_answer(
    question_id: str,
    answer: Any,
    *,
    specs: Optional[dict[str, dict[str, Any]]] = None,
) -> str | list[str]:
    if not isinstance(question_id, str) or not QUESTION_ID_RE.fullmatch(question_id):
        raise ValueError("访谈问题 ID 格式无效")
    specs = specs or _question_specs()
    question = specs.get(question_id)
    if question is None:
        raise ValueError(f"未知访谈问题：{question_id}")

    question_type = question.get("type")
    if question_type == "multi_choice":
        if not isinstance(answer, list):
            raise ValueError(f"问题 {question_id} 必须提交文本列表")
        if len(answer) > MAX_INTERVIEW_LIST_ITEMS:
            raise ValueError(f"问题 {question_id} 的选项过多")
        if any(not isinstance(item, str) for item in answer):
            raise ValueError(f"问题 {question_id} 只能包含文本选项")
        if any(len(item) > MAX_INTERVIEW_LIST_ITEM_CHARS for item in answer):
            raise ValueError(f"问题 {question_id} 的选项文本过长")
        if len(set(answer)) != len(answer):
            raise ValueError(f"问题 {question_id} 包含重复选项")
        unknown = set(answer) - _choice_values(question)
        if unknown:
            raise ValueError(f"问题 {question_id} 包含未知选项")
        normalized: str | list[str] = list(answer)
    else:
        if not isinstance(answer, str):
            raise ValueError(f"问题 {question_id} 必须提交文本答案")
        normalized_text = answer.strip()
        if question_type == "choice" and normalized_text not in _choice_values(question):
            raise ValueError(f"问题 {question_id} 包含未知选项")
        if question_id == "org_name":
            max_chars = 255
        elif question.get("is_other_field") or question_type == "text":
            max_chars = MAX_SHORT_ANSWER_CHARS
        else:
            max_chars = MAX_INTERVIEW_ANSWER_CHARS
        if len(normalized_text) > max_chars:
            raise ValueError(f"问题 {question_id} 的答案不能超过 {max_chars} 个字符")
        normalized = normalized_text

    if _serialized_json_size(normalized) > MAX_INTERVIEW_SYNC_BYTES:
        raise ValueError(f"问题 {question_id} 的答案序列化后过大")
    return normalized


def _normalize_answers(answers: Any) -> dict[str, str | list[str]]:
    if not isinstance(answers, dict):
        raise ValueError("answers 必须是对象")
    if len(answers) > MAX_INTERVIEW_ANSWER_KEYS:
        raise ValueError(f"单次最多同步 {MAX_INTERVIEW_ANSWER_KEYS} 个访谈答案")
    if _serialized_json_size(answers) > MAX_INTERVIEW_SYNC_BYTES:
        raise ValueError(f"批量同步答案不能超过 {MAX_INTERVIEW_SYNC_BYTES // 1024}KB")
    specs = _question_specs()
    return {
        question_id: _normalize_answer(question_id, answer, specs=specs)
        for question_id, answer in answers.items()
    }


def _upload_purpose_map(script: Optional[dict[str, Any]] = None) -> dict[str, Optional[str]]:
    script = script or load_interview_script()
    purposes: dict[str, Optional[str]] = {"general": None}
    for question in script.get("questions") or []:
        if not isinstance(question, dict):
            continue
        upload = question.get("upload_field")
        if not isinstance(upload, dict):
            continue
        purpose = upload.get("purpose")
        parse_into = upload.get("parse_into")
        if isinstance(purpose, str) and QUESTION_ID_RE.fullmatch(purpose):
            purposes[purpose] = parse_into if isinstance(parse_into, str) else None
    return purposes


def _validate_upload_binding(
    purpose: str,
    *,
    parse_into: Optional[str] = None,
    merge_mode: str = "append",
) -> None:
    purposes = _upload_purpose_map()
    if purpose not in purposes:
        raise ValueError("未知的访谈附件用途")
    if merge_mode not in {"append", "replace"}:
        raise ValueError("merge_mode 须为 append 或 replace")
    expected_target = purposes[purpose]
    if parse_into is not None:
        if parse_into not in _question_specs():
            raise ValueError("未知的附件解析目标")
        if expected_target != parse_into:
            raise ValueError("附件用途与解析目标不匹配")


def _template_usage(root: Path) -> tuple[int, int]:
    count = 0
    total_bytes = 0
    if not root.exists():
        return count, total_bytes
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        dirnames[:] = [
            name
            for name in dirnames
            if not (base / name).is_symlink()
        ]
        for name in filenames:
            if name.startswith("."):
                continue
            path = base / name
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                size = path.stat().st_size
            except OSError:
                continue
            count += 1
            total_bytes += max(0, int(size))
    return count, total_bytes


def _assert_template_quota(user_id: int, incoming_bytes: int) -> None:
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("用户 ID 无效")
    if incoming_bytes <= 0:
        raise ValueError("模板文件为空")
    if incoming_bytes > MAX_TEMPLATE_FILE_BYTES:
        raise ValueError(
            f"单个模板文件不能超过 {MAX_TEMPLATE_FILE_BYTES // (1024 * 1024)}MB"
        )
    user_count, user_bytes = _template_usage(TEMPLATES_DIR / f"user_{user_id}")
    if user_count >= MAX_TEMPLATES_PER_USER:
        raise ValueError(f"每位用户最多保存 {MAX_TEMPLATES_PER_USER} 个 Playbook 模板")
    if user_bytes + incoming_bytes > MAX_TEMPLATE_BYTES_PER_USER:
        raise ValueError(
            f"每位用户的 Playbook 模板合计不能超过 {MAX_TEMPLATE_BYTES_PER_USER // (1024 * 1024)}MB"
        )
    instance_count, instance_bytes = _template_usage(TEMPLATES_DIR)
    if instance_count >= MAX_TEMPLATES_INSTANCE:
        raise ValueError("本实例保存的 Playbook 模板数量已达上限")
    if instance_bytes + incoming_bytes > MAX_TEMPLATE_BYTES_INSTANCE:
        raise ValueError("本实例保存的 Playbook 模板总量已达上限")


def _resolve_industry_focus_keys(industry_focus: list[str]) -> list[str]:
    keys: list[str] = []
    for item in industry_focus:
        raw = str(item).strip()
        if raw.startswith("other:"):
            continue
        if raw in INDUSTRY_FOCUS_DEFAULT_DIMENSIONS:
            keys.append(raw)
    return keys or ["new_energy"]


def default_compliance_dimensions_for_profile(industry_focus: list[str]) -> list[str]:
    dims: list[str] = []
    for key in _resolve_industry_focus_keys(industry_focus):
        for dim in INDUSTRY_FOCUS_DEFAULT_DIMENSIONS.get(key, []):
            if dim in VALID_SCOPE_DIMENSIONS and dim not in dims:
                dims.append(dim)
    return dims or list(INDUSTRY_FOCUS_DEFAULT_DIMENSIONS["new_energy"])


def suggested_checklist_codes_for_profile(industry_focus: list[str]) -> list[str]:
    codes: list[str] = []
    for key in _resolve_industry_focus_keys(industry_focus):
        for code in INDUSTRY_FOCUS_SUGGESTED_CODES.get(key, []):
            if code not in codes:
                codes.append(code)
    return codes


def playbook_scope_hints(
    user_id: Optional[int],
    *,
    owner_email: Optional[str] = None,
    owner_auth_provider: Optional[str] = None,
    owner_external_subject: Optional[str] = None,
) -> dict[str, Any]:
    profile = profile_for_generation(
        user_id,
        owner_email=owner_email,
        owner_auth_provider=owner_auth_provider,
        owner_external_subject=owner_external_subject,
    )
    if not profile.get("completed"):
        return {
            "default_compliance_dimensions": [],
            "suggested_checklist_codes": [],
            "playbook_completed": False,
        }
    return {
        "default_compliance_dimensions": list(
            profile.get("default_compliance_dimensions")
            or default_compliance_dimensions_for_profile(profile.get("industry_focus") or ["new_energy"])
        ),
        "suggested_checklist_codes": list(
            profile.get("suggested_checklist_codes")
            or suggested_checklist_codes_for_profile(profile.get("industry_focus") or ["new_energy"])
        ),
        "playbook_completed": True,
        "risk_tolerance": profile.get("risk_tolerance"),
    }


def resolve_compliance_dimensions(
    selected: list[str] | None,
    *,
    user_id: Optional[int] = None,
    owner_email: Optional[str] = None,
    owner_auth_provider: Optional[str] = None,
    owner_external_subject: Optional[str] = None,
) -> list[str]:
    """Use explicit selection, else Playbook defaults, else empty (caller may fall back to all)."""
    if selected:
        return [d for d in selected if d in VALID_SCOPE_DIMENSIONS]
    hints = playbook_scope_hints(
        user_id,
        owner_email=owner_email,
        owner_auth_provider=owner_auth_provider,
        owner_external_subject=owner_external_subject,
    )
    return list(hints.get("default_compliance_dimensions") or [])


def get_playbook_profile(
    user_id: int,
    *,
    owner_email: Optional[str] = None,
    owner_auth_provider: Optional[str] = None,
    owner_external_subject: Optional[str] = None,
) -> dict[str, Any]:
    expected_binding = _owner_binding(
        user_id,
        owner_email=owner_email,
        owner_auth_provider=owner_auth_provider,
        owner_external_subject=owner_external_subject,
    )
    if expected_binding is None:
        return _profile_unavailable(user_id, "无法验证 Playbook 所属账号，已禁用该档案")
    path = _profile_path(user_id)
    if not path.exists():
        return _profile_unavailable(user_id, "尚未完成冷启动访谈，将使用平台默认 playbook")
    try:
        with open(path, encoding="utf-8") as f:
            profile = json.load(f)
    except (OSError, json.JSONDecodeError):
        return _profile_unavailable(user_id, "Playbook 档案不可验证，已禁用该档案")
    if profile.get("user_id") != user_id or profile.get("owner_binding") != expected_binding:
        return _profile_unavailable(user_id, "Playbook 所属账号不匹配，已禁用该档案")
    return profile


def is_onboarding_complete(
    user_id: int,
    *,
    owner_email: Optional[str] = None,
    owner_auth_provider: Optional[str] = None,
    owner_external_subject: Optional[str] = None,
) -> bool:
    profile = get_playbook_profile(
        user_id,
        owner_email=owner_email,
        owner_auth_provider=owner_auth_provider,
        owner_external_subject=owner_external_subject,
    )
    return bool(profile.get("completed"))


@synchronized_json_store
def start_interview(user_id: int) -> dict[str, Any]:
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("用户 ID 无效")
    script = load_interview_script()
    retained = _cleanup_expired_sessions()
    active_for_user = [
        (path, session)
        for path, session in retained
        if session.get("user_id") == user_id and session.get("status") == "in_progress"
    ]
    active_for_user.sort(
        key=lambda item: _session_activity(item[1], item[0]),
        reverse=True,
    )
    for stale_path, _ in active_for_user[MAX_ACTIVE_SESSIONS_PER_USER:]:
        _remove_session(stale_path)
    active_for_user = active_for_user[:MAX_ACTIVE_SESSIONS_PER_USER]
    if active_for_user:
        active_path, active = active_for_user[0]
        active["updated_at"] = _utcnow_iso()
        _assert_session_size(active)
        atomic_write_json(active_path, active)
        answers = active.get("answers") or {}
        main_question_ids = {
            question.get("id")
            for question in script.get("questions") or []
            if isinstance(question, dict)
        }
        completed = sum(
            1 for question_id in main_question_ids if question_id and answers.get(question_id)
        )
        return {
            "session_id": active["session_id"],
            "script": script,
            "completed_steps": completed,
            "total_steps": len(script.get("questions") or []),
        }

    if len(retained) >= MAX_SESSIONS_INSTANCE:
        raise ValueError("本实例的访谈会话数量已达上限，请稍后重试")
    session_id = str(uuid.uuid4())
    session = {
        "session_id": session_id,
        "user_id": user_id,
        "started_at": _utcnow_iso(),
        "answers": {},
        "uploaded_templates": [],
        "status": "in_progress",
    }
    _assert_session_size(session)
    atomic_write_json(_session_path(session_id), session)
    return {
        "session_id": session_id,
        "script": script,
        "completed_steps": 0,
        "total_steps": len(script.get("questions") or []),
    }


@synchronized_json_store
def submit_interview_answer(session_id: str, user_id: int, question_id: str, answer: Any) -> dict[str, Any]:
    path, session = _load_session(session_id, user_id)
    normalized = _normalize_answer(question_id, answer)
    answers = dict(session.get("answers") or {})
    answers[question_id] = normalized
    if len(answers) > MAX_INTERVIEW_ANSWER_KEYS:
        raise ValueError(f"访谈答案数量不能超过 {MAX_INTERVIEW_ANSWER_KEYS} 项")
    session["answers"] = answers
    session["updated_at"] = _utcnow_iso()
    _assert_session_size(session)
    atomic_write_json(path, session)
    script = load_interview_script()
    total = len(script.get("questions") or [])
    done = len(session.get("answers") or {})
    return {
        "session_id": session_id,
        "question_id": question_id,
        "completed_steps": done,
        "total_steps": total,
        "ready_to_complete": done >= total,
    }


@synchronized_json_store
def save_playbook_template(
    user_id: int,
    *,
    session_id: Optional[str],
    filename: str,
    content: bytes,
    purpose: Optional[str] = None,
    answer_updates: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    _validate_template_filename(filename)
    _assert_template_quota(user_id, len(content))
    normalized_purpose = str(purpose or "general")
    if answer_updates is not None and len(answer_updates) != 1:
        raise ValueError("附件一次只能写入一个解析目标")
    answer_target = next(iter(answer_updates), None) if answer_updates else None
    _validate_upload_binding(normalized_purpose, parse_into=answer_target)
    session_path: Optional[Path] = None
    session: Optional[dict[str, Any]] = None
    if session_id is not None:
        session_path, session = _load_session(session_id, user_id)

    user_dir = TEMPLATES_DIR / f"user_{user_id}"
    stored = f"{uuid.uuid4().hex[:12]}__{_safe_name(filename)}"
    path = user_dir / stored
    meta = {
        "id": stored,
        "original_name": filename,
        "size": len(content),
        "uploaded_at": _utcnow_iso(),
        "purpose": normalized_purpose,
    }
    if session is not None:
        session.setdefault("uploaded_templates", []).append(meta)
        session.setdefault("uploaded_files", []).append(meta)
        if answer_updates:
            normalized_updates = _normalize_answers(answer_updates)
            answers = dict(session.get("answers") or {})
            answers.update(normalized_updates)
            if len(answers) > MAX_INTERVIEW_ANSWER_KEYS:
                raise ValueError(f"访谈答案数量不能超过 {MAX_INTERVIEW_ANSWER_KEYS} 项")
            session["answers"] = answers
        session["updated_at"] = _utcnow_iso()
        _assert_session_size(session)
    elif answer_updates:
        raise ValueError("没有访谈会话时不能写入解析答案")

    atomic_write_bytes(path, content)
    if session_path is not None and session is not None:
        try:
            atomic_write_json(session_path, session)
        except Exception:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            raise
    return meta


@synchronized_json_store
def upload_interview_attachment(
    session_id: str,
    user_id: int,
    *,
    purpose: str,
    filename: str,
    content: bytes,
    parse: bool = True,
    parse_into: Optional[str] = None,
    merge_mode: str = "append",
) -> dict[str, Any]:
    """Upload interview attachment, optionally parse text into an answer field."""
    from app.services.document_extractor import read_upload_text

    _path, session = _load_session(session_id, user_id)
    _assert_template_quota(user_id, len(content))
    _validate_upload_binding(purpose, parse_into=parse_into, merge_mode=merge_mode)

    parsed_text = ""
    parse_error: Optional[str] = None
    if parse:
        try:
            parsed_text = read_upload_text(filename, content).strip()[:12000]
        except ValueError as exc:
            parse_error = str(exc)

    merged_value: Optional[str] = None
    if parse_into and parsed_text and not parse_error:
        answers = session.get("answers") or {}
        existing = str(answers.get(parse_into) or "").strip()
        if merge_mode == "append" and existing:
            candidate = f"{existing}\n\n--- 自上传文件：{filename} ---\n\n{parsed_text}"
        else:
            candidate = parsed_text
        normalized = _normalize_answer(parse_into, candidate)
        if not isinstance(normalized, str):
            raise ValueError("附件解析目标必须是文本问题")
        merged_value = normalized

    meta = save_playbook_template(
        user_id,
        session_id=session_id,
        filename=filename,
        content=content,
        purpose=purpose,
        answer_updates={parse_into: merged_value}
        if parse_into and merged_value is not None
        else None,
    )

    return {
        "meta": meta,
        "text": parsed_text,
        "preview": parsed_text[:500] if parsed_text else "",
        "parse_error": parse_error,
        "merged_field": parse_into,
        "merged_value": merged_value,
    }


@synchronized_json_store
def sync_interview_answers(session_id: str, user_id: int, answers: dict[str, Any]) -> dict[str, Any]:
    path, session = _load_session(session_id, user_id)
    normalized = _normalize_answers(answers)
    merged_answers = dict(session.get("answers") or {})
    merged_answers.update(normalized)
    if len(merged_answers) > MAX_INTERVIEW_ANSWER_KEYS:
        raise ValueError(f"访谈答案数量不能超过 {MAX_INTERVIEW_ANSWER_KEYS} 项")
    session["answers"] = merged_answers
    session["updated_at"] = _utcnow_iso()
    _assert_session_size(session)
    atomic_write_json(path, session)
    return {"session_id": session_id, "saved_keys": list(normalized.keys())}


@synchronized_json_store
def complete_interview(
    session_id: str,
    user_id: int,
    *,
    owner_email: str,
    owner_auth_provider: str,
    owner_external_subject: Optional[str],
) -> dict[str, Any]:
    path, session = _load_session(session_id, user_id)
    answers = _normalize_answers(session.get("answers") or {})
    session["answers"] = answers
    script = load_interview_script()
    required = [q["id"] for q in script.get("questions", []) if q.get("required")]
    missing = [q for q in required if not answers.get(q)]
    if missing:
        raise ValueError(f"尚有必填项未完成：{', '.join(missing)}")

    style = answers.get("brief_template_style", "law_firm_memo")
    uploaded = session.get("uploaded_files") or session.get("uploaded_templates") or []
    has_brief_sample = any(f.get("purpose") == "brief_template_sample" for f in uploaded)
    if style == "custom_sample" and not has_brief_sample:
        raise ValueError("选择「上传律所自有体例」时，请上传协查底稿样例文件")

    risk = answers.get("risk_tolerance", "conservative")
    threshold_adj = {"conservative": 5, "balanced": 0, "expedited": -5}.get(risk, 0)

    raw_industry = answers.get("industry_focus", ["new_energy"])
    if isinstance(raw_industry, list):
        industry_focus = [str(s).strip() for s in raw_industry if str(s).strip()]
    else:
        industry_focus = [s.strip() for s in str(raw_industry).split(",") if s.strip()]

    other_text = str(answers.get("industry_focus_other") or "").strip()
    if "other" in industry_focus:
        industry_focus = [x for x in industry_focus if x != "other"]
        if other_text:
            industry_focus.append(f"other:{other_text}")
        elif not industry_focus:
            raise ValueError("选择「其他」时请填写具体行业")

    if not industry_focus:
        industry_focus = ["new_energy"]

    profile = {
        "completed": True,
        "user_id": user_id,
        "profile_schema_version": PLAYBOOK_PROFILE_SCHEMA_VERSION,
        "profile_version": f"interview-{script.get('version') or 'unknown'}",
        "profile_source": "interview",
        "completed_at": _utcnow_iso(),
        "org_name": answers.get("org_name", ""),
        "primary_jurisdiction": answers.get("primary_jurisdiction", "brazil"),
        "industry_focus": industry_focus,
        "default_compliance_dimensions": default_compliance_dimensions_for_profile(industry_focus),
        "suggested_checklist_codes": suggested_checklist_codes_for_profile(industry_focus),
        "output_language": answers.get("output_language", "zh_pt_bilingual"),
        "risk_tolerance": risk,
        "match_threshold_adjustment": threshold_adj,
        "contract_house_rules": answers.get("contract_house_rules") or "",
        "brief_template_style": style,
        "brief_template_samples": [f for f in uploaded if f.get("purpose") == "brief_template_sample"],
        "interview_uploads": uploaded,
        "external_counsel_triggers": answers.get("external_counsel_threshold") or "",
        "uploaded_templates": session.get("uploaded_templates") or uploaded,
        "playbook_md": _build_playbook_md(answers, uploaded_files=uploaded),
    }
    profile = save_playbook_profile(
        user_id,
        profile,
        owner_email=owner_email,
        owner_auth_provider=owner_auth_provider,
        owner_external_subject=owner_external_subject,
    )
    session["status"] = "completed"
    session["completed_at"] = _utcnow_iso()
    session["updated_at"] = session["completed_at"]
    _assert_session_size(session)
    atomic_write_json(path, session)
    return profile


def _label_for_question(script: dict[str, Any], question_id: str, value: Any) -> str:
    for q in script.get("questions") or []:
        if q.get("id") != question_id:
            continue
        if isinstance(value, list):
            labels: list[str] = []
            for v in value:
                vstr = str(v)
                if vstr.startswith("other:"):
                    labels.append(f"其他（{vstr[6:]}）")
                    continue
                for opt in q.get("options") or []:
                    if isinstance(opt, dict) and opt.get("value") == v:
                        labels.append(str(opt.get("label") or v))
                        break
                else:
                    labels.append(vstr)
            return "、".join(labels)
        for opt in q.get("options") or []:
            if isinstance(opt, dict) and opt.get("value") == value:
                return str(opt.get("label") or value)
            if opt == value:
                return str(value)
        return str(value)
    return str(value)


def _normalize_industry_for_display(answers: dict[str, Any]) -> list[str]:
    raw = answers.get("industry_focus", [])
    if isinstance(raw, list):
        items = [str(s).strip() for s in raw if str(s).strip()]
    else:
        items = [s.strip() for s in str(raw).split(",") if s.strip()]
    other_text = str(answers.get("industry_focus_other") or "").strip()
    if "other" in items:
        items = [x for x in items if x != "other"]
        if other_text:
            items.append(f"other:{other_text}")
    return items or ["new_energy"]


def _build_playbook_md(answers: dict[str, Any], *, uploaded_files: Optional[list[dict[str, Any]]] = None) -> str:
    script = load_interview_script()
    org = answers.get("org_name", "法务团队")
    jurisdiction = _label_for_question(script, "primary_jurisdiction", answers.get("primary_jurisdiction", "brazil"))
    industry = _label_for_question(
        script,
        "industry_focus",
        _normalize_industry_for_display(answers),
    )
    output = _label_for_question(script, "output_language", answers.get("output_language", "zh_pt_bilingual"))
    risk = _label_for_question(script, "risk_tolerance", answers.get("risk_tolerance", "conservative"))
    style = _label_for_question(script, "brief_template_style", answers.get("brief_template_style", "law_firm_memo"))
    uploads_note = ""
    files = uploaded_files or []
    contract_files = [f.get("original_name") for f in files if f.get("purpose") == "contract_house_rules"]
    brief_files = [f.get("original_name") for f in files if f.get("purpose") == "brief_template_sample"]
    if contract_files:
        uploads_note += f"\n- 合同底线附件：{', '.join(contract_files)}"
    if brief_files:
        uploads_note += f"\n- 底稿样例：{', '.join(brief_files)}"
    return (
        f"# {org} · Vela Playbook Profile\n\n"
        f"- 法域：{jurisdiction}\n"
        f"- 行业：{industry}\n"
        f"- 输出：{output}\n"
        f"- 门控：{risk}\n"
        f"- 底稿风格：{style}{uploads_note}\n\n"
        f"## 合同审查底线\n{answers.get('contract_house_rules') or '（未填写，使用平台默认）'}\n\n"
        f"## 外聘律师触发\n{answers.get('external_counsel_threshold') or 'S3 硬阻断项；零命中高优先级核查项'}\n"
    )


def profile_for_generation(
    user_id: Optional[int],
    *,
    owner_email: Optional[str] = None,
    owner_auth_provider: Optional[str] = None,
    owner_external_subject: Optional[str] = None,
) -> dict[str, Any]:
    if not user_id:
        return {"match_threshold_adjustment": 0, "contract_house_rules": "", "completed": False}
    p = get_playbook_profile(
        user_id,
        owner_email=owner_email,
        owner_auth_provider=owner_auth_provider,
        owner_external_subject=owner_external_subject,
    )
    if not p.get("completed"):
        return {"match_threshold_adjustment": 0, "contract_house_rules": "", "completed": False}
    return p
