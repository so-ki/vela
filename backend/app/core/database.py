from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy import or_

from app.core.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    settings.data_dir  # ensure data directory exists
    from app.models import audit_log, scenario, user  # noqa: F401

    # Local SQLite remains zero-setup for demos and tests.  PostgreSQL schemas
    # are exclusively managed by Alembic so a web worker can never silently
    # drift production DDL through metadata.create_all().
    if engine.dialect.name != "sqlite":
        return

    Base.metadata.create_all(bind=engine)
    try:
        from app.core.migrate import (
            migrate_sqlite_checklist_revision_column,
            migrate_sqlite_generation_attempt_columns,
            migrate_sqlite_scenario_columns,
            migrate_sqlite_user_columns,
        )

        migrate_sqlite_user_columns()
        migrate_sqlite_scenario_columns()
        migrate_sqlite_generation_attempt_columns()
        migrate_sqlite_checklist_revision_column()
    except Exception:
        pass


def validate_instance_database_boundary(*, runtime_settings=None, db: Session | None = None) -> None:
    """Refuse restored databases containing users from another organisation."""

    runtime_settings = runtime_settings or get_settings()
    if not runtime_settings.is_production:
        return

    from app.models.user import User

    own_session = db is None
    session = db or SessionLocal()
    try:
        mismatch = (
            session.query(User.id)
            .filter(
                or_(
                    User.organization.is_(None),
                    User.organization != runtime_settings.instance_organization.strip(),
                )
            )
            .first()
        )
        if mismatch is not None:
            raise RuntimeError(
                "database contains an account outside INSTANCE_ORGANIZATION; "
                "refusing to start the single-tenant pilot"
            )
    finally:
        if own_session:
            session.close()
