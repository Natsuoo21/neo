"""SQLite database connection and session management."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

_DEFAULT_DB_PATH = os.environ.get("NEO_DB_PATH", "./data/neo.db")

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(db_path: str = _DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode and row factory enabled."""
    # Ensure the data directory exists
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_session(db_path: str = _DEFAULT_DB_PATH):
    """Context manager for database transactions.

    Auto-commits on success, rolls back on exception.
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(db_path: str = _DEFAULT_DB_PATH) -> None:
    """Initialize the database schema from schema.sql.

    Idempotent — uses CREATE TABLE IF NOT EXISTS.
    """
    schema_sql = _SCHEMA_PATH.read_text()
    with get_session(db_path) as conn:
        conn.executescript(schema_sql)


def get_tables(db_path: str = _DEFAULT_DB_PATH) -> list[str]:
    """Return a list of all table names in the database."""
    with get_session(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [row["name"] for row in rows]
