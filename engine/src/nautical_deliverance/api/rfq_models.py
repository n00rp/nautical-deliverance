"""RFQ request and response models (B3 spec section 4)."""

import uuid  # noqa: TC003  (pydantic runtime)
from datetime import datetime  # noqa: TC003
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, Field

from nautical_deliverance.api.common import Strict

MAX_RECIPIENTS = 50


class RecipientIn(Strict):
    """One counterparty and the contact who receives its RFQ."""

    counterparty_id: uuid.UUID
    contact_id: uuid.UUID


class RfqCreate(Strict):
    """Create one draft per recipient."""

    deadline: AwareDatetime
    recipients: Annotated[list[RecipientIn], Field(min_length=1, max_length=MAX_RECIPIENTS)]


class RfqPatch(Strict):
    """Edit a draft; absent fields stay as they are."""

    version: int = Field(ge=1)
    contact_id: uuid.UUID | None = None
    response_deadline: AwareDatetime | None = None


class SuggestedContact(BaseModel):
    """An active contact with an e-mail address."""

    id: uuid.UUID
    name: str
    email: str
    is_primary: bool


class Suggestion(BaseModel):
    """A counterparty offered as a recipient."""

    counterparty_id: uuid.UUID
    name: str
    type: str
    contacts: list[SuggestedContact]
    primary_contact_id: uuid.UUID | None
    covered_product_ids: list[uuid.UUID]
    active_rfq_id: uuid.UUID | None


class Suggestions(BaseModel):
    """Counterparties by how much of the inquiry they cover at its port."""

    covers_all: list[Suggestion]
    covers_some: list[Suggestion]
    not_listed: list[Suggestion]


class RfqItem(BaseModel):
    """One row of the RFQ log."""

    id: uuid.UUID
    counterparty_name: str
    contact_name: str
    email: str
    generated_at: datetime
    sent_at: datetime | None
    status: str
    response_deadline: datetime
    offer_received: bool
    changed_since_sent: bool
    version: int


class PreviewOut(BaseModel):
    """The exact text and mail link of an RFQ."""

    to: str
    subject: str
    body: str
    mailto: str
    body_in_link: bool
