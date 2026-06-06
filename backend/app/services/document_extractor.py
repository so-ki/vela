from __future__ import annotations

import io
import re
from typing import Any, Optional

import httpx
from docx import Document
from pypdf import PdfReader

from app.core.config import get_settings
from app.services.intent_parser import _extract_json
from app.services.llm_client import get_llm_config

MAX_BYTES = 200 * 1024 * 1024
MAX_BATCH_FILES = 50
MAX_BATCH_TOTAL_BYTES = MAX_BYTES * 10
ALLOWED_SUFFIXES = {".txt", ".md", ".docx", ".pdf"}

VALID_DIMENSIONS = ["labor", "foreign_investment", "tax", "environment", "industry_access"]

DIMENSION_KEYWORDS: dict[str, list[str]] = {
    "labor": ["雇员", "员工", "用工", "CLT", "工会", "外派", "岗位"],
    "foreign_investment": ["外资", "子公司", "100%", "全资", "合资", "CNPJ", "投资结构", "并购", "CADE"],
    "tax": ["税", "ICMS", "关税", "激励", "PADIS", "进口设备"],
    "environment": ["环评", "EIA", "IBAMA", "环境", "排放", "危废", "PNRS", "RIMA"],
    "industry_access": ["许可", "厂房", "认证", "电池", "客车", "光伏", "储能", "设厂", "制造", "Alvará", "INMETRO"],
}

EXTRACT_SYSTEM = """你是 Vela 出海法务平台的文档事实抽取助手。
任务：从用户上传的中文巴西投资方案材料中，抽取可填入「协查材料核对表」的事实。
核对表对应企业境外投资方案中业务侧应确认的项目事实（非法律结论；不限于设厂场景）。

核对表字段（须尽量全部填满，格式简洁、可直接展示）：
- project_name：项目名称（完整官方名称）
  · 只取【项目名称】或「项目名称：」后的正式名称
  · 禁止把「参考案例」「业务描述」等模板标题当作项目名称
- investment_destination：投资目的地（国家/州/城市，如「巴西圣保罗州坎皮纳斯市」）
  · 只取【投资目的地】或「国家/州/市」等标签后的地点
  · 禁止截取业务描述里的叙事句（如「已被选为…所在地」）
- investment_structure：投资结构（投资主体、股权层级、外资比例，如「中资母公司通过巴西全资子公司投资，100% 外资」）
- funding_source：资金来源（自有/贷款/发债/实物出资等；文档未写则 null）
- project_content_scale：主要内容（一句话概括建设内容）
- facility_notes：规模（含面积、产能或投资规模等，如「厂房 32,000 m² + 20,000 m²；含研发中心」）
- capacity_notes：产能说明（一句话，如「首年最多 1000 台电动客车及配套电池」）
- employee_count：雇员规模（整数，单位：人）
- description：业务描述（3～6 句连贯中文，概括地点、产品、规模、计划、补充规划）
  · 只写项目实质，禁止包含「参考案例」「案例一/二/三」「【业务描述】」等模板/目录标题
  · 若文档含多个案例，只抽取其中一个案例的正文段落，不要拼接案例标题
  · 文档中「备注/补充说明」段落内容并入本字段，不要单独输出
- known_risks：已知风险与关注事项（须来自文档中明确标注的风险/关注段落；无则 null）
- board_date：董事会日期（YYYY-MM-DD；无则 null）
- start_date：预计开工日期（YYYY-MM-DD；无则 null）
- production_date：预计投产日期（YYYY-MM-DD；无则 null）

硬性规则：
1. 仅输出 JSON，不要 markdown
2. 只抽取文档中明确出现的信息，不得编造法条、风险结论或未提及的数字
3. compliance_dimensions 只能从 labor, foreign_investment, tax, environment, industry_access 中选择
4. 若某字段文档未提及，返回 null 或空字符串
5. facts 数组为每个已填字段提供依据：field、value、source_snippet（原文短引≤40字）

JSON 格式：
{
  "project_name": "",
  "investment_destination": "",
  "investment_structure": "",
  "funding_source": "",
  "project_content_scale": "",
  "facility_notes": "",
  "capacity_notes": "",
  "employee_count": null,
  "description": "",
  "known_risks": "",
  "board_date": null,
  "start_date": null,
  "production_date": null,
  "compliance_dimensions": [],
  "facts": [{"field":"employee_count","value":"450","source_snippet":"创造约450名新的就业岗位"}]
}"""


def read_upload_text(filename: str, content: bytes) -> str:
    suffix = _suffix(filename)
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"仅支持 {', '.join(sorted(ALLOWED_SUFFIXES))} 文件")

    if len(content) > MAX_BYTES:
        raise ValueError("文件大小不能超过 200MB")

    if suffix in {".txt", ".md"}:
        for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
            try:
                return content.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
        raise ValueError("无法识别文本编码，请使用 UTF-8 保存")

    if suffix == ".pdf":
        return _read_pdf_text(content)

    doc = Document(io.BytesIO(content))
    parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("Word 文档未读取到有效文本，请确认非扫描件图片")
    return text


def _read_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception as exc:
        raise ValueError("无法解析 PDF 文件，请确认文件未损坏") from exc

    parts: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            parts.append(page_text.strip())

    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("PDF 未读取到有效文本，请确认非扫描件图片或使用 Word/文本格式")
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


