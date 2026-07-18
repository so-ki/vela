"""canonical_hash_v1 — HASH-FROZEN (D-0015). DO NOT EDIT.

Byte-for-byte the algorithm historically used by generation_guard.stable_hash
at commit efc76e0. Every hash stored by compiler 0.2 and coverage proof 0.1
readers/writers is produced by this exact function. Any change breaks stored
historical hashes; new algorithms must be added as v2+, never by editing v1.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_hash_v1(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
