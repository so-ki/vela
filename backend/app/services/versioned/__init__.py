"""Versioned reader/writer units for hash-frozen mechanism artifacts (WS-1C/C3).

Historical readers are append-only: entries must never be removed or edited.
Dispatch is by the persisted version string only — never by "current",
"latest" or map ordering. See docs/ai-review/DECISION_LOG.md D-0008/D-0013.
"""
