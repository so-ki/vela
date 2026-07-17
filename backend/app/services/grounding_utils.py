"""Shared mechanical grounding utilities (Lavern-inspired char overlap, no LLM)."""

from __future__ import annotations

import re
from typing import Any

DEFAULT_MIN_OVERLAP = 0.80
GROUNDED_THRESHOLD = 0.55
GROUNDED_THRESHOLD_HIGH = 0.65

BOILERPLATE_PHRASES = frozenset(
    {
        "不构成正式法律意见",
        "仅供协查参考",
        "须人工核对",
        "请法务复核",
        "nao constitui parecer",
        "does not constitute legal advice",
        "for reference only",
        "sem prejuízo",
        "salvo disposição em contrário",
        "conforme legislação vigente",
        "nos termos da lei",
        "de acordo com a legislação",
        "subject to applicable law",
    }
)


def normalize_text(text: str) -> str:
    """Collapse whitespace and lowercase for comparison."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def is_boilerplate_phrase(text: str) -> bool:
    """True when snippet is empty or essentially generic legal boilerplate."""
    normalized = normalize_text(text)
    if not normalized or len(normalized) < 12:
        return True
    if normalized in BOILERPLATE_PHRASES:
        return True
    for phrase in BOILERPLATE_PHRASES:
        if len(phrase) >= 20 and phrase in normalized and len(normalized) <= len(phrase) + 8:
            return True
    return False


def char_overlap(needle: str, haystack: str) -> float:
    """Sliding-window character overlap ratio (0–1), Lavern-style."""
    n = normalize_text(needle)
    h = normalize_text(haystack)
    if not n or not h:
        return 0.0
    if n in h:
        return 1.0
    if len(n) <= len(h) and h in n:
        return min(1.0, len(h) / len(n))

    window = len(n)
    if window > len(h):
        # Needle longer than haystack: compare prefix windows of needle against full haystack
        best = 0.0
        for start in range(0, min(len(n), 400), max(1, window // 8)):
            chunk = n[start : start + min(window, len(n) - start)]
            if not chunk:
                continue
            if chunk in h:
                return max(best, len(chunk) / len(n))
            best = max(best, _window_ratio(chunk, h))
        return round(min(1.0, best), 3)

    best = 0.0
    step = max(1, window // 12)
    for i in range(0, len(h) - window + 1, step):
        segment = h[i : i + window]
        best = max(best, _window_ratio(n, segment))
        if best >= 0.99:
            break
    return round(min(1.0, best), 3)


def _window_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    matches = sum(1 for i, ch in enumerate(a) if i < len(b) and b[i] == ch)
    return matches / max(len(a), len(b))


def verify_snippet_in_source(
    snippet: str,
    source_text: str,
    *,
    min_overlap: float = DEFAULT_MIN_OVERLAP,
    grounded_threshold: float = GROUNDED_THRESHOLD,
) -> dict[str, Any]:
    """Check full normalized excerpt containment in the cited local source.

    Character overlap remains diagnostic only.  It can never make a citation
    pass, because a correct prefix followed by fabricated text must fail.
    """
    snip_norm = normalize_text(snippet)
    src_norm = normalize_text(source_text)

    if not snip_norm:
        return {
            "grounded": False,
            "grounding_score": 0.0,
            "reason": "摘录为空",
            "citation_status": "ungrounded",
            "verification_scope": "excerpt_consistency_only",
        }
    if not src_norm:
        return {
            "grounded": False,
            "grounding_score": 0.0,
            "reason": "原文为空",
            "citation_status": "ungrounded",
            "verification_scope": "excerpt_consistency_only",
        }

    full_excerpt_match = snip_norm in src_norm
    if full_excerpt_match:
        score = 1.0
    else:
        score = char_overlap(snip_norm[:400], src_norm)

    # Short exact fact anchors (common in Chinese source material) are valid;
    # only known generic disclaimer phrases are rejected as boilerplate.
    boilerplate_only = snip_norm in BOILERPLATE_PHRASES or any(
        phrase in snip_norm and len(snip_norm) <= len(phrase) + 8
        for phrase in BOILERPLATE_PHRASES
        if len(phrase) >= 20
    )
    grounded = full_excerpt_match and not boilerplate_only

    if score >= grounded_threshold and boilerplate_only:
        citation_status = "weak_grounding"
    elif grounded:
        citation_status = "excerpt_matched"
    elif score >= grounded_threshold * 0.7:
        citation_status = "weak_grounding"
    else:
        citation_status = "ungrounded"

    reason = None
    if not grounded:
        if boilerplate_only:
            reason = "摘录主要为通用套话，须法务核对原文"
        elif not full_excerpt_match:
            reason = "完整摘录未在本地语料原文中找到；相似前缀或部分重合不能通过"
        else:
            reason = "摘录仅为通用套话，不能作为证据锚点"

    return {
        "grounded": grounded,
        "grounding_score": round(score, 3),
        "reason": reason,
        "citation_status": citation_status,
        "verification_scope": "excerpt_consistency_only",
        "full_excerpt_match": full_excerpt_match,
    }


def citation_status_from_score(score: float, *, grounded: bool, boilerplate_only: bool = False) -> str:
    if grounded and not boilerplate_only:
        return "excerpt_matched"
    if score >= GROUNDED_THRESHOLD * 0.7:
        return "weak_grounding"
    return "ungrounded"
