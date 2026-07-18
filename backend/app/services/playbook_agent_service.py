"""Playbook agent: auto-generate checklist from scenario + user profile."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.rule_engine import ScenarioInput, generate_checklist
from app.services.generation_guard import GenerationConfig, require_generation_config


def generate_playbook_draft(
    db: Session,
    scenario: ScenarioInput,
    *,
    user_id: Optional[int] = None,
    pack_id: str | None = None,
    include_playbook_suggestions: bool = False,
    extra_checklist_codes: set[str] | None = None,
    generation_config: GenerationConfig | None = None,
) -> dict[str, Any]:
    """Rules engine draft + profile overlay (no manual JSON editing per run)."""
    config = require_generation_config(db, generation_config)
    if (
        (pack_id and pack_id != config.rules_pack_id)
        or include_playbook_suggestions != config.include_playbook_suggestions
        or set(extra_checklist_codes or set()) - set(config.selected_issue_codes)
    ):
        raise ValueError("Playbook 参数与冻结配置不一致")
    extra_codes: set[str] = set(config.selected_issue_codes)
    extra_codes |= set(extra_checklist_codes or [])
    if config.include_playbook_suggestions:
        extra_codes |= set(config.playbook_suggestion_codes)
    checklist = generate_checklist(
        db,
        scenario,
        pack_id,
        extra_codes_from_playbook=extra_codes or None,
        generation_config=config,
    )
    checklist["playbook_suggestions"] = {
        "checklist_codes": list(config.playbook_suggestion_codes),
        "default_compliance_dimensions": list(config.compliance_dimensions),
        "included_in_checklist": config.include_playbook_suggestions,
    }
    checklist["playbook_profile"] = {"profile_hash": config.profile_hash, "frozen": True}

    checklist["generation_mode"] = "playbook_agent_v1"
    checklist["agent_steps"] = [
        {"step": "detect_industry_action", "status": "ok"},
        {"step": "rule_engine_checklist", "status": "ok", "items": checklist.get("total_items", 0)},
        {"step": "profile_overlay", "status": "frozen" if config.include_playbook_suggestions else "disabled"},
    ]
    return checklist
