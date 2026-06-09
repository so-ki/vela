"""Project intelligence: unified knowledge + cross-module conflicts + light multi-agent debate."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.models.scenario import InvestigationScenario
from app.services.conflict_detection_service import detect_material_conflicts
from app.services.project_hub_service import ensure_project_hub, project_context


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def collect_project_knowledge(
    payload: dict[str, Any],
    scenario: InvestigationScenario,
) -> dict[str, Any]:
    """Aggregate all project artifacts into one structured knowledge bundle."""
    ensure_project_hub(payload)
    ctx = project_context(payload, scenario)
    texts: list[dict[str, Any]] = []

    texts.append({"source": "scenario", "label": "项目描述", "text": scenario.description or ""})

    doc_extract = payload.get("document_extract") or {}
    for f in doc_extract.get("archived_files") or []:
        texts.append(
            {
                "source": "material_file",
                "label": f.get("original_name") or f.get("stored_name"),
                "text": (f.get("extract_preview") or "")[:4000],
            }
        )

    for key in ("_contract_texts", "_diligence_texts"):
        store = payload.get(key) or {}
        kind = "contract" if "contract" in key else "diligence"
        for doc_id, body in store.items():
            texts.append({"source": kind, "doc_id": doc_id, "text": (body or "")[:6000]})

    checklist_items: list[dict[str, Any]] = []
    for section in payload.get("sections_with_legal") or payload.get("sections") or []:
        for item in section.get("items") or []:
            checklist_items.append(
                {
                    "code": item.get("code"),
                    "title": item.get("title"),
                    "dimension": section.get("dimension_id"),
                    "legal_hits": len(item.get("legal_hits") or []),
                    "tier": item.get("tier"),
                    "gate_status": item.get("gate_status"),
                }
            )

    contracts = (payload.get("project_hub") or {}).get("modules", {}).get("contracts", {})
    contract_summaries = []
    for doc in contracts.get("documents") or []:
        contract_summaries.append(
            {
                "id": doc.get("id"),
                "filename": doc.get("filename"),
                "red": (doc.get("analysis") or {}).get("red_count", 0),
                "yellow": (doc.get("analysis") or {}).get("yellow_count", 0),
            }
        )

    diligence = (payload.get("project_hub") or {}).get("modules", {}).get("diligence", {})
    dd_issues = (payload.get("diligence_report") or {}).get("issues") or diligence.get("issues") or []

    review = payload.get("review") or {}
    review_items = [
        {"code": i.get("code"), "decision": i.get("decision"), "comment": i.get("comment")}
        for i in (review.get("items") or [])
    ]

    return {
        "collected_at": _utcnow_iso(),
        "project_context": ctx,
        "texts": texts,
        "checklist_items": checklist_items,
        "contract_summaries": contract_summaries,
        "diligence_issue_count": len(dd_issues),
        "review_summary": {
            "status": review.get("status"),
            "approved": review.get("approved_count"),
            "rejected": review.get("rejected_count"),
        },
        "review_items": review_items,
        "existing_conflict_flags": payload.get("conflict_flags") or [],
    }


def run_analyst_pass(knowledge: dict[str, Any]) -> dict[str, Any]:
    """Neutral synthesis of all project facts (not yet adversarial)."""
    ctx = knowledge.get("project_context") or {}
    inv = ctx.get("investigation_summary") or {}
    items = knowledge.get("checklist_items") or []
    s3 = inv.get("s3_blocked_codes") or []
    zero = inv.get("zero_hit_items") or []
    contracts = knowledge.get("contract_summaries") or []
    red_total = sum(c.get("red") or 0 for c in contracts)

    findings: list[dict[str, Any]] = []
    if s3:
        findings.append(
            {
                "id": _uid("analyst-s3"),
                "category": "investigation",
                "severity": "high",
                "statement": f"协查存在 {len(s3)} 条 S3 硬阻断：{', '.join(s3[:5])}",
                "evidence": [{"type": "tier_report", "codes": s3}],
            }
        )
    if zero:
        findings.append(
            {
                "id": _uid("analyst-zero"),
                "category": "legal_source",
                "severity": "medium",
                "statement": f"{len(zero)} 条核查项法源零命中或仅门户降级",
                "evidence": [{"type": "retrieval", "codes": zero}],
            }
        )
    if red_total:
        findings.append(
            {
                "id": _uid("analyst-contract"),
                "category": "contract",
                "severity": "high",
                "statement": f"合同审查累计 {red_total} 条 RED 条款",
                "evidence": [{"type": "contract_analysis", "count": red_total}],
            }
        )
    rejected = [
        r for r in knowledge.get("review_items") or [] if r.get("decision") == "rejected"
    ]
    if rejected:
        findings.append(
            {
                "id": _uid("analyst-review"),
                "category": "review",
                "severity": "medium",
                "statement": f"法务已驳回 {len(rejected)} 条协查结论",
                "evidence": [{"type": "review", "codes": [r.get("code") for r in rejected[:8]]}],
            }
        )

    text_blob = " ".join(t.get("text", "") for t in knowledge.get("texts") or []).lower()
    if "lgpd" in text_blob or "数据" in text_blob:
        dat_items = [i for i in items if (i.get("code") or "").startswith("DAT")]
        if not dat_items:
            findings.append(
                {
                    "id": _uid("analyst-dat-gap"),
                    "category": "data_compliance",
                    "severity": "medium",
                    "statement": "材料涉及数据/LGPD 表述，但核查清单中未见 DAT 维度条目",
                    "evidence": [{"type": "text_signal", "keywords": ["lgpd", "数据"]}],
                }
            )

    summary = (
        f"项目「{ctx.get('project_name')}」：核查项 {len(items)} 条；"
        f"S3 {len(s3)}；零命中 {len(zero)}；合同 RED {red_total}；"
        f"尽调 issue {knowledge.get('diligence_issue_count', 0)}。"
    )

    return {
        "agent": "analyst",
        "role": "统摄汇总（中性事实整合）",
        "summary": summary,
        "findings": findings,
        "completed_at": _utcnow_iso(),
    }


def run_red_team_pass(
    knowledge: dict[str, Any],
    analyst: dict[str, Any],
) -> dict[str, Any]:
    """Challenge analyst synthesis: contradictions, gaps, overconfidence."""
    challenges: list[dict[str, Any]] = []
    text_blob = " ".join(t.get("text", "") for t in knowledge.get("texts") or [])

    # 材料声称 vs 模块结论
    if re.search(r"无.*环保.*处罚|no environmental", text_blob, re.I):
        inv = (knowledge.get("project_context") or {}).get("investigation_summary") or {}
        env_blocked = [
            i
            for i in knowledge.get("checklist_items") or []
            if i.get("dimension") == "environment" and i.get("gate_status") != "passed"
        ]
        if env_blocked or inv.get("s3_blocked_codes"):
            challenges.append(
                {
                    "id": _uid("rt-env"),
                    "severity": "high",
                    "title": "材料与协查环境维度不一致",
                    "challenge": "材料表述「无环保处罚」，但环境相关核查未全部通过或存在 S3。",
                    "counter_evidence": [
                        {"type": "material_claim", "pattern": "无环保处罚"},
                        {"type": "checklist", "items": [i.get("code") for i in env_blocked[:5]]},
                    ],
                    "suggested_action": "统一对外表述或补充环评/许可证明材料",
                }
            )

    # 雇员数跨文档
    scenario_desc = next(
        (t.get("text") for t in knowledge.get("texts") or [] if t.get("source") == "scenario"),
        "",
    )
    ctx = knowledge.get("project_context") or {}
    emp_form = None
    for t in knowledge.get("texts") or []:
        m = re.search(r"雇员\s*(\d+)|员工\s*(\d+)|(\d+)\s*名", t.get("text", ""))
        if m:
            val = next(g for g in m.groups() if g)
            if emp_form is None:
                emp_form = int(val)
            elif abs(int(val) - emp_form) > 30:
                challenges.append(
                    {
                        "id": _uid("rt-emp"),
                        "severity": "medium",
                        "title": "雇员规模跨文件不一致",
                        "challenge": f"不同材料出现 {emp_form} 与 {val} 等差异较大的雇员数。",
                        "counter_evidence": [{"type": "cross_document", "values": [emp_form, int(val)]}],
                        "suggested_action": "业务统一用工计划数字",
                    }
                )
                break

    # 合同 RED 但协查简报可能已通过相关项
    red_contracts = [c for c in knowledge.get("contract_summaries") or [] if (c.get("red") or 0) > 0]
    if red_contracts:
        passed_high = [
            i
            for i in knowledge.get("checklist_items") or []
            if i.get("gate_status") == "passed" and i.get("code", "").startswith(("TAX", "IND", "FOR"))
        ]
        if passed_high:
            challenges.append(
                {
                    "id": _uid("rt-contract-inv"),
                    "severity": "high",
                    "title": "协查通过 vs 合同 RED",
                    "challenge": "部分投资/行业核查项已通过门控，但项目合同存在 RED 条款，交易文件可能与协查结论不同步。",
                    "counter_evidence": [
                        {"type": "contract", "files": [c.get("filename") for c in red_contracts]},
                        {"type": "checklist_passed", "codes": [i.get("code") for i in passed_high[:4]]},
                    ],
                    "suggested_action": "在定稿前交叉审阅合同与协查简报",
                }
            )

    # 质疑 analyst 是否遗漏尽调
    if knowledge.get("diligence_issue_count", 0) == 0 and len(knowledge.get("contract_summaries") or []) == 0:
        if len(knowledge.get("checklist_items") or []) > 10:
            challenges.append(
                {
                    "id": _uid("rt-dd-missing"),
                    "severity": "low",
                    "title": "尽调/合同模块未运行",
                    "challenge": "协查项较多但未上传合同或运行尽调，项目视图可能不完整。",
                    "counter_evidence": [{"type": "module_gap"}],
                    "suggested_action": "上传交易合同与 DD 支持文件后重新统摄",
                }
            )

    # 对 analyst 每条 high finding 要求证据（Lavern-style challenge）
    for f in analyst.get("findings") or []:
        if f.get("severity") == "high" and not f.get("evidence"):
            challenges.append(
                {
                    "id": _uid("rt-evidence"),
                    "severity": "medium",
                    "title": "Analyst 高风险结论缺证据",
                    "challenge": f"质疑：{f.get('statement')} — 未附可核对证据",
                    "counter_evidence": [{"type": "analyst_finding", "id": f.get("id")}],
                    "suggested_action": "补充 evidence 或降级 severity",
                }
            )

    return {
        "agent": "red_team",
        "role": "对抗挑错（专找矛盾、遗漏与过度结论）",
        "summary": f"Red Team 提出 {len(challenges)} 项质疑与挑战",
        "challenges": challenges,
        "completed_at": _utcnow_iso(),
    }


def detect_cross_module_conflicts(
    payload: dict[str, Any],
    scenario: InvestigationScenario,
) -> list[dict[str, Any]]:
    """Rule-based cross-module conflict detection."""
    flags = list(detect_material_conflicts(scenario, payload))
    knowledge = collect_project_knowledge(payload, scenario)
    ensure_project_hub(payload)

    # 协查 vs 尽调
    for issue in (payload.get("diligence_report") or {}).get("issues") or []:
        if issue.get("severity") == "high":
            flags.append(
                {
                    "id": issue.get("id") or _uid("xmod-dd"),
                    "conflict_type": "cross_module",
                    "severity": "high",
                    "title": issue.get("title"),
                    "summary": issue.get("description"),
                    "source_label": f"尽调 × {issue.get('source')}",
                    "suggested_action": "纳入项目 intelligence 报告并法务确认",
                }
            )

    # 合同 finding vs 场景描述
    for doc in (payload.get("project_hub") or {}).get("modules", {}).get("contracts", {}).get("documents") or []:
        for finding in (doc.get("findings") or [])[:20]:
            if finding.get("risk") != "RED":
                continue
            flags.append(
                {
                    "id": _uid("xmod-contract"),
                    "conflict_type": "contract",
                    "severity": "high",
                    "title": f"合同 RED：{doc.get('filename')}",
                    "summary": finding.get("excerpt", "")[:200],
                    "source_label": "合同审查 × 项目统摄",
                    "suggested_action": finding.get("investigation_link") or "法务复核合同条款",
                }
            )

    return flags


def run_project_intelligence(
    payload: dict[str, Any],
    scenario: InvestigationScenario,
    *,
    user_id: Optional[int] = None,
) -> dict[str, Any]:
    """Full pipeline: collect → analyst → red team → cross conflicts → debate resolution."""
    knowledge = collect_project_knowledge(payload, scenario)
    analyst = run_analyst_pass(knowledge)
    red_team = run_red_team_pass(knowledge, analyst)
    cross_flags = detect_cross_module_conflicts(payload, scenario)

    # Orchestrator resolution (simple: union with severity rank)
    unified_issues: list[dict[str, Any]] = []
    for f in cross_flags:
        unified_issues.append(
            {
                "id": f.get("id"),
                "severity": f.get("severity", "medium"),
                "title": f.get("title"),
                "detail": f.get("summary"),
                "sources": [f.get("source_label")],
                "requires_review": True,
            }
        )
    for c in red_team.get("challenges") or []:
        unified_issues.append(
            {
                "id": c.get("id"),
                "severity": c.get("severity", "medium"),
                "title": c.get("title"),
                "detail": c.get("challenge"),
                "sources": ["red_team"],
                "suggested_action": c.get("suggested_action"),
                "requires_review": c.get("severity") == "high",
            }
        )

    seen_titles: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for issue in sorted(
        unified_issues,
        key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("severity", "low"), 9),
    ):
        key = (issue.get("title") or "")[:80]
        if key in seen_titles:
            continue
        seen_titles.add(key)
        deduped.append(issue)

    report = {
        "version": "1.0",
        "generated_at": _utcnow_iso(),
        "user_id": user_id,
        "debate": {
            "analyst": analyst,
            "red_team": red_team,
            "resolution": "Red Team 挑战已合并入 unified_issues；高风险项须 Human Gate 确认",
        },
        "knowledge_snapshot": {
            "text_sources": len(knowledge.get("texts") or []),
            "checklist_items": len(knowledge.get("checklist_items") or []),
            "contracts": len(knowledge.get("contract_summaries") or []),
        },
        "unified_issues": deduped,
        "issue_count": len(deduped),
        "high_count": sum(1 for i in deduped if i.get("severity") == "high"),
        "disclaimer": "项目 intelligence 为 AI 辅助统摄，不构成法律意见；须律师定稿。",
    }

    ensure_project_hub(payload)
    payload["project_intelligence"] = report
    payload["conflict_flags"] = cross_flags
    payload["project_hub"]["modules"]["intelligence"] = {
        "label": "项目统摄",
        "status": "analyzed",
        "last_analyzed_at": report["generated_at"],
        "issue_count": report["issue_count"],
        "high_count": report["high_count"],
    }
    return report
