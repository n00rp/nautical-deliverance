"""Who is calling: the authenticated principal."""

import uuid  # noqa: TC003 - dataclass field types
from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    """Roles carried in the access token."""

    ADMIN = "admin"
    BUNKER_BUYER = "bunker_buyer"
    OPERATOR = "operator"
    VIEWER = "viewer"


@dataclass(frozen=True)
class Principal:
    """An authenticated caller bound to one organization."""

    user_id: uuid.UUID
    organization_id: uuid.UUID
    roles: frozenset[Role]
    name: str = ""
    email: str = ""
