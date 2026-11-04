"""Engine and organization-scoped sessions (D-034)."""

from contextlib import contextmanager
from functools import lru_cache
from typing import TYPE_CHECKING

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from nautical_deliverance.settings import Settings

if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterator


@lru_cache
def get_engine() -> Engine:
    """Process-wide engine connecting as nd_app (no DDL, no RLS bypass)."""
    return create_engine(Settings().database_url)  # type: ignore[call-arg]


@contextmanager
def org_session(organization_id: uuid.UUID, engine: Engine | None = None) -> Iterator[Session]:
    """Open a transaction whose RLS scope is one organization; commits on success."""
    with Session(engine or get_engine()) as session, session.begin():
        # is_local=true: the setting dies with the transaction, never leaks via the pool.
        session.execute(
            text("SELECT set_config('app.organization_id', :id, true)"),
            {"id": str(organization_id)},
        )
        yield session
