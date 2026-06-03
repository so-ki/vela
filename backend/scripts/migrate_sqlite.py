from sqlalchemy import inspect, text

from app.core.database import engine
from app.core.migrate import migrate_sqlite_user_columns

if __name__ == "__main__":
    migrate_sqlite_user_columns()
    print("migrate ok", inspect(engine).get_table_names())
