"""User directory: lazy upsert of the caller from token claims, and GET /users."""

import uuid  # noqa: TC003  (pydantic runtime)
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import OperationalError

from nautical_deliverance.api.auth import get_principal
from nautical_deliverance.api.common import DB_DOWN, scope
from nautical_deliverance.api.me import NO_ACCESS, upsert_user
from nautical_deliverance.domain.identity import Principal, Role  # noqa: TC001  (FastAPI runtime)
from nautical_deliverance.persistence.db import get_engine, org_session
from nautical_deliverance.persistence.models import AppUser, Organization

router = APIRouter()


def get_users_engine() -> Engine:
    """Database engine dependency (overridable in tests)."""
    return get_engine()


Eng = Annotated[Engine, Depends(get_users_engine)]


def current_user(principal: Annotated[Principal, Depends(get_principal)], engine: Eng) -> Principal:
    """Return the authenticated caller, recorded in the directory (written only on change)."""
    try:
        with org_session(principal.organization_id, engine) as session:
            if session.get(Organization, principal.organization_id) is None:
                raise HTTPException(status.HTTP_403_FORBIDDEN, NO_ACCESS)
            upsert_user(session, principal, principal.organization_id, always=False)
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
    """List users of the caller's organization who hold a role, optionally one specific role."""
    if not principal.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    stmt = select(AppUser).where(func.cardinality(AppUser.roles) > 0)
    if role:
        stmt = stmt.where(AppUser.roles.contains([role.value]))
    with scope(principal, engine) as s:
        rows = s.scalars(stmt.order_by(AppUser.name, AppUser.id))
        return [UserOut(id=u.id, name=u.name, email=u.email, roles=u.roles) for u in rows]
