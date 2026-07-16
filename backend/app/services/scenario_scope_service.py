from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.capability_packs.loader import LoadedCapabilityPack
from app.capability_packs.registry import (
    CapabilityPackRegistry,
    CapabilityPackRegistryError,
    CapabilityPackUnsupportedError,
    get_capability_pack_registry,
    load_frozen_capability_pack,
)
from app.models.scenario import InvestigationScenario, ScenarioGenerationAttempt, ScenarioGenerationInput
from app.models.user import User
from app.services.cold_start_service import profile_for_generation
from app.services.generation_guard import (
    GenerationConflictError,
    normalize_strings,
    snapshot_hash,
    stable_hash,
)
from app.services.rules_registry import build_supported_locations


SCOPE_SCHEMA_VERSION = "2.0"
SCOPE_NOTICE_VERSION = "scope-notice-v1"
GENERATION_INPUT_SCHEMA_VERSION = "1.0"
GENERATION_LEASE_SECONDS = 300
GENERATION_MAX_SECONDS = 1800
GENERATION_HEARTBEAT_SECONDS = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().isoformat()


def _proposal_semantics(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        key: proposal.get(key)
        for key in (
            "pack_id", "pack_version", "pack_hash", "rules_artifact_id",
            "country", "state", "city", "industry", "action_type",
        )
    }


def _validate_proposal(proposal: dict[str, Any], expected_hash: str) -> None:
    canonical = stable_hash(_proposal_semantics(proposal))
    if not expected_hash or proposal.get("proposal_hash") != canonical or expected_hash != canonical:
        raise GenerationConflictError("场景提议内容或哈希已变化，请刷新后重新确认")


def _proposal_for_pack(pack: LoadedCapabilityPack) -> dict[str, Any]:
    manifest = pack.manifest
    rules = pack.rules
    binding = manifest.artifact_binding
    jurisdiction = rules.get("jurisdiction") or {}
    locations = build_supported_locations(rules)
    location = locations[0] if locations else {}
    industry = (rules.get("industries") or {}).get(binding.industry, {})
    action = (rules.get("action_types") or {}).get(binding.action_type, {})
    proposal = {
        "pack_id": manifest.pack_id,
        "pack_version": manifest.version,
        "pack_hash": manifest.semantic_hash,
        "capability_pack_id": manifest.pack_id,
        "capability_pack_version": manifest.version,
        "capability_pack_hash": manifest.semantic_hash,
        "rules_artifact_id": manifest.rules_artifact.artifact_id,
        "rules_pack_id": manifest.rules_artifact.artifact_id,
        "country": manifest.country,
        "state": location.get("state") or jurisdiction.get("default_state") or "",
        "city": location.get("city") or "",
        "industry": manifest.industry,
        "action_type": manifest.action_type,
        "labels": {
            "country": jurisdiction.get("name") or manifest.country,
            "industry": industry.get("name") or manifest.industry,
            "action_type": action.get("name") or manifest.action_type,
            "pack": manifest.display_name,
        },
    }
    proposal["proposal_hash"] = stable_hash(_proposal_semantics(proposal))
    return proposal


def build_current_scope_proposal() -> dict[str, Any]:
    """Compatibility helper for the single formal MVP; never falls back on error."""
    active = get_capability_pack_registry().list_active()
    if len(active) != 1:
        raise CapabilityPackRegistryError("当前正式 Capability Pack 数量不唯一，不能隐式选择")
    return _proposal_for_pack(active[0])


def _material_text(payload: Any) -> str:
    fields = (
        "project_name", "investment_destination", "project_content_scale", "description",
        "investment_structure", "known_risks", "capacity_notes", "facility_notes", "remarks",
    )
    values = [str(getattr(payload, field, None) or "") for field in fields]
    extract = getattr(payload, "document_extract", None)
    if extract is not None:
        if hasattr(extract, "model_dump"):
            values.append(str(extract.model_dump(mode="json", exclude_none=True)))
        else:
            values.append(str(extract))
    return " ".join(values)


