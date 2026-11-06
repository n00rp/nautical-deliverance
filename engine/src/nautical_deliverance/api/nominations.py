"""Nomination REST API (B5): create, list, preview, edit, send, withdraw, history.

Admin and Bunker Buyer write; Viewer reads; Operator gets 403 everywhere (B5-D11). The first send
moves the inquiry from Winner selected to Nominated; later sends are amendments. Every change is
audited in the same transaction.
"""

import uuid
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from nautical_deliverance.api.access import Eng, Now, Reader, Writer  # noqa: TC001
from nautical_deliverance.api.common import conflict, scope, unprocessable
from nautical_deliverance.api.inquiries import advance
from nautical_deliverance.api.inquiry_models import HistoryOut, VersionIn
from nautical_deliverance.api.nomination_models import (
    NominationCreate,
    NominationItem,
    NominationPatch,
)
from nautical_deliverance.api.rfq_models import PreviewOut
from nautical_deliverance.api.rfqs import _contact_problem
from nautical_deliverance.domain.identity import Principal  # noqa: TC001
from nautical_deliverance.domain.inquiry import Status
from nautical_deliverance.domain.nomination import (
    NominationStatus,
    can_nomination_transition,
    render_nomination,
)
from nautical_deliverance.persistence import nomination_repo
from nautical_deliverance.persistence.audit import Action, history, record_change
from nautical_deliverance.persistence.models import Contact, Inquiry, Nomination

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

router = APIRouter()

NOMINATABLE = frozenset({Status.WINNER_SELECTED, Status.NOMINATED})


def _get[T](s: Session, model: type[T], ident: uuid.UUID, *, lock: bool = False) -> T:
    row = s.get(model, ident, with_for_update=lock)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return row


def _lock(s: Session, nom_id: uuid.UUID, version: int) -> tuple[Inquiry, Nomination]:
    """Lock the inquiry, then the nomination (always this order); 409 when the version is stale."""
    inquiry_id = s.scalar(select(Nomination.inquiry_id).where(Nomination.id == nom_id))
    if inquiry_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    inq = _get(s, Inquiry, inquiry_id, lock=True)
    nom = _get(s, Nomination, nom_id, lock=True)
    if nom.version != version:
        raise conflict()
    return inq, nom


def _move(nom: Nomination, to: NominationStatus) -> None:
    if not can_nomination_transition(NominationStatus(nom.status), to):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Cannot move from {nom.status} to {to.value}"
        )


def _contact_or_422(s: Session, contact_id: uuid.UUID, offer_id: uuid.UUID) -> None:
    """422 on contact_id unless the contact is a usable one of the offer's counterparty."""
    cp = nomination_repo.offer_counterparty(s, offer_id)
    problem = _contact_problem(s.get(Contact, contact_id), cp)
    if problem:
        field = "contact_id"
        raise unprocessable(field, problem)


def _default_contact(s: Session, offer_id: uuid.UUID) -> uuid.UUID:
    """Return the winning RFQ's contact if usable, else the counterparty's first usable one."""
    cp = nomination_repo.offer_counterparty(s, offer_id)
    for ident in nomination_repo.contact_candidates(s, offer_id, cp):
        if _contact_problem(s.get(Contact, ident), cp) is None:
            return ident
    field, message = "contact_id", "No active contact with e-mail"
    raise unprocessable(field, message)


def _audit(  # noqa: PLR0913, PLR0917
    s: Session,
    principal: Principal,
    nom: Nomination,
    action: Action,
    before: dict[str, Any] | None,
    after: dict[str, Any],
) -> None:
    record_change(
        s, actor=principal.user_id, entity_type="nomination", entity_id=nom.id,
        action=action, before=before, after=after,
    )  # fmt: skip


def _finish(  # noqa: PLR0913, PLR0917
    s: Session,
    principal: Principal,
    now: datetime,
    nom: Nomination,
    action: Action,
    values: dict[str, Any],
) -> object:
    """Apply the values, bump the version, write one audit entry, return the list item."""
    before = {k: getattr(nom, k) for k in values}
    for k, v in values.items():
        setattr(nom, k, v)
    nom.version += 1
    nom.updated_at = now
    s.flush()
    _audit(s, principal, nom, action, before, values)
    return nomination_repo.items(s, nom.inquiry_id, nom.id)[0]


# --- routes ------------------------------------------------------------------------------------


@router.get("/inquiries/{inquiry_id}/nominations", response_model=list[NominationItem])
def list_nominations(inquiry_id: uuid.UUID, principal: Reader, engine: Eng) -> object:
    """All versions of the inquiry's nomination, newest first."""
    with scope(principal, engine) as s:
        _get(s, Inquiry, inquiry_id)
        return nomination_repo.items(s, inquiry_id)