def _extract_labeled_value(text: str, labels: list[str]) -> Optional[str]:
    for label in labels:
        bracket = re.search(
            rf"【{re.escape(label)}】\s*\n?\s*(.+?)(?=\n\s*【|\Z)",
            text,
            flags=re.DOTALL,
        )
        if bracket:
            value = _clean_single_line_value(bracket.group(1))
            if value:
                return value

        inline = re.search(rf"【{re.escape(label)}】\s*([^\n【]+)", text)
        if inline:
            value = _clean_single_line_value(inline.group(1))
            if value:
                return value

        m = re.search(rf"(?:{re.escape(label)})[:：]\s*(.+?)(?:\n|$)", text)
        if m:
            value = _clean_single_line_value(m.group(1))
            if value:
                return value
    return None


def _clean_single_line_value(raw: str) -> str:
    line = raw.strip().splitlines()[0].strip()
    line = line.strip("「」\"“”")
    return line.rstrip("。")


def _looks_like_junk_project_name(value: str) -> bool:
    if not value or len(value) < 2:
        return True
    if _looks_like_template_description(value):
        return True
    if re.search(r"业务描述|参考案例|案例[一二三四五六七八九十\d]+", value):
        return True
    if re.search(
        r"方案书|PROPOSAL|报告类型|目标国家|\.pdf|商业方案|直接投资（FDI）|市场准入",
        value,
        flags=re.IGNORECASE,
    ):
        return True
    if value.startswith("【") or value.endswith("】"):
        return True
    return False


def _looks_like_narrative_snippet(value: str) -> bool:
    if not value:
        return False
    return bool(
        re.search(
            r"已被选(?:为|定)?|该项目|预计|创造.*(?:就业|岗位)|制造基地所在地|"
            r"不仅将|还将生产|首年规划|拉美制造基地",
            value,
        )
    )


def _format_investment_destination(value: str) -> Optional[str]:
    cleaned = _clean_single_line_value(value)
    if not cleaned or _looks_like_narrative_snippet(cleaned):
        return None
    if len(cleaned) > 80:
        return None

    if re.search(r"[/／]", cleaned):
        parts = [part.strip() for part in re.split(r"\s*[/／]\s*", cleaned) if part.strip()]
        if len(parts) >= 3:
            country, state, city = parts[0], parts[1], parts[2]
            if not city.endswith("市"):
                city = f"{city}市"
            return f"{country}{state}{city}"[:120]
        if len(parts) == 2:
            return f"{parts[0]}{parts[1]}"[:120]

    if re.fullmatch(r"巴西[^。\n]{2,40}", cleaned) and not _looks_like_narrative_snippet(cleaned):
        return cleaned[:120]
    return cleaned[:120] if len(cleaned) <= 40 and not _looks_like_narrative_snippet(cleaned) else None


