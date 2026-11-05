"""Current-caller endpoint."""

import uuid  # noqa: TC003
from datetime import UTC, datetime, timedelta
from typing import Annotated

import psycopg.errors
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import (
    Engine,
    or_,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session  # noqa: TC002

from nautical_deliverance.api.auth import get_principal
from nautical_deliverance.api.common import DB_DOWN
from nautical_deliverance.domain.identity import Principal  # noqa: TC001  (FastAPI runtime)
from nautical_deliverance.persistence.db import get_engine, org_session
from nautical_deliverance.persistence.models import AppUser, Organization

router = APIRouter()
STALE_AFTER = timedelta(hours=1)


def get_me_engine() -> Engine:
    """Database engine dependency (overridable in tests)."""
    return get_engine()


NO_ACCESS = "Organization not accessible"


def upsert_user(
    session: Session, principal: Principal, org_id: uuid.UUID, *, always: bool = True
) -> None:
    """Record the caller. With always=False, write only if a claim changed or last_seen is stale."""
    now = datetime.now(UTC)
    values = {
        "name": principal.name,
        "email": principal.email,
        "roles": sorted(r.value for r in principal.roles),
    }
    stmt = insert(AppUser).values(
        id=principal.user_id, organization_id=org_id, last_seen_at=now, **values
    )
    changed = None
    if not always:
        changed = or_(
            AppUser.last_seen_at < now - STALE_AFTER,
            AppUser.organization_id != org_id,  # a foreign row must hit RLS, not be skipped
            *(getattr(AppUser, k).is_distinct_from(stmt.excluded[k]) for k in values),
        )
    try:
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=[AppUser.id], set_={"last_seen_at": now, **values}, where=changed
            )
        )
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NO_ACCESS) from exc
    except ProgrammingError as exc:
        # The user id exists under another org: its row is hidden by RLS (never say so).
        if not isinstance(exc.orig, psycopg.errors.InsufficientPrivilege):
            raise
        raise HTTPException(status.HTTP_403_FORBIDDEN, NO_ACCESS) from exc


@router.get("/me")
def me(
    principal: Annotated[Principal, Depends(get_principal)],
    engine: Annotated[Engine, Depends(get_me_engine)],
) -> dict[str, object]:
    """Return the caller and their organization; record the visit."""
    try:
        with org_session(principal.organization_id, engine) as session:
            org = session.get(Organization, principal.organization_id)
            if org is None:  # not visible under RLS: do not reveal whether it exists elsewhere
                raise HTTPException(status.HTTP_403_FORBIDDEN, NO_ACCESS)
            upsert_user(session, principal, org.id)
            return {
                "user_id": str(principal.user_id),
                "organization": {"id": str(org.id), "name": org.name},
                "roles": sorted(principal.roles),
            }
    except OperationalError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, DB_DOWN) from exc
