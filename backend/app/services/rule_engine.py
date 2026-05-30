from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

RULES_PATH = Path(__file__).resolve().parents[1] / "rules" / "brazil_new_energy.json"

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class ScenarioInput:
    project_name: str
    country: str
    state: str
    city: str
    industry: str
    action_type: str
    investment_structure: str
    description: str
    compliance_dimensions: list[str]
    employee_count: Optional[int] = None
    capacity_notes: Optional[str] = None
    facility_notes: Optional[str] = None
    board_date: Optional[str] = None
    start_date: Optional[str] = None
    production_date: Optional[str] = None
    remarks: Optional[str] = None


@lru_cache
def load_rules() -> dict[str, Any]:
    with open(RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_rules_catalog() -> dict[str, Any]:
    rules = load_rules()
    return {
        "jurisdiction": rules["jurisdiction"],
        "industries": [
            {"id": k, "name": v["name"]} for k, v in rules["industries"].items()
        ],
        "action_types": [
            {"id": k, "name": v["name"]} for k, v in rules["action_types"].items()
        ],
        "dimensions": [
            {
                "id": k,
                "name": v["name"],
                "name_pt": v["name_pt"],
                "description": v["description"],
                "order": v["order"],
            }
            for k, v in sorted(rules["dimensions"].items(), key=lambda x: x[1]["order"])
        ],
        "supported_locations": [
            {"country": "brazil", "state": "sao_paulo", "state_name": "圣保罗州", "city": "campinas", "city_name": "坎皮纳斯"}
        ],
    }


def _normalize_text(text: str) -> str:
    return text.lower()


def _score_item(item: dict[str, Any], corpus: str, selected_dimensions: set[str]) -> Optional[dict[str, Any]]:
    if item["dimension"] not in selected_dimensions:
        return None

    score = 0
    matched_triggers: list[str] = []
    for trigger in item.get("triggers", []):
        if trigger.lower() in corpus or trigger in corpus:
            score += 2
            matched_triggers.append(trigger)

    if item.get("always_include"):
        score += 5

    if score == 0:
        return None

    return {
        **item,
        "relevance_score": score,
        "matched_triggers": matched_triggers,
        "rationale": _build_rationale(item, matched_triggers),
    }


def _build_rationale(item: dict[str, Any], matched_triggers: list[str]) -> str:
    if item.get("always_include") and matched_triggers:
        return f"该维度必查项；场景描述匹配关键词：{', '.join(matched_triggers)}"
    if item.get("always_include"):
        return "该维度核心必查项，与所选合规关注点直接相关。"
    if matched_triggers:
        return f"场景描述匹配关键词：{', '.join(matched_triggers)}"
    return "根据所选审查维度纳入核查清单。"


def detect_industry(description: str, industry: str) -> str:
    rules = load_rules()
    corpus = _normalize_text(description)
    if industry in rules["industries"]:
        return industry
    for ind_id, ind in rules["industries"].items():
        if any(kw.lower() in corpus for kw in ind["keywords"]):
            return ind_id
    return industry or "new_energy"


def detect_action_type(description: str, action_type: str) -> str:
    rules = load_rules()
    corpus = _normalize_text(description)
    if action_type in rules["action_types"]:
        return action_type
    for act_id, act in rules["action_types"].items():
        if any(kw.lower() in corpus for kw in act["keywords"]):
            return act_id
    return action_type or "greenfield_plant"


def generate_checklist(scenario: ScenarioInput) -> dict[str, Any]:
    rules = load_rules()
    corpus = _normalize_text(
        " ".join(
            filter(
                None,
                [
                    scenario.description,
                    scenario.project_name,
                    scenario.investment_structure,
                    scenario.capacity_notes or "",
                    scenario.facility_notes or "",
                    scenario.remarks or "",
                    str(scenario.employee_count or ""),
                ],
            )
        )
    )

    selected = set(scenario.compliance_dimensions)
    valid_dimensions = set(rules["dimensions"].keys())
    selected = selected & valid_dimensions

    intent_meta: dict[str, Any] = {"mode": "rules"}
    try:
        from app.services.intent_parser import parse_scenario_intent

        intent, err = parse_scenario_intent(
            description=scenario.description,
            project_name=scenario.project_name,
            investment_structure=scenario.investment_structure,
        )
        if intent and intent.get("dimensions"):
            selected = selected | (set(intent["dimensions"]) & valid_dimensions)
            intent_meta = intent
        elif err:
            intent_meta = {"mode": "rules", "llm_skipped": err}
    except Exception as exc:
        intent_meta = {"mode": "rules", "llm_skipped": str(exc)[:120]}

    if not selected:
        selected = valid_dimensions

    scored_items: list[dict[str, Any]] = []
    for item in rules["checklist_items"]:
        result = _score_item(item, corpus, selected)
        if result:
            scored_items.append(result)

    # State/city overlay: ensure referenced items included
    state_overlay = rules.get("state_overlays", {}).get(scenario.state, {})
    city_overlay = state_overlay.get("cities", {}).get(scenario.city, {})
    extra_ids = set(city_overlay.get("extra_items", []))
    item_by_id = {i["id"]: i for i in rules["checklist_items"]}
    existing_ids = {i["id"] for i in scored_items}
    for eid in extra_ids:
        if eid in item_by_id and eid not in existing_ids and item_by_id[eid]["dimension"] in selected:
            extra = {
                **item_by_id[eid],
                "relevance_score": 6,
                "matched_triggers": ["campinas"],
                "rationale": "坎皮纳斯市/圣保罗州地域叠加必查项。",
            }
            scored_items.append(extra)

    scored_items.sort(
        key=lambda x: (
            rules["dimensions"][x["dimension"]]["order"],
            PRIORITY_ORDER.get(x["priority"], 9),
            -x["relevance_score"],
            x["id"],
        )
    )

    sections: list[dict[str, Any]] = []
    for dim_id in sorted(selected, key=lambda d: rules["dimensions"][d]["order"]):
        dim = rules["dimensions"][dim_id]
        items = [i for i in scored_items if i["dimension"] == dim_id]
        if not items:
            continue
        sections.append(
            {
                "dimension_id": dim_id,
                "dimension_name": dim["name"],
                "dimension_name_pt": dim["name_pt"],
                "description": dim["description"],
                "items": [
                    {
                        "code": i["id"],
                        "title": i["title"],
                        "description": i["description"],
                        "priority": i["priority"],
                        "relevance_score": i["relevance_score"],
                        "rationale": i["rationale"],
                        "matched_triggers": i.get("matched_triggers", []),
                        "status": "pending",
                    }
                    for i in items
                ],
            }
        )

    detected_industry = detect_industry(scenario.description, scenario.industry)
    detected_action = detect_action_type(scenario.description, scenario.action_type)

    return {
        "title": f"《拉美投资合规专项核查清单》— {scenario.project_name}",
        "jurisdiction": rules["jurisdiction"]["name"],
        "detected_industry": detected_industry,
        "detected_industry_name": rules["industries"].get(detected_industry, {}).get("name", detected_industry),
        "detected_action_type": detected_action,
        "detected_action_type_name": rules["action_types"].get(detected_action, {}).get("name", detected_action),
        "selected_dimensions": list(selected),
        "intent_parsing": intent_meta,
        "total_items": sum(len(s["items"]) for s in sections),
        "sections": sections,
        "disclaimer": (
            "本清单为 AI 辅助生成的协查备料清单，不构成正式法律意见。"
            "每条事项须在 Step 3 法条检索后绑定溯源片段，并经法务复核后方可定稿。"
        ),
    }


def get_demo_scenario_template() -> dict[str, Any]:
    return {
        "project_name": "BYD 坎皮纳斯新能源工厂（演示案例）",
        "country": "brazil",
        "state": "sao_paulo",
        "city": "campinas",
        "industry": "new_energy",
        "action_type": "greenfield_plant",
        "investment_structure": "中资母公司通过巴西全资子公司投资，100% 外资",
        "description": (
            "巴西圣保罗州的坎皮纳斯市（Campinas）已被选为比亚迪最新工厂的所在地，"
            "该项目将为当地创造约450个新的就业岗位。该工厂预计于2020年投产，"
            "不仅将启动南美洲唯一一款长续航纯电动公交车的制造与组装业务，"
            "还将生产首款具备极高防火安全性且可回收的磷酸铁锂电池包。"
            "在投产的第一年，该工厂将具备最高1000辆电动大巴及其所有配套电池的年生产能力。"
            "除了大巴和电池，还计划生产太阳能电池板和储能系统。"
            "除了占地32,000平方米和20,000平方米的制造设施外，"
            "还计划为光伏、智能电网和LED照明业务开设研发中心。"
        ),
        "employee_count": 450,
        "capacity_notes": "首年最多 1000 台电动客车及配套电池",
        "facility_notes": "厂房 32,000 m² + 20,000 m²；含研发中心",
        "compliance_dimensions": ["labor", "foreign_investment", "tax", "industry_access"],
        "board_date": "2013-12-03",
        "start_date": "2015-06-01",
        "production_date": "2020-10-01",
        "remarks": "同时规划光伏、储能产线及研发中心",
    }


def get_mining_demo_scenario_template() -> dict[str, Any]:
    """矿产投资场景模板（行业定制 MVP）。"""
    return {
        "project_name": "巴西铁矿绿地投资（演示模板）",
        "country": "brazil",
        "state": "minas_gerais",
        "city": "belo_horizonte",
        "industry": "new_energy",
        "action_type": "greenfield_plant",
        "investment_structure": "合资 SPV，外资占比 70%",
        "description": (
            "中资矿业企业在米纳斯吉拉斯州考察铁矿选矿与物流枢纽项目，"
            "涉及环境许可、原住民土地咨询、外资登记及州级税制优惠申请。"
        ),
        "employee_count": 120,
        "capacity_notes": "年处理矿石 200 万吨",
        "facility_notes": "选矿厂 + 铁路装车设施",
        "compliance_dimensions": ["foreign_investment", "tax", "industry_access", "labor"],
        "remarks": "行业模板演示：规则库仍以新能源条目为主，展示多场景输入能力",
    }
