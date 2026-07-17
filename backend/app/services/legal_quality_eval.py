"""Deterministic legal-corpus quality gates for the controlled pilot.

This evaluator deliberately does not ask an LLM to grade another LLM.  It
separates mechanical release invariants from legal expert certification:
known-wrong sources must never be retrieved, while general-availability status
remains false until expert-reviewed sources and pinpoint metadata exist.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.services.legal_ingest import (
    CONTROLLED_EVIDENCE_POLICY,
    CORPUS_PATH,
    controlled_evidence_errors,
    corpus_review_status,
    declared_retrievable_corpus_sources,
    load_corpus,
    retrievable_corpus_sources,
)
from app.services.legal_rag import _retrieve_keyword

DEFAULT_CASES_PATH = Path(__file__).resolve().parents[2] / "evals" / "legal_quality_gate_v1.jsonl"
DEFAULT_RULES_PATH = Path(__file__).resolve().parents[1] / "rules" / "brazil_new_energy.json"
DEFAULT_RESOLUTION_EVIDENCE_PATH = (
    Path(__file__).resolve().parents[2] / "evals" / "legal_source_resolution_v1.json"
)
REQUIRED_GA_FIELDS = (
    "authority",
    "instrument_type",
    "status_as_of",
    "last_verified_at",
    "official_url",
    "content_hash",
)
UNSUPPORTED_COMPOSITE_PREFIXES = ("jusbrasil-guide-",)

SOURCE_HOST_ALLOWLIST: dict[str, frozenset[str]] = {
    "alesp": frozenset({"www.al.sp.gov.br"}),
    "apexbrasil": frozenset({"apexbrasil.com.br"}),
    "campinas": frozenset({"portal.campinas.sp.gov.br"}),
    "gov-br": frozenset({"www.gov.br"}),
    "ibama": frozenset({"www.gov.br"}),
    "investsp": frozenset({"www.investe.sp.gov.br"}),
    "jusbrasil": frozenset({"www.jusbrasil.com.br"}),
    "lexml": frozenset({"www.lexml.gov.br"}),
    "planalto-legislacao": frozenset({"www.planalto.gov.br", "www4.planalto.gov.br"}),
    "previdencia": frozenset({"www.gov.br"}),
    "receita-federal": frozenset({"www.gov.br"}),
    "sefaz-sp": frozenset({"portal.fazenda.sp.gov.br"}),
    "stf": frozenset({"portal.stf.jus.br", "www.stf.jus.br"}),
    "stj": frozenset({"scon.stj.jus.br", "www.stj.jus.br"}),
    "trabalho": frozenset({"www.gov.br"}),
}


def source_host_integrity_errors(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return deterministic provenance-label errors for primary and official URLs."""

    errors: list[dict[str, Any]] = []
    for doc in sources:
        source_id = str(doc.get("id") or "")
        source = str(doc.get("source") or "").strip().lower()
        allowed_hosts = SOURCE_HOST_ALLOWLIST.get(source)
        if not allowed_hosts:
            errors.append(
                {
                    "source_id": source_id,
                    "source": source,
                    "url_field": "source",
                    "host": "",
                    "reason": "unknown_source_label",
                }
            )
            continue
        for url_field in ("url", "official_url"):
            value = str(doc.get(url_field) or "").strip()
            if not value:
                if url_field == "url":
                    errors.append(
                        {
                            "source_id": source_id,
                            "source": source,
                            "url_field": url_field,
                            "host": "",
                            "reason": "missing_url",
                        }
                    )
                continue
            host = (urlparse(value).hostname or "").lower()
            if host not in allowed_hosts:
                errors.append(
                    {
                        "source_id": source_id,
                        "source": source,
                        "url_field": url_field,
                        "host": host,
                        "reason": "source_host_mismatch",
                        "allowed_hosts": sorted(allowed_hosts),
                    }
                )
    return errors


def load_eval_cases(path: Path | str = DEFAULT_CASES_PATH) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict) or not value.get("case_id"):
            raise ValueError(f"invalid legal eval case at line {line_no}")
        cases.append(value)
    return cases


def load_resolution_evidence(
    path: Path | str = DEFAULT_RESOLUTION_EVIDENCE_PATH,
) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != "1.0":
        raise ValueError("invalid legal source resolution evidence")
    resolved = set(value.get("resolved_source_ids") or [])
    not_found = set(value.get("not_found_source_ids") or [])
    if resolved & not_found:
        raise ValueError("legal source resolution evidence contains conflicting ids")
    return value


