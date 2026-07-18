from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from app.services.audit_bundle_service import build_audit_bundle
from app.services.review_service import (
    ReviewRevisionConflict,
    ReviewStateConflict,
    approve_all_pending,
    finalize_review,
    update_review_item,
)


def _review() -> dict:
    return {
        "status": "in_progress",
        "items": [
            {
                "code": "LOW-001",
                "tier": "S1",
                "gate_status": "passed",
                "hard_block": False,
                "decision": "pending",
            },
            {
                "code": "MED-001",
                "tier": "S2",
                "gate_status": "needs_review",
                "hard_block": False,
                "decision": "pending",
            },
            {
                "code": "HIGH-001",
                "tier": "S3",
                "gate_status": "blocked",
                "hard_block": True,
                "decision": "pending",
            },
        ],
    }


def test_bulk_approval_only_applies_to_low_risk_s1():
    review = approve_all_pending(_review(), expected_revision=0)
    decisions = {item["code"]: item["decision"] for item in review["items"]}
    assert decisions == {
        "LOW-001": "approved",
        "MED-001": "pending",
        "HIGH-001": "pending",
    }


def test_bulk_approval_replay_is_a_state_conflict() -> None:
    review = approve_all_pending(_review(), expected_revision=0)
    with pytest.raises(ReviewStateConflict, match="没有可批量确认"):
        approve_all_pending(review, expected_revision=review["revision"])


def test_finalize_replay_is_a_state_conflict() -> None:
    review = {
        "status": "in_progress",
        "revision": 0,
        "items": [{"code": "LOW-001", "decision": "approved"}],
    }
    finalized = finalize_review(review, expected_revision=0)
    with pytest.raises(ReviewStateConflict, match="不能重复定稿"):
        finalize_review(finalized, expected_revision=finalized["revision"])


def test_s3_approval_requires_documented_manual_basis():
    review = _review()
    with pytest.raises(ValueError, match="至少 20 字"):
        update_review_item(
            review,
            code="HIGH-001",
            decision="approved",
            comment="确认",
            expected_revision=0,
        )

    updated = update_review_item(
        review,
        code="HIGH-001",
        decision="approved",
        comment="已由巴西执业律师核对官方原文第 12 条，并记录外部意见编号 BR-001。",
        expected_revision=0,
    )
    target = next(item for item in updated["items"] if item["code"] == "HIGH-001")
    assert target["manual_override"] is True


def test_finalize_rejects_undocumented_s3_even_if_payload_was_tampered():
    review = _review()
    for item in review["items"]:
        item["decision"] = "approved"
    with pytest.raises(ValueError, match="缺少逐项覆盖依据"):
        finalize_review(review, expected_revision=0, tier_report={"s3_codes": ["HIGH-001"]})


def test_item_change_is_attributed_versioned_and_rejects_stale_client():
    review = _review()
    updated = update_review_item(
        review,
        code="MED-001",
        decision="rejected",
        comment="法源定位不足",
        reviewer_id=7,
        reviewer_name="法务 B",
        expected_revision=0,
    )

    item = next(i for i in updated["items"] if i["code"] == "MED-001")
    assert updated["revision"] == 1
    assert item["reviewer_id"] == 7
    assert item["reviewer_name"] == "法务 B"
    assert item["reviewed_at"]
    assert item["review_revision"] == 1
    assert updated["change_history"][-1]["previous"]["decision"] == "pending"

    unchanged = copy.deepcopy(updated)
    with pytest.raises(ReviewRevisionConflict, match="请刷新"):
        update_review_item(
            updated,
            code="MED-001",
            decision="approved",
            comment=None,
            reviewer_id=8,
            reviewer_name="法务 A",
            expected_revision=0,
        )
    assert updated == unchanged


def test_bulk_approval_and_finalize_capture_the_actual_actor():
    review = approve_all_pending(
        _review(),
        reviewer_id=11,
        reviewer_name="法务主管",
        expected_revision=0,
    )
    low = next(i for i in review["items"] if i["code"] == "LOW-001")
    assert low["reviewer_id"] == 11
    assert low["reviewer_name"] == "法务主管"
    assert low["review_revision"] == 1

    # Use a single fully reviewed item to isolate finalization attribution.
    finalizable = {
        "status": "in_progress",
        "reviewer_id": 11,
        "reviewer_name": "法务主管",
        "started_at": "2026-07-17T00:00:00+00:00",
        "revision": 1,
        "items": [low],
    }
    finalized = finalize_review(
        finalizable,
        reviewer_id=12,
        reviewer_name="终审法务",
        expected_revision=1,
    )
    assert finalized["revision"] == 2
    assert finalized["finalized_by_id"] == 12
    assert finalized["finalized_by_name"] == "终审法务"


