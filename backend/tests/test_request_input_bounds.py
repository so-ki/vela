from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.review import ReviewItemUpdateRequest
from app.schemas.scenario import (
    BusinessSubmitRequest,
    MAX_DOCUMENT_EXTRACT_FILES,
    MAX_DOCUMENT_EXTRACT_SNAPSHOT_BYTES,
    MAX_SCENARIO_DESCRIPTION_CHARS,
    MAX_SCENARIO_DETAIL_CHARS,
    MAX_SCENARIO_RISK_CHARS,
    ScenarioCreateRequest,
)


def test_review_comment_has_a_persisted_text_limit():
    with pytest.raises(ValidationError):
        ReviewItemUpdateRequest(
            decision="approved",
            comment="x" * 5001,
            expected_revision=0,
        )


def test_scenario_create_rejects_oversized_free_text():
    base = {
        "project_name": "巴西项目",
        "description": "这是长度足够的有效项目说明文本",
    }
    for field, value in (
        ("description", "x" * (MAX_SCENARIO_DESCRIPTION_CHARS + 1)),
        ("known_risks", "x" * (MAX_SCENARIO_RISK_CHARS + 1)),
        ("remarks", "x" * (MAX_SCENARIO_DETAIL_CHARS + 1)),
    ):
        with pytest.raises(ValidationError):
            ScenarioCreateRequest(**{**base, field: value})


def test_business_submit_rejects_oversized_free_text():
    base = {
        "project_name": "巴西项目",
        "description": "这是长度足够的有效项目说明文本",
        "scope_acknowledged": True,
    }
    for field, value in (
        ("description", "x" * (MAX_SCENARIO_DESCRIPTION_CHARS + 1)),
        ("known_risks", "x" * (MAX_SCENARIO_RISK_CHARS + 1)),
        ("facility_notes", "x" * (MAX_SCENARIO_DETAIL_CHARS + 1)),
    ):
        with pytest.raises(ValidationError):
            BusinessSubmitRequest(**{**base, field: value})


def test_document_extract_snapshot_has_deep_size_and_list_bounds():
    base = {
        "project_name": "巴西项目",
        "description": "这是长度足够的有效项目说明文本",
        "scope_acknowledged": True,
    }
    with pytest.raises(ValidationError, match="文档抽取快照"):
        BusinessSubmitRequest(
            **base,
            document_extract={
                "description": "x" * (MAX_DOCUMENT_EXTRACT_SNAPSHOT_BYTES + 1),
            },
        )

    with pytest.raises(ValidationError):
        BusinessSubmitRequest(
            **base,
            document_extract={
                "files": [
                    {"filename": f"source-{index}.txt"}
                    for index in range(MAX_DOCUMENT_EXTRACT_FILES + 1)
                ]
            },
        )

    accepted = BusinessSubmitRequest(
        **base,
        document_extract={
            "files": [
                {"filename": f"source-{index}.txt"}
                for index in range(MAX_DOCUMENT_EXTRACT_FILES)
            ]
        },
    )
    assert len(accepted.document_extract.files) == MAX_DOCUMENT_EXTRACT_FILES
