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


def _use_database(monkeypatch: pytest.MonkeyPatch, path: Path) -> sa.Engine:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path}")
    get_settings.cache_clear()
    return sa.create_engine(f"sqlite:///{path}")


def _insert_legacy_release(
    engine: sa.Engine,
    release_id: str = "legacy-release",
    *,
    schema_version: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    schema_column = ", schema_version" if schema_version is not None else ""
    schema_value = ", :schema_version" if schema_version is not None else ""
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                f"""
                INSERT INTO scenario_delivery_releases (
                    id, scenario_id, expert_attestation_id, uat_acceptance_id,
                    deployment_evidence_id, snapshot_hash, release_hash,
                    release_note, status, released_by, released_at, expires_at,
                    created_at{schema_column}
                ) VALUES (
                    :id, 1, :attestation, :uat, :deployment, :snapshot, :release,
                    :note, 'active', 1, :now, :now, :now{schema_value}
                )
                """
            ),
            {
                "id": release_id,
                "attestation": "a" * 36,
                "uat": "u" * 36,
                "deployment": "d" * 36,
                "snapshot": "1" * 64,
                "release": "2" * 64,
                "note": "legacy release created before schema identity",
                "now": now,
                "schema_version": schema_version,
            },
        )


def test_0007_backfills_not_null_removes_default_and_round_trips(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    engine = _use_database(monkeypatch, tmp_path / "upgrade.db")
    command.upgrade(_config(), "20260718_0006")
    _insert_legacy_release(engine)

    command.upgrade(_config(), "20260719_0007")
    with engine.begin() as connection:
        value = connection.execute(
            sa.text(
                "SELECT schema_version FROM scenario_delivery_releases "
                "WHERE id = 'legacy-release'"
            )
        ).scalar_one()
        columns = {
            row[1]: row for row in connection.execute(
                sa.text("PRAGMA table_info('scenario_delivery_releases')")
            )
        }
        assert value == "1.1"
        assert columns["schema_version"][3] == 1
        assert columns["schema_version"][4] is None
    with pytest.raises(sa.exc.IntegrityError):
        _insert_legacy_release(engine, "missing-explicit-version")

    command.downgrade(_config(), "20260718_0006")
    with engine.begin() as connection:
        names = {
            row[1] for row in connection.execute(
                sa.text("PRAGMA table_info('scenario_delivery_releases')")
            )
        }
        assert "schema_version" not in names
    command.upgrade(_config(), "head")
    with engine.begin() as connection:
        assert connection.execute(
            sa.text(
                "SELECT schema_version FROM scenario_delivery_releases "
                "WHERE id = 'legacy-release'"
            )
        ).scalar_one() == "1.1"


def test_0007_fresh_database_and_unknown_version_downgrade_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    engine = _use_database(monkeypatch, tmp_path / "fresh.db")
    command.upgrade(_config(), "head")
    _insert_legacy_release(engine, schema_version="1.1")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE scenario_delivery_releases SET schema_version = '9.9'"
            )
        )
    with pytest.raises(RuntimeError, match="refusing to drop"):
        command.downgrade(_config(), "20260718_0006")
