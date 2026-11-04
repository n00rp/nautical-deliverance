"""Database fixtures: run migrations as nd_owner, test as nd_app."""

import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

if TYPE_CHECKING:
    from collections.abc import Iterator

APP_URL = os.environ.get("ND_DATABASE_URL")
OWNER_URL = os.environ.get("ND_MIGRATION_DATABASE_URL")

SAFE_HOSTS = {"localhost", "127.0.0.1", "db"}
ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="session")
def owner_engine() -> Iterator[Engine]:
    """Engine as nd_owner on a freshly migrated database."""
    if not (APP_URL and OWNER_URL):
        msg = "ND_DATABASE_URL (nd_app) and ND_MIGRATION_DATABASE_URL (nd_owner) not set"
        if os.environ.get("ND_REQUIRE_DB") == "1":  # CI: a missing DB is a failure, not a skip
            pytest.fail(msg)
        pytest.skip(msg)
    host = make_url(OWNER_URL).host
    if host not in SAFE_HOSTS and os.environ.get("ND_ALLOW_DESTRUCTIVE_TESTS") != "1":
        pytest.fail(
            f"refusing to run 'alembic downgrade base' against host {host!r}; "
            "use localhost/127.0.0.1/db or set ND_ALLOW_DESTRUCTIVE_TESTS=1"
        )
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(ROOT / "src/nautical_deliverance/persistence/migrations")
    )
    os.environ["ND_MIGRATION_DATABASE_URL"] = OWNER_URL
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = create_engine(OWNER_URL)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app_engine(owner_engine: Engine) -> Iterator[Engine]:  # noqa: ARG001
    """Engine as nd_app (runtime role)."""
    assert APP_URL
    engine = create_engine(APP_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def probe(owner_engine: Engine) -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    """Test-only RLS-protected table with one row for each of two orgs."""
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE _rls_probe (id serial PRIMARY KEY, organization_id uuid NOT NULL,"
                " note text NOT NULL)"
            )
        )
        conn.execute(text("ALTER TABLE _rls_probe ENABLE ROW LEVEL SECURITY"))
        conn.execute(text("ALTER TABLE _rls_probe FORCE ROW LEVEL SECURITY"))
        conn.execute(
            text(
                "CREATE POLICY org_isolation ON _rls_probe"
                " USING (organization_id ="
                " nullif(current_setting('app.organization_id', true), '')::uuid)"
                " WITH CHECK (organization_id ="
                " nullif(current_setting('app.organization_id', true), '')::uuid)"
            )
        )
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON _rls_probe TO nd_app"))
        conn.execute(text("GRANT USAGE ON SEQUENCE _rls_probe_id_seq TO nd_app"))
        for org, note in ((org_a, "a"), (org_b, "b")):
            # FORCE RLS binds the owner too, so seed under each org's scope.
            conn.execute(
                text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(org)}
            )
            conn.execute(
                text("INSERT INTO _rls_probe (organization_id, note) VALUES (:o, :n)"),
                {"o": org, "n": note},
            )
    yield org_a, org_b
    with owner_engine.begin() as conn:
        conn.execute(text("DROP TABLE _rls_probe"))
