"""Tests for structured contract review + Red Team."""

from app.services.contract_review_service import _evaluate_structured_rule, _run_contract_red_team
from app.services.contract_house_rules_service import load_structured_house_rules


def test_must_not_violation_without_grounding_downgrades_to_yellow():
    rules = load_structured_house_rules()
    liability = next(r for r in rules if r["id"] == "liability_cap")
    clause = "The parties agree to unlimited liability for all indirect damages whatsoever."
    out = _evaluate_structured_rule(clause, liability)
    assert out is not None
    assert out["risk"] in ("RED", "YELLOW")
    if not out["grounded"]:
        assert out["risk"] == "YELLOW"


def test_must_have_missing_is_yellow():
    rules = load_structured_house_rules()
    liability = next(r for r in rules if r["id"] == "liability_cap")
    clause = "Cláusula sobre responsabilidade entre as partes sem limite explícito."
    out = _evaluate_structured_rule(clause, liability)
    assert out is not None
    assert out["risk"] == "YELLOW"


def test_red_team_downgrades_red_when_must_have_satisfied():
    findings = [
        {
            "clause_index": 1,
            "risk": "RED",
            "must_have_satisfied": True,
            "matched_rules": [{"id": "liability_cap", "label": "x"}],
        }
    ]
    challenges = _run_contract_red_team(findings, [{"index": 1, "text": "x"}])
    assert findings[0]["risk"] == "YELLOW"
    assert any(c["type"] == "false_positive_downgrade" for c in challenges)