def evaluate_legal_quality(
    *,
    corpus_path: Path | str = CORPUS_PATH,
    cases_path: Path | str = DEFAULT_CASES_PATH,
    resolution_evidence_path: Path | str = DEFAULT_RESOLUTION_EVIDENCE_PATH,
    rules_path: Path | str = DEFAULT_RULES_PATH,
    top_k: int = 3,
) -> dict[str, Any]:
    corpus_path = Path(corpus_path)
    corpus = load_corpus(corpus_path)
    sources = list(corpus.get("sources") or [])
    declared_retrievable = declared_retrievable_corpus_sources(corpus)
    retrievable = retrievable_corpus_sources(corpus)
    evidence_envelope_errors = [
        {"source_id": str(doc.get("id") or ""), "errors": controlled_evidence_errors(doc)}
        for doc in declared_retrievable
        if controlled_evidence_errors(doc)
    ]
    evidence_filtered_ids = sorted(
        {str(doc.get("id") or "") for doc in declared_retrievable}
        - {str(doc.get("id") or "") for doc in retrievable}
    )
    status_counts = Counter(corpus_review_status(corpus, doc) for doc in sources)
    resolution_evidence = load_resolution_evidence(resolution_evidence_path)
    host_integrity_errors = source_host_integrity_errors(sources)
    resolved_source_ids = set(resolution_evidence.get("resolved_source_ids") or [])
    not_found_source_ids = set(resolution_evidence.get("not_found_source_ids") or [])
    resolver_source_ids = {
        str(doc.get("id"))
        for doc in sources
        if doc.get("source") == "lexml"
        and str(doc.get("url") or "").startswith("https://www.lexml.gov.br/urn/")
    }
    resolution_audit_missing_ids = sorted(
        resolver_source_ids - resolved_source_ids - not_found_source_ids
    )
    unresolved_retrievable_ids = sorted(
        str(doc.get("id"))
        for doc in retrievable
        if str(doc.get("id")) in not_found_source_ids
    )
    unsupported_composite_retrievable_ids = sorted(
        str(doc.get("id"))
        for doc in retrievable
        if str(doc.get("id") or "").startswith(UNSUPPORTED_COMPOSITE_PREFIXES)
    )

    case_results: list[dict[str, Any]] = []
    forbidden_hits = 0
    unexpected_source_hits = 0
    zero_hit_cases = 0
    expected_source_miss_cases = 0
    for case in load_eval_cases(cases_path):
        hits = _retrieve_keyword(
            item_code=str(case["item_code"]),
            dimension=str(case["dimension"]),
            title=str(case.get("title") or ""),
            description=str(case.get("description") or ""),
            top_k=top_k,
            corpus_path=corpus_path,
        )
        ids = [str(hit.get("id")) for hit in hits]
        forbidden = sorted(set(ids) & set(case.get("forbidden_source_ids") or []))
        min_hits = max(1, int(case.get("min_hits", 1)))
        expected_ids = sorted(set(case.get("expected_source_ids") or []))
        expected_hits = sorted(set(ids) & set(expected_ids))
        allowed_ids = sorted(set(case.get("allowed_source_ids") or []))
        unexpected_hits = sorted(set(ids) - set(allowed_ids)) if allowed_ids else []
        enough_hits = len(ids) >= min_hits
        expected_source_hit = not expected_ids or bool(expected_hits)
        forbidden_hits += len(forbidden)
        unexpected_source_hits += len(unexpected_hits)
        zero_hit_cases += int(not enough_hits)
        expected_source_miss_cases += int(not expected_source_hit)
        case_results.append(
            {
                "case_id": case["case_id"],
                "retrieved_source_ids": ids,
                "forbidden_hits": forbidden,
                "minimum_hits": min_hits,
                "expected_source_ids": expected_ids,
                "expected_source_hits": expected_hits,
                "allowed_source_ids": allowed_ids,
                "unexpected_source_hits": unexpected_hits,
                "passed": (
                    not forbidden
                    and not unexpected_hits
                    and enough_hits
                    and expected_source_hit
                ),
            }
        )

    rules = json.loads(Path(rules_path).read_text(encoding="utf-8"))
    checklist_results: list[dict[str, Any]] = []
    for item in rules.get("checklist_items") or []:
        hits = _retrieve_keyword(
            item_code=str(item["id"]),
            dimension=str(item["dimension"]),
            title=str(item.get("title") or ""),
            description=str(item.get("description") or ""),
            top_k=top_k,
            corpus_path=corpus_path,
        )
        checklist_results.append(
            {
                "item_code": str(item["id"]),
                "retrieved_source_ids": [str(hit.get("id")) for hit in hits],
            }
        )
    checklist_zero_hit_ids = [
        result["item_code"]
        for result in checklist_results
        if not result["retrieved_source_ids"]
    ]

    quarantined_retrievable = [
        doc.get("id")
        for doc in retrievable
        if corpus_review_status(corpus, doc) in {"quarantined", "pending"}
    ]
    non_expert_retrievable = [
        doc for doc in retrievable if corpus_review_status(corpus, doc) != "expert_verified"
    ]
    expert_sources = [
        doc for doc in retrievable if corpus_review_status(corpus, doc) == "expert_verified"
    ]
    ga_complete = [
        doc
        for doc in expert_sources
        if all(str(doc.get(field) or "").strip() for field in REQUIRED_GA_FIELDS)
    ]

    controlled_pilot_passed = bool(
        corpus.get("content_status") == "provisional"
        and corpus.get("default_review_status") == "pending"
        and corpus.get("retrieval_policy") == CONTROLLED_EVIDENCE_POLICY
        and not evidence_envelope_errors
        and not evidence_filtered_ids
        and forbidden_hits == 0
        and unexpected_source_hits == 0
        and zero_hit_cases == 0
        and expected_source_miss_cases == 0
        and not quarantined_retrievable
        and not resolution_audit_missing_ids
        and not unresolved_retrievable_ids
        and not unsupported_composite_retrievable_ids
        and not host_integrity_errors
        and all(result["passed"] for result in case_results)
        and all(corpus_review_status(corpus, doc) in {"provisional", "expert_verified"} for doc in retrievable)
    )
    ga_passed = bool(
        corpus.get("content_status") == "expert_verified"
        and len(expert_sources) >= 10
        and len(ga_complete) == len(expert_sources)
        and not non_expert_retrievable
        and not resolution_audit_missing_ids
        and not unresolved_retrievable_ids
        and not unsupported_composite_retrievable_ids
        and not host_integrity_errors
        and forbidden_hits == 0
        and unexpected_source_hits == 0
        and zero_hit_cases == 0
        and expected_source_miss_cases == 0
        and all(result["passed"] for result in case_results)
    )

    return {
        "schema_version": "1.0",
        "corpus_version": corpus.get("version"),
        "content_status": corpus.get("content_status", "undeclared"),
        "source_count": len(sources),
        "declared_retrievable_count": len(declared_retrievable),
        "retrievable_count": len(retrievable),
        "retrieval_policy": corpus.get("retrieval_policy", "legacy_status_only"),
        "evidence_envelope_error_count": len(evidence_envelope_errors),
        "evidence_envelope_errors": evidence_envelope_errors,
        "evidence_filtered_ids": evidence_filtered_ids,
        "status_counts": dict(sorted(status_counts.items())),
        "known_wrong_cases": len(case_results),
        "checklist_item_count": len(checklist_results),
        "checklist_items_with_hits": len(checklist_results) - len(checklist_zero_hit_ids),
        "checklist_hit_count": sum(
            len(result["retrieved_source_ids"]) for result in checklist_results
        ),
        "checklist_zero_hit_ids": checklist_zero_hit_ids,
        "forbidden_hit_at_k": forbidden_hits,
        "unexpected_source_hit_count": unexpected_source_hits,
        "zero_hit_cases": zero_hit_cases,
        "expected_source_miss_cases": expected_source_miss_cases,
        "quarantined_retrievable_ids": quarantined_retrievable,
        "resolution_evidence_checked_at": resolution_evidence.get("checked_at"),
        "resolution_audited_source_count": len(resolver_source_ids),
        "resolution_resolved_count": len(resolver_source_ids & resolved_source_ids),
        "resolution_not_found_count": len(resolver_source_ids & not_found_source_ids),
        "resolution_audit_missing_ids": resolution_audit_missing_ids,
        "unresolved_retrievable_ids": unresolved_retrievable_ids,
        "unsupported_composite_retrievable_ids": unsupported_composite_retrievable_ids,
        "source_host_integrity_error_count": len(host_integrity_errors),
        "source_host_integrity_errors": host_integrity_errors,
        "expert_verified_count": len(expert_sources),
        "ga_metadata_complete_count": len(ga_complete),
        "controlled_pilot_passed": controlled_pilot_passed,
        "general_availability_passed": ga_passed,
        "case_results": case_results,
        "limitations": [
            "摘录一致性不等于法律结论正确性、时点有效性或个案适用性",
            "当前 provisional 语料必须由法务逐项复核，不能自动成为正式法律意见",
            "checklist 命中仅表示候选法源覆盖；零命中项必须显式转为研究缺口，不能补写结论",
            "LexML URN 可解析性只证明标识符存在，不证明法条时点、语义适用或整合文本新鲜度",
            "general_availability_passed 仅能由巴西法律专家认证语料与完整定位元数据解锁",
        ],
    }
