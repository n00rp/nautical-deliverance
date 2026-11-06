"""Nomination request and response models (B5 spec section 4)."""

import uuid  # noqa: TC003  (pydantic runtime)
from datetime import datetime  # noqa: TC003

from pydantic import BaseModel, Field

from nautical_deliverance.api.common import Strict


class NominationCreate(Strict):
    """Create a draft; the contact defaults to the winner's."""

    contact_id: uuid.UUID | None = None


class NominationPatch(Strict):
    """Change the contact of a draft."""

    version: int = Field(ge=1)
    contact_id: uuid.UUID


class NominationItem(BaseModel):
    """One version of the inquiry's nomination."""

    id: uuid.UUID
    status: str
    sequence: int | None
    contact_name: str
    email: str
    sent_at: datetime | None
    changed_since_sent: bool
    version: int
