from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa

from app.core.config import get_settings


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _config() -> Config:
    return Config(str(BACKEND_ROOT / "alembic.ini"))


def _database(monkeypatch: pytest.MonkeyPatch, path: Path) -> sa.Engine:
    url = f"sqlite:///{path}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    return sa.create_engine(url)


def _insert_legacy_fact(engine: sa.Engine) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO fact_records (
                    id, scenario_id, subject, attribute, value, fact_time,
                    block_id, fact_pack_version, source_document, status,
                    confirmation_note, business_confirmed_by,
                    business_confirmed_at, created_by, created_at
                ) VALUES (
                    'legacy-fact', 1, 'project', 'site', 'Campinas',
                    '2026-07-19', 'upload:legacy', 'facts-v1', NULL,
                    'submitted', NULL, NULL, NULL, 1, :now
                )
                """
            ),
            {"now": now},
        )


def test_0008_backfills_fact_polarity_has_no_default_and_round_trips_empty_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    engine = _database(monkeypatch, tmp_path / "research-upgrade.db")
    command.upgrade(_config(), "20260719_0007")
    _insert_legacy_fact(engine)

    command.upgrade(_config(), "20260719_0008")
    with engine.begin() as connection:
        polarity = connection.execute(
            sa.text(
                "SELECT assertion_polarity FROM fact_records "
                "WHERE id = 'legacy-fact'"
            )
        ).scalar_one()
        columns = {
            row[1]: row
            for row in connection.execute(sa.text("PRAGMA table_info('fact_records')"))
        }
        tables = {
            row[0]
            for row in connection.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        assert polarity == "unspecified"
        assert columns["assertion_polarity"][3] == 1
        assert columns["assertion_polarity"][4] is None
        assert "research_items" in tables

    command.downgrade(_config(), "20260719_0007")
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.execute(sa.text("PRAGMA table_info('fact_records')"))
        }
        assert "assertion_polarity" not in columns
    command.upgrade(_config(), "head")


def test_0008_downgrade_refuses_to_discard_explicit_fact_polarity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    engine = _database(monkeypatch, tmp_path / "research-guard.db")
    command.upgrade(_config(), "20260719_0007")
    _insert_legacy_fact(engine)
    command.upgrade(_config(), "head")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE fact_records SET assertion_polarity = 'negative' "
                "WHERE id = 'legacy-fact'"
            )
        )
    with pytest.raises(RuntimeError, match="refusing to discard"):
        command.downgrade(_config(), "20260719_0007")
