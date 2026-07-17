from __future__ import annotations

import re


_PLACEHOLDER_MARKERS = (
    "changeinproduction",
    "changeme",
    "default",
    "example",
    "placeholder",
    "replaceme",
    "replacewith",
    "sample",
    "todo",
)


def is_placeholder_value(value: str) -> bool:
    """Detect copy/paste placeholders after punctuation-insensitive normalization."""

    candidate = (value or "").strip()
    if not candidate:
        return True
    normalized = re.sub(r"[^a-z0-9]+", "", candidate.casefold())
    return any(marker in normalized for marker in _PLACEHOLDER_MARKERS)


def is_weak_secret(value: str, *, min_length: int, min_unique: int) -> bool:
    candidate = (value or "").strip()
    return bool(
        is_placeholder_value(candidate)
        or len(candidate) < min_length
        or len(set(candidate)) < min_unique
    )
