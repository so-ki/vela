from sqlalchemy import inspect, text

from app.core.database import engine


def migrate_sqlite_user_columns() -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("users")}
    statements = []
    if "auth_provider" not in cols:
        statements.append("ALTER TABLE users ADD COLUMN auth_provider VARCHAR(32) DEFAULT 'local'")
    if "external_subject" not in cols:
        statements.append("ALTER TABLE users ADD COLUMN external_subject VARCHAR(255)")
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def migrate_sqlite_scenario_columns() -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "investigation_scenarios" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("investigation_scenarios")}
    statements = []
    if "business_archived_at" not in cols:
        statements.append(
            "ALTER TABLE investigation_scenarios ADD COLUMN business_archived_at DATETIME"
        )
    if "legal_deleted_at" not in cols:
        statements.append(
            "ALTER TABLE investigation_scenarios ADD COLUMN legal_deleted_at DATETIME"
        )
    if "investment_destination" not in cols:
        statements.append(
            "ALTER TABLE investigation_scenarios ADD COLUMN investment_destination VARCHAR(512)"
        )
    if "project_content_scale" not in cols:
        statements.append(
            "ALTER TABLE investigation_scenarios ADD COLUMN project_content_scale VARCHAR(512)"
        )
    if "funding_source" not in cols:
        statements.append("ALTER TABLE investigation_scenarios ADD COLUMN funding_source TEXT")
    if "known_risks" not in cols:
        statements.append("ALTER TABLE investigation_scenarios ADD COLUMN known_risks TEXT")
    if "rules_pack_id" not in cols:
        statements.append("ALTER TABLE investigation_scenarios ADD COLUMN rules_pack_id VARCHAR(64)")
    if "scenario_scope" not in cols:
        statements.append("ALTER TABLE investigation_scenarios ADD COLUMN scenario_scope JSON")
    if "scope_snapshot_hash" not in cols:
        statements.append("ALTER TABLE investigation_scenarios ADD COLUMN scope_snapshot_hash VARCHAR(64)")
    if "active_generation_attempt_id" not in cols:
        statements.append("ALTER TABLE investigation_scenarios ADD COLUMN active_generation_attempt_id VARCHAR(36)")
    if "is_demo" not in cols:
        statements.append("ALTER TABLE investigation_scenarios ADD COLUMN is_demo BOOLEAN DEFAULT 0 NOT NULL")
    if not statements:
        return
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def migrate_sqlite_generation_attempt_columns() -> None:
    """Backfill P0.1 lease/input columns for existing local SQLite databases."""
    if not str(engine.url).startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "scenario_generation_attempts" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("scenario_generation_attempts")}
    statements = []
    for name, ddl in (
        ("generation_input_id", "VARCHAR(36)"),
        ("generation_input_hash", "VARCHAR(64)"),
        ("sequence", "INTEGER DEFAULT 1 NOT NULL"),
        ("lease_owner", "VARCHAR(128) DEFAULT 'legacy' NOT NULL"),
        ("lease_token", "VARCHAR(64)"),
        ("lease_acquired_at", "DATETIME"),
        ("lease_expires_at", "DATETIME"),
        ("heartbeat_at", "DATETIME"),
    ):
        if name not in cols:
            statements.append(f"ALTER TABLE scenario_generation_attempts ADD COLUMN {name} {ddl}")
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
