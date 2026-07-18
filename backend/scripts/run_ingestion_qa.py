#!/usr/bin/env python3
"""Run the pre-registered official AL-SP PDF ingestion anchor experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.document_extractor import read_upload_text  # noqa: E402


DEFAULT_TARGETS = ROOT / "evals/ingestion_qa_targets_v3.json"
RENDERER = ROOT / "scripts/render_official_pages_to_pdf.mjs"
ALLOWED_SOURCE_TYPES = {"official_html_rendered_pdf", "official_native_pdf"}
ALLOWED_HOST = "www.al.sp.gov.br"


def normalize_for_anchor(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).lower()
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    # NFKD turns Portuguese ordinal indicators into ASCII letters, so both
    # ``5º`` and the typographic ``5.º`` must converge to the same token.
    without_marks = re.sub(r"(?<=\d)\s*\.\s*([oa])\b", r"\1", without_marks)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_marks).split())


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    targets = config.get("targets")
    if not isinstance(targets, list) or len(targets) != 10 or config.get("sample_size") != 10:
        raise ValueError("experiment requires exactly 10 frozen targets")
    ids = {target.get("id") for target in targets}
    urls = {target.get("document_url") for target in targets}
    if len(ids) != 10 or None in ids or len(urls) != 10 or None in urls:
        raise ValueError("experiment target IDs and URLs must be unique")
    anchor_count = 0
    for target in targets:
        parsed = urlparse(target["document_url"])
        if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
            raise ValueError("all experiment inputs must use official AL-SP HTTPS URLs")
        if target.get("source_type") not in ALLOWED_SOURCE_TYPES:
            raise ValueError("unsupported source type")
        anchors = target.get("anchors")
        if not isinstance(anchors, list) or len(anchors) != 3 or not all(anchors):
            raise ValueError("each frozen target must have exactly three non-empty anchors")
        anchor_count += len(anchors)
    if anchor_count != 30:
        raise ValueError("experiment requires exactly 30 frozen anchors")
    return config


def evaluate_pdf(
    target: dict[str, Any],
    pdf_path: Path,
    rendered: dict[str, Any],
    source_text_path: Path | None = None,
) -> dict[str, Any]:
    try:
        if target["source_type"] == "official_html_rendered_pdf":
            if source_text_path is None or not source_text_path.is_file():
                raise ValueError("renderer did not preserve the official HTML text for validation")
            normalized_source = normalize_for_anchor(source_text_path.read_text(encoding="utf-8"))
            source_missed = [
                anchor
                for anchor in target["anchors"]
                if normalize_for_anchor(anchor) not in normalized_source
            ]
            if source_missed:
                raise ValueError(
                    "pre-registered anchors absent from official HTML source: "
                    + "; ".join(source_missed)
                )
        content = pdf_path.read_bytes()
        text = read_upload_text(pdf_path.name, content)
        if not text.strip():
            raise ValueError("PDF extraction returned no usable text")
        normalized_text = normalize_for_anchor(text)
        missed = [
            anchor
            for anchor in target["anchors"]
            if normalize_for_anchor(anchor) not in normalized_text
        ]
        return {
            "id": target["id"],
            "instrument": target["instrument"],
            "source_type": target["source_type"],
            "document_url": target["document_url"],
            "pdf_bytes": len(content),
            "pdf_sha256": hashlib.sha256(content).hexdigest(),
            "source_text_characters": rendered.get("source_text_characters"),
            "source_text_sha256": rendered.get("source_text_sha256"),
            "extracted_characters": len(text),
            "expected_anchor_count": len(target["anchors"]),
            "matched_anchor_count": len(target["anchors"]) - len(missed),
            "missed_anchors": missed,
            "error": None,
        }
    except Exception as exc:
        return {
            "id": target["id"],
            "instrument": target["instrument"],
            "source_type": target["source_type"],
            "document_url": target["document_url"],
            "pdf_bytes": None,
            "pdf_sha256": None,
            "source_text_characters": rendered.get("source_text_characters"),
            "source_text_sha256": rendered.get("source_text_sha256"),
            "extracted_characters": None,
            "expected_anchor_count": len(target["anchors"]),
            "matched_anchor_count": 0,
            "missed_anchors": list(target["anchors"]),
            "error": f"{type(exc).__name__}: {exc}",
        }


def summarize(config: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    if len(results) != 10:
        raise RuntimeError("experiment incomplete: expected 10 document results")
    errors = [(index, item) for index, item in enumerate(results) if item.get("error")]
    if errors:
        details = "; ".join(
            f"{item.get('id') or f'result-{index + 1}'}: {item['error']}"
            for index, item in errors
        )
        raise RuntimeError(
            f"experiment incomplete: {len(errors)} render or extraction errors ({details})"
        )
    expected = sum(int(item["expected_anchor_count"]) for item in results)
    matched = sum(int(item["matched_anchor_count"]) for item in results)
    omitted = expected - matched
    omission_rate = omitted / expected
    threshold = float(config["pre_registered_decision"]["maximum_anchor_omission_rate"])
    decision_key = "at_or_below_threshold" if omission_rate <= threshold else "above_threshold"
    return {
        "experiment_id": config["experiment_id"],
        "observed_at": date.today().isoformat(),
        "sample_size": len(results),
        "metric": config["metric"],
        "pre_registered_maximum_omission_rate": threshold,
        "expected_anchor_count": expected,
        "matched_anchor_count": matched,
        "omitted_anchor_count": omitted,
        "anchor_omission_rate": round(omission_rate, 4),
        "decision": config["pre_registered_decision"][decision_key],
        "limitations": config["metric_limitations"],
        "targets_sha256": hashlib.sha256(
            json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "results": results,
    }


def run(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    with tempfile.TemporaryDirectory(prefix="vela-ingestion-qa-") as temp_dir:
        output_dir = Path(temp_dir)
        completed = subprocess.run(
            [
                "node",
                str(RENDERER),
                "--targets",
                str(config_path.resolve()),
                "--output-dir",
                str(output_dir),
            ],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=15 * 60,
        )
        renderer_output = json.loads(completed.stdout)
        rendered_by_id = {item["id"]: item for item in renderer_output["results"]}
        results = [
            evaluate_pdf(
                target,
                output_dir / f"{target['id']}.pdf",
                rendered_by_id.get(target["id"], {}),
                (
                    output_dir / rendered_by_id[target["id"]]["source_text_filename"]
                    if rendered_by_id.get(target["id"], {}).get("source_text_filename")
                    else None
                ),
            )
            for target in config["targets"]
        ]
    return summarize(config, results)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    args = parser.parse_args()
    result = run(args.targets)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
