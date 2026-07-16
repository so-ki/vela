from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.capability_packs.registry import load_frozen_capability_pack
from app.models.scenario import (
    InvestigationScenario,
    ScenarioGenerationAttempt,
    ScenarioGenerationInput,
)


class GenerationGuardError(ValueError):
    pass


class GenerationConflictError(GenerationGuardError):
    pass


def stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_strings(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


_SNAPSHOT_NON_SEMANTIC = {
    "snapshot_hash",
    "generation_input_id",
    "audit_metadata",
    "labels",
    "confirmed_at",
    "confirmed_by",
    "confirmed_by_name",
}


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    """Hash generation semantics only; audit/display metadata is intentionally separate."""
    body = {key: value for key, value in snapshot.items() if key not in _SNAPSHOT_NON_SEMANTIC}
    return stable_hash(body)


@dataclass(frozen=True)
class GenerationConfig:
    """Database-bound context. It is not an authorization bearer by itself."""

    scenario_id: int
    attempt_id: str
    lease_owner: str
    lease_token: str
    snapshot_hash: str
    config_hash: str
    generation_input_id: str
    generation_input_hash: str
    generation_input: dict[str, Any]
    capability_pack_id: str
    capability_pack_version: str
    capability_pack_hash: str
    capability_pack_display_name: str
    capability_pack_description: str
    issue_modules: tuple[str, ...]
    rules_artifact_id: str
    rules_artifact_version: str
    rules_artifact_hash: str
    corpus_artifact_id: str
    corpus_artifact_version: str
    corpus_artifact_hash: str
    artifact_binding: dict[str, str]
    retrieval_config: dict[str, Any]
    output_profile: dict[str, Any]
    rules_artifact_path: str
    corpus_artifact_path: str
    rules_data: dict[str, Any]
    corpus_data: dict[str, Any]
    rules_pack_id: str
    rules_pack_version: str
    rules_pack_hash: str
    corpus_version: str
    corpus_manifest_hash: str
    country: str
    state: str
    city: str
    industry: str
    action_type: str
    compliance_dimensions: tuple[str, ...]
    selected_issue_codes: tuple[str, ...]
    code_adjustments: tuple[tuple[str, int], ...]
    match_threshold: int
    retrieval_top_k: int
    expansion_enabled: bool
    expansion_candidate_top_k: int
    expansion_min_keyword_score: float
    expansion_context_limit: int
    polish: bool
    include_playbook_suggestions: bool
    playbook_suggestion_codes: tuple[str, ...]
    profile_hash: str
    intent_dimension_expansion: bool

    def as_hash_payload(self) -> dict[str, Any]:
        return {
            "capability_pack_id": self.capability_pack_id,
            "capability_pack_version": self.capability_pack_version,
            "capability_pack_hash": self.capability_pack_hash,
            "issue_modules": list(self.issue_modules),
            "rules_artifact_id": self.rules_artifact_id,
            "rules_artifact_version": self.rules_artifact_version,
            "rules_artifact_hash": self.rules_artifact_hash,
            "corpus_artifact_id": self.corpus_artifact_id,
            "corpus_artifact_version": self.corpus_artifact_version,
            "corpus_artifact_hash": self.corpus_artifact_hash,
            "artifact_binding": self.artifact_binding,
            "retrieval_config": self.retrieval_config,
            "output_profile": self.output_profile,
            "rules_pack_id": self.rules_pack_id,
            "rules_pack_version": self.rules_pack_version,
            "rules_pack_hash": self.rules_pack_hash,
            "corpus_version": self.corpus_version,
            "corpus_manifest_hash": self.corpus_manifest_hash,
            "country": self.country,
            "state": self.state,
            "city": self.city,
            "industry": self.industry,
            "action_type": self.action_type,
            "compliance_dimensions": list(self.compliance_dimensions),
            "selected_issue_codes": list(self.selected_issue_codes),
            "code_adjustments": dict(self.code_adjustments),
            "match_threshold": self.match_threshold,
            "retrieval_top_k": self.retrieval_top_k,
            "expansion_enabled": self.expansion_enabled,
            "expansion_candidate_top_k": self.expansion_candidate_top_k,
            "expansion_min_keyword_score": self.expansion_min_keyword_score,
            "expansion_context_limit": self.expansion_context_limit,
            "polish": self.polish,
            "include_playbook_suggestions": self.include_playbook_suggestions,
            "playbook_suggestion_codes": list(self.playbook_suggestion_codes),
            "profile_hash": self.profile_hash,
            "intent_dimension_expansion": self.intent_dimension_expansion,
            "generation_input_hash": self.generation_input_hash,
        }


def _config_from_snapshot(
    snapshot: dict[str, Any],
    *,
    scenario_id: int,
    attempt: ScenarioGenerationAttempt,
    generation_input: ScenarioGenerationInput,
) -> GenerationConfig:
    stored_snapshot_hash = str(snapshot.get("snapshot_hash") or "")
    if not stored_snapshot_hash or snapshot_hash(snapshot) != stored_snapshot_hash:
        raise GenerationGuardError("协查范围快照哈希校验失败")
    input_payload = copy.deepcopy(generation_input.payload or {})
    input_hash = stable_hash(input_payload)
    if input_hash != generation_input.input_hash or input_hash != snapshot.get("generation_input_hash"):
        raise GenerationGuardError("冻结 generation input 哈希校验失败")
    if generation_input.scenario_id != scenario_id:
        raise GenerationGuardError("generation input 与场景错绑")

    try:
        pack = load_frozen_capability_pack(snapshot)
    except ValueError as exc:
        raise GenerationGuardError(f"冻结 Capability Pack 校验失败：{exc}") from exc

    config = GenerationConfig(
        scenario_id=scenario_id,
        attempt_id=attempt.id,
        lease_owner=attempt.lease_owner,
        lease_token=attempt.lease_token,
        snapshot_hash=stored_snapshot_hash,
        config_hash=str(snapshot.get("generation_config_hash") or ""),
        generation_input_id=generation_input.id,
        generation_input_hash=input_hash,
        generation_input=input_payload,
        capability_pack_id=str(snapshot.get("capability_pack_id") or ""),
        capability_pack_version=str(snapshot.get("capability_pack_version") or ""),
        capability_pack_hash=str(snapshot.get("capability_pack_hash") or ""),
        capability_pack_display_name=pack.manifest.display_name,
        capability_pack_description=pack.manifest.description,
        issue_modules=tuple(snapshot.get("issue_modules") or ()),
        rules_artifact_id=str(snapshot.get("rules_artifact_id") or ""),
        rules_artifact_version=str(snapshot.get("rules_artifact_version") or ""),
        rules_artifact_hash=str(snapshot.get("rules_artifact_hash") or ""),
        corpus_artifact_id=str(snapshot.get("corpus_artifact_id") or ""),
        corpus_artifact_version=str(snapshot.get("corpus_artifact_version") or ""),
        corpus_artifact_hash=str(snapshot.get("corpus_artifact_hash") or ""),
        artifact_binding=copy.deepcopy(snapshot.get("artifact_binding") or {}),
        retrieval_config=copy.deepcopy(snapshot.get("retrieval_config") or {}),
        output_profile=copy.deepcopy(snapshot.get("output_profile") or {}),
        rules_artifact_path=str(pack.rules_path),
        corpus_artifact_path=str(pack.corpus_path),
        rules_data=copy.deepcopy(pack.rules),
        corpus_data=copy.deepcopy(pack.corpus),
        rules_pack_id=str(snapshot.get("rules_pack_id") or ""),
        rules_pack_version=str(snapshot.get("rules_pack_version") or ""),
        rules_pack_hash=str(snapshot.get("rules_pack_hash") or ""),
        corpus_version=str(snapshot.get("corpus_version") or ""),
        corpus_manifest_hash=str(snapshot.get("corpus_manifest_hash") or snapshot.get("corpus_hash") or ""),
        country=str(snapshot.get("country") or ""),
        state=str(snapshot.get("state") or ""),
        city=str(snapshot.get("city") or ""),
        industry=str(snapshot.get("industry") or ""),
        action_type=str(snapshot.get("action_type") or ""),
        compliance_dimensions=tuple(snapshot.get("compliance_dimensions") or ()),
        selected_issue_codes=tuple(snapshot.get("selected_issue_codes") or ()),
        code_adjustments=tuple(sorted((str(k), int(v)) for k, v in (snapshot.get("code_adjustments") or {}).items())),
        match_threshold=int(snapshot.get("match_threshold") or 0),
        retrieval_top_k=int(snapshot.get("retrieval_top_k") if snapshot.get("retrieval_top_k") is not None else -1),
        expansion_enabled=bool(snapshot.get("expansion_enabled")),
        expansion_candidate_top_k=int(snapshot.get("expansion_candidate_top_k") or 0),
        expansion_min_keyword_score=float(snapshot.get("expansion_min_keyword_score") or 0),
        expansion_context_limit=int(snapshot.get("expansion_context_limit") or 0),
        polish=bool(snapshot.get("polish")),
        include_playbook_suggestions=bool(snapshot.get("include_playbook_suggestions")),
        playbook_suggestion_codes=tuple(snapshot.get("playbook_suggestion_codes") or ()),
        profile_hash=str(snapshot.get("profile_hash") or ""),
        intent_dimension_expansion=bool(snapshot.get("intent_dimension_expansion")),
    )
    if not config.config_hash or stable_hash(config.as_hash_payload()) != config.config_hash:
        raise GenerationGuardError("生成配置哈希校验失败")
    if config.intent_dimension_expansion:
        raise GenerationGuardError("正式生成禁止 LLM 扩展冻结维度")
    if not config.compliance_dimensions:
        raise GenerationGuardError("冻结快照缺少协查维度")
    if not 50 <= config.match_threshold <= 95 or not 0 <= config.retrieval_top_k <= 10:
        raise GenerationGuardError("冻结快照的检索参数无效")
    if config.expansion_enabled:
        if config.expansion_candidate_top_k < config.retrieval_top_k or config.expansion_context_limit < 0:
            raise GenerationGuardError("冻结 expansion 参数无效")

    rules = config.rules_data
    valid_dimensions = set((rules.get("dimensions") or {}).keys())
    if set(config.compliance_dimensions) - valid_dimensions:
        raise GenerationGuardError("冻结快照包含 Capability Pack 不支持的维度")
    if set(config.compliance_dimensions) - set(config.issue_modules):
        raise GenerationGuardError("冻结维度不属于 Capability Pack issue modules")
    if (
        config.rules_pack_id != config.rules_artifact_id
        or config.rules_pack_version != config.rules_artifact_version
        or config.rules_pack_hash != config.rules_artifact_hash
    ):
        raise GenerationGuardError("规则引擎兼容身份与 rules artifact 不一致")
    if (
        config.corpus_version != config.corpus_artifact_version
        or config.corpus_manifest_hash != config.corpus_artifact_hash
    ):
        raise GenerationGuardError("语料兼容身份与 corpus artifact 不一致")
    manifest = pack.manifest
    if (
        config.country != manifest.country
        or config.industry != manifest.industry
        or config.action_type != manifest.action_type
    ):
        raise GenerationGuardError("冻结路由与 Capability Pack 不一致")
    retrieval = manifest.retrieval_config
    expected_candidate_top_k = min(
        config.retrieval_top_k + retrieval.expansion_candidate_extra,
        retrieval.top_k_max,
    )
    if not retrieval.match_threshold_min <= config.match_threshold <= retrieval.match_threshold_max:
        raise GenerationGuardError("冻结 threshold 超出 Capability Pack 范围")
    if not retrieval.top_k_min <= config.retrieval_top_k <= retrieval.top_k_max:
        raise GenerationGuardError("冻结 top-k 超出 Capability Pack 范围")
    if (
        config.expansion_enabled != retrieval.expansion_enabled
        or config.expansion_candidate_top_k != expected_candidate_top_k
        or config.expansion_min_keyword_score != retrieval.expansion_min_keyword_score
        or config.expansion_context_limit != retrieval.expansion_context_limit
    ):
        raise GenerationGuardError("冻结 expansion 配置与 Capability Pack 不一致")
    return config


def _load_bound_context(
    db: Session,
    *,
    scenario_id: int,
    attempt_id: str,
    lease_token: str,
    allowed_states: set[str],
    require_running: bool = True,
) -> GenerationConfig:
    scenario = db.get(InvestigationScenario, scenario_id)
    attempt = db.get(ScenarioGenerationAttempt, attempt_id)
    if not scenario or not attempt:
        raise GenerationGuardError("生成场景或 attempt 不存在")
    if scenario.status not in allowed_states:
        raise GenerationGuardError(f"当前状态 {scenario.status} 不允许执行生成相关操作")
    if attempt.scenario_id != scenario.id or attempt.snapshot_hash != scenario.scope_snapshot_hash:
        raise GenerationGuardError("attempt 与场景/snapshot 错绑")
    if attempt.lease_token != lease_token or not lease_token:
        raise GenerationGuardError("生成 lease token 无效")
    if require_running:
        active = (
            db.query(ScenarioGenerationAttempt.id)
            .filter(
                ScenarioGenerationAttempt.id == attempt.id,
                ScenarioGenerationAttempt.scenario_id == scenario.id,
                ScenarioGenerationAttempt.status == "running",
                ScenarioGenerationAttempt.lease_token == lease_token,
                ScenarioGenerationAttempt.lease_expires_at > func.current_timestamp(),
                InvestigationScenario.active_generation_attempt_id == attempt.id,
            )
            .join(InvestigationScenario, InvestigationScenario.id == ScenarioGenerationAttempt.scenario_id)
            .first()
        )
        if not active:
            raise GenerationGuardError("生成 lease 已失效或过期")
    scope = scenario.scenario_scope or {}
    snapshot = scope.get("snapshot") or {}
    input_id = str(snapshot.get("generation_input_id") or "")
    if input_id != attempt.generation_input_id:
        raise GenerationGuardError("attempt 与 generation input 错绑")
    generation_input = db.get(ScenarioGenerationInput, input_id)
    if not generation_input:
        raise GenerationGuardError("冻结 generation input 不存在")
    config = _config_from_snapshot(
        snapshot,
        scenario_id=scenario.id,
        attempt=attempt,
        generation_input=generation_input,
    )
    if attempt.config_hash != config.config_hash or attempt.generation_input_hash != config.generation_input_hash:
        raise GenerationGuardError("attempt 的 config/input hash 与 snapshot 不一致")
    return config


def load_generation_context(
    db: Session,
    scenario: InvestigationScenario,
    *,
    attempt_id: str,
    lease_token: str,
) -> GenerationConfig:
    return _load_bound_context(
        db,
        scenario_id=scenario.id,
        attempt_id=attempt_id,
        lease_token=lease_token,
        allowed_states={"scope_generating"},
    )


def require_generation_config(db: Session, config: GenerationConfig | None) -> GenerationConfig:
    """Reload every formal service authorization from persistence; self-made configs fail."""
    if config is None or not isinstance(config, GenerationConfig):
        raise GenerationGuardError("缺少数据库绑定的冻结生成上下文")
    bound = _load_bound_context(
        db,
        scenario_id=config.scenario_id,
        attempt_id=config.attempt_id,
        lease_token=config.lease_token,
        allowed_states={"scope_generating"},
    )
    if bound != config:
        raise GenerationGuardError("调用配置与数据库绑定的生成上下文不一致")
    return bound


def require_generated_result(db: Session, scenario: InvestigationScenario) -> GenerationConfig:
    require_formal_scenario(scenario)
    if scenario.status not in {
        "pending_legal_review", "review_in_progress", "review_approved", "review_partial", "review_rejected"
    }:
        raise GenerationGuardError(f"当前状态 {scenario.status} 没有可用的正式生成结果")
    scope = scenario.scenario_scope or {}
    snapshot = scope.get("snapshot") or {}
    attempt_id = str((scenario.checklist.payload if scenario.checklist else {}).get("generation_attempt_id") or "")
    attempt = db.get(ScenarioGenerationAttempt, attempt_id)
    if not attempt or attempt.status != "succeeded" or attempt.scenario_id != scenario.id:
        raise GenerationGuardError("成功 generation attempt 不存在或错绑")
    input_id = str(snapshot.get("generation_input_id") or "")
    generation_input = db.get(ScenarioGenerationInput, input_id)
    if not generation_input:
        raise GenerationGuardError("冻结 generation input 不存在")
    config = _config_from_snapshot(snapshot, scenario_id=scenario.id, attempt=attempt, generation_input=generation_input)
    payload = scenario.checklist.payload if scenario.checklist else {}
    if (
        scenario.scope_snapshot_hash != config.snapshot_hash
        or payload.get("generation_snapshot_hash") != config.snapshot_hash
        or payload.get("generation_config_hash") != config.config_hash
        or payload.get("generation_input_hash") != config.generation_input_hash
    ):
        raise GenerationGuardError("已生成内容与冻结 snapshot/config/input 不一致")
    if not payload.get("sections") or not payload.get("sections_with_legal") or not payload.get("brief"):
        raise GenerationGuardError("协查包尚未完整生成")
    return config


def require_formal_scenario(scenario: InvestigationScenario) -> None:
    if scenario.is_demo:
        raise GenerationGuardError("演示项目不得进入正式业务流程")
