from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from app.models.scenario import InvestigationScenario
from app.services.disclaimer import DISCLAIMER_FULL_TEXT


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]', "_", name)
    return cleaned[:80] or "vela_sample"


def build_sample_docx(scenario: InvestigationScenario) -> tuple[bytes, str]:
    payload = scenario.checklist.payload
    brief = payload.get("brief") or {}
    review = payload.get("review") or {}
    checklist = payload

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "PingFang SC"
    style.font.size = Pt(11)

    title = doc.add_heading("拉美投资合规协查底稿", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph(f"项目名称：{scenario.project_name}")
    doc.add_paragraph(f"地点：{scenario.city} · {scenario.state} · {scenario.country}")
    doc.add_paragraph(f"行业：{checklist.get('detected_industry_name', scenario.industry)}")
    doc.add_paragraph(f"动作类型：{checklist.get('detected_action_type_name', scenario.action_type)}")
    doc.add_paragraph(f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    doc.add_paragraph(f"场景状态：{scenario.status}")

    doc.add_heading("一、业务场景摘要", level=1)
    doc.add_paragraph(scenario.description)
    if scenario.investment_structure:
        doc.add_paragraph(f"投资结构：{scenario.investment_structure}")
    if scenario.employee_count:
        doc.add_paragraph(f"雇员规模：约 {scenario.employee_count} 人")

    doc.add_heading("二、专项核查清单", level=1)
    for section in payload.get("sections", []):
        doc.add_heading(section.get("dimension_name", ""), level=2)
        doc.add_paragraph(section.get("description", ""))
        for item in section.get("items", []):
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(f"[{item.get('code')}] {item.get('title')} ").bold = True
            p.add_run(f"（{item.get('priority', '')} 优先级）")
            doc.add_paragraph(item.get("description", ""))

    sections_legal = payload.get("sections_with_legal") or payload.get("sections", [])
    doc.add_heading("三、法源绑定摘要", level=1)
    for section in sections_legal:
        for item in section.get("items", []):
            hits = item.get("legal_hits") or []
            if not hits:
                continue
            doc.add_paragraph(f"{item.get('code')} — {item.get('title')}", style="List Bullet")
            for hit in hits[:2]:
                doc.add_paragraph(
                    f"  · {hit.get('title_zh') or hit.get('title_pt')} "
                    f"(匹配度 {hit.get('match_score', 0)}，{hit.get('source_label', '')})"
                )

    if brief:
        doc.add_heading("四、中葡双语法律风险简报", level=1)
        doc.add_heading("执行摘要（中文）", level=2)
        doc.add_paragraph(brief.get("summary_zh", ""))
        doc.add_heading("Resumo Executivo (Português)", level=2)
        doc.add_paragraph(brief.get("summary_pt", ""))

        for section in brief.get("sections", []):
            doc.add_heading(section.get("dimension_name", ""), level=2)
            doc.add_paragraph(section.get("summary_zh", ""))
            for item in section.get("items", []):
                if item.get("gate_status") != "passed":
                    continue
                doc.add_paragraph(f"{item.get('code')} {item.get('title')}", style="List Bullet")
                doc.add_paragraph(item.get("risk_zh", ""))
                doc.add_paragraph(item.get("risk_pt", ""))

        blocked = brief.get("blocked_items") or []
        if blocked:
            doc.add_heading("需法务复核条目", level=2)
            for item in blocked:
                doc.add_paragraph(
                    f"{item.get('code')} — {item.get('title')}（{item.get('block_reason', '')}）"
                )

    if review and review.get("items"):
        doc.add_heading("五、法务复核记录", level=1)
        doc.add_paragraph(
            f"复核人：{review.get('reviewer_name', '')} · 状态：{review.get('status', '')}"
        )
        if review.get("finalized_at"):
            doc.add_paragraph(f"定稿时间：{review.get('finalized_at')}")
        for item in review.get("items", []):
            decision = {"approved": "确认", "rejected": "驳回", "pending": "待复核"}.get(
                item.get("decision", "pending"), item.get("decision")
            )
            line = f"{item.get('code')} — {item.get('title')}：{decision}"
            if item.get("comment"):
                line += f"（批注：{item.get('comment')}）"
            doc.add_paragraph(line, style="List Bullet")

    doc.add_heading("六、免责声明", level=1)
    for para in DISCLAIMER_FULL_TEXT.split("\n\n"):
        doc.add_paragraph(para)

    buf = io.BytesIO()
    doc.save(buf)
    filename = f"{_safe_filename(scenario.project_name)}_协查底稿.docx"
    return buf.getvalue(), filename
