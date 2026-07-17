from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_state_metadata_coverage.py"
SPEC = importlib.util.spec_from_file_location("state_metadata_coverage", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_frozen_experiment_has_exactly_30_unique_targets() -> None:
    config = module.load_config(Path(__file__).resolve().parents[1] / "evals/state_metadata_targets_v1.json")
    assert config["sample_size"] == 30
    assert config["pre_registered_decision"]["state_coverage_threshold"] == 0.7


def test_inspect_response_distinguishes_absence_from_unresolved() -> None:
    resolved = module.inspect_response(
        b'<div>Nome Uniforme</div><script>{"legislationChanges": []}</script><p>Texto Atualizado</p>'
    )
    assert resolved["resolved"] is True
    assert resolved["legislation_changes_present"] is True
    assert resolved["consolidated_text_present"] is True

    missing = module.inspect_response("Resolver de URN :: urn não encontrada".encode())
    assert missing["resolved"] is False
    assert missing["legislation_changes_present"] is False


def test_transport_error_blocks_decision_instead_of_counting_as_zero() -> None:
    config = json.loads(
        (Path(__file__).resolve().parents[1] / "evals/state_metadata_targets_v1.json").read_text()
    )
    result = {
        "error": "TimeoutError",
        "resolved": False,
        "legislation_changes_present": False,
        "consolidated_text_present": False,
    }
    with pytest.raises(RuntimeError, match="incomplete"):
        module.summarize(config, [result] * 30)
