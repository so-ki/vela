from __future__ import annotations

import copy

import pytest

from evals.rule_cards.validate_rule_cards import (
    DEFAULT_EXPERIMENT_PATH,
    DEFAULT_SCHEMA_PATH,
    EXPECTED_CARD_IDS,
    load_json,
    validate_experiment,
)


@pytest.fixture()
def experiment() -> dict:
    return load_json(DEFAULT_EXPERIMENT_PATH)


@pytest.fixture()
def schema() -> dict:
    return load_json(DEFAULT_SCHEMA_PATH)


def test_current_dual_track_experiment_passes_all_gates(experiment, schema):
    assert validate_experiment(experiment, schema) == []
    assert [card["rule_id"] for card in experiment["cards"]] == EXPECTED_CARD_IDS
    assert experiment["summary"]["card_count"] == 10
    assert sum(experiment["summary"]["difference_type_counts"].values()) == 10


def test_all_cards_are_provisional_non_production_and_have_two_untimed_tracks(experiment):
    assert experiment["status"] == "evidence_only"
    assert experiment["certification_status"] == "provisional"
    assert experiment["runtime_integration"] is False
    assert experiment["timing"]["statute_forward_total_minutes"] is None
    assert experiment["timing"]["form_reverse_total_minutes"] is None

    for card in experiment["cards"]:
        assert card["certification_status"] == "provisional"
        assert card["production_ready"] is False
        assert card["non_legal_opinion"] is True
        assert set(card["production_tracks"]) == {"statute_forward", "form_reverse"}
        for track in card["production_tracks"].values():
            assert track["effort_minutes"] is None
            assert track["effort_unavailable_reason"].strip()


def test_schema_freezes_exactly_ten_cards_and_draft_2020_12(schema):
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["cards"]["minItems"] == 10
    assert schema["properties"]["cards"]["maxItems"] == 10


@pytest.mark.parametrize(
    ("mutate", "expected_error"),
    [
        (
            lambda value: value["cards"].__setitem__(
                1,
                {**value["cards"][1], "rule_id": "BR-SP-ENV-RC-001"},
            ),
            "duplicate rule_id",
        ),
        (
            lambda value: value["cards"][0]["production_tracks"]["form_reverse"][
                "required_facts"
            ].append("invented_unregistered_fact"),
            "unknown facts",
        ),
        (
            lambda value: value["source_registry"][0].update(
                {
                    "official_url": "https://example.com/not-official",
                    "official_host": "example.com",
                }
            ),
            "is not allowlisted",
        ),
        (
            lambda value: value["cards"][0]["production_tracks"]["statute_forward"].update(
                {"effort_minutes": 12}
            ),
            "must be null because timing was not captured",
        ),
        (
            lambda value: value["cards"][0]["citations"][0].update(
                {"official_url": value["excluded_sources"][0]["url"]}
            ),
            "excluded source must not be cited",
        ),
    ],
)
def test_validator_fails_closed_on_cross_record_safety_errors(
    experiment, schema, mutate, expected_error
):
    candidate = copy.deepcopy(experiment)
    mutate(candidate)

    errors = validate_experiment(candidate, schema)

    assert any(expected_error in error for error in errors), errors


def test_schema_validator_rejects_missing_card_and_unexpected_property(experiment, schema):
    candidate = copy.deepcopy(experiment)
    candidate["cards"].pop()
    candidate["unreviewed_runtime_override"] = True

    errors = validate_experiment(candidate, schema)

    assert any("expected at least 10 items" in error for error in errors)
    assert any("unexpected property 'unreviewed_runtime_override'" in error for error in errors)