def test_audit_bundle_contains_item_attribution_override_and_final_status():
    item = {
        "code": "HIGH-001",
        "decision": "approved",
        "gate_status": "blocked",
        "match_score": 80,
        "comment": "巴西律师已核对原文并给出编号明确的书面覆盖意见。",
        "manual_override": True,
        "reviewer_id": 9,
        "reviewer_name": "法务 B",
        "reviewed_at": "2026-07-17T01:00:00+00:00",
        "review_revision": 3,
    }
    payload = {
        "review": {
            "status": "approved",
            "reviewer_id": 9,
            "reviewer_name": "法务 B",
            "finalized_by_id": 10,
            "finalized_by_name": "终审法务",
            "revision": 4,
            "items": [item],
        },
        "sections_with_legal": [
            {
                "items": [
                    {
                        "code": "ENV-001",
                        "legal_hits": [
                            {
                                "id": "alesp-decreto-8468-1976-arts-57-58",
                                "source": "alesp",
                                "source_label": "圣保罗州议会官方立法库",
                                "url": "https://www.al.sp.gov.br/decreto-8468",
                                "official_url": "https://www.al.sp.gov.br/decreto-8468",
                                "title_pt": "Decreto estadual nº 8.468/1976",
                                "title_zh": "圣保罗州第 8,468/1976 号法令",
                                "match_score": 95,
                                "requires_review": True,
                            }
                        ],
                    }
                ]
            }
        ],
    }
    scenario = SimpleNamespace(
        is_demo=False,
        id=3,
        project_name="巴西工厂",
        status="review_in_progress",
        compliance_dimensions=["environment"],
        scenario_scope={},
    )
    config = SimpleNamespace(
        corpus_data={
            "version": "test",
            "default_review_status": "provisional",
            "sources": [
                {
                    "id": "alesp-decreto-8468-1976-arts-57-58",
                    "source": "alesp",
                    "review_status": "provisional",
                    "verification_scope": "official host only; expert review required",
                    "authority": "Assembleia Legislativa do Estado de São Paulo",
                    "instrument_type": "state_decree",
                    "pinpoint": "Arts. 57-58",
                    "status_as_of": "2026-07-17",
                    "last_verified_at": "2026-07-17",
                    "validity": "vigente",
                }
            ],
        },
        capability_pack_id="pack",
        capability_pack_version="1",
        capability_pack_hash="pack-hash",
        rules_artifact_id="rules",
        rules_artifact_version="1",
        rules_artifact_hash="rules-hash",
        corpus_artifact_id="corpus",
        corpus_artifact_version="1",
        corpus_artifact_hash="corpus-hash",
    )

    bundle = build_audit_bundle(
        scenario,
        payload_override=payload,
        generation_config=config,
        scenario_status_override="review_approved",
    )
    bundled_item = bundle["review_items"][0]
    assert bundle["scenario"]["status"] == "review_approved"
    assert bundled_item["reviewer_id"] == 9
    assert bundled_item["reviewer_name"] == "法务 B"
    assert bundled_item["reviewed_at"] == item["reviewed_at"]
    assert bundled_item["decision"] == "approved"
    assert bundled_item["comment"] == item["comment"]
    assert bundled_item["override"] is True
    legal_hit = bundle["legal_hits"][0]
    assert bundle["bundle_version"] == "1.2"
    assert legal_hit["source_key"] == "alesp"
    assert legal_hit["review_status"] == "provisional"
    assert legal_hit["requires_review"] is True
    assert legal_hit["verification_scope"] == "official host only; expert review required"
    assert legal_hit["pinpoint"] == "Arts. 57-58"
    assert legal_hit["status_as_of"] == "2026-07-17"
    assert legal_hit["last_verified_at"] == "2026-07-17"
