"""
PostgreSQL connection layer.

Uses psycopg2 with RealDictCursor so rows support dict-like access (row['col']).
A thin DBConnection wrapper provides the same execute() / commit() / close()
interface the routers and ETL already use, so no other files need restructuring.
"""

import os
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Load .env from the backend/ directory (parent of this app/ package)
load_dotenv(Path(__file__).parent.parent / ".env")

SCHEMA_PATH = Path(__file__).parent / "models" / "db_schema.sql"


def _db_config() -> dict:
    return {
        "host":     os.getenv("DB_HOST", "localhost"),
        "port":     int(os.getenv("DB_PORT", 5432)),
        "dbname":   os.getenv("DB_NAME", "dbw_accidents"),
        "user":     os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "postgres"),
    }


class _Result:
    """Wraps a psycopg2 cursor — mimics the sqlite3 cursor interface."""

    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        return self._cur.fetchone()     # returns RealDictRow (dict-like) or None

    def fetchall(self):
        return self._cur.fetchall()     # returns list[RealDictRow]

    @property
    def rowcount(self):
        return self._cur.rowcount


class DBConnection:
    """
    Wraps a psycopg2 connection and exposes a sqlite3-compatible execute() API.
    Parameter placeholder is %s (PostgreSQL standard), NOT ? (SQLite).
    """

    def __init__(self):
        self._conn = psycopg2.connect(
            **_db_config(),
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        self._conn.autocommit = False

    def execute(self, sql: str, params=None) -> _Result:
        cur = self._conn.cursor()
        cur.execute(sql, params or ())
        return _Result(cur)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type:
            self.rollback()
        self.close()


def get_connection() -> DBConnection:
    return DBConnection()


def init_db():
    """Create all tables and indexes from the SQL schema file."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_connection()
    try:
        cur = conn._conn.cursor()
        cur.execute(schema)
        conn.commit()
        cfg = _db_config()
        print(f"[DB] PostgreSQL ready — {cfg['host']}:{cfg['port']}/{cfg['dbname']}")
    finally:
        conn.close()


def get_db():
    """FastAPI dependency — yields one DBConnection per request, always closes after."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
