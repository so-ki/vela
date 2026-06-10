from unittest.mock import patch

from app.models.scenario import ComplianceChecklist, InvestigationScenario
from app.services.issue_identification_service import run_issue_identification


def _scenario(**kwargs) -> InvestigationScenario:
    defaults = dict(
        id=1,
        user_id=1,
        project_name="测试",
        rules_pack_id="brazil_new_energy",
        country="brazil",
        state="sao_paulo",
        city="campinas",
        industry="new_energy",
        action_type="greenfield_plant",
        description="计划在坎皮纳斯新建储能工厂，创造450个岗位。",
        status="pending_scope",
    )
    defaults.update(kwargs)
    s = InvestigationScenario(**defaults)
    s.checklist = ComplianceChecklist(scenario_id=1, title="t", version="v0", payload={}, total_items=0)
    return s


def test_issue_identification_grounding_filters_bad_anchor():
    scenario = _scenario()
    payload = {"document_extract": {"facts": []}}
    mock_llm = {
        "suggestions": [
            {
                "code": "FOR-005",
                "title": "合资并购",
                "confidence": "high",
                "fact_anchor": "这段文字不在材料里",
                "rationale": "test",
            }
        ]
    }
    with patch("app.services.issue_identification_service.is_llm_enabled", return_value=True):
        with patch(
            "app.services.issue_identification_service.chat_completion_json",
            return_value=(mock_llm, None),
        ):
            result = run_issue_identification(scenario, payload, user_id=1)
    assert result["suggestions"] == []
    assert result["agent_step"]["status"] == "empty"


def test_issue_identification_keeps_grounded_suggestion():
    scenario = _scenario(description="计划与本地企业合资收购电池产线，需 CADE 审查。")
    payload = {}
    anchor = "合资收购电池产线"
    mock_llm = {
        "suggestions": [
            {
                "code": "FOR-005",
                "title": "合资并购",
                "confidence": "medium",
                "fact_anchor": anchor,
                "rationale": "材料提及合资收购",
            }
        ]
    }
    with patch("app.services.issue_identification_service.is_llm_enabled", return_value=True):
        with patch(
            "app.services.issue_identification_service.chat_completion_json",
            return_value=(mock_llm, None),
        ):
            result = run_issue_identification(scenario, payload, user_id=1)
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["code"] == "FOR-005"


def test_issue_identification_skipped_without_llm():
    scenario = _scenario()
    with patch("app.services.issue_identification_service.is_llm_enabled", return_value=False):
        result = run_issue_identification(scenario, {}, user_id=1)
    assert result["agent_step"]["status"] == "skipped"
