"""Clean polluted LexML HTML/JS from corpus text_pt and build display excerpts."""

from __future__ import annotations

import re
from typing import Any

GARBAGE_MARKERS = (
    "var url = document.location",
    "_gaq.push",
    "_gaq || []",
    ".list-group-item",
    "@media only screen",
    "google-analytics.com",
    "Página Anterior",
    "Pesquisa Avançada",
    "Doutrina Referenciada",
    "Multivigente Presidência",
    "function() {",
    "document.createElement('script')",
)

MAX_CLEAN_PT = 1200


def is_polluted(text: str) -> bool:
    if not text:
        return False
    if len(text) > 2500:
        return True
    return any(m in text for m in GARBAGE_MARKERS)


def _extract_ementa(text: str) -> str:
    m = re.search(
        r"Ementa\s+(.+?)(?:\s+Nome Uniforme|\s+Publicação|\s+Mais detalhes|\s+Localidade|\s+Autoridade|$)",
        text,
        re.I | re.S,
    )
    if m:
        ementa = re.sub(r"\s+", " ", m.group(1)).strip()
        if len(ementa) > 20:
            return ementa[:600]
    return ""


def clean_text_pt(
    text: str,
    *,
    title_pt: str = "",
    text_zh: str = "",
) -> str:
    """Return readable Portuguese excerpt for indexing and display."""
    raw = (text or "").strip()
    if not raw:
        return (text_zh or title_pt or "")[:MAX_CLEAN_PT]

    for marker in GARBAGE_MARKERS:
        idx = raw.find(marker)
        if idx > 40:
            raw = raw[:idx].strip()
            break

    if ":: Legislação::" in raw:
        head = raw.split(":: Legislação::")[0].strip()
        if len(head) > 25:
            raw = head

    raw = re.sub(r"\s+", " ", raw).strip()
    ementa = _extract_ementa(raw)
    if ementa:
        if title_pt:
            return f"{title_pt} — Ementa: {ementa}"[:MAX_CLEAN_PT]
        return f"Ementa: {ementa}"[:MAX_CLEAN_PT]

    if is_polluted(text) and text_zh:
        if title_pt:
            return title_pt[:MAX_CLEAN_PT]
        return raw[:120].strip()[:MAX_CLEAN_PT] if raw else text_zh[:MAX_CLEAN_PT]

    if len(raw) > MAX_CLEAN_PT:
        raw = raw[:MAX_CLEAN_PT] + "…"
    return raw


def excerpt_for_display(doc: dict[str, Any]) -> tuple[str, str]:
    """UI/API excerpt: prefer clean PT; zh always from curated summary."""
    title_pt = doc.get("title_pt") or ""
    text_zh = doc.get("text_zh") or ""
    clean_pt = doc.get("text_pt_clean") or clean_text_pt(
        doc.get("text_pt") or "",
        title_pt=title_pt,
        text_zh=text_zh,
    )
    excerpt_pt = clean_pt[:600]
    excerpt_zh = text_zh[:600] if text_zh else ""
    if not excerpt_zh and title_pt:
        excerpt_zh = doc.get("title_zh") or ""
    return excerpt_pt, excerpt_zh


def text_for_retrieval(doc: dict[str, Any]) -> str:
    """Tokenize-friendly text — avoid HTML noise in keyword scoring."""
    parts = [
        doc.get("title_pt") or "",
        doc.get("title_zh") or "",
        doc.get("text_pt_clean") or clean_text_pt(
            doc.get("text_pt") or "",
            title_pt=doc.get("title_pt") or "",
            text_zh=doc.get("text_zh") or "",
        ),
        doc.get("text_zh") or "",
        " ".join(doc.get("tags") or []),
    ]
    return " ".join(p for p in parts if p)