def material_text_from_uploads(
    uploads: list[tuple[str, bytes, str | None]] | None,
) -> str:
    """Extract deterministic text from uploaded source files for pack routing."""
    if not uploads:
        return ""
    from app.services.document_extractor import read_upload_text

    parts: list[str] = []
    for filename, content, _content_type in uploads:
        text = read_upload_text(filename, content)
        if text:
            parts.append(text)
    return " ".join(parts)


def assess_submitted_scene(payload: Any, proposal: dict[str, Any]) -> dict[str, Any]:
    mismatches: list[dict[str, str]] = []
    submitted_pack = getattr(payload, "rules_pack_id", None)
    accepted_pack_ids = {proposal.get("pack_id"), proposal.get("rules_artifact_id")}
    if submitted_pack and submitted_pack not in accepted_pack_ids:
        mismatches.append(
            {"field": "rules_pack_id", "submitted": str(submitted_pack), "supported": str(proposal.get("pack_id"))}
        )
    return {
        "result": "blocked" if mismatches else "requires_legal_confirmation",
        "reasons": ["提交的场景路由与当前唯一支持场景不一致"] if mismatches else ["业务已知情；是否适用仍需法务结合材料确认"],
        "mismatches": mismatches,
        "assessed_at": _utcnow_iso(),
        "assessor": "deterministic_scope_guard_v1",
    }


def build_proposed_scenario_scope(
    payload: Any,
    user: User,
    *,
    registry: CapabilityPackRegistry | None = None,
    material_text_extra: str = "",
) -> dict[str, Any]:
    if not getattr(payload, "scope_acknowledged", False):
        raise ValueError("请确认已知悉当前完整支持场景后再提交材料")
    notice_version = getattr(payload, "scope_notice_version", SCOPE_NOTICE_VERSION)
    if notice_version != SCOPE_NOTICE_VERSION:
        raise ValueError("当前支持场景说明已更新，请刷新页面后重新确认")
    active_registry = registry or get_capability_pack_registry()
    pack = match_capability_pack_for_payload(
        payload,
        registry=active_registry,
        material_text_extra=material_text_extra,
    )
    proposed = _proposal_for_pack(pack)
    fit = assess_submitted_scene(payload, proposed)
    if fit["result"] == "blocked":
        raise ValueError("提交的能力包提示与后端 Registry 匹配结果不一致")
    return {
        "schema_version": SCOPE_SCHEMA_VERSION,
        "status": "proposed",
        "proposed": proposed,
        "business_ack": {
            "acknowledged": True,
            "acknowledged_by": user.id,
            "acknowledged_by_name": user.full_name,
            "acknowledged_at": _utcnow_iso(),
            "statement_version": SCOPE_NOTICE_VERSION,
        },
        "fit_assessment": fit,
        "snapshot": None,
    }


def match_capability_pack_for_payload(
    payload: Any,
    *,
    registry: CapabilityPackRegistry | None = None,
    material_text_extra: str = "",
) -> LoadedCapabilityPack:
    active_registry = registry or get_capability_pack_registry()
    try:
        pack = active_registry.match_material(
            material_text=f"{_material_text(payload)} {material_text_extra}".strip(),
            country_hint=getattr(payload, "country", None),
            industry_hint=getattr(payload, "industry", None),
            action_type_hint=getattr(payload, "action_type", None),
        )
    except CapabilityPackUnsupportedError as exc:
        raise ValueError("项目材料不属于当前支持的正式 Capability Pack") from exc
    return pack


