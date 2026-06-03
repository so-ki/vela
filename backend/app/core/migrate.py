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
