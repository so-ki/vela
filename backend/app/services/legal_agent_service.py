"""Investigation agent: retrieve → validate → tier → quality (Legal-Skills workflow)."""

from __future__ import annotations

from typing import Any, Optional

from app.core.config import get_settings
from app.services.brazil_connector_service import connector_retrieve_for_sections
from app.services.cold_start_service import profile_for_generation
from app.services.grounding_verifier_service import verify_sections_grounding
from app.services.legal_rag import retrieve_for_checklist
from app.services.llm_client import llm_status
from app.services.match_tier_service import classify_sections
from app.services.project_hub_service import apply_profile_threshold
from app.services.quality_reports_service import attach_quality_reports
from app.services.user_preference_service import get_retrieval_preferences, resolve_retrieval_top_k


def run_investigation_agent(
    sections: list[dict[str, Any]],
    *,
    match_threshold: int = 70,
    retrieval_top_k: Optional[int] = None,
    expansion_context: str = "",
    user_id: Optional[int] = None,
    polish: bool = False,
    brief_input: Optional[dict[str, Any]] = None,
    state: Optional[str] = None,
    use_brazil_connector: bool = True,
) -> dict[str, Any]:
    """Orchestrate RAG + grounding + tier classification + verification passes."""
    prefs = get_retrieval_preferences(user_id)
    profile = profile_for_generation(user_id)
    effective_threshold = apply_profile_threshold(
        int(prefs.get("match_threshold") or match_threshold),
        profile,
    )
    effective_top_k = resolve_retrieval_top_k(user_id, retrieval_top_k)

    if use_brazil_connector:
        retrieval = connector_retrieve_for_sections(
            sections,
            state=state,
            match_threshold=effective_threshold,
            top_k=effective_top_k,
        )
    else:
        retrieval = retrieve_for_checklist(
            sections,
            top_k=effective_top_k,
            match_threshold=effective_threshold,
            expansion_context=expansion_context,
        )
    enriched = retrieval["sections"]

    grounding = verify_sections_grounding(enriched)
    grounded_sections = grounding.get("sections") or enriched
    tiered = classify_sections(
        grounded_sections,
        base_threshold=effective_threshold,
        grounding_report=grounding,
        user_threshold_adjustments=prefs.get("code_adjustments"),
    )

    payload: dict[str, Any] = {
        "sections_with_legal": tiered["sections"],
        "retrieval": {
            "total_hits": retrieval.get("total_hits", 0),
            "zero_hit_items": retrieval.get("zero_hit_items", []),
            "disclaimer": retrieval.get("disclaimer", ""),
            "connector_runs": retrieval.get("connector_runs"),
            "brazil_connector": use_brazil_connector,
        },
        "grounding_report": grounding,
        "tier_report": tiered["tier_summary"],
        "match_threshold": effective_threshold,
        "requested_threshold": match_threshold,
        "retrieval_top_k": effective_top_k,
        "requested_retrieval_top_k": retrieval_top_k,
        "user_preferences_applied": bool(user_id and prefs.get("code_adjustments")),
        "agent_steps": [
            {"step": "retrieve", "status": "ok", "connector": use_brazil_connector},
            {"step": "grounding", "status": "ok" if not grounding.get("requires_legal_check") else "review"},
            {
                "step": "tier_classify",
                "status": "blocked" if tiered["tier_summary"].get("has_hard_block") else "ok",
                "S1": tiered["tier_summary"].get("S1", 0),
                "S2": tiered["tier_summary"].get("S2", 0),
                "S3": tiered["tier_summary"].get("S3", 0),
            },
        ],
    }

    if brief_input is not None:
        payload.update(brief_input)
        payload = attach_quality_reports(payload, brief_input.get("brief"))

    llm = llm_status()
    payload["llm_config"] = {
        **llm,
        "polish_enabled": get_settings().llm_polish_enabled and llm.get("available"),
        "polish_requested": polish,
    }
    return payload


def s3_blocking_message(tier_report: dict[str, Any] | None) -> Optional[str]:
    if not tier_report or not tier_report.get("has_hard_block"):
        return None
    codes = tier_report.get("s3_codes") or []
    shown = ", ".join(codes[:6])
    extra = f" 等 {len(codes)} 条" if len(codes) > 6 else ""
    return (
        f"存在 S3 硬阻断条目（{shown}{extra}）：高优先级且无可靠法条支撑。"
        "须补充材料、调整检索或经法务逐项确认后再进入复核/定稿。"
    )
