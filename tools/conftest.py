"""Registers the `req` marker for tools tests (engine/pyproject.toml covers engine tests only)."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register the requirement marker."""
    config.addinivalue_line("markers", "req(id): ties a test to a requirement id, e.g. S0-R09")
