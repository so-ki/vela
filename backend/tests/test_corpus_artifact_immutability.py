from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

import app.services.corpus_maintenance_agent_service as corpus_agent
import app.services.legal_corpus_service as corpus_service
import app.services.lexml_fetch_service as lexml_service


def _corpus() -> dict:
    return {
        "version": "1.0",
        "sources": [
            {
                "id": "source-1",
                "source": "lexml",
                "urn": "urn:lex:br:test",
                "url": "https://www.lexml.gov.br/test",
                "title_pt": "Fonte",
                "title_zh": "法源",
                "dimension": "environment",
                "level": "federal",
                "validity": "vigente",
                "published_at": "2026-01-01",
                "tags": [],
                "checklist_codes": ["ENV-001"],
                "text_pt": "texto publicado",
                "text_zh": "已发布文本",
            }
        ],
    }


def test_active_corpus_cannot_be_created_updated_or_deleted(monkeypatch):
    corpus = _corpus()
    monkeypatch.setattr(corpus_service, "load_corpus", lambda: corpus)

    with pytest.raises(HTTPException) as update_error:
        corpus_service.update_corpus_source("source-1", {"text_pt": "mutated"})
    assert update_error.value.status_code == 409
    assert corpus["sources"][0]["text_pt"] == "texto publicado"

    with pytest.raises(HTTPException) as delete_error:
        corpus_service.delete_corpus_source("source-1")
    assert delete_error.value.status_code == 409
    assert len(corpus["sources"]) == 1


def test_lexml_fetch_is_candidate_only_and_never_persists(monkeypatch):
    corpus = _corpus()
    monkeypatch.setattr(lexml_service, "load_corpus", lambda: corpus)
    monkeypatch.setattr(
        lexml_service,
        "fetch_lexml_by_urn",
        lambda _urn: {
            "status": "ok",
            "url": "https://www.lexml.gov.br/official",
            "text_pt": "candidate official text that is long enough for review",
        },
    )

    blocked = lexml_service.enrich_corpus_document_from_lexml("source-1", persist=True)
    assert blocked["status"] == "error"
    assert corpus["sources"][0]["text_pt"] == "texto publicado"

    candidate = lexml_service.enrich_corpus_document_from_lexml("source-1", persist=False)
    assert candidate["status"] == "ok"
    assert candidate["candidate"]["text_pt"].startswith("candidate official")
    assert corpus["sources"][0]["text_pt"] == "texto publicado"


def test_corpus_agent_mutating_options_are_off_by_default():
    signature = inspect.signature(corpus_agent.run_corpus_maintenance_agent)
    assert signature.parameters["sync_lexml"].default is False
    assert signature.parameters["auto_reindex"].default is False
