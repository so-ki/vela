"""删除巴西测试。

判据（docs/design/CODE_REVIEW_CHECKLIST.md）：
  删掉全部巴西语料和规则后仍能运行的，是平台；
  删掉后不知道该查什么的，是包。

本文件验证两件事：
  1. 机制层（账本/五元组/Claim/覆盖/拒答门/加载器）在一个法域中立的
     fixture 包上跑通成功路径与拒答路径——不依赖任何巴西内容。
  2. 机制层源码不含法域字面量（回归护栏 grep）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.core.statuses import AnswerabilityReason, ClaimVerdict, MaterialBlockState
from app.packs import loader
from app.services.answerability_gate import assess_answerability
from app.services.claim_compiler import compile_claims
from app.services.coverage_service import build_scenario_proof, sync_tasks_from_payload
from app.services.fact_service import record_facts_from_extract
from app.services.material_ledger_service import bulk_transition, ledger_projection, record_intake

APP_DIR = Path(__file__).resolve().parents[1] / "app"

NEUTRAL_MANIFEST = {
    "manifest_version": "0.1-draft",
    "pack_id": "neutralia_basic",
    "jurisdiction": {"chain": ["NT"], "country": "neutralia"},
    "supported_issues": ["general_compliance"],
    "exclusions": ["everything else"],
    "certification_status": "provisional",
    "coverage_denominators": {
        "neutral_list": {"label": "official neutral list", "kind": "curated_official_list"}
    },
}


def _install_neutral_pack(tmp_path):
    pack_dir = tmp_path / "neutralia_basic"
    pack_dir.mkdir()
    (pack_dir / "manifest.json").write_text(json.dumps(NEUTRAL_MANIFEST), encoding="utf-8")
    return tmp_path


def test_loader_works_with_neutral_pack_only(tmp_path):
    root = _install_neutral_pack(tmp_path)
    loader.clear_caches()
    packs = loader.list_installed_packs(root=root)
    assert [p["pack_id"] for p in packs] == ["neutralia_basic"]
    assert loader.coverage_denominators("neutralia_basic", root=root)["neutral_list"]["kind"] == (
        "curated_official_list"
    )


def test_mechanism_layer_success_path_without_brazil(db_session, scenario_row):
    """成功路径：中立材料 → 账本 → 事实 → Claim(supported) → 覆盖证明 → 可答。"""
    snapshot = {
        "filename": "neutral.pdf",
        "facts": [
            {
                "field": "workforce_size",
                "value": "42",
                "source_filename": "neutral.pdf",
                "verification_status": "verified",
                "grounding_score": 0.95,
            }
        ],
    }
    mapping = record_intake(
        db_session,
        scenario_id=scenario_row.id,
        pack_id="neutralia_basic",
        uploads=[("neutral.pdf", b"neutral content", None)],
        extract_snapshot=snapshot,
    )
    record_facts_from_extract(
        db_session,
        scenario_id=scenario_row.id,
        subject="Neutral Project",
        extract_snapshot=snapshot,
        block_by_name=mapping,
    )
    brief = {
        "sections": [
            {
                "items": [
                    {
                        "code": "GEN-001",
                        "gate_status": "passed",
                        "match_score": 88,
                        "requires_review": False,
                        "risk_zh": "neutral conclusion",
                        "citations": [
                            {
                                "id": "n-1",
                                "url": "https://official.neutralia.test/law/1",
                                "source_label": "neutral-official",
                                "citation_status": "corpus_verified",
                                "grounding_score": 0.9,
                            }
                        ],
                    }
                ]
            }
        ]
    }
    payload = {
        "brief": brief,
        "investigation_adequacy": {
            "dimensions": [{"dimension_id": "gen", "elements": [{"id": "e1", "status": "covered"}]}],
            "is_investigation_ready": True,
        },
        "grounding_report": {"grounding_rate": 0.9, "total_hits": 1},
    }
    projections = compile_claims(db_session, scenario_row.id, brief)
    assert projections[0]["verdict"] == ClaimVerdict.SUPPORTED.value
    sync_tasks_from_payload(db_session, scenario_row.id, payload)
    proof = build_scenario_proof(db_session, scenario_row.id, payload, claim_projections=projections)
    assert proof is not None and proof.covered_count == 1
    decision = assess_answerability(
        pack_resolved=True,
        grounding_report=payload["grounding_report"],
        adequacy=payload["investigation_adequacy"],
    )
    assert decision.answerable is True
    moved = bulk_transition(db_session, scenario_row.id, MaterialBlockState.IN_USE)
    assert moved >= 1
    assert all(
        p["state"] in {s.value for s in MaterialBlockState}
        for p in ledger_projection(db_session, scenario_row.id)
    )


def test_mechanism_layer_refusal_path_without_brazil(db_session, scenario_row):
    """拒答路径：没有能力包 → pack_not_installed；有包无证据 → no_grounded_evidence。"""
    no_pack = assess_answerability(pack_resolved=False)
    assert no_pack.answerable is False
    assert no_pack.reason_code == AnswerabilityReason.PACK_NOT_INSTALLED.value

    brief = {
        "sections": [
            {
                "items": [
                    {
                        "code": "GEN-002",
                        "gate_status": "passed",
                        "match_score": 0,
                        "requires_review": True,
                        "risk_zh": "no evidence conclusion",
                        "citations": [],
                    }
                ]
            }
        ]
    }
    projections = compile_claims(db_session, scenario_row.id, brief)
    assert projections[0]["verdict"] == ClaimVerdict.UNANSWERABLE.value

    decision = assess_answerability(
        pack_resolved=True,
        grounding_report={"grounding_rate": 0.0, "total_hits": 0},
        adequacy={"is_investigation_ready": True},
    )
    assert decision.answerable is False
    assert decision.reason_code == AnswerabilityReason.NO_GROUNDED_EVIDENCE.value


MECHANISM_MODULES = [
    APP_DIR / "core" / "statuses.py",
    APP_DIR / "packs" / "loader.py",
    APP_DIR / "services" / "material_ledger_service.py",
    APP_DIR / "services" / "fact_service.py",
    APP_DIR / "services" / "claim_compiler.py",
    APP_DIR / "services" / "coverage_service.py",
    APP_DIR / "services" / "answerability_gate.py",
]

FORBIDDEN = re.compile(r"brazil|brasil|lexml|campinas|sao.?paulo|planalto|jusbrasil", re.IGNORECASE)


def test_mechanism_modules_are_jurisdiction_neutral():
    """回归护栏：机制层源码不得出现法域字面量（危险带守卫）。"""
    offenders: list[str] = []
    for module in MECHANISM_MODULES:
        text = module.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if FORBIDDEN.search(line):
                offenders.append(f"{module.name}:{i}: {line.strip()}")
    assert not offenders, "机制层出现法域字面量：\n" + "\n".join(offenders)
