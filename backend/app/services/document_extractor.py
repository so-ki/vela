from __future__ import annotations

import io
import re
from typing import Any, Optional

import httpx
from docx import Document

from app.core.config import get_settings
from app.services.intent_parser import _extract_json
from app.services.llm_client import get_llm_config

MAX_BYTES = 2 * 1024 * 1024
ALLOWED_SUFFIXES = {".txt", ".md", ".docx"}

VALID_DIMENSIONS = ["labor", "foreign_investment", "tax", "industry_access"]

DIMENSION_KEYWORDS: dict[str, list[str]] = {
    "labor": ["雇员", "员工", "用工", "CLT", "工会", "外派", "岗位"],
    "foreign_investment": ["外资", "子公司", "100%", "全资", "合资", "CNPJ", "投资结构"],
    "tax": ["税", "ICMS", "关税", "激励", "PADIS", "进口设备"],
    "industry_access": ["许可", "环评", "厂房", "认证", "电池", "客车", "光伏", "储能", "设厂", "制造"],
}

EXTRACT_SYSTEM = """你是 Vela 出海法务平台的文档事实抽取助手。
任务：从用户上传的中文投资/设厂方案材料中，抽取可填入协查表单的客观事实。

硬性规则：
1. 仅输出 JSON，不要 markdown
2. 只抽取文档中明确出现的信息，不得编造法条、风险结论或未提及的数字
3. description 用 3～6 句中文概括项目（地点、产品、规模、计划），可直接作为业务描述
4. compliance_dimensions 只能从 labor, foreign_investment, tax, industry_access 中选择
5. 若某字段文档未提及，返回 null 或空字符串
6. facts 数组列出每条抽取事实，含 field、value、source_snippet（原文短引≤40字）

JSON 格式：
{
  "project_name": "",
  "investment_structure": "",
  "description": "",
  "employee_count": null,
  "capacity_notes": "",
  "facility_notes": "",
  "remarks": "",
  "compliance_dimensions": [],
  "facts": [{"field":"employee_count","value":"450","source_snippet":"..."}]
}"""


def read_upload_text(filename: str, content: bytes) -> str:
    suffix = _suffix(filename)
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"仅支持 {', '.join(sorted(ALLOWED_SUFFIXES))} 文件")

    if len(content) > MAX_BYTES:
        raise ValueError("文件大小不能超过 2MB")

    if suffix in {".txt", ".md"}:
        for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
            try:
                return content.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
        raise ValueError("无法识别文本编码，请使用 UTF-8 保存")

    doc = Document(io.BytesIO(content))
    parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("Word 文档未读取到有效文本，请确认非扫描件图片")
    return text


def _suffix(filename: str) -> str:
    dot = filename.rfind(".")
    if dot < 0:
        raise ValueError("文件名缺少扩展名")
    return filename[dot:].lower()


def _first_match(patterns: list[str], text: str) -> Optional[str]:
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip()
    return None


def _guess_dimensions(text: str) -> list[str]:
    found = [dim for dim, kws in DIMENSION_KEYWORDS.items() if any(kw in text for kw in kws)]
    return found or list(VALID_DIMENSIONS)


def _append_fact(facts: list[dict[str, Any]], field: str, value: Any, snippet: str) -> None:
    if value is None or value == "":
        return
    facts.append(
        {
            "field": field,
            "value": str(value),
            "source_snippet": snippet[:80] if snippet else None,
        }
    )


