"""User directory: lazy upsert of the caller from token claims, and GET /users."""

import uuid  # noqa: TC003  (pydantic runtime)
from datetime import UTC, datetime, timedelta
from typing import Annotated

import psycopg.errors
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session  # noqa: TC002

from nautical_deliverance.api.auth import get_principal
from nautical_deliverance.api.common import DB_DOWN, email_ok, scope
from nautical_deliverance.domain.identity import Principal, Role
from nautical_deliverance.persistence.db import get_engine, org_session
from nautical_deliverance.persistence.models import AppUser

router = APIRouter()
NO_ACCESS = "Organization not accessible"
STALE_AFTER = timedelta(hours=1)
MAX_NAME = 200
MAX_EMAIL = 320


def get_users_engine() -> Engine:
    """Database engine dependency (overridable in tests)."""
    return get_engine()


Eng = Annotated[Engine, Depends(get_users_engine)]


def _claims(principal: Principal) -> dict[str, object]:
    """Token claims as stored: name truncated, an invalid or overlong e-mail dropped."""
    email = principal.email
    return {
        "name": principal.name[:MAX_NAME],
        "email": email if len(email) <= MAX_EMAIL and email_ok(email) else "",
        "roles": sorted(r.value for r in principal.roles),
    }


def upsert_user(session: Session, principal: Principal, org_id: uuid.UUID) -> None:
    """Insert or update the caller and stamp last_seen_at."""
    now = datetime.now(UTC)
    values = _claims(principal)
    try:
        session.execute(
            insert(AppUser)
            .values(id=principal.user_id, organization_id=org_id, last_seen_at=now, **values)
            .on_conflict_do_update(
                index_elements=[AppUser.id], set_={"last_seen_at": now, **values}
            )
        )
    except IntegrityError as exc:  # unknown organization (FK)
        raise HTTPException(status.HTTP_403_FORBIDDEN, NO_ACCESS) from exc
    except ProgrammingError as exc:
        # The user id exists under another org: its row is hidden by RLS (never say so).
        if not isinstance(exc.orig, psycopg.errors.InsufficientPrivilege):
            raise
        raise HTTPException(status.HTTP_403_FORBIDDEN, NO_ACCESS) from exc


def current_user(principal: Annotated[Principal, Depends(get_principal)], engine: Eng) -> Principal:
    """Return the authenticated caller, recorded in the directory (written only on change)."""
    org = principal.organization_id
    try:
        with org_session(org, engine) as session:
            row = session.execute(
                select(AppUser.name, AppUser.email, AppUser.roles, AppUser.last_seen_at).where(
                    AppUser.id == principal.user_id, AppUser.organization_id == org
                )
            ).one_or_none()
            # A row under another org is hidden by RLS, so it looks missing and the insert
            # below is refused (403).
            claims = _claims(principal)
            fresh = (
                row is not None
                and (row.name, row.email, row.roles)
                == (claims["name"], claims["email"], claims["roles"])
                and datetime.now(UTC) - row.last_seen_at < STALE_AFTER
            )
            if not fresh:
                upsert_user(session, principal, org)
    except OperationalError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, DB_DOWN) from exc
    return principal


class UserOut(BaseModel):
    """A directory entry."""

    id: uuid.UUID
    name: str
    email: str
    roles: list[str]


@router.get("/users", response_model=list[UserOut])
def list_users(
    principal: Annotated[Principal, Depends(current_user)], engine: Eng, role: Role | None = None
) -> object:
    """List users of the caller's organization who hold a bunker role, or one specific role."""
    if not principal.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    # All four roles are bunker roles (D-072): a user with only unknown roles is not listed.
    wanted = [role.value] if role else [r.value for r in Role]
    stmt = select(AppUser).where(AppUser.roles.overlap(wanted))
    with scope(principal, engine) as s:
        rows = s.scalars(stmt.order_by(AppUser.name, AppUser.id))
        return [UserOut(id=u.id, name=u.name, email=u.email, roles=u.roles) for u in rows]
