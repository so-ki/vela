from app.core.statuses import AnswerabilityReason
from app.services.answerability_gate import assess_answerability


def test_no_pack_refuses_with_specific_reason():
    decision = assess_answerability(pack_resolved=False)
    assert decision.answerable is False
    assert decision.reason_code == AnswerabilityReason.PACK_NOT_INSTALLED.value


def test_llm_unavailable_is_not_material_insufficiency():
    decision = assess_answerability(pack_resolved=True, llm_required=True, llm_available=False)
    assert decision.answerable is False
    assert decision.reason_code == AnswerabilityReason.LLM_UNAVAILABLE.value


def test_material_gap_refuses_as_insufficient_material():
    decision = assess_answerability(
        pack_resolved=True,
        adequacy={"is_investigation_ready": False},
        grounding_report={"grounding_rate": 0.9, "total_hits": 10},
    )
    assert decision.answerable is False
    assert decision.reason_code == AnswerabilityReason.INSUFFICIENT_MATERIAL.value


def test_zero_hits_refuses_as_no_grounded_evidence():
    decision = assess_answerability(
        pack_resolved=True,
        adequacy={"is_investigation_ready": True},
        grounding_report={"grounding_rate": 0.0, "total_hits": 0},
    )
    assert decision.answerable is False
    assert decision.reason_code == AnswerabilityReason.NO_GROUNDED_EVIDENCE.value


def test_low_grounding_rate_refuses():
    decision = assess_answerability(
        pack_resolved=True,
        grounding_report={"grounding_rate": 0.1, "total_hits": 20},
    )
    assert decision.answerable is False
    assert decision.reason_code == AnswerabilityReason.NO_GROUNDED_EVIDENCE.value


def test_healthy_scenario_is_answerable():
    decision = assess_answerability(
        pack_resolved=True,
        adequacy={"is_investigation_ready": True},
        grounding_report={"grounding_rate": 0.85, "total_hits": 12},
        tier_report={"hard_blocked_codes": []},
    )
    assert decision.answerable is True
    assert decision.reason_code is None
    assert decision.signals["grounding_rate"] == 0.85
