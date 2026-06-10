"""Playbook agent: auto-generate checklist from scenario + user profile."""

from __future__ import annotations

from typing import Any, Optional

from app.services.cold_start_service import playbook_scope_hints, profile_for_generation
from app.services.rule_engine import ScenarioInput, generate_checklist


def generate_playbook_draft(
    scenario: ScenarioInput,
    *,
    user_id: Optional[int] = None,
    pack_id: str | None = None,
    include_playbook_suggestions: bool = False,
    extra_checklist_codes: set[str] | None = None,
) -> dict[str, Any]:
    """Rules engine draft + profile overlay (no manual JSON editing per run)."""
    profile = profile_for_generation(user_id)
    extra_codes: set[str] = set(extra_checklist_codes or [])
    if include_playbook_suggestions and profile.get("completed"):
        extra_codes |= set(profile.get("suggested_checklist_codes") or [])
    checklist = generate_checklist(
        scenario,
        pack_id,
        extra_codes_from_playbook=extra_codes or None,
    )

    hints = playbook_scope_hints(user_id)
    checklist["playbook_suggestions"] = {
        "checklist_codes": hints.get("suggested_checklist_codes") or [],
        "default_compliance_dimensions": hints.get("default_compliance_dimensions") or [],
        "included_in_checklist": bool(include_playbook_suggestions),
    }

    if profile.get("completed"):
        focus = set(profile.get("industry_focus") or [])
        if focus and scenario.industry not in focus and "new_energy" in focus:
            checklist.setdefault("agent_notes", []).append(
                f"Playbook 行业偏好 {', '.join(focus)}；当前场景 industry={scenario.industry}"
            )
        checklist["playbook_profile"] = {
            "org_name": profile.get("org_name"),
            "risk_tolerance": profile.get("risk_tolerance"),
            "brief_template_style": profile.get("brief_template_style"),
            "match_threshold_adjustment": profile.get("match_threshold_adjustment"),
        }

    checklist["generation_mode"] = "playbook_agent_v1"
    checklist["agent_steps"] = [
        {"step": "detect_industry_action", "status": "ok"},
        {"step": "rule_engine_checklist", "status": "ok", "items": checklist.get("total_items", 0)},
        {"step": "profile_overlay", "status": "ok" if profile.get("completed") else "skipped"},
    ]
    return checklist
