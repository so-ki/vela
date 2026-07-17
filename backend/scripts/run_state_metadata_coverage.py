#!/usr/bin/env python3
"""Run the pre-registered LexML state-metadata coverage experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ROOT / "evals/state_metadata_targets_v1.json"
LEX_ML_BASE = "https://www.lexml.gov.br/urn/"
NOT_FOUND_MARKERS = ("urn não encontrada", "documento solicitado não pôde de ser encontrado")
CHANGE_MARKERS = ("legislationchanges", 'itemprop="legislationchanges"')
CONSOLIDATED_MARKERS = (
    "texto atualizado",
    "multivigente",
    "texto consolidado",
    "legislationconsolidates",
)


def _urn(target: dict[str, str]) -> str:
    return (
        f"urn:lex:br;sao.paulo:estadual:{target['type']}:"
        f"{target['date']};{target['number']}"
    )


def inspect_response(body: bytes) -> dict[str, Any]:
    text = body.decode("utf-8", errors="replace").lower()
    not_found = any(marker in text for marker in NOT_FOUND_MARKERS)
    return {
        "resolved": not not_found and "nome uniforme" in text,
        "legislation_changes_present": any(marker in text for marker in CHANGE_MARKERS),
        "consolidated_text_present": any(marker in text for marker in CONSOLIDATED_MARKERS),
        "response_sha256": hashlib.sha256(body).hexdigest(),
    }


def fetch_target(target: dict[str, str], *, timeout: int = 30) -> dict[str, Any]:
    urn = _urn(target)
    # LexML's legacy resolver returns an empty 200 body when the URN's ':' and
    # ';' separators are percent-encoded, so retain the standardized separators.
    url = LEX_ML_BASE + quote(urn, safe=":;")
    try:
        curl = shutil.which("curl")
        if not curl:
            raise RuntimeError("curl is required for the LexML experiment")
        completed = subprocess.run(
            [
                curl,
                "-L",
                "--fail",
                "--silent",
                "--show-error",
                "--max-time",
                str(timeout),
                "--max-filesize",
                str(4 * 1024 * 1024),
                url,
            ],
            check=True,
            capture_output=True,
            timeout=timeout + 5,
        )
        body = completed.stdout
        if not body:
            raise RuntimeError("LexML returned an empty response body")
        if len(body) > 4 * 1024 * 1024:
            raise RuntimeError("LexML response exceeded 4 MiB experiment ceiling")
        result = inspect_response(body)
        result["http_status"] = 200
        result["error"] = None
    except Exception as exc:  # record transport failure; do not convert it to absence
        result = {
            "resolved": False,
            "legislation_changes_present": False,
            "consolidated_text_present": False,
            "response_sha256": None,
            "http_status": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        **target,
        "urn": urn,
        "lexml_url": url,
        "alesp_url": f"https://www.al.sp.gov.br/norma/{target['norm_id']}",
        **result,
    }


def summarize(config: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    transport_errors = sum(bool(item["error"]) for item in results)
    if transport_errors:
        raise RuntimeError(f"experiment incomplete: {transport_errors} transport errors")
    total = len(results)
    changes = sum(bool(item["legislation_changes_present"]) for item in results)
    consolidated = sum(bool(item["consolidated_text_present"]) for item in results)
    resolved = sum(bool(item["resolved"]) for item in results)
    threshold = float(config["pre_registered_decision"]["state_coverage_threshold"])
    coverage = changes / total
    decision_key = "at_or_above_threshold" if coverage >= threshold else "below_threshold"
    return {
        "experiment_id": config["experiment_id"],
        "observed_at": date.today().isoformat(),
        "sample_size": total,
        "pre_registered_threshold": threshold,
        "resolved_count": resolved,
        "resolved_rate": round(resolved / total, 4),
        "legislation_changes_count": changes,
        "legislation_changes_coverage": round(coverage, 4),
        "consolidated_text_count": consolidated,
        "consolidated_text_coverage": round(consolidated / total, 4),
        "decision": config["pre_registered_decision"][decision_key],
        "interpretation": (
            "This measures field availability in the LexML resolver, not legal validity, "
            "completeness of amendment history, or current applicability."
        ),
        "official_relation_page": config["official_relation_page"],
        "results": results,
    }


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    targets = config.get("targets")
    if not isinstance(targets, list) or len(targets) != 30:
        raise ValueError("experiment requires exactly 30 frozen targets")
    identities = {(item["type"], item["number"], item["date"]) for item in targets}
    if len(identities) != 30:
        raise ValueError("experiment targets must be unique")
    return config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8")

    config = load_config(args.targets)
    ordered: list[dict[str, Any] | None] = [None] * len(config["targets"])
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(fetch_target, target): index
            for index, target in enumerate(config["targets"])
        }
        for future in as_completed(futures):
            ordered[futures[future]] = future.result()
    result = summarize(config, [item for item in ordered if item is not None])
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
