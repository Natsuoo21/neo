"""Proof-of-life test — verifies the test infrastructure works."""

import neo


def test_version_exists():
    assert hasattr(neo, "__version__")
    assert neo.__version__ == "0.1.0"


def test_cli_entry_point_exists():
    from neo.main import main

    assert callable(main)
