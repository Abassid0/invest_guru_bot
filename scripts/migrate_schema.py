"""
Schema migration — creates new tables and adds columns for the upgrade.
Run once: python scripts/migrate_schema.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database.models import Base, create_database_engine, get_session


def migrate():
    engine = create_database_engine()

    # Create all new tables (ConversationHistory, Watchlist, UserFeedback, SyncLog)
    Base.metadata.create_all(engine)
    print("Tables created/verified.")

    # Add new columns to Company table (nullable, non-breaking)
    session = get_session(engine)
    try:
        alter_statements = [
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS market VARCHAR(10) DEFAULT 'NGX'",
            "ALTER TABLE companies ADD COLUMN IF NOT EXISTS currency VARCHAR(3) DEFAULT 'NGN'",
        ]
        for stmt in alter_statements:
            try:
                session.execute(text(stmt))
                session.commit()
            except Exception as e:
                session.rollback()
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print(f"Column already exists, skipping: {stmt[:60]}")
                else:
                    print(f"Warning: {e}")

        # Verify
        result = session.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        ))
        tables = [row[0] for row in result]
        print(f"Tables in database: {', '.join(tables)}")

        result = session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'companies' ORDER BY ordinal_position"
        ))
        columns = [row[0] for row in result]
        print(f"Company columns: {', '.join(columns)}")

    finally:
        session.close()

    print("Migration complete.")


if __name__ == "__main__":
    migrate()
