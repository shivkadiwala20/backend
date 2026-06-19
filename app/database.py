import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "dbw_accidents.db"
SCHEMA_PATH = Path(__file__).parent / "models" / "db_schema.sql"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row        # enables row['column_name'] access
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA cache_size = -64000")   # 64 MB page cache
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db():
    """Create all tables and indexes from the SQL schema file."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as conn:
        conn.executescript(schema)
    print(f"[DB] Ready: {DB_PATH}")


def get_db():
    """FastAPI dependency — yields one connection per request, always closes after."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
