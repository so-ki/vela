from app.models.scenario import ComplianceChecklist, InvestigationScenario
from app.services.material_scope_review_service import run_material_scope_review


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
        description="",
        status="pending_scope",
    )
    defaults.update(kwargs)
    s = InvestigationScenario(**defaults)
    s.checklist = ComplianceChecklist(scenario_id=1, title="t", version="v0", payload={}, total_items=0)
    return s


def test_missing_destination_rule():
    scenario = _scenario(
        description="计划在本地新建厂房32000平方米，生产储能系统，未说明具体城市。",
        facility_notes="厂房 32000 m²",
    )
    findings = run_material_scope_review(scenario, {})
    ids = [f["rule_id"] for f in findings]
    assert "missing_destination" in ids


def test_env_conflict_rule():
    scenario = _scenario(
        description="本项目为扩建产线，无需环评即可开工，年产500MW组件。",
    )
    findings = run_material_scope_review(scenario, {})
    ids = [f["rule_id"] for f in findings]
    assert "env_claim_vs_new_build" in ids