def _extract_project_name_from_narrative(text: str) -> Optional[str]:
    patterns = [
        r"本项目(?:拟|计划|将)?(?:在[^，。；\n]{0,40})?(?:设立|建设|投资成立|成立|打造)(?:一个|一座|一处)?([^，。；\n]{2,40}(?:研发中心|制造基地|组装厂|储能系统|工厂|项目|产线|有限公司))",
        r"主要内容和规模[：:]\s*([^，。；\n]{2,40}(?:工厂|项目|中心|基地|产线))",
        r"项目(?:简称|名称)[：:]\s*([^\n【]{2,40})",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        name = _clean_single_line_value(m.group(1))
        if name and not _looks_like_junk_project_name(name):
            return name[:80]
    return None


def _normalize_project_name(raw: Optional[str], text: str) -> Optional[str]:
    candidates: list[str] = []
    labeled = _extract_labeled_value(
        text,
        ["项目名称", "项目名", "项目简称", "拟定项目名称", "Project Name"],
    )
    if labeled:
        candidates.append(labeled)
    if raw:
        candidates.append(raw.strip())

    for candidate in candidates:
        cleaned = _clean_single_line_value(candidate)
        if cleaned and not _looks_like_junk_project_name(cleaned):
            return cleaned[:80]

    narrative = _extract_project_name_from_narrative(text)
    if narrative:
        return narrative
    return None


def _normalize_investment_destination(raw: Optional[str], text: str) -> Optional[str]:
    candidates: list[str] = []
    labeled = _extract_labeled_value(
        text,
        ["投资目的地", "项目地点", "建设地点", "所在城市", "投资地点", "国家/州/市", "国家/州/城市"],
    )
    if labeled:
        candidates.append(labeled)
    if raw:
        candidates.append(raw.strip())

    for candidate in candidates:
        formatted = _format_investment_destination(candidate)
        if formatted:
            return formatted

    m = re.search(
        r"(巴西(?:圣保罗州|圣保罗)[^。\n]{0,24}(?:里贝朗普雷图|坎皮纳斯|Campinas|Ribeirão)[^。\n]{0,12})",
        text,
        flags=re.IGNORECASE,
    )
    if m and not _looks_like_narrative_snippet(m.group(1)):
        formatted = _format_investment_destination(m.group(1))
        if formatted:
            return formatted

    if "坎皮纳斯" in text or "Campinas" in text:
        return "巴西圣保罗州坎皮纳斯市"
    return None


def _extract_section_body(text: str, headings: list[str]) -> Optional[str]:
    for heading in headings:
        m = re.search(
            rf"{re.escape(heading)}\s*[：:]?\s*\n(.*?)(?:\n(?:[一二三四五六七八九十]+、|[^\n]{{2,30}}[：:])|\Z)",
            text,
            flags=re.DOTALL,
        )
        if m:
            body = re.sub(r"\s+", " ", m.group(1).strip())
            if len(body) >= 10:
                return body
    return None


def _looks_like_template_description(text: str) -> bool:
    return bool(
        re.search(
            r"参考案例|案例[一二三四五六七八九十\d]+[：:]|【业务描述】|"
            r"直接投资方案业务描述|Business Description \(Reference",
            text,
            flags=re.IGNORECASE,
        )
    )


def _sanitize_description_sentences(raw: str) -> str:
    text = raw.strip()
    for noise in (
        r"^巴西直接投资方案业务描述（参考案例）\s*",
        r"^案例[一二三四五六七八九十\d]+[：:][^\n。]{0,80}",
        r"^【业务描述】\s*",
        r"^Business Description \(Reference Case\)\s*",
    ):
        text = re.sub(noise, "", text, flags=re.IGNORECASE)
    text = re.sub(r"[「」\"“”]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""

    sentences: list[str] = []
    for part in re.split(r"(?<=[。！？])", text):
        sent = part.strip()
        if len(sent) < 12:
            continue
        if _looks_like_template_description(sent):
            continue
        if re.match(r"^(案例|参考|【)", sent):
            continue
        sentences.append(sent)

    if sentences:
        return "".join(sentences[:6])[:1200]

    cleaned = text
    for noise in (
        r"巴西直接投资方案业务描述（参考案例）",
        r"【业务描述】",
        r"案例[一二三四五六七八九十\d]+[：:][^。]*",
    ):
        cleaned = re.sub(noise, "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:1200]


def _collapse_soft_line_breaks(text: str) -> str:
    """将段落内软换行合并为空格，保留空行分段。"""
    normalized = re.sub(r"\r\n?", "\n", text)
    paragraphs = re.split(r"\n\s*\n", normalized)
    return "\n\n".join(re.sub(r"\n+", " ", p).strip() for p in paragraphs)


def _extract_description_from_markers(text: str) -> Optional[str]:
    text = _collapse_soft_line_breaks(text)
    patterns = [
        r"【业务描述】\s*[「\"“]?([^」\"”\n]{40,1200})",
        r"业务描述[：:]\s*[「\"“]?([^」\"”\n]{40,1200})",
        r"项目说明[：:]\s*\n?([^」\"”\n]{20,1200})",
        r"项目背景[：:]\s*\n?([^」\"”\n]{20,1200})",
        r"投资概述[：:]\s*\n?([^」\"”\n]{20,1200})",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        body = m.group(1).strip()
        body = re.split(r"\n案例[一二三四五六七八九十\d]+", body)[0]
        cleaned = _sanitize_description_sentences(body)
        if len(cleaned) >= 20 and not _looks_like_template_description(cleaned):
            return cleaned
    return None


def _extract_description_from_case_blocks(text: str, project_name: Optional[str] = None) -> Optional[str]:
    blocks = re.split(r"(?=案例[一二三四五六七八九十\d]+[：:])", text)
    if len(blocks) <= 1:
        return None

    scored: list[tuple[int, str]] = []
    for block in blocks[1:]:
        marker_body = _extract_description_from_markers(block)
        if marker_body:
            score = 10
            if project_name and project_name[:4] in block:
                score += 20
            scored.append((score, marker_body))
            continue

        m = re.search(
            r"([「\"“][^」\"”]{40,900}[」\"”])|((?:巴西|本项目|该项目)[^。\n]{40,900}(?:。[^。\n]{0,200}){1,4})",
            block,
        )
        if not m:
            continue
        body = (m.group(1) or m.group(2) or "").strip().strip("「」\"“”")
        cleaned = _sanitize_description_sentences(body)
        if len(cleaned) < 20:
            continue
        score = 5
        if project_name and project_name[:4] in block:
            score += 20
        scored.append((score, cleaned))

    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def _merge_description_parts(*parts: Optional[str]) -> Optional[str]:
    seen: set[str] = set()
    sentences: list[str] = []
    for part in parts:
        if not part:
            continue
        cleaned = _sanitize_description_sentences(part.strip())
        if len(cleaned) < 12 or _looks_like_template_description(cleaned):
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        sentences.append(cleaned)
    if not sentences:
        return None
    merged = "".join(sentences)
    return merged[:1200]


def _normalize_description(
    raw: Optional[str],
    text: str = "",
    project_name: Optional[str] = None,
) -> Optional[str]:
    # Prefer structured extraction from the document over raw LLM text (often includes template headers).
    candidates: list[str] = []
    marker = _extract_description_from_markers(text)
    if marker:
        candidates.append(marker)
    case_body = _extract_description_from_case_blocks(text, project_name)
    if case_body:
        candidates.append(case_body)
    narrative = _extract_narrative_section(text)
    if narrative:
        candidates.append(narrative)
    if raw and not _looks_like_template_description(raw):
        candidates.append(raw)

    for candidate in candidates:
        cleaned = _sanitize_description_sentences(candidate)
        if len(cleaned) >= 20 and not _looks_like_template_description(cleaned):
            return cleaned
    return None


def _extract_narrative_section(text: str) -> Optional[str]:
    text = _collapse_soft_line_breaks(text)
    section = _extract_section_body(
        text,
        [
            "项目说明",
            "项目背景",
            "投资概述",
            "四、项目描述",
            "四、业务描述",
            "项目描述",
            "一、项目概况",
            "项目概况",
        ],
    )
    if section and len(section) >= 20:
        return section[:1200]

    narrative = _first_match(
        [
            r"((?:已被选为|已(?:被)?选定为|已确定)[^。\n]{20,900}(?:。[^。\n]{0,200}){0,5})",
            r"((?:本项目|该项目)[^。\n]{40,900}(?:。[^。\n]{0,200}){1,5})",
            r"((?:巴西)[^\n]{30,1500})",
            r"(巴西[^。\n]{40,900}(?:。[^。\n]{0,200}){2,4})",
        ],
        text,
    )
    if narrative and len(narrative) >= 20:
        return narrative[:1200]
    return None


def _extract_supplementary_description(text: str) -> Optional[str]:
    """仅从显式「备注/补充说明」段落抽取，并入业务描述；禁止模板臆造。"""
    section = _extract_section_body(text, ["备注", "补充说明", "七、备注", "其他说明"])
    if not section:
        return None
    cleaned = section.strip()
    if not cleaned or len(cleaned) < 8:
        return None
    if re.search(r"Vela 平台|仅供演示|请人工核对|自动抽取", cleaned):
        return None
    return cleaned[:500]


def _extract_narrative_description(text: str, project_name: Optional[str] = None) -> Optional[str]:
    return _normalize_description(None, text, project_name)


def _finalize_extract_result(result: dict[str, Any], text: str) -> dict[str, Any]:
    project_name = _normalize_project_name(result.get("project_name"), text)
    result["project_name"] = project_name

    investment_destination = _normalize_investment_destination(result.get("investment_destination"), text)
    result["investment_destination"] = investment_destination

    normalized_desc = _merge_description_parts(
        _normalize_description(result.get("description"), text, project_name),
        _extract_supplementary_description(text),
    )
    result["description"] = normalized_desc
    result["remarks"] = None

    kr = (result.get("known_risks") or "").strip()
    if _looks_like_junk_known_risks(kr):
        result["known_risks"] = None
    elif _is_empty_risk_placeholder(kr):
        result["known_risks"] = None

    facility = (result.get("facility_notes") or "").strip()
    if _looks_like_junk_facility_notes(facility):
        result["facility_notes"] = None

    facts = list(result.get("facts") or [])
    facts = [
        f
        for f in facts
        if not (
            isinstance(f, dict)
            and f.get("field") in {"description", "project_name", "investment_destination", "facility_notes"}
        )
    ]

    if project_name:
        _append_fact(facts, "project_name", project_name, project_name[:80])
    if investment_destination:
        _append_fact(facts, "investment_destination", investment_destination, investment_destination[:80])
    if normalized_desc:
        _append_fact(facts, "description", "（见业务描述）", normalized_desc[:80])
    facility_notes = result.get("facility_notes")
    if facility_notes:
        _append_fact(facts, "facility_notes", facility_notes, facility_notes[:80])
    result["facts"] = facts[:24]
    return result


def _normalize_capacity_notes(raw: Optional[str], text: str = "") -> Optional[str]:
    combined = re.sub(r"\s+", " ", f"{raw or ''} {text or ''}").strip()
    if not combined:
        return None
    bus = re.search(r"(\d+)\s*辆(?:电动)?(?:大巴|客车)", combined) or re.search(
        r"最高\s*(\d+)\s*辆(?:电动)?(?:大巴|客车)", combined
    )
    if bus:
        return f"首年最多 {bus.group(1)} 台电动客车及配套电池"
    cleaned = re.sub(r"^产能(?:规划|说明)?[:：]\s*", "", (raw or combined).strip())
    m = re.search(r"首年[^。\n]{0,80}", cleaned)
    if m:
        return m.group(0).strip()
    m = re.search(r"\d+\s*MW[^。\n]{0,30}", combined)
    if m:
        return m.group(0).strip()
    if len(cleaned) < 6 or cleaned in {"产能", "产能力", "产能说明", "产能规划"}:
        return None
    return cleaned[:80] if cleaned else None


def _looks_like_junk_facility_notes(value: str) -> bool:
    if not value or len(value.strip()) < 4:
        return True
    text = value.strip()
    if re.search(
        r"方案书|PROPOSAL|报告类型|目标国家|\.pdf|商业方案|直接投资（FDI）|"
        r"市场准入|投资规划方案|Federative Republic",
        text,
        flags=re.IGNORECASE,
    ):
        return True
    has_area = bool(re.search(r"\d[\d,]*\s*(?:m²|平方米|平米|亩)", text))
    has_facility_context = bool(re.search(r"厂房|占地|用地|车间|仓库|研发中心", text))
    if not has_area and not (has_facility_context and re.search(r"\d", text)):
        return True
    return False


def _normalize_facility_notes(raw: Optional[str], text: str = "") -> Optional[str]:
    if not raw or not raw.strip():
        return None

    cleaned = re.sub(r"^厂房(?:设施|说明|面积)?[:：]\s*", "", raw.strip())
    cleaned = re.sub(r"^占地[:：]\s*", "", cleaned).strip()
    if not cleaned or _looks_like_junk_facility_notes(cleaned):
        return None

    combined = re.sub(r"\s+", " ", f"{cleaned} {text or ''}").strip()
    areas = re.findall(r"(\d[\d,]*\s*(?:m²|平方米|平米|亩))", combined)
    unique_areas: list[str] = []
    for area in areas:
        normalized = re.sub(r"\s+", " ", area.strip())
        if normalized not in unique_areas:
            unique_areas.append(normalized)
    if len(unique_areas) >= 2:
        base = f"厂房 {unique_areas[0]} + {unique_areas[1]}"
        if any(k in combined for k in ("研发", "中心")):
            return f"{base}；含研发中心"
        return base
    if len(unique_areas) == 1:
        note = cleaned
        if "厂房" not in note and "占地" not in note:
            note = f"厂房 {unique_areas[0]}"
        if any(k in combined for k in ("研发", "中心")) and "研发" not in note:
            return f"{note}；含研发中心"
        return note[:120]
    m = re.search(r"((?:占地|厂房|用地)[^。\n]{0,80}\d[\d,]*\s*(?:m²|平方米|平米|亩)[^。\n]{0,20})", cleaned)
    if m:
        note = m.group(1).strip()
        if any(k in combined for k in ("研发", "中心")) and "研发" not in note:
            return f"{note}；含研发中心"
        return note[:120]
    if re.search(r"(?:厂房|占地|用地)", cleaned) and re.search(r"\d", cleaned):
        return cleaned[:120]
    return None


def _normalize_date(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    text = raw.strip()
    m = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", text)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def _extract_date_field(text: str, labels: list[str]) -> Optional[str]:
    for label in labels:
        m = re.search(
            rf"(?:{re.escape(label)})[:：]?\s*(\d{{4}}[-/年]\d{{1,2}}[-/月]\d{{1,2}})",
            text,
        )
        if m:
            normalized = _normalize_date(m.group(1))
            if normalized:
                return normalized
    return None


def _extract_investment_destination(text: str) -> Optional[str]:
    return _normalize_investment_destination(None, text)


def _extract_funding_source(text: str) -> Optional[str]:
    labeled = _extract_labeled_value(text, ["资金来源", "出资方式", "投资资金来源", "中方投资额构成"])
    if labeled:
        return labeled.rstrip("。")[:300]

    parts: list[str] = []
    for kw in ("自有资金", "银行贷款", "境内发债", "股东贷款", "实物出资", "融资", "担保"):
        if kw in text:
            parts.append(kw)
    if parts:
        return "、".join(dict.fromkeys(parts))
    return None


def _extract_project_content_scale(text: str) -> Optional[str]:
    labeled = _extract_labeled_value(
        text,
        ["主要内容和规模", "项目规模", "建设规模", "主要内容", "项目内容"],
    )
    if labeled:
        return labeled.rstrip("。")[:300]

    m = re.search(
        r"((?:建设|设立|投资)[^。\n]{0,20}(?:工厂|制造|组装|产线|研发中心)[^。\n]{0,60})",
        text,
    )
    if m:
        return m.group(1).strip()[:200]
    return None


def _is_empty_risk_placeholder(value: Optional[str]) -> bool:
    if not value:
        return True
    text = value.strip()
    if len(text) < 4:
        return True
    if re.fullmatch(r"[【\[]?已知风险[^】\]]*[】\]]?", text):
        return True
    if re.search(r"方案未写|留空|暂无|未提及|（略）|\(略\)", text):
        return True
    if re.search(r"方案未写可留空|业务侧已识别的(?:政策|市场)?/?(?:运营)?/?合规关注点", text):
        return True
    return False


def _looks_like_junk_known_risks(text: str) -> bool:
    if not text or len(text.strip()) < 8:
        return True
    t = text.strip()
    if re.match(r"^[及；。、\d]", t):
        return True
    if re.match(r"^\d+(?:\.\d+)*\s", t):
        return True
    if re.search(r"对冲策略|投资回报潜力|完全可控|风险评估与对冲", t) and not re.search(
        r"已知风险|主要风险|关注事项", t
    ):
        return True
    if len(t) > 400 and t.count("；") >= 4:
        return True
    return False


def _extract_known_risks(text: str) -> Optional[str]:
    labeled = _extract_labeled_value(
        text,
        ["已知风险与关注事项", "已知风险", "主要风险", "关注事项", "不利情况"],
    )
    if labeled and not _is_empty_risk_placeholder(labeled) and not _looks_like_junk_known_risks(labeled):
        return labeled.rstrip("。")[:500]

    section = _extract_section_body(text, ["风险分析", "主要风险", "风险与关注"])
    if section and not _looks_like_junk_known_risks(section):
        return section[:500]

    return None


def _normalize_investment_structure(raw: Optional[str], text: str) -> Optional[str]:
    if raw:
        cleaned = raw.strip().rstrip("。")
        if "100%" in cleaned and "外资" in cleaned and len(cleaned) < 25:
            labeled = _extract_labeled_value(
                text,
                ["投资主体", "投资结构", "投资方式"],
            )
            if labeled and len(labeled) > len(cleaned):
                return labeled.rstrip("。")
        return cleaned

    return _extract_labeled_value(text, ["投资主体", "投资结构", "投资方式"])


def _ensure_facts_from_fields(result: dict[str, Any], text: str) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = list(result.get("facts") or [])
    covered = {f.get("field") for f in facts if isinstance(f, dict)}
    snippets = {
        "project_name": result.get("project_name") or "",
        "investment_destination": result.get("investment_destination") or "",
        "investment_structure": result.get("investment_structure") or "",
        "funding_source": result.get("funding_source") or "",
        "project_content_scale": result.get("project_content_scale") or "",
        "employee_count": str(result.get("employee_count") or ""),
        "capacity_notes": result.get("capacity_notes") or "",
        "facility_notes": result.get("facility_notes") or "",
        "description": (result.get("description") or "")[:60],
        "known_risks": result.get("known_risks") or "",
        "board_date": result.get("board_date") or "",
        "start_date": result.get("start_date") or "",
        "production_date": result.get("production_date") or "",
    }
    for field, value in snippets.items():
        if field in covered or not value:
            continue
        _append_fact(facts, field, value, str(value)[:80])
    return facts[:24]


def extract_facts_rule_based(text: str) -> dict[str, Any]:
    facts: list[dict[str, Any]] = []

    project_name = _normalize_project_name(None, text)

    investment_raw = _extract_labeled_value(text, ["投资主体", "投资结构", "投资方式"]) or _first_match(
        [
            r"(中资[^。\n]{0,40}100%\s*外资[^。\n]{0,20})",
            r"(100%\s*外资[^\n]{0,40})",
            r"(中资[^。\n]{0,20}全资[^。\n]{0,30})",
            r"(合资[^。\n]{0,40})",
        ],
        text,
    )
    investment_structure = _normalize_investment_structure(investment_raw, text)
    investment_destination = _extract_investment_destination(text)
    funding_source = _extract_funding_source(text)
    project_content_scale = _extract_project_content_scale(text)
    known_risks = _extract_known_risks(text)

    board_date = _extract_date_field(text, ["董事会", "投委会", "决策日期", "board"])
    start_date = _extract_date_field(text, ["预计开工", "开工日期", "建设启动"])
    production_date = _extract_date_field(text, ["预计投产", "投产日期", "投产时间"])
    if not production_date:
        year_match = re.search(r"预计于(\d{4})年投产", text)
        if year_match:
            production_date = f"{year_match.group(1)}-01-01"

    emp_match = re.search(
        r"(?:约|大约|预计)?\s*(\d{2,5})\s*(?:名|个)?\s*(?:本地|新的)?(?:就业|雇员|员工|岗位|人)",
        text,
    )
    employee_count = int(emp_match.group(1)) if emp_match else None
    if emp_match:
        _append_fact(facts, "employee_count", employee_count, emp_match.group(0))

    capacity_raw = _extract_labeled_value(text, ["产能规划", "产能说明", "年产能", "产能"]) or _first_match(
        [
            r"((?:首年|年产|年产能|产能)[^。\n]{0,80})",
            r"(\d+\s*台[^。\n]{0,40})",
            r"(\d+\s*MW[^。\n]{0,30})",
        ],
        text,
    )
    capacity_notes = _normalize_capacity_notes(capacity_raw, text)
    if capacity_notes:
        _append_fact(facts, "capacity_notes", capacity_notes, capacity_raw or capacity_notes)

    facility_raw = _extract_labeled_value(
        text,
        ["厂房设施", "厂房说明", "厂房面积", "厂房占地", "用地面积"],
    ) or _first_match(
        [
            r"((?:厂房占地|厂房面积|生产厂房|建设厂房)[^。\n]{0,80})",
            r"((?:占地|用地)\s*约?\s*\d[\d,]*\s*(?:m²|平方米|平米|亩)[^。\n]{0,40})",
            r"(\d[\d,]*\s*(?:m²|平方米)[^。\n]{0,40}(?:厂房|车间|仓库))",
        ],
        text,
    )
    facility_notes = _normalize_facility_notes(facility_raw, text)
    if facility_notes:
        _append_fact(facts, "facility_notes", facility_notes, facility_raw or facility_notes)

    if project_name:
        _append_fact(facts, "project_name", project_name, project_name)
    if investment_structure:
        _append_fact(facts, "investment_structure", investment_structure, investment_structure)
    if investment_destination:
        _append_fact(facts, "investment_destination", investment_destination, investment_destination)
    if funding_source:
        _append_fact(facts, "funding_source", funding_source, funding_source)
    if project_content_scale:
        _append_fact(facts, "project_content_scale", project_content_scale, project_content_scale)
    if known_risks:
        _append_fact(facts, "known_risks", known_risks, known_risks[:80])
    if board_date:
        _append_fact(facts, "board_date", board_date, board_date)
    if start_date:
        _append_fact(facts, "start_date", start_date, start_date)
    if production_date:
        _append_fact(facts, "production_date", production_date, production_date)

    description = _merge_description_parts(
        _normalize_description(None, text, project_name),
        _extract_supplementary_description(text),
    )
    if description:
        _append_fact(facts, "description", "（见业务描述）", description[:60])

    dims = _guess_dimensions(text)
    result = {
        "mode": "rules",
        "project_name": project_name,
        "investment_destination": investment_destination,
        "investment_structure": investment_structure,
        "funding_source": funding_source,
        "project_content_scale": project_content_scale,
        "description": description,
        "employee_count": employee_count,
        "capacity_notes": capacity_notes,
        "facility_notes": facility_notes,
        "known_risks": known_risks,
        "board_date": board_date,
        "start_date": start_date,
        "production_date": production_date,
        "remarks": None,
        "compliance_dimensions": dims,
        "facts": facts,
        "disclaimer": "抽取结果仅供预填核对表，不构成法律意见；请人工核对后再提交。",
        "llm_skipped": None,
    }
    result["facts"] = _ensure_facts_from_fields(result, text)
    return _finalize_extract_result(result, text)


def extract_facts_llm(text: str) -> tuple[dict[str, Any] | None, str | None]:
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
        extra = (parsed.get("remarks") or "").strip()
        if extra and extra not in desc:
            desc = _merge_description_parts(desc or None, extra) or desc or extra
        result = {
            "mode": "llm",
            "project_name": (parsed.get("project_name") or "").strip() or None,
            "investment_destination": (parsed.get("investment_destination") or "").strip() or None,
            "investment_structure": (parsed.get("investment_structure") or "").strip() or None,
            "funding_source": (parsed.get("funding_source") or "").strip() or None,
            "project_content_scale": (parsed.get("project_content_scale") or "").strip() or None,
            "description": desc if len(desc) >= 10 else None,
            "employee_count": parsed.get("employee_count"),
            "capacity_notes": (parsed.get("capacity_notes") or "").strip() or None,
            "facility_notes": (parsed.get("facility_notes") or "").strip() or None,
            "known_risks": (parsed.get("known_risks") or "").strip() or None,
            "board_date": _normalize_date((parsed.get("board_date") or "").strip() or None),
            "start_date": _normalize_date((parsed.get("start_date") or "").strip() or None),
            "production_date": _normalize_date((parsed.get("production_date") or "").strip() or None),
            "remarks": None,
            "compliance_dimensions": dims,
            "facts": parsed.get("facts", [])[:24],
            "disclaimer": "AI 抽取结果仅供预填核对表，不构成法律意见；须人工核对后再提交。",
            "llm_skipped": None,
        }
        result["facts"] = _ensure_facts_from_fields(result, text)
        return _finalize_extract_result(result, text), None
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


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _merge_unique_text_parts(values: list[Any], separator: str = "；") -> str | None:
    seen: set[str] = set()
    parts: list[str] = []
    for value in values:
        text = _normalize_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        parts.append(text)
    return separator.join(parts) if parts else None


def _merge_descriptions(values: list[Any]) -> str | None:
    seen: set[str] = set()
    parts: list[str] = []
    for value in values:
        text = _normalize_text(value)
        if not text:
            continue
        normalized = re.sub(r"\s+", " ", text)
        if normalized in seen:
            continue
        seen.add(normalized)
        parts.append(text)
    if not parts:
        return None
    merged = "\n\n".join(parts)
    if len(merged) > 3000:
        merged = merged[:3000].rstrip() + "…"
    return merged


def _merge_employee_counts(values: list[Any]) -> int | None:
    nums: list[int] = []
    for value in values:
        if value is None:
            continue
        try:
            nums.append(int(value))
        except (TypeError, ValueError):
            continue
    return max(nums) if nums else None


def _merge_dimensions(all_dims: list[list[str]]) -> list[str]:
    merged: list[str] = []
    for dims in all_dims:
        for dim in dims:
            if dim in VALID_DIMENSIONS and dim not in merged:
                merged.append(dim)
    return merged or list(VALID_DIMENSIONS)


def _merge_facts(file_results: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for filename, result in file_results:
        for fact in result.get("facts", []):
            if not isinstance(fact, dict):
                continue
            item = dict(fact)
            item["source_filename"] = filename
            facts.append(item)
    return facts


def merge_extract_results(file_results: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    if not file_results:
        raise ValueError("没有可合并的抽取结果")

    if len(file_results) == 1:
        _, only = file_results[0]
        merged = dict(only)
        merged["facts"] = _merge_facts(file_results)
        return merged

    project_name = next(
        (_normalize_text(result.get("project_name")) or None for _, result in file_results),
        None,
    )
    investment_structure = _merge_unique_text_parts(
        [result.get("investment_structure") for _, result in file_results]
    )
    investment_destination = _merge_unique_text_parts(
        [result.get("investment_destination") for _, result in file_results]
    )
    funding_source = _merge_unique_text_parts(
        [result.get("funding_source") for _, result in file_results]
    )
    project_content_scale = _merge_unique_text_parts(
        [result.get("project_content_scale") for _, result in file_results]
    )
    known_risks = _merge_unique_text_parts(
        [result.get("known_risks") for _, result in file_results]
    )
    capacity_notes = _merge_unique_text_parts(
        [result.get("capacity_notes") for _, result in file_results]
    )
    facility_notes = _merge_unique_text_parts(
        [result.get("facility_notes") for _, result in file_results]
    )
    description_parts: list[Any] = [result.get("description") for _, result in file_results]
    for _, result in file_results:
        extra = _normalize_text(result.get("remarks"))
        if extra:
            description_parts.append(extra)
    merged_description = _merge_descriptions(description_parts)

    modes = [result.get("mode") for _, result in file_results]
    llm_skipped_parts = [
        str(result.get("llm_skipped")).strip()
        for _, result in file_results
        if result.get("llm_skipped")
    ]

    return {
        "mode": "llm" if any(mode == "llm" for mode in modes) else "rules",
        "project_name": project_name,
        "investment_destination": investment_destination,
        "investment_structure": investment_structure,
        "funding_source": funding_source,
        "project_content_scale": project_content_scale,
        "description": merged_description,
        "employee_count": _merge_employee_counts([result.get("employee_count") for _, result in file_results]),
        "capacity_notes": capacity_notes,
        "facility_notes": facility_notes,
        "known_risks": known_risks,
        "board_date": next(
            (_normalize_text(result.get("board_date")) or None for _, result in file_results if result.get("board_date")),
            None,
        ),
        "start_date": next(
            (_normalize_text(result.get("start_date")) or None for _, result in file_results if result.get("start_date")),
            None,
        ),
        "production_date": next(
            (
                _normalize_text(result.get("production_date")) or None
                for _, result in file_results
                if result.get("production_date")
            ),
            None,
        ),
        "remarks": None,
        "compliance_dimensions": _merge_dimensions(
            [result.get("compliance_dimensions", []) for _, result in file_results]
        ),
        "facts": _merge_facts(file_results),
        "disclaimer": (
            f"已分别抽取 {len(file_results)} 个文件并合并去重，仅供预填表单，不构成法律意见；"
            "请核对各文件结果与合并表后再提交。"
        ),
        "llm_skipped": "；".join(llm_skipped_parts) if llm_skipped_parts else None,
    }


CONFLICT_FIELD_LABELS: dict[str, str] = {
    "project_name": "项目名称",
    "investment_destination": "投资目的地",
    "investment_structure": "投资结构",
    "funding_source": "资金来源",
    "project_content_scale": "主要内容",
    "employee_count": "雇员规模",
    "capacity_notes": "产能说明",
    "facility_notes": "规模",
    "description": "业务描述",
    "known_risks": "已知风险与关注事项",
    "board_date": "董事会日期",
    "start_date": "预计开工",
    "production_date": "预计投产",
}

CONFLICT_CHECK_FIELDS = list(CONFLICT_FIELD_LABELS.keys())


def _display_field_value(field: str, value: Any) -> str:
    if value is None:
        return ""
    if field == "employee_count":
        try:
            return f"{int(value)} 人"
        except (TypeError, ValueError):
            return str(value)
    return _normalize_text(value)


def _compare_key(field: str, value: Any) -> str | None:
    if value is None:
        return None
    if field == "employee_count":
        try:
            return str(int(value))
        except (TypeError, ValueError):
            return None
    text = _normalize_text(value)
    if not text:
        return None
    if field == "description":
        return re.sub(r"\s+", " ", text)
    return text


def _merge_note_for_field(field: str) -> str:
    notes = {
        "project_name": "合并表已采用首个非空值，请核对是否为主方案名称",
        "investment_destination": "合并表已拼接不同表述，请保留正确一条",
        "employee_count": "合并表已取各文件最大值，请核对实际用工计划",
        "investment_structure": "合并表已拼接不同表述，请保留正确一条",
        "funding_source": "合并表已拼接不同表述，请保留正确一条",
        "project_content_scale": "合并表已拼接不同表述，请保留正确一条",
        "capacity_notes": "合并表已拼接不同表述，请保留正确一条",
        "facility_notes": "合并表已拼接不同表述，请保留正确一条",
        "description": "合并表已拼接各文件描述，请整理为一份连贯说明",
        "known_risks": "合并表已拼接不同风险描述，请整理为一份",
        "board_date": "多文件日期不一致，请核对内部决策日期",
        "start_date": "多文件日期不一致，请核对开工计划",
        "production_date": "多文件日期不一致，请核对投产计划",
    }
    return notes.get(field, "合并表已自动处理，请人工确认")


def detect_field_conflicts(file_results: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    """多文件抽取：同字段出现不同取值时返回冲突清单（供前端高亮）。"""
    if len(file_results) < 2:
        return []

    conflicts: list[dict[str, Any]] = []
    for field in CONFLICT_CHECK_FIELDS:
        sources: list[dict[str, str]] = []
        compare_keys: set[str] = set()
        for filename, result in file_results:
            raw = result.get(field)
            cmp_key = _compare_key(field, raw)
            if cmp_key is None:
                continue
            compare_keys.add(cmp_key)
            sources.append({"filename": filename, "value": _display_field_value(field, raw)})

        if len(compare_keys) > 1:
            conflicts.append(
                {
                    "field": field,
                    "label": CONFLICT_FIELD_LABELS.get(field, field),
                    "sources": sources,
                    "merge_note": _merge_note_for_field(field),
                }
            )
    return conflicts


def extract_documents_batch(
    uploads: list[tuple[str, bytes]],
) -> tuple[list[tuple[str, dict[str, Any]]], list[str], dict[str, Any], list[dict[str, Any]]]:
    if not uploads:
        raise ValueError("请至少上传一个文件")
    if len(uploads) > MAX_BATCH_FILES:
        raise ValueError(f"单次最多上传 {MAX_BATCH_FILES} 个文件")

    total_bytes = sum(len(content) for _, content in uploads)
    if total_bytes > MAX_BATCH_TOTAL_BYTES:
        raise ValueError("所有文件合计不能超过 2GB")

    successes: list[tuple[str, dict[str, Any]]] = []
    failures: list[str] = []
    for filename, content in uploads:
        try:
            successes.append((filename, extract_facts_from_document(filename, content)))
        except ValueError as exc:
            failures.append(f"{filename}: {exc}")

    if not successes:
        raise ValueError("；".join(failures) if failures else "未能从上传文件中抽取有效内容")

    merged = merge_extract_results(successes)
    conflicts = detect_field_conflicts(successes)
    if conflicts:
        conflict_names = "、".join(item["label"] for item in conflicts)
        merged["disclaimer"] = (
            merged.get("disclaimer", "")
            + f" 检测到 {len(conflicts)} 项多文件字段冲突（{conflict_names}），请在合并核对表中确认后再提交。"
        )
    return successes, failures, merged, conflicts
