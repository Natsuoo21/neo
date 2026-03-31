"""Shared test fixtures for Neo."""

import os
import sqlite3
import tempfile

import pytest


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
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    # Load schema
    schema_path = os.path.join(os.path.dirname(__file__), "..", "neo", "memory", "schema.sql")
    if os.path.exists(schema_path):
        with open(schema_path) as f:
            conn.executescript(f.read())

    yield conn
    conn.close()
