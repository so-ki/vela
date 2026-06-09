"""Tests for rules pack closed-loop suggestions."""

from app.services.playbook_deviation_service import record_deviation
from app.services.rules_pack_loop_service import generate_rules_pack_suggestions


def test_rules_pack_suggestions_empty_when_no_deviations():
    result = generate_rules_pack_suggestions("brazil_new_energy", min_reject_count=99)
    assert result["pack_id"] == "brazil_new_energy"
    assert result["auto_apply"] is False
    assert result["suggestion_count"] == 0


def test_rules_pack_suggestions_tighten_triggers(monkeypatch):
    for i in range(3):
        record_deviation(
            scenario_id=9000 + i,
            project_name="Test",
            code="LAB-001",
            title="CLT",
            comment="与本项目无关，误触发",
            reviewer_name="legal@test",
        )
    result = generate_rules_pack_suggestions("brazil_new_energy", min_reject_count=2)
    types = [s["suggestion_type"] for s in result["suggestions"]]
    assert "tighten_triggers" in types