def extract_facts_rule_based(text: str) -> dict[str, Any]:
    facts: list[dict[str, Any]] = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    project_name = _first_match(
        [
            r"(?:项目名称|项目名|Project)[:：]\s*(.+)",
            r"^(.{4,60}(?:工厂|项目|设厂|投资).*)$",
        ],
        text,
    )
    if not project_name and lines:
        project_name = lines[0][:80]

    investment_structure = _first_match(
        [
            r"(100%\s*外资[^\n]{0,40})",
            r"(中资[^。\n]{0,20}全资[^。\n]{0,30})",
            r"(合资[^。\n]{0,40})",
            r"(?:投资结构)[:：]\s*(.+)",
        ],
        text,
    )

    emp_match = re.search(
        r"(?:约|大约|预计)?\s*(\d{2,5})\s*(?:名|个)?\s*(?:本地|新的)?(?:就业|雇员|员工|岗位|人)",
        text,
    )
    employee_count = int(emp_match.group(1)) if emp_match else None
    if emp_match:
        _append_fact(facts, "employee_count", employee_count, emp_match.group(0))

    capacity_notes = _first_match(
        [
            r"((?:首年|年产|年产能|产能)[^。\n]{0,60})",
            r"(\d+\s*台[^。\n]{0,40})",
            r"(\d+\s*MW[^。\n]{0,30})",
        ],
        text,
    )
    if capacity_notes:
        _append_fact(facts, "capacity_notes", capacity_notes, capacity_notes)

    facility_notes = _first_match(
        [
            r"((?:占地|厂房)[^。\n]{0,80})",
            r"(\d[\d,]*\s*(?:m²|平方米)[^。\n]{0,40})",
        ],
        text,
    )
    if facility_notes:
        _append_fact(facts, "facility_notes", facility_notes, facility_notes)

    if project_name:
        _append_fact(facts, "project_name", project_name, project_name)
    if investment_structure:
        _append_fact(facts, "investment_structure", investment_structure, investment_structure)

    description = text if len(text) <= 1200 else text[:1200].rstrip() + "…"
    if len(description) >= 10:
        _append_fact(facts, "description", "（见业务描述）", description[:60])

    dims = _guess_dimensions(text)
    return {
        "mode": "rules",
        "project_name": project_name,
        "investment_structure": investment_structure,
        "description": description if len(description) >= 10 else None,
        "employee_count": employee_count,
        "capacity_notes": capacity_notes,
        "facility_notes": facility_notes,
        "remarks": "由上传方案自动抽取（规则模式），提交前请人工核对。",
        "compliance_dimensions": dims,
        "facts": facts,
        "disclaimer": "抽取结果仅供预填表单，不构成法律意见；请人工核对后再提交。",
        "llm_skipped": None,
    }


def extract_facts_llm(text: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    cfg = get_llm_config()
    if not cfg or not get_settings().llm_polish_enabled:
        return None, "未配置 LLM，使用规则抽取"

    clipped = text[:6000]
    prompt = f"请从以下方案材料抽取事实并返回 JSON：\n\n{clipped}"

    try:
        url = f"{cfg['base_url']}/chat/completions"
        body = {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
                json=body,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
        parsed = _extract_json(raw)
        dims = [d for d in parsed.get("compliance_dimensions", []) if d in VALID_DIMENSIONS]
        if not dims:
            dims = _guess_dimensions(text)
        desc = (parsed.get("description") or "").strip()
        return {
            "mode": "llm",
            "project_name": (parsed.get("project_name") or "").strip() or None,
            "investment_structure": (parsed.get("investment_structure") or "").strip() or None,
            "description": desc if len(desc) >= 10 else None,
            "employee_count": parsed.get("employee_count"),
            "capacity_notes": (parsed.get("capacity_notes") or "").strip() or None,
            "facility_notes": (parsed.get("facility_notes") or "").strip() or None,
            "remarks": (parsed.get("remarks") or "").strip() or "由上传方案 AI 抽取，提交前请人工核对。",
            "compliance_dimensions": dims,
            "facts": parsed.get("facts", [])[:20],
            "disclaimer": "AI 抽取结果仅供预填表单，不构成法律意见；须人工核对后再提交。",
            "llm_skipped": None,
        }, None
    except Exception as exc:
        return None, str(exc)[:200]


def extract_facts_from_document(filename: str, content: bytes) -> dict[str, Any]:
    text = read_upload_text(filename, content)
    if len(text) < 20:
        raise ValueError("文档内容过短，请上传包含完整项目说明的材料")

    llm_result, llm_err = extract_facts_llm(text)
    if llm_result and llm_result.get("description"):
        if llm_err:
            llm_result["llm_skipped"] = llm_err
        return llm_result

    rule_result = extract_facts_rule_based(text)
    if llm_err:
        rule_result["llm_skipped"] = llm_err
    return rule_result