def build_demo_scenario_scope() -> dict[str, Any]:
    return {
        "schema_version": SCOPE_SCHEMA_VERSION,
        "mode": "demo",
        "status": "demo_proposed",
        "proposed": build_current_scope_proposal(),
        "business_ack": None,
        "fit_assessment": {
            "result": "requires_legal_confirmation",
            "reasons": ["演示记录仅用于演示域，不得进入正式法务审批"],
            "mismatches": [],
            "assessed_at": _utcnow_iso(),
        },
        "snapshot": None,
    }


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _generation_input_payload(scenario: InvestigationScenario) -> dict[str, Any]:
    payload = copy.deepcopy(scenario.checklist.payload if scenario.checklist else {})
    scenario_input = {
        field: _json_value(getattr(scenario, field))
        for field in (
            "project_name", "country", "state", "city", "industry", "action_type",
            "investment_structure", "investment_destination", "project_content_scale", "funding_source",
            "description", "known_risks", "employee_count", "capacity_notes", "facility_notes",
            "board_date", "start_date", "production_date", "remarks", "rules_pack_id",
        )
    }
    document_extract = copy.deepcopy(payload.get("document_extract") or {})
    material_review = copy.deepcopy(payload.get("material_review") or {})
    draft_history = copy.deepcopy(payload.get("investigation_draft_history") or [])
    baseline = copy.deepcopy(material_review.get("return_baseline_snapshot"))
    previous_pack = copy.deepcopy(draft_history[-1]) if draft_history and baseline else None
    expansion_context = " ".join(
        str(scenario_input.get(key) or "")
        for key in (
            "description", "project_content_scale", "known_risks", "investment_structure",
            "facility_notes", "capacity_notes", "remarks",
        )
    )[:1200]
    return {
        "schema_version": GENERATION_INPUT_SCHEMA_VERSION,
        "scenario_input": scenario_input,
        "document_extract": {
            "version": document_extract.get("extracted_at") or document_extract.get("version") or "unversioned",
            "content_hash": stable_hash(document_extract),
            "content": document_extract,
        },
        "material_context": {
            "material_scope_findings": copy.deepcopy(payload.get("material_scope_findings") or []),
            "issue_suggestions": copy.deepcopy(payload.get("issue_suggestions") or []),
            "revision_history": copy.deepcopy(payload.get("revision_history") or []),
            "revision_round": int(payload.get("revision_round") or 0),
            "material_review": material_review,
        },
        "incremental": {
            "enabled": bool(baseline is not None and previous_pack is not None),
            "baseline": baseline,
            "baseline_hash": stable_hash(baseline) if baseline is not None else None,
            "previous_pack": previous_pack,
            "previous_pack_hash": stable_hash(previous_pack) if previous_pack is not None else None,
            "returned_missing_elements": normalize_strings(material_review.get("returned_missing_elements") or []),
        },
        "expansion_context": expansion_context,
    }


@dataclass(frozen=True)
class GenerationLease:
    acquired: bool
    attempt_id: str | None
    lease_owner: str | None
    lease_token: str | None
    outcome: str


