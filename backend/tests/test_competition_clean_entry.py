from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, validate_runtime_configuration
from app.core.database import Base
from app.models import (  # noqa: F401
    audit_log,
    delivery_assurance,
    legal_source_version,
    mechanism,
    scenario,
    user,
)
from app.models.mechanism import ClaimRecord, CoverageProof, ResearchItem
from app.models.scenario import InvestigationScenario
from app.models.user import User
from scripts.seed_competition_demo import (
    AURORA_PROJECT_NAME,
    reset_competition_database,
    seed_competition_demo,
)


def test_competition_reset_never_deletes_ordinary_development_database(tmp_path: Path) -> None:
    ordinary = tmp_path / "vela.db"
    competition = tmp_path / "vela_competition.db"
    ordinary.write_bytes(b"ordinary-development-database")
    competition.write_bytes(b"stale-competition-database")
    Path(f"{competition}-wal").write_bytes(b"wal")
    Path(f"{competition}-shm").write_bytes(b"shm")

    reset_competition_database(competition)

    assert ordinary.read_bytes() == b"ordinary-development-database"
    assert not competition.exists()
    assert not Path(f"{competition}-wal").exists()
    assert not Path(f"{competition}-shm").exists()
    with pytest.raises(RuntimeError, match="restricted"):
        reset_competition_database(ordinary)


def test_competition_mode_refuses_a_non_competition_database() -> None:
    with pytest.raises(RuntimeError, match="isolated vela_competition.db"):
        validate_runtime_configuration(
            Settings(
                vela_app_mode="competition",
                database_url="sqlite:///./data/vela.db",
            )
        )


def test_fresh_competition_database_contains_only_aurora(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "vela_competition.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setenv("VELA_APP_MODE", "competition")
    monkeypatch.setenv("VELA_COMPETITION_DB_PATH", str(database_path))

    with factory() as db:
        scenario_id = seed_competition_demo(db)

        assert [row.email for row in db.query(User).order_by(User.email)] == [
            "biz@demo.vela",
            "legal@demo.vela",
        ]
        scenarios = db.query(InvestigationScenario).all()
        assert len(scenarios) == 1
        assert scenarios[0].id == scenario_id
        assert scenarios[0].project_name == AURORA_PROJECT_NAME
        assert scenarios[0].city == ""
        assert scenarios[0].is_demo is False
        assert len(scenarios[0].compliance_dimensions) == 6
        assert db.query(ResearchItem).count() == 30
        assert db.query(ClaimRecord).count() == 1
        proof = db.query(CoverageProof).one()
        assert proof.denominator_count == 30
        assert proof.proof["schema_version"] == "0.2"

    with sqlite3.connect(database_path) as raw_db:
        database_text = "\n".join(raw_db.iterdump())
    for forbidden in ("BYD", "byd", "Campinas", "campinas", "坎皮纳斯"):
        assert forbidden not in database_text
