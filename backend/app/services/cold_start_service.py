"""Cold-start interview + playbook profile (Claude for Legal pattern)."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

INTERVIEW_PATH = Path(__file__).resolve().parents[1] / "data" / "cold_start_interview.json"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PROFILES_DIR = DATA_DIR / "playbook_profiles"
TEMPLATES_DIR = DATA_DIR / "playbook_templates"
SESSIONS_DIR = DATA_DIR / "interview_sessions"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w.\-]", "_", name or "template")[:120]


def load_interview_script() -> dict[str, Any]:
    with open(INTERVIEW_PATH, encoding="utf-8") as f:
        return json.load(f)


def _profile_path(user_id: int) -> Path:
    return PROFILES_DIR / f"user_{user_id}.json"


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def get_playbook_profile(user_id: int) -> dict[str, Any]:
    path = _profile_path(user_id)
    if not path.exists():
        return {
            "completed": False,
            "user_id": user_id,
            "message": "尚未完成冷启动访谈，将使用平台默认 playbook",
        }
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def is_onboarding_complete(user_id: int) -> bool:
    profile = get_playbook_profile(user_id)
    return bool(profile.get("completed"))


def start_interview(user_id: int) -> dict[str, Any]:
    script = load_interview_script()
    session_id = str(uuid.uuid4())
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session = {
        "session_id": session_id,
        "user_id": user_id,
        "started_at": _utcnow_iso(),
        "answers": {},
        "uploaded_templates": [],
        "status": "in_progress",
    }
    with open(_session_path(session_id), "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)
    return {
        "session_id": session_id,
        "script": script,
        "completed_steps": 0,
        "total_steps": len(script.get("questions") or []),
    }


def submit_interview_answer(session_id: str, user_id: int, question_id: str, answer: Any) -> dict[str, Any]:
    path = _session_path(session_id)
    if not path.exists():
        raise ValueError("访谈会话不存在或已过期")
    with open(path, encoding="utf-8") as f:
        session = json.load(f)
    if session.get("user_id") != user_id:
        raise ValueError("无权访问该访谈会话")
    session.setdefault("answers", {})[question_id] = answer
    session["updated_at"] = _utcnow_iso()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)
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


def save_playbook_template(
    user_id: int,
    *,
    session_id: Optional[str],
    filename: str,
    content: bytes,
    purpose: Optional[str] = None,
) -> dict[str, Any]:
    user_dir = TEMPLATES_DIR / f"user_{user_id}"
    user_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex[:12]}__{_safe_name(filename)}"
    path = user_dir / stored
    path.write_bytes(content)
    meta = {
        "id": stored,
        "original_name": filename,
        "stored_path": str(path),
        "size": len(content),
        "uploaded_at": _utcnow_iso(),
        "purpose": purpose or "general",
    }
    if session_id:
        sp = _session_path(session_id)
        if sp.exists():
            with open(sp, encoding="utf-8") as f:
                session = json.load(f)
            if session.get("user_id") == user_id:
                session.setdefault("uploaded_templates", []).append(meta)
                session.setdefault("uploaded_files", []).append(meta)
                with open(sp, "w", encoding="utf-8") as f:
                    json.dump(session, f, ensure_ascii=False, indent=2)
    return meta


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

    path = _session_path(session_id)
    if not path.exists():
        raise ValueError("访谈会话不存在或已过期")
    with open(path, encoding="utf-8") as f:
        session = json.load(f)
    if session.get("user_id") != user_id:
        raise ValueError("无权访问该访谈会话")

    parsed_text = ""
    parse_error: Optional[str] = None
    if parse:
        try:
            parsed_text = read_upload_text(filename, content).strip()[:12000]
        except ValueError as exc:
            parse_error = str(exc)

    meta = save_playbook_template(
        user_id,
        session_id=session_id,
        filename=filename,
        content=content,
        purpose=purpose,
    )

    merged_value: Optional[str] = None
    if parse_into and parsed_text and not parse_error:
        answers = session.setdefault("answers", {})
        existing = str(answers.get(parse_into) or "").strip()
        if merge_mode == "append" and existing:
            merged_value = f"{existing}\n\n--- 自上传文件：{filename} ---\n\n{parsed_text}"
        else:
            merged_value = parsed_text
        answers[parse_into] = merged_value
        session["updated_at"] = _utcnow_iso()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session, f, ensure_ascii=False, indent=2)

    return {
        "meta": meta,
        "text": parsed_text,
        "preview": parsed_text[:500] if parsed_text else "",
        "parse_error": parse_error,
        "merged_field": parse_into,
        "merged_value": merged_value,
    }


def sync_interview_answers(session_id: str, user_id: int, answers: dict[str, Any]) -> dict[str, Any]:
    path = _session_path(session_id)
    if not path.exists():
        raise ValueError("访谈会话不存在或已过期")
    with open(path, encoding="utf-8") as f:
        session = json.load(f)
    if session.get("user_id") != user_id:
        raise ValueError("无权访问该访谈会话")
    session.setdefault("answers", {}).update(answers)
    session["updated_at"] = _utcnow_iso()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)
    return {"session_id": session_id, "saved_keys": list(answers.keys())}


def complete_interview(session_id: str, user_id: int) -> dict[str, Any]:
    path = _session_path(session_id)
    if not path.exists():
        raise ValueError("访谈会话不存在")
    with open(path, encoding="utf-8") as f:
        session = json.load(f)
    if session.get("user_id") != user_id:
        raise ValueError("无权完成该访谈")
    answers = session.get("answers") or {}
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
        "completed_at": _utcnow_iso(),
        "org_name": answers.get("org_name", ""),
        "primary_jurisdiction": answers.get("primary_jurisdiction", "brazil"),
        "industry_focus": industry_focus,
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
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    with open(_profile_path(user_id), "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    session["status"] = "completed"
    session["completed_at"] = _utcnow_iso()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)
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


def profile_for_generation(user_id: Optional[int]) -> dict[str, Any]:
    if not user_id:
        return {"match_threshold_adjustment": 0, "contract_house_rules": "", "completed": False}
    p = get_playbook_profile(user_id)
    if not p.get("completed"):
        return {"match_threshold_adjustment": 0, "contract_house_rules": "", "completed": False}
    return p
