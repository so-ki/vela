"""共享测试 fixture：内存数据库会话（不触碰现有 8 个测试文件的行为）。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    from app.models import audit_log, claim, coverage, fact, material_ledger, scenario, user  # noqa: F401

    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def scenario_row(db_session):
    """一条法域中立的场景记录（刻意不使用任何真实法域值）。"""
    from app.models.scenario import ComplianceChecklist, InvestigationScenario

    row = InvestigationScenario(
        user_id=1,
        project_name="Test Project",
        country="testland",
        state="test_state",
        city="test_city",
        industry="test_industry",
        action_type="test_action",
        description="neutral fixture scenario",
        compliance_dimensions=[],
        status="pending_scope",
    )
    db_session.add(row)
    db_session.flush()
    checklist = ComplianceChecklist(
        scenario_id=row.id, title="t", version="v0.1", payload={}, total_items=0
    )
    db_session.add(checklist)
    db_session.flush()
    row.checklist = checklist
    return row
