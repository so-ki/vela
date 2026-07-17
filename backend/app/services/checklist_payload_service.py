"""Atomic helpers for the versioned compliance-checklist JSON document."""

from __future__ import annotations

import copy

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm.exc import StaleDataError

from app.models.scenario import InvestigationScenario


CHECKLIST_REVISION_CONFLICT_MESSAGE = (
    "项目内容已被其他用户更新，请刷新后重试；本次更改未保存"
)


class ChecklistRevisionConflict(RuntimeError):
    """Raised when a stale session attempts to replace the checklist JSON."""


def assign_checklist_payload(
    scenario: InvestigationScenario,
    payload: dict,
) -> None:
    """Assign a detached JSON snapshot while preserving mapper-level CAS."""

    if scenario.checklist is None:
        raise ValueError("场景缺少协查清单")
    scenario.checklist.payload = copy.deepcopy(payload)
    flag_modified(scenario.checklist, "payload")


def commit_checklist_payload(
    db: Session,
    scenario: InvestigationScenario,
    payload: dict,
) -> None:
    """Replace and commit the payload, translating a failed CAS consistently."""

    assign_checklist_payload(scenario, payload)
    try:
        db.commit()
    except StaleDataError as exc:
        db.rollback()
        raise ChecklistRevisionConflict(CHECKLIST_REVISION_CONFLICT_MESSAGE) from exc
