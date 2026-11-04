"""Shared fixtures."""

import pytest

from nautical_deliverance.settings import Settings


@pytest.fixture
def settings() -> Settings:
    """Explicit test settings (no environment dependence)."""
    return Settings(
        git_sha="abc123",
        database_url="postgresql://test",
        oidc_issuer="https://issuer.test",
        oidc_audience="nd",
        oidc_jwks_url="https://issuer.test/jwks",
    )
