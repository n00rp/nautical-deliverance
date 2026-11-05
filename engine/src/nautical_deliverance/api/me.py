"""Current-caller endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Engine  # noqa: TC002  (FastAPI runtime)
from sqlalchemy.exc import OperationalError

from nautical_deliverance.api.auth import get_principal
from nautical_deliverance.api.common import DB_DOWN
from nautical_deliverance.api.users import NO_ACCESS, upsert_user
from nautical_deliverance.domain.identity import Principal  # noqa: TC001  (FastAPI runtime)
from nautical_deliverance.persistence.db import get_engine, org_session
from nautical_deliverance.persistence.models import Organization

router = APIRouter()


def get_me_engine() -> Engine:
    """Database engine dependency (overridable in tests)."""
    return get_engine()


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
