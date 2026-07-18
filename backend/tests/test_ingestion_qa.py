from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_ingestion_qa.py"
SPEC = importlib.util.spec_from_file_location("ingestion_qa", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_frozen_experiment_has_ten_official_documents_and_thirty_anchors() -> None:
    config = module.load_config(
        Path(__file__).resolve().parents[1] / "evals/ingestion_qa_targets_v3.json"
    )
    assert config["experiment_id"] == "ingestion-qa-v3"
    assert config["sample_size"] == 10
    assert config["pre_registered_decision"]["maximum_anchor_omission_rate"] == 0.05
    assert sum(len(target["anchors"]) for target in config["targets"]) == 30
    assert sum(target["source_type"] == "official_native_pdf" for target in config["targets"]) == 1


def test_anchor_normalization_handles_accents_ordinals_and_punctuation() -> None:
    extracted = module.normalize_for_anchor(
        "PARÁGRAFO ÚNICO — Artigo 5.º; licença de instalação (LI)"
    )
    assert module.normalize_for_anchor("Parágrafo único") in extracted
    assert module.normalize_for_anchor("Artigo 5º") in extracted
    assert module.normalize_for_anchor("Licença de Instalação (LI)") in extracted


def test_summary_uses_pre_registered_threshold_and_errors_block_decision() -> None:
    config = module.load_config(
        Path(__file__).resolve().parents[1] / "evals/ingestion_qa_targets_v3.json"
    )
    base = {
        "error": None,
        "expected_anchor_count": 3,
        "matched_anchor_count": 3,
    }
    passing = [dict(base) for _ in range(10)]
    passing[0]["matched_anchor_count"] = 2
    result = module.summarize(config, passing)
    assert result["anchor_omission_rate"] == 0.0333
    assert result["decision"].startswith("pdf_ingestion_anchor_consistency_supported")

    failing = [dict(base) for _ in range(10)]
    failing[0]["matched_anchor_count"] = 1
    result = module.summarize(config, failing)
    assert result["anchor_omission_rate"] == 0.0667
    assert result["decision"].startswith("pdf_ingestion_requires_manual")

    incomplete = [dict(base) for _ in range(10)]
    incomplete[3]["error"] = "TimeoutError"
    with pytest.raises(RuntimeError, match="incomplete"):
        module.summarize(config, incomplete)


def test_html_anchor_absent_from_official_source_is_an_experiment_error(tmp_path: Path) -> None:
    target = {
        "id": "example",
        "instrument": "Example",
        "source_type": "official_html_rendered_pdf",
        "document_url": "https://www.al.sp.gov.br/example",
        "anchors": ["present", "missing", "also present"],
    }
    source = tmp_path / "example.source.txt"
    source.write_text("present and also present", encoding="utf-8")
    result = module.evaluate_pdf(target, tmp_path / "example.pdf", {}, source)
    assert "absent from official HTML source" in result["error"]
    assert "missing" in result["error"]


def test_invalid_iterations_are_retained_and_never_report_a_decision() -> None:
    evals = Path(__file__).resolve().parents[1] / "evals"
    v1 = module.json.loads((evals / "ingestion_qa_v1.json").read_text(encoding="utf-8"))
    v2 = module.json.loads((evals / "ingestion_qa_v2.json").read_text(encoding="utf-8"))
    v3 = module.json.loads((evals / "ingestion_qa_v3.json").read_text(encoding="utf-8"))
    assert v1["status"].startswith("invalidated")
    assert v1["decision"] == "invalid_pre_registered_anchors_no_ingestion_decision"
    assert v2["status"].startswith("invalidated")
    assert v2["decision"] == "source_anchor_validation_failed_no_ingestion_decision"
    assert v3["anchor_omission_rate"] == 0
    assert v3["matched_anchor_count"] == v3["expected_anchor_count"] == 30
