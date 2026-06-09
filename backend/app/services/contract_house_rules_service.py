"""Structured contract house rules loader."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "contract_house_rules.json"


def load_structured_house_rules() -> list[dict[str, Any]]:
    with open(RULES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("rules") or [])


def merge_profile_house_rules(
    rules: list[dict[str, Any]],
    custom_text: str,
) -> list[dict[str, Any]]:
    if not (custom_text or "").strip():
        return rules
    merged = list(rules)
    merged.append(
        {
            "id": "custom_house",
            "label": "团队自定义底线",
            "severity": "high",
            "detect_patterns": [re.escape(custom_text[:120])] if len(custom_text) < 120 else [r".+"],
            "must_not": [],
            "must_have": [],
            "exceptions": [],
            "guidance": custom_text[:500],
            "profile_custom": True,
        }
    )
    return merged


def phrase_hits(text: str, phrases: list[str]) -> list[str]:
    hits: list[str] = []
    lower = text.lower()
    for phrase in phrases:
        p = (phrase or "").strip()
        if not p:
            continue
        if len(p) <= 40:
            if p.lower() in lower:
                hits.append(p)
        elif re.search(p, text, re.I):
            hits.append(p)
    return hits


def rule_detected(clause_text: str, rule: dict[str, Any]) -> bool:
    patterns = rule.get("detect_patterns") or []
    if rule.get("pattern"):
        patterns = list(patterns) + [rule["pattern"]]
    for pat in patterns:
        if pat == r".+":
            return True
        try:
            if re.search(pat, clause_text, re.I):
                return True
        except re.error:
            if pat.lower() in clause_text.lower():
                return True
    return False