def _snapshot_for_request(
    scenario: InvestigationScenario,
    user: User,
    generation_input_hash: str,
    generation_input_id: str,
    *,
    expected_proposal_hash: str,
    compliance_dimensions: list[str],
    selected_issue_codes: list[str],
    match_threshold: int,
    retrieval_top_k: int,
    fit_decision: str,
    polish: bool,
    include_playbook_suggestions: bool,
    registry: CapabilityPackRegistry | None = None,
) -> dict[str, Any]:
    if polish:
        raise ValueError("P0 冻结生成暂不允许动态 LLM polish")
    scope = dict(scenario.scenario_scope or {})
    if scope.get("schema_version") != SCOPE_SCHEMA_VERSION or scope.get("status") != "proposed":
        raise GenerationConflictError("项目缺少当前版本的正式 Scope 提议，不能隐式选择 Capability Pack")
    business_ack = scope.get("business_ack") or {}
    if not business_ack.get("acknowledged"):
        raise GenerationConflictError("项目缺少业务知情确认，不能冻结 Capability Pack")
    if fit_decision not in {"fit", "accept_warning"}:
        raise ValueError("请由法务明确确认当前场景适用性")
    proposed = scope.get("proposed") or {}
    _validate_proposal(proposed, expected_proposal_hash)
    if (scope.get("fit_assessment") or {}).get("result") == "blocked":
        raise ValueError("当前项目不属于现有规则包支持场景，不能生成协查包")

    dimensions = normalize_strings(compliance_dimensions)
    issue_codes = normalize_strings(selected_issue_codes)
    active_registry = registry or get_capability_pack_registry()
    pack = active_registry.get_exact(
        str(proposed.get("pack_id") or ""),
        str(proposed.get("pack_version") or ""),
        str(proposed.get("pack_hash") or ""),
    )
    manifest = pack.manifest
    if proposed.get("rules_artifact_id") != manifest.rules_artifact.artifact_id:
        raise GenerationConflictError("场景提议中的 rules artifact 身份已变化")
    rules = pack.rules
    valid_dimensions = set((rules.get("dimensions") or {}).keys())
    if not dimensions or set(dimensions) - valid_dimensions or set(dimensions) - set(manifest.issue_modules):
        raise ValueError("协查维度为空或不属于当前 Capability Pack")
    retrieval = manifest.retrieval_config
    if not retrieval.match_threshold_min <= int(match_threshold) <= retrieval.match_threshold_max:
        raise ValueError("match threshold 超出 Capability Pack 允许范围")
    if not retrieval.top_k_min <= int(retrieval_top_k) <= retrieval.top_k_max:
        raise ValueError("retrieval top-k 超出 Capability Pack 允许范围")
    corpus = pack.corpus
    profile = (
        profile_for_generation(
            user.id,
            owner_email=user.email,
            owner_auth_provider=user.auth_provider,
            owner_external_subject=user.external_subject,
        )
        if include_playbook_suggestions
        else {"completed": False}
    )
    playbook_codes = normalize_strings(profile.get("suggested_checklist_codes") or [])
    profile_snapshot = {
        "completed": bool(profile.get("completed")),
        "suggested_checklist_codes": playbook_codes,
        "risk_tolerance": profile.get("risk_tolerance"),
        "match_threshold_adjustment": profile.get("match_threshold_adjustment"),
    }
    expansion_candidate_top_k = min(
        int(retrieval_top_k) + retrieval.expansion_candidate_extra,
        retrieval.top_k_max,
    )
    retrieval_config = retrieval.model_dump(mode="json")
    output_profile = manifest.output_profile.model_dump(mode="json")
    config_payload = {
        "capability_pack_id": manifest.pack_id,
        "capability_pack_version": manifest.version,
        "capability_pack_hash": manifest.semantic_hash,
        "issue_modules": list(manifest.issue_modules),
        "rules_artifact_id": manifest.rules_artifact.artifact_id,
        "rules_artifact_version": manifest.rules_artifact.version,
        "rules_artifact_hash": manifest.rules_artifact.content_hash,
        "corpus_artifact_id": manifest.corpus_artifact.artifact_id,
        "corpus_artifact_version": manifest.corpus_artifact.version,
        "corpus_artifact_hash": manifest.corpus_artifact.content_hash,
        "artifact_binding": manifest.artifact_binding.model_dump(mode="json"),
        "retrieval_config": retrieval_config,
        "output_profile": output_profile,
        # Compatibility aliases consumed by stable engines during this MVP.
        "rules_pack_id": manifest.rules_artifact.artifact_id,
        "rules_pack_version": manifest.rules_artifact.version,
        "rules_pack_hash": manifest.rules_artifact.content_hash,
        "corpus_version": str(corpus.get("version") or manifest.corpus_artifact.version),
        "corpus_manifest_hash": manifest.corpus_artifact.content_hash,
        "country": proposed.get("country"),
        "state": proposed.get("state"),
        "city": proposed.get("city"),
        "industry": proposed.get("industry"),
        "action_type": proposed.get("action_type"),
        "compliance_dimensions": dimensions,
        "selected_issue_codes": issue_codes,
        "code_adjustments": {},
        "match_threshold": int(match_threshold),
        "retrieval_top_k": int(retrieval_top_k),
        "expansion_enabled": retrieval.expansion_enabled,
        "expansion_candidate_top_k": expansion_candidate_top_k,
        "expansion_min_keyword_score": retrieval.expansion_min_keyword_score,
        "expansion_context_limit": retrieval.expansion_context_limit,
        "polish": False,
        "include_playbook_suggestions": bool(include_playbook_suggestions),
        "playbook_suggestion_codes": playbook_codes,
        "profile_hash": stable_hash(profile_snapshot),
        "intent_dimension_expansion": False,
        "generation_input_hash": generation_input_hash,
    }
    snapshot = {
        **config_payload,
        "generation_config_hash": stable_hash(config_payload),
        "generation_input_id": generation_input_id,
        "fit_decision": fit_decision,
        "audit_metadata": {
            "confirmed_by": user.id,
            "confirmed_by_name": user.full_name,
            "confirmed_at": _utcnow_iso(),
            "labels": copy.deepcopy(proposed.get("labels") or {}),
            "profile_snapshot": profile_snapshot,
        },
    }
    snapshot["snapshot_hash"] = snapshot_hash(snapshot)
    return snapshot


