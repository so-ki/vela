"""End-to-end scenario pipelines for business submit and legal review prep."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.scenario import InvestigationScenario
from app.models.user import User
from app.schemas.scenario import BusinessSubmitRequest, ScenarioCreateRequest
from app.services.audit import write_audit_log
from app.services.brief_generator import generate_brief
from app.services.legal_ingest import ingest_corpus
from app.services.conflict_detection_service import detect_material_conflicts
from app.services.legal_monitor import upsert_scenario_subscription
from app.services.quality_reports_service import attach_quality_reports
from app.services.legal_agent_service import run_investigation_agent
from app.services.user_preference_service import (
    record_dimension_selection,
    record_match_threshold_choice,
    record_retrieval_top_k_choice,
)
from app.services.investigation_adequacy_service import aggregate_investigation_adequacy
from app.services.incremental_investigation_service import (
    can_run_incremental,
    run_incremental_investigation_attach,
)
from app.services.material_review_service import (
    build_material_return_record,
)
from app.services.material_file_storage import save_scenario_material_files
from app.services.cold_start_service import playbook_scope_hints, resolve_compliance_dimensions
from app.services.rule_engine import get_material_field_labels
from app.services.scenario_service import (
    _materials_only_payload,
    attach_document_extract_to_payload,
    merge_business_resubmit_request,
    create_scenario_materials_only,
    create_scenario_with_checklist,
    regenerate_scenario_checklist,
    scenario_to_create_request,
)


def _expansion_context(scenario: InvestigationScenario) -> str:
    parts = [
        scenario.description or "",
        scenario.project_content_scale or "",
        scenario.known_risks or "",
        scenario.investment_structure or "",
        scenario.facility_notes or "",
        scenario.capacity_notes or "",
    ]
    return " ".join(p for p in parts if p)[:1200]


def _attach_legal_and_brief(
    scenario: InvestigationScenario,
    payload: dict[str, Any],
    *,
    polish: bool,
    match_threshold: int = 70,
    retrieval_top_k: Optional[int] = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    ingest_corpus(force=False)
    agent_result = run_investigation_agent(
        payload.get("sections", []),
        match_threshold=match_threshold,
        retrieval_top_k=retrieval_top_k,
        expansion_context=_expansion_context(scenario),
        user_id=user_id,
        polish=False,
        state=scenario.state,
        use_brazil_connector=True,
    )
    sections = agent_result["sections_with_legal"]
    payload = {
        **payload,
        "sections_with_legal": sections,
        "legal_retrieved": True,
        "grounding_report": agent_result.get("grounding_report"),
        "tier_report": agent_result.get("tier_report"),
        "agent_steps": agent_result.get("agent_steps"),
        "retrieval_meta": agent_result.get("retrieval"),
    }
    scenario.checklist.payload = payload

    brief = generate_brief(
        scenario,
        payload,
        sections_with_legal=sections,
        polish=polish,
        threshold=match_threshold,
    )
    payload = {**payload, "brief": brief}
    payload = attach_quality_reports(
        payload,
        sections_with_legal=sections,
        brief=brief,
    )
    payload["conflict_flags"] = detect_material_conflicts(scenario, payload)
    payload["investigation_settings"] = {
        "match_threshold": agent_result.get("match_threshold", match_threshold),
        "retrieval_top_k": agent_result.get("retrieval_top_k", retrieval_top_k or 3),
        "expansion_enabled": True,
        "tier_policy": agent_result.get("tier_policy"),
    }
    payload["llm_config"] = agent_result.get("llm_config")
    scenario.checklist.payload = payload
    scenario.status = "brief_generated" if brief["status"] != "blocked" else "brief_blocked"
    return payload


def run_business_submit_materials(
    db: Session,
    user: User,
    payload: BusinessSubmitRequest,
    *,
    uploads: list[tuple[str, bytes, str | None]] | None = None,
) -> InvestigationScenario:
    """业务：上传/填写项目材料，提交法务确认协查范围（不生成清单）。"""
    return create_scenario_materials_only(db, user, payload, uploads=uploads)


def run_generate_investigation_pack(
    db: Session,
    user: User,
    scenario: InvestigationScenario,
    compliance_dimensions: list[str],
    *,
    polish: bool = False,
    match_threshold: int = 70,
    retrieval_top_k: Optional[int] = None,
    include_playbook_suggestions: bool = False,
) -> InvestigationScenario:
    """法务：选定协查维度并一次生成清单、法源检索、匹配度与简报，进入统一复核。"""
    if scenario.status != "pending_scope":
        raise ValueError("当前状态不可生成协查包，请确认项目处于待生成协查阶段")

    resolved_dimensions = resolve_compliance_dimensions(compliance_dimensions, user_id=user.id)
    if not resolved_dimensions:
        resolved_dimensions = list(scenario.compliance_dimensions or [])
    if not resolved_dimensions:
        raise ValueError("请至少选择一个协查维度，或完成 Playbook 冷启动以使用默认维度")

    old_payload = copy.deepcopy(scenario.checklist.payload if scenario.checklist else {})
    document_extract = old_payload.get("document_extract")
    revision_history = list(old_payload.get("revision_history") or [])
    revision_round = int(old_payload.get("revision_round") or 0)
    material_review_old = dict(old_payload.get("material_review") or {})
    draft_history = list(old_payload.get("investigation_draft_history") or [])
    use_incremental = can_run_incremental(old_payload, material_review_old)
    previous_pack = draft_history[-1] if use_incremental else None

    base = scenario_to_create_request(scenario)
    request = base.model_copy(update={"compliance_dimensions": resolved_dimensions})
    regenerate_scenario_checklist(
        db,
        scenario,
        request,
        include_playbook_suggestions=include_playbook_suggestions,
    )

    checklist_payload = scenario.checklist.payload if scenario.checklist else {}
    if document_extract:
        checklist_payload = {**checklist_payload, "document_extract": document_extract}
    checklist_payload.pop("materials_only", None)

    if revision_history:
        checklist_payload["revision_history"] = revision_history
        checklist_payload["revision_round"] = revision_round

    incremental_meta: dict[str, Any] | None = None
    if use_incremental and previous_pack:
        checklist_payload, incremental_meta = run_incremental_investigation_attach(
            scenario,
            checklist_payload,
            previous_pack,
            compliance_dimensions=resolved_dimensions,
            baseline_snapshot=material_review_old["return_baseline_snapshot"],
            returned_missing_elements=list(material_review_old.get("returned_missing_elements") or []),
            polish=polish,
            match_threshold=match_threshold,
            retrieval_top_k=retrieval_top_k,
            reviewer_name=user.full_name,
            reviewer_id=user.id,
        )
        scenario.checklist.payload = checklist_payload
        scenario.status = (
            "brief_generated"
            if (checklist_payload.get("brief") or {}).get("status") != "blocked"
            else "brief_blocked"
        )
    else:
        checklist_payload = _attach_legal_and_brief(
            scenario,
            checklist_payload,
            polish=polish,
            match_threshold=match_threshold,
            retrieval_top_k=retrieval_top_k,
            user_id=user.id,
        )
        adequacy = aggregate_investigation_adequacy(scenario, checklist_payload, resolved_dimensions)
        checklist_payload["investigation_adequacy"] = adequacy
        checklist_payload.pop("review", None)

    material_review = dict(material_review_old)
    material_review.update(
        {
            "selected_dimensions": resolved_dimensions,
            "status": "investigation_generated",
            "match_threshold": match_threshold,
            "retrieval_top_k": (checklist_payload.get("investigation_settings") or {}).get("retrieval_top_k")
            or retrieval_top_k
            or 3,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": user.full_name,
            "generated_by_id": user.id,
            "field_labels": get_material_field_labels(),
            "element_labels": (checklist_payload.get("investigation_adequacy") or {}).get("element_labels")
            or {},
        }
    )
    material_review.pop("return_baseline_snapshot", None)
    material_review.pop("returned_missing_elements", None)
    material_review.pop("returned_missing_fields", None)
    checklist_payload["material_review"] = material_review
    if incremental_meta:
        checklist_payload["incremental_regen"] = incremental_meta
    if draft_history:
        checklist_payload["investigation_draft_history"] = draft_history

    record_match_threshold_choice(user.id, match_threshold)
    effective_top_k = int((checklist_payload.get("investigation_settings") or {}).get("retrieval_top_k") or retrieval_top_k or 3)
    record_retrieval_top_k_choice(user.id, effective_top_k)
    record_dimension_selection(user.id, resolved_dimensions)
    scenario.status = "pending_legal_review"
    scenario.compliance_dimensions = resolved_dimensions
    scenario.checklist.payload = copy.deepcopy(checklist_payload)
    flag_modified(scenario.checklist, "payload")
    db.commit()
    db.refresh(scenario)

    try:
        upsert_scenario_subscription(scenario.id, scenario.project_name, checklist_payload)
    except Exception:
        pass

    brief = checklist_payload.get("brief") or {}
    mode_note = ""
    if incremental_meta:
        mode_note = (
            f"；增量更新 {len(incremental_meta.get('target_codes') or [])} 条，"
            f"沿用 {len(incremental_meta.get('frozen_codes') or [])} 条"
        )
    write_audit_log(
        db,
        user=user,
        action="scenario.generate_investigation",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=(
            f"法务生成协查包：{scenario.project_name}；"
            f"维度 {', '.join(resolved_dimensions)}；"
            f"通过 {brief.get('passed_count', 0)} 条，需复核 {brief.get('blocked_count', 0)} 条"
            f"{mode_note}"
        ),
    )
    return scenario


def run_confirm_scope_and_generate(
    db: Session,
    user: User,
    scenario: InvestigationScenario,
    compliance_dimensions: list[str],
    *,
    polish: bool = False,
) -> InvestigationScenario:
    """兼容旧接口：等同 run_generate_investigation_pack。"""
    return run_generate_investigation_pack(
        db, user, scenario, compliance_dimensions, polish=polish
    )


def run_generate_and_submit(
    db: Session,
    user: User,
    payload: ScenarioCreateRequest,
    *,
    polish: bool = False,
) -> InvestigationScenario:
    """法务/演示：场景 → 清单 → 法源 → 简报 → 提交法务复核（保留兼容）。"""
    scenario = create_scenario_with_checklist(db, user, payload)
    checklist_payload = attach_document_extract_to_payload(scenario.checklist.payload, payload)
    scenario.checklist.payload = checklist_payload
    checklist_payload = _attach_legal_and_brief(scenario, checklist_payload, polish=polish)

    dims = list(payload.compliance_dimensions or [])
    if dims:
        adequacy = aggregate_investigation_adequacy(scenario, checklist_payload, dims)
        checklist_payload["investigation_adequacy"] = adequacy

    scenario.status = "pending_legal_review"
    scenario.checklist.payload = copy.deepcopy(checklist_payload)
    flag_modified(scenario.checklist, "payload")
    db.commit()
    db.refresh(scenario)

    brief = checklist_payload.get("brief") or {}
    write_audit_log(
        db,
        user=user,
        action="scenario.generate_and_submit",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=(
            f"一键提交法务：{scenario.project_name}；"
            f"通过 {brief.get('passed_count', 0)} 条，需复核 {brief.get('blocked_count', 0)} 条"
        ),
    )
    return scenario


MATERIAL_RETURN_STATUSES = frozenset(
    {
        "pending_scope",
        "pending_legal_review",
        "review_in_progress",
        "brief_generated",
        "brief_blocked",
    }
)


def _archive_investigation_draft(
    payload: dict[str, Any],
    *,
    field_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "brief": payload.get("brief"),
        "sections": payload.get("sections"),
        "sections_with_legal": payload.get("sections_with_legal"),
        "investigation_adequacy": payload.get("investigation_adequacy"),
        "review": payload.get("review"),
        "selected_dimensions": payload.get("selected_dimensions"),
        "total_items": payload.get("total_items"),
        "field_snapshot": field_snapshot,
        "incremental_regen": payload.get("incremental_regen"),
    }


def _reset_payload_after_material_return(
    payload: dict[str, Any],
    create_req: ScenarioCreateRequest,
) -> dict[str, Any]:
    materials_payload = _materials_only_payload(create_req)
    for key in (
        "document_extract",
        "revision_history",
        "revision_round",
        "material_review",
        "investigation_draft_history",
    ):
        if key in payload:
            materials_payload[key] = payload[key]
    return materials_payload


def run_return_materials(
    db: Session,
    user: User,
    scenario: InvestigationScenario,
    compliance_dimensions: list[str],
    missing_fields: list[str] | None = None,
    *,
    missing_elements: list[str] | None = None,
    note: str | None = None,
) -> InvestigationScenario:
    """法务驳回业务材料（构成要件/字段）；未定稿前均可打回，已生成协查包会归档草稿。"""
    if scenario.status not in MATERIAL_RETURN_STATUSES:
        raise ValueError("当前状态不可打回补充材料")

    payload = copy.deepcopy(scenario.checklist.payload or {})
    review = payload.get("review") or {}
    if review.get("status") in ("approved", "partial", "rejected"):
        raise ValueError("协查已定稿，无法再打回补充材料")

    if not scenario.checklist:
        raise ValueError("场景缺少核查清单")

    had_investigation = bool(payload.get("brief"))
    if had_investigation:
        from app.services.material_review_service import scenario_field_snapshot

        archive = _archive_investigation_draft(
            payload,
            field_snapshot=scenario_field_snapshot(scenario),
        )
        history = list(payload.get("investigation_draft_history") or [])
        history.append(archive)
        payload["investigation_draft_history"] = history

    material_review = build_material_return_record(
        scenario,
        user,
        compliance_dimensions=compliance_dimensions,
        missing_fields=missing_fields,
        missing_elements=missing_elements,
        note=note,
    )
    payload["material_review"] = material_review

    if had_investigation:
        create_req = scenario_to_create_request(scenario)
        payload = _reset_payload_after_material_return(payload, create_req)
        scenario.compliance_dimensions = []
        if scenario.checklist:
            scenario.checklist.title = payload["title"]
            scenario.checklist.total_items = 0

    payload.pop("brief", None)
    payload.pop("sections_with_legal", None)
    payload.pop("investigation_adequacy", None)
    payload.pop("review", None)
    payload.pop("sections", None)
    payload.pop("legal_retrieved", None)
    payload.pop("selected_dimensions", None)

    scenario.status = "returned_for_revision"
    scenario.checklist.payload = payload
    flag_modified(scenario.checklist, "payload")
    db.commit()
    db.refresh(scenario)

    write_audit_log(
        db,
        user=user,
        action="scenario.return_materials",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=(
            f"法务驳回提交表：{scenario.project_name}；"
            f"维度 {', '.join(compliance_dimensions)}；"
            f"缺项 {', '.join(material_review.get('missing_elements') or missing_fields or [])}"
        ),
    )
    return scenario


def run_revise_and_resubmit(
    db: Session,
    user: User,
    scenario: InvestigationScenario,
    payload: BusinessSubmitRequest,
    *,
    uploads: list[tuple[str, bytes, str | None]] | None = None,
) -> InvestigationScenario:
    """业务在同一项目补充材料后重新提交，待法务再次确认协查范围。"""
    if scenario.status != "returned_for_revision":
        raise ValueError("当前状态不可补充提交，请确认法务已退回该项目")

    old_payload = copy.deepcopy(scenario.checklist.payload if scenario.checklist else {})
    old_material = old_payload.get("material_review") or {}
    revision_history = list(old_payload.get("revision_history") or [])
    material_history = list(old_material.get("history") or [])

    if old_material.get("status") == "returned" and old_material.get("return_kind") == "materials":
        material_history.append(
            {
                "round": len(material_history) + 1,
                "returned_at": old_material.get("returned_at"),
                "return_note": old_material.get("return_note"),
                "missing_fields": list(old_material.get("missing_fields") or []),
                "submitted_snapshot": old_material.get("submitted_snapshot"),
            }
        )
    else:
        revision_round = len(revision_history) + 1
        revision_history.append(
            {
                "round": revision_round,
                "returned_at": old_payload.get("review", {}).get("returned_at"),
                "return_note": old_payload.get("review", {}).get("return_note"),
                "review": old_payload.get("review"),
                "description_snapshot": scenario.description,
                "compliance_dimensions": list(scenario.compliance_dimensions or []),
            }
        )

    create_req = merge_business_resubmit_request(scenario, payload)
    scenario.project_name = create_req.project_name
    scenario.country = create_req.country
    scenario.state = create_req.state
    scenario.city = create_req.city
    scenario.industry = create_req.industry
    scenario.action_type = create_req.action_type
    scenario.investment_structure = create_req.investment_structure
    scenario.investment_destination = create_req.investment_destination
    scenario.project_content_scale = create_req.project_content_scale
    scenario.funding_source = create_req.funding_source
    scenario.description = create_req.description
    scenario.known_risks = create_req.known_risks
    scenario.employee_count = create_req.employee_count
    scenario.capacity_notes = create_req.capacity_notes
    scenario.facility_notes = create_req.facility_notes
    scenario.compliance_dimensions = []
    scenario.board_date = create_req.board_date
    scenario.start_date = create_req.start_date
    scenario.production_date = create_req.production_date
    scenario.remarks = create_req.remarks
    scenario.status = "pending_scope"

    materials_payload = _materials_only_payload(create_req)
    materials_payload = attach_document_extract_to_payload(materials_payload, create_req)

    old_doc = old_payload.get("document_extract") or {}
    archived_files = list(old_doc.get("archived_files") or [])
    if uploads:
        archived_files.extend(save_scenario_material_files(scenario.id, uploads))
    if archived_files:
        doc = dict(materials_payload.get("document_extract") or {})
        doc["archived_files"] = archived_files
        materials_payload["document_extract"] = doc

    materials_payload["revision_history"] = revision_history
    materials_payload["revision_round"] = len(revision_history)

    selected_dimensions = list(old_material.get("selected_dimensions") or [])
    return_baseline_snapshot = old_material.get("submitted_snapshot")
    returned_missing_elements = list(old_material.get("missing_elements") or [])
    returned_missing_fields = list(old_material.get("missing_fields") or [])
    investigation_draft_history = list(old_payload.get("investigation_draft_history") or [])

    if selected_dimensions or material_history or return_baseline_snapshot:
        materials_payload["material_review"] = {
            "selected_dimensions": selected_dimensions,
            "status": "resubmitted",
            "revision_round": len(material_history),
            "history": material_history,
            "field_labels": get_material_field_labels(),
            "return_baseline_snapshot": return_baseline_snapshot,
            "returned_missing_elements": returned_missing_elements,
            "returned_missing_fields": returned_missing_fields,
        }

    if investigation_draft_history:
        materials_payload["investigation_draft_history"] = investigation_draft_history

    if not scenario.checklist:
        raise ValueError("场景缺少核查清单")

    scenario.checklist.title = materials_payload["title"]
    scenario.checklist.payload = materials_payload
    scenario.checklist.total_items = 0
    flag_modified(scenario.checklist, "payload")
    db.commit()
    db.refresh(scenario)

    write_audit_log(
        db,
        user=user,
        action="scenario.revise_and_resubmit",
        resource_type="scenario",
        resource_id=str(scenario.id),
        detail=(
            f"业务补充后重新提交材料（第 {len(revision_history) + 1} 轮）：{scenario.project_name}；"
            f"待法务确认协查范围"
        ),
    )
    return scenario


def scenario_summary_meta(status: str, checklist_payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = checklist_payload or {}
    brief = payload.get("brief") or {}
    blocked = int(brief.get("blocked_count") or 0)
    passed = int(brief.get("passed_count") or 0)

    if status == "pending_scope":
        progress_status = "pending_scope"
    elif status == "pending_legal_review":
        progress_status = "submitted"
    elif status == "returned_for_revision":
        progress_status = "needs_revision"
    elif status == "review_in_progress":
        progress_status = "in_review"
    elif status.startswith("review_"):
        progress_status = "finalized"
    elif status in ("checklist_generated", "brief_generated", "brief_blocked"):
        progress_status = "processing"
    else:
        progress_status = "processing"

    needs_revision = status == "returned_for_revision"

    if status == "pending_legal_review" and blocked >= 3:
        review_priority = "high"
    elif blocked > 0 or status == "brief_blocked":
        review_priority = "medium"
    else:
        review_priority = "low"

    priority_order = {"high": 0, "medium": 1, "low": 2}

    return {
        "progress_status": progress_status,
        "review_priority": review_priority,
        "priority_order": priority_order.get(review_priority, 9),
        "blocked_count": blocked,
        "passed_count": passed,
        "needs_revision": needs_revision,
    }
