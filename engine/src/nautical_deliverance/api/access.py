"""Access dependencies and sent-flow helpers shared by the RFQ, offer and nomination routers.

No Operator: B3-D11.
"""

import uuid  # noqa: TC003  (type annotations only, kept next to the models)
from datetime import datetime
from enum import StrEnum  # noqa: TC003
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends, HTTPException, status
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session  # noqa: TC002

from nautical_deliverance.api.common import conflict
from nautical_deliverance.api.inquiries import _allow, get_now
from nautical_deliverance.api.users import get_users_engine
from nautical_deliverance.domain.identity import Principal, Role
from nautical_deliverance.domain.rfq import single_address
from nautical_deliverance.persistence.audit import Action, record_change
from nautical_deliverance.persistence.models import Contact, Inquiry

if TYPE_CHECKING:
    from collections.abc import Callable

RfqReader = Annotated[Principal, Depends(_allow(Role.ADMIN, Role.BUNKER_BUYER, Role.VIEWER))]
Writer = Annotated[Principal, Depends(_allow(Role.ADMIN, Role.BUNKER_BUYER))]
Eng = Annotated[Engine, Depends(get_users_engine)]
Now = Annotated[datetime, Depends(get_now)]


def contact_problem(contact: Contact | None, counterparty_id: uuid.UUID | None) -> str | None:
    """Why a contact cannot receive an outgoing e-mail for the counterparty, else None."""
    if contact is None:
        return "Unknown contact"
    if counterparty_id is not None and contact.counterparty_id != counterparty_id:
        return "Contact belongs to another counterparty"
    if not contact.active:
        return "Inactive contact"
    if not contact.email:
        return "Contact has no e-mail address"
    return None if single_address(contact.email) else "Contact e-mail cannot be used in a mail link"


def lock_pair[T](s: Session, model: type[T], row_id: uuid.UUID, version: int) -> tuple[Inquiry, T]:
    """Lock the inquiry, then the row (always this order); 404 unknown, 409 on a stale version."""
    inquiry_id = s.scalar(select(model.inquiry_id).where(model.id == row_id))  # type: ignore[attr-defined]
    if inquiry_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    inq = s.get(Inquiry, inquiry_id, with_for_update=True)
    row = s.get(model, row_id, with_for_update=True)
    assert inq is not None  # noqa: S101  (FK)
    assert row is not None  # noqa: S101  (selected above)
    if row.version != version:  # type: ignore[attr-defined]
        raise conflict()
    return inq, row


def move(row: Any, to: StrEnum, can: Callable[[Any, Any], bool]) -> None:  # noqa: ANN401
    """409 unless `can` allows the row's status to move to `to`."""
    if not can(type(to)(row.status), to):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Cannot move from {row.status} to {to.value}"
        )


def finish(  # noqa: PLR0913, PLR0917
    s: Session,
    principal: Principal,
    now: datetime,
    row: Any,  # noqa: ANN401
    action: Action,
    values: dict[str, Any],
) -> None:
    """Apply the values, bump the version and write one audit entry for the row's table."""
    before = {k: getattr(row, k) for k in values}
    for k, v in values.items():
        setattr(row, k, v)
    row.version += 1
    row.updated_at = now
    s.flush()
    record_change(
        s, actor=principal.user_id, entity_type=row.__tablename__, entity_id=row.id,
        action=action, before=before, after=values,
    )  # fmt: skip