def _request_matches_snapshot(request: dict[str, Any], snapshot: dict[str, Any], proposal: dict[str, Any]) -> bool:
    _validate_proposal(proposal, str(request.get("expected_proposal_hash") or ""))
    expected = {
        "compliance_dimensions": normalize_strings(request.get("compliance_dimensions") or []),
        "selected_issue_codes": normalize_strings(request.get("selected_issue_codes") or []),
        "match_threshold": int(request.get("match_threshold") or 0),
        "retrieval_top_k": int(request.get("retrieval_top_k") if request.get("retrieval_top_k") is not None else -1),
        "polish": bool(request.get("polish")),
        "include_playbook_suggestions": bool(request.get("include_playbook_suggestions")),
        "fit_decision": request.get("fit_decision"),
    }
    return all(snapshot.get(key) == value for key, value in expected.items())


def _new_attempt(
    *, scenario_id: int, snapshot: dict[str, Any], user_id: int, sequence: int
) -> ScenarioGenerationAttempt:
    now = _utcnow()
    return ScenarioGenerationAttempt(
        id=str(uuid.uuid4()),
        scenario_id=scenario_id,
        snapshot_hash=str(snapshot["snapshot_hash"]),
        config_hash=str(snapshot["generation_config_hash"]),
        generation_input_id=str(snapshot["generation_input_id"]),
        generation_input_hash=str(snapshot["generation_input_hash"]),
        status="running",
        sequence=sequence,
        lease_owner=f"legal:{user_id}:{uuid.uuid4()}",
        lease_token=uuid.uuid4().hex,
        lease_acquired_at=now,
        lease_expires_at=now + timedelta(seconds=GENERATION_LEASE_SECONDS),
        heartbeat_at=now,
        created_by=user_id,
    )


def _lease_result(attempt: ScenarioGenerationAttempt, outcome: str, acquired: bool = True) -> GenerationLease:
    return GenerationLease(acquired, attempt.id, attempt.lease_owner, attempt.lease_token, outcome)


