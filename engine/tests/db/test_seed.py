"""The dev seed is idempotent and visible to each org only."""

from typing import TYPE_CHECKING

from sqlalchemy import Engine, text

from nautical_deliverance.persistence import seed

if TYPE_CHECKING:
    import pytest


def test_seed_is_idempotent(owner_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running the seed twice leaves exactly one row per organization."""
    url = owner_engine.url.render_as_string(hide_password=False)
    monkeypatch.setenv("ND_MIGRATION_DATABASE_URL", url)
    seed.main()
    seed.seed_orgs(owner_engine)  # second run must not fail
    for org_id, name in seed.DEV_ORGS.items():
        with owner_engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(org_id)}
            )
            rows = conn.execute(text("SELECT name FROM organization")).scalars().all()
        assert rows == [name]
