"""Validate the Brazil/SP dual-track provisional rule-card experiment.

The experiment is deliberately evidence-only.  This module performs two
layers of deterministic validation without adding a runtime dependency:

1. the subset of JSON Schema Draft 2020-12 used by the bundled schema; and
2. cross-record safety invariants that JSON Schema cannot express cleanly.

It is not a legal-validity checker and does not certify any card for use in
production.  Brazilian counsel must review the underlying sources and every
rule interpretation before runtime integration is considered.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


HERE = Path(__file__).resolve().parent
DEFAULT_EXPERIMENT_PATH = HERE / "brazil_sp_environment_dual_track_v0.1.json"
DEFAULT_SCHEMA_PATH = HERE / "rule_card_experiment.schema.json"

EXPECTED_PACK_ID = "brazil_new_energy_greenfield"
EXPECTED_CARD_IDS = [f"BR-SP-ENV-RC-{number:03d}" for number in range(1, 11)]
EXPECTED_TRACKS = ("statute_forward", "form_reverse")
ALLOWED_DIFFERENCE_TYPES = {
    "scope_to_form_fields",
    "form_adds_branching_logic",
    "form_adds_identity_control",
    "form_adds_property_evidence",
}
OFFICIAL_HOSTS = {
    "www.al.sp.gov.br",
    "cetesb.sp.gov.br",
    "e.cetesb.sp.gov.br",
}
EXPECTED_SOURCE_URLS = {
    "alsp-lei-997-1976": (
        "https://www.al.sp.gov.br/repositorio/legislacao/lei/1976/"
        "compilacao-lei-997-31.05.1976.html"
    ),
    "alsp-decreto-8468-1976": (
        "https://www.al.sp.gov.br/repositorio/legislacao/decreto/1976/"
        "decreto-8468-08.09.1976.html"
    ),
    "cetesb-pla-faq": (
        "https://cetesb.sp.gov.br/licenciamentoambiental/"
        "duvidas-sobre-o-portal-de-licenciamento-ambiental-pla/"
    ),
    "cetesb-e-portal": "https://e.cetesb.sp.gov.br/portal-servicos-frontend/",
}


def load_json(path: Path | str) -> dict[str, Any]:
    """Load a JSON object, rejecting non-object roots."""

    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object at {path}")
    return value


def _json_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _resolve_local_ref(root_schema: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"only local JSON Schema references are supported: {ref}")
    node: Any = root_schema
    for raw_part in ref[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"unresolvable JSON Schema reference: {ref}")
        node = node[part]
    if not isinstance(node, dict):
        raise ValueError(f"JSON Schema reference does not resolve to an object: {ref}")
    return node


def _validate_schema_node(
    value: Any,
    node: dict[str, Any],
    root_schema: dict[str, Any],
    path: str,
    errors: list[str],
) -> None:
    """Validate the Draft 2020-12 keywords used by this evidence artifact."""

    if "$ref" in node:
        _validate_schema_node(
            value,
            _resolve_local_ref(root_schema, str(node["$ref"])),
            root_schema,
            path,
            errors,
        )
        return

    if "const" in node and value != node["const"]:
        errors.append(f"{path}: expected constant {node['const']!r}, got {value!r}")
    if "enum" in node and value not in node["enum"]:
        errors.append(f"{path}: value {value!r} is not in the allowed enum")

    expected_type = node.get("type")
    if expected_type is not None and not _json_type_matches(value, str(expected_type)):
        errors.append(f"{path}: expected type {expected_type}, got {type(value).__name__}")
        return

    if isinstance(value, dict):
        required = node.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}: missing required property {key!r}")

        properties = node.get("properties", {})
        additional = node.get("additionalProperties", True)
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in properties:
                _validate_schema_node(child, properties[key], root_schema, child_path, errors)
            elif additional is False:
                errors.append(f"{path}: unexpected property {key!r}")
            elif isinstance(additional, dict):
                _validate_schema_node(child, additional, root_schema, child_path, errors)

    if isinstance(value, list):
        minimum = node.get("minItems")
        maximum = node.get("maxItems")
        if minimum is not None and len(value) < int(minimum):
            errors.append(f"{path}: expected at least {minimum} items, got {len(value)}")
        if maximum is not None and len(value) > int(maximum):
            errors.append(f"{path}: expected at most {maximum} items, got {len(value)}")

        prefix_items = node.get("prefixItems", [])
        for index, child_schema in enumerate(prefix_items):
            if index < len(value):
                _validate_schema_node(
                    value[index], child_schema, root_schema, f"{path}[{index}]", errors
                )

        item_schema = node.get("items")
        start = len(prefix_items) if prefix_items else 0
        if item_schema is False and len(value) > start:
            errors.append(f"{path}: items beyond prefixItems are not allowed")
        elif isinstance(item_schema, dict):
            for index in range(start, len(value)):
                _validate_schema_node(
                    value[index], item_schema, root_schema, f"{path}[{index}]", errors
                )

    if isinstance(value, str):
        minimum_length = node.get("minLength")
        if minimum_length is not None and len(value) < int(minimum_length):
            errors.append(
                f"{path}: expected at least {minimum_length} characters, got {len(value)}"
            )
        pattern = node.get("pattern")
        if pattern and re.search(str(pattern), value) is None:
            errors.append(f"{path}: value does not match pattern {pattern!r}")
        value_format = node.get("format")
        if value_format == "date":
            try:
                parsed = date.fromisoformat(value)
                if parsed.isoformat() != value:
                    raise ValueError
            except ValueError:
                errors.append(f"{path}: value is not an ISO 8601 full date")
        elif value_format == "uri":
            parsed_uri = urlparse(value)
            if parsed_uri.scheme not in {"http", "https"} or not parsed_uri.netloc:
                errors.append(f"{path}: value is not an absolute HTTP(S) URI")

    if isinstance(value, int) and not isinstance(value, bool) and "minimum" in node:
        if value < int(node["minimum"]):
            errors.append(f"{path}: value is below minimum {node['minimum']}")


def validate_against_bundled_schema(
    experiment: dict[str, Any], schema: dict[str, Any]
) -> list[str]:
    """Return structural errors for the schema subset used by this artifact."""

    errors: list[str] = []
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        errors.append("schema.$schema: expected JSON Schema Draft 2020-12")
    cards_schema = (schema.get("properties") or {}).get("cards") or {}
    if cards_schema.get("minItems") != 10 or cards_schema.get("maxItems") != 10:
        errors.append("schema.properties.cards: minItems and maxItems must both equal 10")
    try:
        _validate_schema_node(experiment, schema, schema, "$", errors)
    except ValueError as exc:
        errors.append(f"schema: {exc}")
    return errors


def _duplicates(values: list[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def _semantic_errors(experiment: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    cards = experiment.get("cards")
    sources = experiment.get("source_registry")
    excluded_sources = experiment.get("excluded_sources")
    if not isinstance(cards, list) or not isinstance(sources, list):
        return errors
    if not isinstance(excluded_sources, list):
        excluded_sources = []

    if experiment.get("pack_id") != EXPECTED_PACK_ID:
        errors.append(f"pack_id: expected {EXPECTED_PACK_ID!r}")
    if experiment.get("status") != "evidence_only":
        errors.append("status: experiment must remain evidence_only")
    if experiment.get("certification_status") != "provisional":
        errors.append("certification_status: experiment must remain provisional")
    if experiment.get("runtime_integration") is not False:
        errors.append("runtime_integration: evidence experiment must not enter runtime")
    disclaimer = str(experiment.get("disclaimer") or "")
    if "不构成巴西法律意见" not in disclaimer:
        errors.append("disclaimer: must state that the experiment is not Brazilian legal advice")
    if "巴西执业律师" not in disclaimer:
        errors.append("disclaimer: must require review by Brazilian licensed counsel")

    methodology = experiment.get("methodology") or {}
    if methodology.get("tracks") != list(EXPECTED_TRACKS):
        errors.append("methodology.tracks: expected statute_forward then form_reverse")
    timing = experiment.get("timing") or {}
    for key in ("statute_forward_total_minutes", "form_reverse_total_minutes"):
        if timing.get(key) is not None:
            errors.append(f"timing.{key}: must be null because contemporaneous timing was not captured")
    if not str(timing.get("unavailable_reason") or "").strip():
        errors.append("timing.unavailable_reason: reason is required for null timing")

    source_ids = [str(source.get("source_id") or "") for source in sources if isinstance(source, dict)]
    for duplicate in _duplicates(source_ids):
        errors.append(f"source_registry: duplicate source_id {duplicate!r}")
    source_by_id = {
        str(source.get("source_id")): source
        for source in sources
        if isinstance(source, dict) and source.get("source_id")
    }
    if set(source_by_id) != set(EXPECTED_SOURCE_URLS):
        errors.append(
            "source_registry: source ids must equal the four frozen AL-SP/CETESB sources"
        )

    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            continue
        source_path = f"source_registry[{index}]"
        url = str(source.get("official_url") or "")
        host = (urlparse(url).hostname or "").lower()
        declared_host = str(source.get("official_host") or "").lower()
        expected_url = EXPECTED_SOURCE_URLS.get(str(source.get("source_id") or ""))
        if expected_url is not None and url != expected_url:
            errors.append(f"{source_path}.official_url: does not match the frozen official URL")
        if host not in OFFICIAL_HOSTS:
            errors.append(f"{source_path}.official_url: host {host!r} is not allowlisted")
        if declared_host != host:
            errors.append(
                f"{source_path}.official_host: {declared_host!r} does not match URL host {host!r}"
            )
        if source.get("review_status") != "provisional":
            errors.append(f"{source_path}.review_status: must remain provisional")
        if source.get("access_verified_at") != experiment.get("as_of"):
            errors.append(f"{source_path}.access_verified_at: must match experiment as_of")

    excluded_urls = {
        str(item.get("url"))
        for item in excluded_sources
        if isinstance(item, dict) and item.get("url")
    }
    registry_urls = {
        str(source.get("official_url"))
        for source in sources
        if isinstance(source, dict) and source.get("official_url")
    }
    for url in sorted(excluded_urls & registry_urls):
        errors.append(f"excluded_sources: excluded URL is present in source_registry: {url}")

    actual_ids = [str(card.get("rule_id") or "") for card in cards if isinstance(card, dict)]
    if actual_ids != EXPECTED_CARD_IDS:
        errors.append(
            "cards: rule_id values must be exactly BR-SP-ENV-RC-001 through "
            "BR-SP-ENV-RC-010 in order"
        )
    for duplicate in _duplicates(actual_ids):
        errors.append(f"cards: duplicate rule_id {duplicate!r}")

    difference_counts: Counter[str] = Counter()
    top_version = experiment.get("version")
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            continue
        rule_id = str(card.get("rule_id") or f"index-{index}")
        card_path = f"cards[{index}]({rule_id})"
        if card.get("pack_id") != experiment.get("pack_id"):
            errors.append(f"{card_path}.pack_id: does not match experiment pack_id")
        if card.get("version") != top_version:
            errors.append(f"{card_path}.version: does not match experiment version")
        if card.get("certification_status") != "provisional":
            errors.append(f"{card_path}.certification_status: must remain provisional")
        if card.get("production_ready") is not False:
            errors.append(f"{card_path}.production_ready: must remain false")
        if card.get("non_legal_opinion") is not True:
            errors.append(f"{card_path}.non_legal_opinion: must remain true")

        difference_type = str(card.get("difference_type") or "")
        difference_counts[difference_type] += 1
        if difference_type not in ALLOWED_DIFFERENCE_TYPES:
            errors.append(f"{card_path}.difference_type: unsupported difference type")

        citations = card.get("citations") or []
        citation_source_ids: set[str] = set()
        has_statute_source = False
        has_form_source = False
        for citation_index, citation in enumerate(citations):
            if not isinstance(citation, dict):
                continue
            citation_path = f"{card_path}.citations[{citation_index}]"
            source_id = str(citation.get("source_id") or "")
            citation_source_ids.add(source_id)
            source = source_by_id.get(source_id)
            if source is None:
                errors.append(f"{citation_path}.source_id: unknown source {source_id!r}")
                continue
            official_url = str(citation.get("official_url") or "")
            if official_url != source.get("official_url"):
                errors.append(f"{citation_path}.official_url: does not match source_registry")
            if official_url in excluded_urls:
                errors.append(f"{citation_path}.official_url: excluded source must not be cited")
            if not str(citation.get("pinpoint") or "").strip():
                errors.append(f"{citation_path}.pinpoint: pinpoint is required")
            if citation.get("access_verified_at") != source.get("access_verified_at"):
                errors.append(f"{citation_path}.access_verified_at: does not match source_registry")
            has_statute_source = has_statute_source or source_id.startswith("alsp-")
            has_form_source = has_form_source or source_id.startswith("cetesb-")
        if not has_statute_source:
            errors.append(f"{card_path}.citations: at least one AL-SP statute/decree source is required")
        if not has_form_source:
            errors.append(f"{card_path}.citations: at least one CETESB form/portal source is required")

        element_ids = [
            str(element.get("element_id") or "")
            for element in card.get("elements") or []
            if isinstance(element, dict)
        ]
        for duplicate in _duplicates(element_ids):
            errors.append(f"{card_path}.elements: duplicate element_id {duplicate!r}")
        fact_ids = [
            str(field.get("field_id") or "")
            for field in card.get("fact_fields") or []
            if isinstance(field, dict)
        ]
        for duplicate in _duplicates(fact_ids):
            errors.append(f"{card_path}.fact_fields: duplicate field_id {duplicate!r}")
        exception_ids = [
            str(exception.get("exception_id") or "")
            for exception in card.get("exceptions") or []
            if isinstance(exception, dict)
        ]
        for duplicate in _duplicates(exception_ids):
            errors.append(f"{card_path}.exceptions: duplicate exception_id {duplicate!r}")

        tracks = card.get("production_tracks") or {}
        if set(tracks) != set(EXPECTED_TRACKS):
            errors.append(f"{card_path}.production_tracks: exactly two named tracks are required")
        for track_name in EXPECTED_TRACKS:
            track = tracks.get(track_name)
            if not isinstance(track, dict):
                continue
            track_path = f"{card_path}.production_tracks.{track_name}"
            track_source_ids = {str(value) for value in track.get("source_ids") or []}
            unknown_sources = track_source_ids - set(source_by_id)
            if unknown_sources:
                errors.append(f"{track_path}.source_ids: unknown sources {sorted(unknown_sources)!r}")
            uncited_sources = track_source_ids - citation_source_ids
            if uncited_sources:
                errors.append(f"{track_path}.source_ids: uncited sources {sorted(uncited_sources)!r}")
            if track_name == "statute_forward" and not any(
                source_id.startswith("alsp-") for source_id in track_source_ids
            ):
                errors.append(f"{track_path}.source_ids: AL-SP source is required")
            if track_name == "form_reverse" and not any(
                source_id.startswith("cetesb-") for source_id in track_source_ids
            ):
                errors.append(f"{track_path}.source_ids: CETESB source is required")
            required_facts = {str(value) for value in track.get("required_facts") or []}
            missing_facts = required_facts - set(fact_ids)
            if missing_facts:
                errors.append(f"{track_path}.required_facts: unknown facts {sorted(missing_facts)!r}")
            if track.get("effort_minutes") is not None:
                errors.append(
                    f"{track_path}.effort_minutes: must be null because timing was not captured"
                )
            if not str(track.get("effort_unavailable_reason") or "").strip():
                errors.append(f"{track_path}.effort_unavailable_reason: reason is required")

    summary = experiment.get("summary") or {}
    if summary.get("card_count") != len(cards) or len(cards) != 10:
        errors.append("summary.card_count: must equal the exactly 10 cards in the experiment")
    declared_counts = summary.get("difference_type_counts") or {}
    if dict(difference_counts) != declared_counts:
        errors.append(
            "summary.difference_type_counts: does not match counts computed from cards "
            f"({dict(difference_counts)!r})"
        )
    for key in ("measured_statute_forward_minutes", "measured_form_reverse_minutes"):
        if summary.get(key) is not None:
            errors.append(f"summary.{key}: must be null because timing was not captured")

    return errors


def validate_experiment(
    experiment: dict[str, Any], schema: dict[str, Any] | None = None
) -> list[str]:
    """Return sorted, de-duplicated structural and semantic errors."""

    effective_schema = schema if schema is not None else load_json(DEFAULT_SCHEMA_PATH)
    errors = validate_against_bundled_schema(experiment, effective_schema)
    errors.extend(_semantic_errors(experiment))
    return sorted(set(errors))


def build_report(experiment_path: Path | str, schema_path: Path | str) -> dict[str, Any]:
    experiment = load_json(experiment_path)
    schema = load_json(schema_path)
    errors = validate_experiment(experiment, schema)
    return {
        "schema_version": "1.0",
        "experiment_path": str(Path(experiment_path)),
        "schema_path": str(Path(schema_path)),
        "experiment_id": experiment.get("experiment_id"),
        "card_count": len(experiment.get("cards") or []),
        "status": "passed" if not errors else "failed",
        "production_certified": False,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, default=DEFAULT_EXPERIMENT_PATH)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH)
    args = parser.parse_args()
    report = build_report(args.experiment, args.schema)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
