"""Engine factory tests (no database connection is made)."""

import pytest

from nautical_deliverance.persistence.db import get_engine


@pytest.mark.req("S0-R04")
def test_engine_uses_app_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """The runtime engine is built from ND_DATABASE_URL (the nd_app DSN)."""
    get_engine.cache_clear()
    monkeypatch.setenv("ND_DATABASE_URL", "postgresql+psycopg://nd_app:pw@localhost/nd")
    monkeypatch.setenv("ND_OIDC_ISSUER", "i")
    monkeypatch.setenv("ND_OIDC_AUDIENCE", "a")
    monkeypatch.setenv("ND_OIDC_JWKS_URL", "j")
    try:
        assert get_engine().url.username == "nd_app"
    finally:
        get_engine.cache_clear()