@router.post("/inquiries/{inquiry_id}/nominations", response_model=NominationItem, status_code=201)
def create_nomination(
    inquiry_id: uuid.UUID, body: NominationCreate, principal: Writer, engine: Eng, now: Now
) -> object:
    """Create a draft to the winning supplier; one at a time, also as an amendment."""
    with scope(principal, engine) as s:
        inq = _get(s, Inquiry, inquiry_id, lock=True)  # serializes concurrent creates
        if Status(inq.status) not in NOMINATABLE:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Inquiry is {inq.status}")
        if inq.winner_offer_id is None:
            field, message = "inquiry_id", "No winning offer"
            raise unprocessable(field, message)
        if s.scalar(
            select(Nomination.id).where(
                Nomination.inquiry_id == inq.id, Nomination.status == NominationStatus.DRAFT
            )
        ):
            field, message = "inquiry_id", "A nomination draft already exists"
            raise unprocessable(field, message)
        if body.contact_id is None:
            contact_id = _default_contact(s, inq.winner_offer_id)
        else:
            contact_id = body.contact_id
            _contact_or_422(s, contact_id, inq.winner_offer_id)
        nom = Nomination(
            id=uuid.uuid4(),
            organization_id=inq.organization_id,
            inquiry_id=inq.id,
            offer_id=inq.winner_offer_id,
            contact_id=contact_id,
            status=NominationStatus.DRAFT.value,
            version=1,
            created_at=now,
            created_by=principal.user_id,
            updated_at=now,
        )
        s.add(nom)
        s.flush()
        after = {"offer_id": nom.offer_id, "contact_id": contact_id, "status": nom.status}
        _audit(s, principal, nom, "create", None, after)
        return nomination_repo.items(s, inq.id, nom.id)[0]


@router.get("/nominations/{nomination_id}/preview", response_model=PreviewOut)
def get_preview(nomination_id: uuid.UUID, principal: Reader, engine: Eng) -> object:
    """Return the exact text and mail link: live for a draft, frozen once sent."""
    with scope(principal, engine) as s:
        try:
            return nomination_repo.preview(s, _get(s, Nomination, nomination_id))
        except ValueError as exc:  # a stored address that cannot go into a mail link
            field = "contact_id"
            raise unprocessable(field, "Contact e-mail cannot be used in a mail link") from exc


@router.patch("/nominations/{nomination_id}", response_model=NominationItem)
def update_nomination(
    nomination_id: uuid.UUID, body: NominationPatch, principal: Writer, engine: Eng, now: Now
) -> object:
    """Change the contact of a draft. A no-op writes nothing."""
    with scope(principal, engine) as s:
        nom = _get(s, Nomination, nomination_id, lock=True)
        if nom.version != body.version:
            raise conflict()
        if nom.status != NominationStatus.DRAFT:
            raise HTTPException(status.HTTP_409_CONFLICT, "Nomination is not a draft")
        if nom.contact_id != body.contact_id:
            _contact_or_422(s, body.contact_id, nom.offer_id)
            _finish(s, principal, now, nom, "update", {"contact_id": body.contact_id})
        return nomination_repo.items(s, nom.inquiry_id, nom.id)[0]


@router.post("/nominations/{nomination_id}/mark-sent", response_model=NominationItem)
def mark_sent(
    nomination_id: uuid.UUID, body: VersionIn, principal: Writer, engine: Eng, now: Now
) -> object:
    """Freeze the live text; the first send moves the inquiry to Nominated."""
    with scope(principal, engine) as s:
        inq, nom = _lock(s, nomination_id, body.version)
        _move(nom, NominationStatus.SENT)
        if Status(inq.status) not in NOMINATABLE:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Inquiry is {inq.status}")
        if nom.offer_id != inq.winner_offer_id:
            detail = "Winning offer changed; withdraw this draft"
            raise HTTPException(status.HTTP_409_CONFLICT, detail)
        _contact_or_422(s, nom.contact_id, nom.offer_id)
        ctx = nomination_repo.build_nomination_context(s, nom)
        subject, text_ = render_nomination(ctx)
        if Status(inq.status) is Status.WINNER_SELECTED:
            advance(s, principal, now, inq, Status.NOMINATED)
        values = {  # after the bump: the inquiry version this nomination was sent against
            "status": NominationStatus.SENT.value,
            "sequence": ctx.sequence,
            "sent_at": now,
            "sent_to_email": ctx.recipient_email,
            "sent_subject": subject,
            "sent_body": text_,
            "inquiry_version_at_send": inq.version,
        }
        return _finish(s, principal, now, nom, "send", values)


@router.post("/nominations/{nomination_id}/withdraw", response_model=NominationItem)
def withdraw(
    nomination_id: uuid.UUID, body: VersionIn, principal: Writer, engine: Eng, now: Now
) -> object:
    """Withdraw a draft; a new one may then be created."""
    with scope(principal, engine) as s:
        _, nom = _lock(s, nomination_id, body.version)
        _move(nom, NominationStatus.WITHDRAWN)
        values = {"status": NominationStatus.WITHDRAWN.value}
        return _finish(s, principal, now, nom, "withdraw", values)


@router.get("/nominations/{nomination_id}/history", response_model=list[HistoryOut])
def nomination_history(nomination_id: uuid.UUID, principal: Reader, engine: Eng) -> object:
    """Audit entries of the nomination, newest first."""
    with scope(principal, engine) as s:
        _get(s, Nomination, nomination_id)
        return [HistoryOut.model_validate(e) for e in history(s, "nomination", nomination_id)]
