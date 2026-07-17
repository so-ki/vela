from __future__ import annotations

import copy
import json

from app.services.grounding_utils import verify_snippet_in_source
from app.services.legal_corpus_service import VALID_SOURCES
from app.services.legal_ingest import (
    corpus_review_status,
    load_corpus,
    retrievable_corpus_sources,
)
from app.services.legal_quality_eval import (
    SOURCE_HOST_ALLOWLIST,
    evaluate_legal_quality,
    source_host_integrity_errors,
)
from app.services.legal_rag import SOURCE_LABELS, _retrieve_keyword


def test_current_corpus_passes_controlled_pilot_not_general_availability():
    report = evaluate_legal_quality()
    assert report["known_wrong_cases"] == 7
    assert report["forbidden_hit_at_k"] == 0
    assert report["zero_hit_cases"] == 0
    assert report["expected_source_miss_cases"] == 0
    assert report["quarantined_retrievable_ids"] == []
    assert report["resolution_audited_source_count"] == 36
    assert report["resolution_resolved_count"] == 19
    assert report["resolution_not_found_count"] == 17
    assert report["resolution_audit_missing_ids"] == []
    assert report["unresolved_retrievable_ids"] == []
    assert report["source_host_integrity_error_count"] == 0
    assert report["source_host_integrity_errors"] == []
    assert report["controlled_pilot_passed"] is True
    assert report["general_availability_passed"] is False
    assert report["expert_verified_count"] == 0
    padis = next(item for item in report["case_results"] if item["case_id"].startswith("TAX-005"))
    assert padis["expected_source_hits"] == ["planalto-lei-11484-padis"]
    worker_rights = next(
        item for item in report["case_results"] if item["case_id"] == "LAB-001-WRONG-CLT-ART7"
    )
    assert worker_rights["expected_source_hits"] == ["planalto-constituicao-1988-art-7"]
    assert worker_rights["forbidden_hits"] == []


def test_current_corpus_source_labels_match_hosts_and_have_display_labels():
    corpus = load_corpus()
    assert source_host_integrity_errors(corpus["sources"]) == []
    assert {doc["source"] for doc in corpus["sources"]} <= set(SOURCE_LABELS)
    assert VALID_SOURCES == set(SOURCE_HOST_ALLOWLIST) == set(SOURCE_LABELS)


def test_source_host_mismatch_blocks_controlled_pilot(tmp_path):
    corpus = copy.deepcopy(load_corpus())
    target = next(doc for doc in corpus["sources"] if doc["id"] == "ref-camex-resolucoes")
    target["source"] = "jusbrasil"
    corpus_path = tmp_path / "mislabeled.json"
    corpus_path.write_text(json.dumps(corpus, ensure_ascii=False), encoding="utf-8")

    report = evaluate_legal_quality(corpus_path=corpus_path)

    assert report["source_host_integrity_error_count"] == 1
    assert report["source_host_integrity_errors"][0] == {
        "source_id": "ref-camex-resolucoes",
        "source": "jusbrasil",
        "url_field": "url",
        "host": "www.gov.br",
        "reason": "source_host_mismatch",
        "allowed_hosts": ["www.jusbrasil.com.br"],
    }
    assert report["controlled_pilot_passed"] is False


def test_new_official_sources_are_provisional_pinpointed_and_clt_mismatch_is_quarantined():
    corpus = load_corpus()
    by_id = {doc["id"]: doc for doc in corpus["sources"]}
    active_ids = {doc["id"] for doc in retrievable_corpus_sources(corpus)}

    assert by_id["lexml-clt-art-7"]["review_status"] == "quarantined"
    assert "lexml-clt-art-7" not in active_ids
    for source_id in (
        "alesp-lei-997-1976-controle-poluicao",
        "alesp-decreto-8468-1976-arts-57-58",
        "planalto-constituicao-1988-art-7",
    ):
        source = by_id[source_id]
        assert source["review_status"] == "provisional"
        assert source["requires_expert_review"] is True
        assert source["authority"]
        assert source["instrument_type"]
        assert source["pinpoint"]
        assert source["status_as_of"] == "2026-07-17"
        assert source["last_verified_at"] == "2026-07-17"
        assert source["official_url"] == source["url"]
        assert source_id in active_ids

    environment_hits = _retrieve_keyword(
        item_code="ENV-001",
        dimension="environment",
        title="São Paulo CETESB environmental installation licence",
        description="Lei 997 Decreto 8468 arts 57 58",
        top_k=3,
    )
    assert [hit["id"] for hit in environment_hits[:2]] == [
        "alesp-decreto-8468-1976-arts-57-58",
        "alesp-lei-997-1976-controle-poluicao",
    ]
    assert all(hit["review_status"] == "provisional" for hit in environment_hits[:2])
    assert all(hit["requires_review"] is True for hit in environment_hits[:2])
    assert all(hit["pinpoint"] for hit in environment_hits[:2])


def test_empty_retrieval_cannot_pass_a_quality_case(tmp_path):
    corpus_path = tmp_path / "empty.json"
    corpus_path.write_text(
        '{"version":"test","content_status":"provisional","default_review_status":"provisional","sources":[]}',
        encoding="utf-8",
    )
    report = evaluate_legal_quality(corpus_path=corpus_path)
    assert report["zero_hit_cases"] == report["known_wrong_cases"]
    assert report["controlled_pilot_passed"] is False


def test_undeclared_review_status_fails_closed():
    corpus = {"version": "test", "sources": [{"id": "unknown"}]}
    assert corpus_review_status(corpus, corpus["sources"][0]) == "pending"
    assert retrievable_corpus_sources(corpus) == []


def test_unresolved_lexml_source_blocks_controlled_pilot(tmp_path):
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(
        '{"version":"test","content_status":"provisional","default_review_status":"provisional",'
        '"sources":[{"id":"bad","source":"lexml","url":"https://www.lexml.gov.br/urn/bad",'
        '"title_pt":"bad","title_zh":"bad","dimension":"tax","level":"federal",'
        '"validity":"vigente","published_at":"2026-01-01","tags":[],"checklist_codes":[],"text_pt":"bad"}]}',
        encoding="utf-8",
    )
    evidence_path = tmp_path / "resolution.json"
    evidence_path.write_text(
        '{"schema_version":"1.0","checked_at":"2026-07-17","resolved_source_ids":[],"not_found_source_ids":["bad"]}',
        encoding="utf-8",
    )

    report = evaluate_legal_quality(
        corpus_path=corpus_path,
        resolution_evidence_path=evidence_path,
    )

    assert report["unresolved_retrievable_ids"] == ["bad"]
    assert report["controlled_pilot_passed"] is False


def test_full_excerpt_consistency_rejects_fabricated_tail():
    source = "Artigo oficial com uma passagem suficientemente longa e verificável."
    honest = verify_snippet_in_source("passagem suficientemente longa", source)
    fabricated = verify_snippet_in_source(
        "passagem suficientemente longa e portanto autoriza qualquer investimento",
        source,
    )
    assert honest["citation_status"] == "excerpt_matched"
    assert fabricated["grounded"] is False
    assert fabricated["full_excerpt_match"] is False
