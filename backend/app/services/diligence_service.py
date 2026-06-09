"""Due diligence workflow linked to project investigation context."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.services.document_extractor import read_upload_text
from app.services.project_hub_service import project_context

DD_CATEGORIES = [
    {"id": "corporate", "label": "公司主体与股权", "keywords": ["contrato social", "bylaws", "章程", "股权", "quota", "CADE"]},
    {"id": "real_estate", "label": "土地与厂房", "keywords": ["imóvel", "matrícula", "土地", "厂房", "zoneamento", "alvará"]},
    {"id": "environment", "label": "环境许可", "keywords": ["licença ambiental", "IBAMA", "EIA", "环评", "LP", "LO"]},
    {"id": "labor", "label": "劳动用工", "keywords": ["CLT", "emprego", "劳动", "FGTS", "工会"]},
    {"id": "tax", "label": "税务", "keywords": ["ICMS", "tax", "税务", "fiscal", "CND"]},
    {"id": "litigation", "label": "诉讼与合规", "keywords": ["processo", "litígio", "诉讼", "multa", "ANPD"]},
    {"id": "contracts", "label": "重大合同", "keywords": ["contrato", "supply", "lease", "合同", "供应"]},
]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _categorize_text(text: str) -> list[str]:
    found: list[str] = []
    lower = text.lower()
    for cat in DD_CATEGORIES:
        if any(kw.lower() in lower for kw in cat["keywords"]):
            found.append(cat["id"])
    return found or ["general"]


def upload_diligence_document(
    payload: dict[str, Any],
    *,
    filename: str,
    content: bytes,
    doc_category: Optional[str] = None,
) -> dict[str, Any]:
    from app.services.project_hub_service import ensure_project_hub

    ensure_project_hub(payload)
    text = read_upload_text(filename, content)
    cats = [doc_category] if doc_category else _categorize_text(text)
    doc_id = uuid.uuid4().hex[:16]
    doc = {
        "id": doc_id,
        "filename": filename,
        "categories": cats,
        "size": len(content),
        "char_count": len(text),
        "uploaded_at": _utcnow_iso(),
        "text_preview": text[:400],
    }
    payload["project_hub"]["modules"]["diligence"].setdefault("documents", []).append(doc)
    payload.setdefault("_diligence_texts", {})[doc_id] = text
    payload["project_hub"]["modules"]["diligence"]["status"] = "uploaded"
    return doc


def run_diligence_analysis(
    payload: dict[str, Any],
    scenario: Any,
    *,
    user_id: Optional[int] = None,
) -> dict[str, Any]:
    from app.services.project_hub_service import ensure_project_hub

    ensure_project_hub(payload)
    ctx = project_context(payload, scenario)
    texts = payload.get("_diligence_texts") or {}
    docs = payload["project_hub"]["modules"]["diligence"].get("documents") or []
    issues: list[dict[str, Any]] = []

    inv = ctx.get("investigation_summary") or {}
    for code in inv.get("s3_blocked_codes") or []:
        title = next((t["title"] for t in ctx.get("checklist_titles") or [] if t.get("code") == code), code)
        issues.append(
            {
                "id": f"inv-s3-{code}",
                "severity": "high",
                "category": "investigation_gap",
                "title": f"协查 S3 未决：{code}",
                "description": f"投资协查项「{title}」处于硬阻断，DD 须核实 supporting documents 是否补齐。",
                "source": "investigation_module",
                "evidence": [],
                "requires_review": True,
            }
        )

    for code in inv.get("zero_hit_items") or []:
        issues.append(
            {
                "id": f"inv-zero-{code}",
                "severity": "medium",
                "category": "legal_source_gap",
                "title": f"法源零命中：{code}",
                "description": "协查阶段未找到足够法源依据，尽调应重点收集对应许可/批复原件。",
                "source": "investigation_module",
                "evidence": [],
                "requires_review": True,
            }
        )

    checklist_codes = {t.get("code") for t in ctx.get("checklist_titles") or []}
    doc_cats: set[str] = set()
    for doc in docs:
        doc_cats.update(doc.get("categories") or [])
        text = texts.get(doc.get("id", ""), "")
        flags = _extract_dd_flags(text, doc.get("filename", ""))
        for flag in flags:
            flag["document_id"] = doc["id"]
            flag["document_name"] = doc["filename"]
            issues.append(flag)

    for cat in DD_CATEGORIES:
        if cat["id"] in ("general",):
            continue
        related_check = any(
            any(kw.lower() in (t.get("title") or "").lower() for kw in cat["keywords"])
            for t in ctx.get("checklist_titles") or []
        )
        if related_check and cat["id"] not in doc_cats:
            issues.append(
                {
                    "id": f"missing-doc-{cat['id']}",
                    "severity": "medium",
                    "category": "document_gap",
                    "title": f"可能缺失：{cat['label']} 支持文件",
                    "description": f"协查清单涉及 {cat['label']}，但 uploaded DD 包中未见该类文档。",
                    "source": "cross_module_inference",
                    "evidence": [],
                    "requires_review": True,
                }
            )

    contract_mod = (payload.get("project_hub") or {}).get("modules", {}).get("contracts", {})
    for cdoc in contract_mod.get("documents") or []:
        analysis = cdoc.get("analysis") or {}
        if analysis.get("red_count", 0) > 0:
            issues.append(
                {
                    "id": f"contract-red-{cdoc.get('id')}",
                    "severity": "high",
                    "category": "contract_risk",
                    "title": f"合同 RED 条款：{cdoc.get('filename')}",
                    "description": f"合同审查发现 {analysis.get('red_count')} 条 RED，须在 DD 报告中披露。",
                    "source": "contracts_module",
                    "evidence": [{"type": "contract", "doc_id": cdoc.get("id")}],
                    "requires_review": True,
                }
            )

    issues.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("severity", "low"), 9))
    summary = {
        "analyzed_at": _utcnow_iso(),
        "document_count": len(docs),
        "issue_count": len(issues),
        "high_count": sum(1 for i in issues if i.get("severity") == "high"),
        "cross_module": True,
        "disclaimer": "尽调 issue list 为 AI 辅助线索，须律师核实证据与法律结论。",
    }
    payload["project_hub"]["modules"]["diligence"]["issues"] = issues
    payload["project_hub"]["modules"]["diligence"]["status"] = "analyzed"
    payload["project_hub"]["modules"]["diligence"]["last_analyzed_at"] = summary["analyzed_at"]
    payload["diligence_report"] = {"summary": summary, "issues": issues}
    return {"summary": summary, "issues": issues}


def _extract_dd_flags(text: str, filename: str) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    lower = (text + " " + filename).lower()
    patterns = [
        (r"pendente|pending|未获|待批", "high", "许可/批复存在 pending 表述"),
        (r"multa|fine|罚款|sanção", "medium", "存在处罚/罚款相关表述"),
        (r"litígio|processo judicial|诉讼", "medium", "涉及诉讼/司法程序"),
        (r"passivo|liability|债务|passivo trabalhista", "high", "潜在债务/劳动负债表述"),
        (r"revogad|cancelad|失效", "high", "许可或批文可能存在失效/revoked 风险"),
    ]
    for pat, sev, desc in patterns:
        if re.search(pat, lower, re.I):
            excerpt = text[:300].replace("\n", " ")
            flags.append(
                {
                    "id": uuid.uuid4().hex[:12],
                    "severity": sev,
                    "category": "document_signal",
                    "title": desc,
                    "description": f"在文档「{filename}」中检测到风险信号，须人工核对上下文。",
                    "source": "document_nlp",
                    "evidence": [{"excerpt": excerpt}],
                    "requires_review": True,
                }
            )
            break
    return flags
