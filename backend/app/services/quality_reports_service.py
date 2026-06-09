"""Attach grounding + verification reports after RAG/brief generation."""

from __future__ import annotations

from typing import Any

from app.services.grounding_verifier_service import verify_sections_grounding
from app.services.verification_service import run_brief_verification_passes


def attach_quality_reports(
    payload: dict[str, Any],
    brief: dict[str, Any] | None = None,
    *,
    sections_with_legal: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    sections = sections_with_legal or payload.get("sections_with_legal") or []
    brief_obj = brief or payload.get("brief") or {}
    payload = {
        **payload,
        "grounding_report": verify_sections_grounding(sections),
    }
    payload["verification_report"] = run_brief_verification_passes(payload, brief_obj)
    return payload
