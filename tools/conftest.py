"""Registers the `req` marker for tools tests (engine/pyproject.toml covers engine tests only)."""

import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register the requirement marker."""
    config.addinivalue_line("markers", "req(id): ties a test to a requirement id, e.g. S0-R09")
    # CI job `pilot-user` sets ND_KC_REQUIRED=1: a misspelt ND_KC_TESTS must not skip silently.
    if os.environ.get("ND_KC_REQUIRED") == "1" and os.environ.get("ND_KC_TESTS") != "1":
        msg = "ND_KC_REQUIRED=1 needs ND_KC_TESTS=1"
        raise pytest.UsageError(msg)
