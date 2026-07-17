from __future__ import annotations

from app.services.dimension_gate_service import _law_preview_for_dimension


def _source(source_id: str, *, review_status: str, validity: str = "vigente") -> dict:
    return {
        "id": source_id,
        "source": "lexml",
        "url": f"https://www.lexml.gov.br/urn/{source_id}",
        "title_pt": "Licenciamento ambiental",
        "title_zh": "环境许可",
        "dimension": "environment",
        "validity": validity,
        "tags": ["licenciamento"],
        "checklist_codes": ["ENV-001"],
        "text_pt_clean": "Fonte ambiental para teste.",
        "text_zh": "用于测试的环境法源。",
        "review_status": review_status,
    }


def test_gate_a_law_preview_excludes_quarantined_pending_and_revoked_sources() -> None:
    corpus = {
        "default_review_status": "pending",
        "sources": [
            _source("allowed", review_status="provisional"),
            _source("quarantined", review_status="quarantined"),
            _source("pending", review_status="pending"),
            _source("revoked", review_status="provisional", validity="revoked"),
        ],
    }

    hits = _law_preview_for_dimension(
        "environment",
        [{"label": "环境许可", "feeds_checklist": ["ENV-001"]}],
        top_k=10,
        corpus_data=corpus,
    )

    assert [hit["id"] for hit in hits] == ["allowed"]
    assert hits[0]["review_status"] == "provisional"
    assert hits[0]["requires_review"] is True
