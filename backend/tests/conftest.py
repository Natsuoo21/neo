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
    """Provide an in-memory SQLite connection for tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # Load schema
    schema_path = os.path.join(os.path.dirname(__file__), "..", "neo", "memory", "schema.sql")
    if os.path.exists(schema_path):
        with open(schema_path) as f:
            conn.executescript(f.read())

    yield conn
    conn.close()
