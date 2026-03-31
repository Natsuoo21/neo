"""Shared test fixtures for Neo."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "neo" / "memory" / "schema.sql"


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory for test file outputs."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def memory_db():
    """Provide an in-memory SQLite connection for tests.

    Mirrors production settings: row_factory, foreign_keys enabled.
    Note: WAL mode is not supported on :memory: databases, so we skip it.
    """
    assert _SCHEMA_PATH.exists(), f"Schema file not found: {_SCHEMA_PATH}"

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    schema_sql = _SCHEMA_PATH.read_text()
    for statement in schema_sql.split(";"):
        statement = statement.strip()
        if statement:
            conn.execute(statement)

    yield conn
    conn.close()