def acquire_generation_lease(db: Session, scenario: InvestigationScenario, user: User, **request: Any) -> GenerationLease:
    if scenario.is_demo:
        raise GenerationConflictError("演示项目不得进入正式生成或法务审批")
    scope = dict(scenario.scenario_scope or {})
    existing = dict(scope.get("snapshot") or {})
    if existing:
        if snapshot_hash(existing) != existing.get("snapshot_hash"):
            raise GenerationConflictError("已冻结 snapshot 哈希损坏")
        try:
            load_frozen_capability_pack(existing)
        except ValueError as exc:
            raise GenerationConflictError(f"冻结 Capability Pack 校验失败：{exc}") from exc
        if not _request_matches_snapshot(request, existing, scope.get("proposed") or {}):
            raise GenerationConflictError("协查范围已冻结，重复确认参数与原请求不一致")
        if scenario.status in {"pending_legal_review", "review_in_progress", "review_approved", "review_partial", "review_rejected"}:
            return GenerationLease(False, None, None, None, "completed")

        if scenario.status == "scope_generating" and scenario.active_generation_attempt_id:
            current = db.get(ScenarioGenerationAttempt, scenario.active_generation_attempt_id)
            if current and current.status == "running":
                unexpired = (
                    db.query(ScenarioGenerationAttempt.id)
                    .filter(
                        ScenarioGenerationAttempt.id == current.id,
                        ScenarioGenerationAttempt.status == "running",
                        ScenarioGenerationAttempt.lease_expires_at > func.current_timestamp(),
                    )
                    .first()
                )
                if unexpired:
                    return _lease_result(current, "in_progress", acquired=False)
                takeover = _new_attempt(
                    scenario_id=scenario.id,
                    snapshot=existing,
                    user_id=user.id,
                    sequence=current.sequence + 1,
                )
                result = db.execute(
                    update(InvestigationScenario)
                    .where(
                        InvestigationScenario.id == scenario.id,
                        InvestigationScenario.status == "scope_generating",
                        InvestigationScenario.active_generation_attempt_id == current.id,
                        InvestigationScenario.scope_snapshot_hash == existing["snapshot_hash"],
                        current.lease_expires_at <= func.current_timestamp(),
                    )
                    .values(active_generation_attempt_id=takeover.id)
                )
                if result.rowcount != 1:
                    db.rollback()
                    db.refresh(scenario)
                    return acquire_generation_lease(db, scenario, user, **request)
                current.status = "superseded"
                current.completed_at = _utcnow()
                db.add(takeover)
                db.commit()
                db.refresh(scenario)
                return _lease_result(takeover, "takeover")
            if current is None or current.status != "running":
                sequence = int(
                    db.query(func.max(ScenarioGenerationAttempt.sequence))
                    .filter_by(scenario_id=scenario.id)
                    .scalar()
                    or 0
                ) + 1
                recovery = _new_attempt(
                    scenario_id=scenario.id,
                    snapshot=existing,
                    user_id=user.id,
                    sequence=sequence,
                )
                result = db.execute(
                    update(InvestigationScenario)
                    .where(
                        InvestigationScenario.id == scenario.id,
                        InvestigationScenario.status == "scope_generating",
                        InvestigationScenario.active_generation_attempt_id
                        == scenario.active_generation_attempt_id,
                        InvestigationScenario.scope_snapshot_hash == existing["snapshot_hash"],
                    )
                    .values(active_generation_attempt_id=recovery.id)
                )
                if result.rowcount != 1:
                    db.rollback()
                    db.refresh(scenario)
                    return acquire_generation_lease(db, scenario, user, **request)
                db.add(recovery)
                db.commit()
                db.refresh(scenario)
                return _lease_result(recovery, "orphan_recovery")

        if scenario.status != "scope_generation_failed":
            raise GenerationConflictError("当前状态不可重复确认或接管")
        sequence = int(db.query(func.max(ScenarioGenerationAttempt.sequence)).filter_by(scenario_id=scenario.id).scalar() or 0) + 1
        attempt = _new_attempt(scenario_id=scenario.id, snapshot=existing, user_id=user.id, sequence=sequence)
        result = db.execute(
            update(InvestigationScenario)
            .where(
                InvestigationScenario.id == scenario.id,
                InvestigationScenario.status == "scope_generation_failed",
                InvestigationScenario.scope_snapshot_hash == existing["snapshot_hash"],
                InvestigationScenario.active_generation_attempt_id.is_(None),
            )
            .values(status="scope_generating", active_generation_attempt_id=attempt.id)
        )
        if result.rowcount != 1:
            db.rollback()
            db.refresh(scenario)
            return acquire_generation_lease(db, scenario, user, **request)
        db.add(attempt)
        db.commit()
        db.refresh(scenario)
        return _lease_result(attempt, "retry")

    if scenario.status != "pending_scope" or scenario.scope_snapshot_hash is not None:
        db.refresh(scenario)
        return acquire_generation_lease(db, scenario, user, **request)
    input_payload = _generation_input_payload(scenario)
    input_hash = stable_hash(input_payload)
    input_record = ScenarioGenerationInput(
        id=str(uuid.uuid4()), scenario_id=scenario.id, input_hash=input_hash,
        schema_version=GENERATION_INPUT_SCHEMA_VERSION, payload=input_payload, created_by=user.id,
    )
    candidate = _snapshot_for_request(scenario, user, input_hash, input_record.id, **request)
    scope.update({"status": "generating", "snapshot": candidate})
    sequence = int(
        db.query(func.max(ScenarioGenerationAttempt.sequence))
        .filter_by(scenario_id=scenario.id)
        .scalar()
        or 0
    ) + 1
    attempt = _new_attempt(
        scenario_id=scenario.id, snapshot=candidate, user_id=user.id, sequence=sequence
    )
    result = db.execute(
        update(InvestigationScenario)
        .where(
            InvestigationScenario.id == scenario.id,
            InvestigationScenario.status == "pending_scope",
            InvestigationScenario.scope_snapshot_hash.is_(None),
        )
        .values(
            scenario_scope=scope,
            scope_snapshot_hash=candidate["snapshot_hash"],
            status="scope_generating",
            active_generation_attempt_id=attempt.id,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        db.refresh(scenario)
        return acquire_generation_lease(db, scenario, user, **request)
    db.add(input_record)
    db.add(attempt)
    db.commit()
    db.refresh(scenario)
    return _lease_result(attempt, "acquired")


def renew_generation_lease(db: Session, config: Any) -> bool:
    now = _utcnow()
    result = db.execute(
        update(ScenarioGenerationAttempt)
        .where(
            ScenarioGenerationAttempt.id == config.attempt_id,
            ScenarioGenerationAttempt.scenario_id == config.scenario_id,
            ScenarioGenerationAttempt.snapshot_hash == config.snapshot_hash,
            ScenarioGenerationAttempt.config_hash == config.config_hash,
            ScenarioGenerationAttempt.generation_input_hash == config.generation_input_hash,
            ScenarioGenerationAttempt.status == "running",
            ScenarioGenerationAttempt.lease_owner == config.lease_owner,
            ScenarioGenerationAttempt.lease_token == config.lease_token,
            ScenarioGenerationAttempt.lease_expires_at > func.current_timestamp(),
            ScenarioGenerationAttempt.lease_acquired_at
            > now - timedelta(seconds=GENERATION_MAX_SECONDS),
        )
        .values(heartbeat_at=now, lease_expires_at=now + timedelta(seconds=GENERATION_LEASE_SECONDS))
    )
    db.commit()
    return result.rowcount == 1


def legacy_scope_for_scenario(scenario: InvestigationScenario) -> dict[str, Any]:
    """Represent a pre-Scope record without assigning today's active pack to it."""
    return {
        "schema_version": SCOPE_SCHEMA_VERSION,
        "status": "legacy_unconfirmed",
        "proposed": {},
        "business_ack": None,
        "fit_assessment": {
            "result": "not_assessed",
            "reasons": ["该项目创建于 Scope Confirmation Layer 上线前，尚未绑定正式 Capability Pack"],
            "mismatches": [],
        },
        "snapshot": None,
    }
