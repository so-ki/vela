from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.shared import Pt, RGBColor


def source_trace(hit: dict[str, Any]) -> dict[str, str]:
    """Normalize the source envelope used by every human-facing export.

    Empty values stay explicit so a recipient can distinguish missing metadata
    from a formatting omission.  The export is an audit hand-off, not a place
    to silently improve provisional source records.
    """

    return {
        "citation_id": str(
            hit.get("citation_id") or hit.get("urn") or hit.get("id") or "—"
        ),
        "pinpoint": str(hit.get("pinpoint") or "—"),
        "validity": str(hit.get("validity") or "—"),
        "status_as_of": str(hit.get("status_as_of") or "—"),
        "review_status": str(hit.get("review_status") or "pending"),
        "verification_scope": str(hit.get("verification_scope") or "provisional corpus entry"),
        "last_verified_at": str(hit.get("last_verified_at") or "—"),
        "official_url": str(hit.get("official_url") or hit.get("url") or ""),
    }


def source_trace_lines(hit: dict[str, Any]) -> list[str]:
    trace = source_trace(hit)
    return [
        f"标识：{trace['citation_id']}；定位：{trace['pinpoint']}",
        (
            f"效力：{trace['validity']}；状态时点：{trace['status_as_of']}；"
            f"最近核验：{trace['last_verified_at']}"
        ),
        f"语料审核：{trace['review_status']}；核验范围：{trace['verification_scope']}",
    ]


def add_external_hyperlink(
    paragraph: Any,
    *,
    url: str,
    label: str | None = None,
    font_name: str = "宋体",
    size_pt: float = 10.5,
) -> None:
    """Append a real external hyperlink to a python-docx paragraph."""

    if not url:
        paragraph.add_run("—")
        return

    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or not parsed.hostname:
        # Source metadata is rendered as untrusted input.  Do not create file,
        # javascript, custom-protocol, or malformed relationships in a DOCX.
        paragraph.add_run("链接不可用（仅允许 HTTPS 官方来源）")
        return

    safe_url = parsed.geturl()
    relationship_id = paragraph.part.relate_to(safe_url, RT.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)

    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")

    fonts = OxmlElement("w:rFonts")
    fonts.set(qn("w:ascii"), font_name)
    fonts.set(qn("w:hAnsi"), font_name)
    fonts.set(qn("w:eastAsia"), font_name)
    properties.append(fonts)

    color = OxmlElement("w:color")
    color.set(qn("w:val"), str(RGBColor(0x05, 0x63, 0xC1)))
    properties.append(color)

    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    properties.append(underline)

    size = OxmlElement("w:sz")
    size.set(qn("w:val"), str(int(Pt(size_pt).pt * 2)))
    properties.append(size)

    run.append(properties)
    text = OxmlElement("w:t")
    text.text = label or safe_url
    run.append(text)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)
