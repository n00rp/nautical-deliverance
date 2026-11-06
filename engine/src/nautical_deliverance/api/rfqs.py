"""RFQ REST API (B3): suggestions, drafts, log, preview, edit, send, withdraw, decline, history.

Admin and Bunker Buyer write; Viewer reads; Operator gets 403 everywhere (B3-D11). Drafts are
created atomically, one per recipient. Every change is audited in the same transaction.
"""

import uuid
from datetime import datetime  # noqa: TC003  (FastAPI runtime)
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session  # noqa: TC002  (FastAPI runtime)

from nautical_deliverance.api.access import (
    Eng,
    Now,
    Reader,
    Writer,
    contact_problem,
    finish,
    lock_pair,
    move,
)
from nautical_deliverance.api.common import conflict, scope, unprocessable
from nautical_deliverance.api.inquiries import advance, bump_and_audit
from nautical_deliverance.api.inquiry_models import HistoryOut, VersionIn
from nautical_deliverance.api.rfq_models import (
    PreviewOut,
    RecipientIn,
    RfqCreate,
    RfqItem,
    RfqPatch,
    Suggestions,
)
from nautical_deliverance.domain.identity import Principal  # noqa: TC001
from nautical_deliverance.domain.inquiry import Status, ready_to_leave_draft
from nautical_deliverance.domain.rfq import (
    RfqStatus,
    can_rfq_transition,
    render_rfq,
)
from nautical_deliverance.persistence import rfq_repo
from nautical_deliverance.persistence.audit import Action, history, record_change
from nautical_deliverance.persistence.inquiry_repo import is_active_rfq
from nautical_deliverance.persistence.models import (
    Contact,
    Counterparty,
    Inquiry,
    Offer,
    Rfq,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

router = APIRouter()

CREATABLE = frozenset({Status.DRAFT, Status.RFQ_SENT, Status.OFFERS_RECEIVED})


def _inquiry(s: Session, inquiry_id: uuid.UUID, *, lock: bool = False) -> Inquiry:
    inq = s.get(Inquiry, inquiry_id, with_for_update=lock)
    if inq is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return inq


def _rfq(s: Session, rfq_id: uuid.UUID, *, lock: bool = False) -> Rfq:
    rfq = s.get(Rfq, rfq_id, with_for_update=lock)
    if rfq is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return rfq


def _future(deadline: datetime, now: datetime, field: str) -> None:
    if deadline <= now:
        raise unprocessable(field, "Must be in the future")


def _check_recipients(s: Session, inquiry_id: uuid.UUID, recipients: Sequence[RecipientIn]) -> None:
    """422 on every recipient that is not an active counterparty with a usable active contact."""
    cps = {
        c.id: c
        for c in s.scalars(
            select(Counterparty).where(Counterparty.id.in_({r.counterparty_id for r in recipients}))
        )
    }
    contacts = {
        c.id: c
        for c in s.scalars(
            select(Contact).where(Contact.id.in_({r.contact_id for r in recipients}))
        )
    }
    active = set(
        s.scalars(select(Rfq.counterparty_id).where(Rfq.inquiry_id == inquiry_id, is_active_rfq()))
    )
    batch: set[uuid.UUID] = set()
    problems: list[dict[str, str]] = []
    for i, r in enumerate(recipients):
        cp = cps.get(r.counterparty_id)
        cp_problem = None
        if cp is None:
            cp_problem = "Unknown counterparty"
        elif not cp.active:
            cp_problem = "Inactive counterparty"
        elif r.counterparty_id in batch:
            cp_problem = "Duplicate counterparty"
        elif r.counterparty_id in active:
            cp_problem = "Already has an RFQ"
        batch.add(r.counterparty_id)
        contact_issue = contact_problem(contacts.get(r.contact_id), None if cp is None else cp.id)
        for name, problem in (("counterparty_id", cp_problem), ("contact_id", contact_issue)):
            if problem:
                problems.append({"field": f"recipients[{i}].{name}", "message": problem})
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problems)


def _audit(  # noqa: PLR0913, PLR0917
    s: Session,
    principal: Principal,
    rfq: Rfq,
    before: Mapping[str, object] | None,
    after: Mapping[str, object],
    action: Action | None = None,
) -> None:
    record_change(
        s,
        actor=principal.user_id,
        entity_type="rfq",
        entity_id=rfq.id,
        action=action or ("update" if before else "create"),
        before=before,
        after=after,
    )


# --- routes ------------------------------------------------------------------------------------


@router.get("/inquiries/{inquiry_id}/suggestions", response_model=Suggestions)
def get_suggestions(inquiry_id: uuid.UUID, principal: Reader, engine: Eng) -> object:
    """Active counterparties by coverage, with their usable contacts."""
    with scope(principal, engine) as s:
        return rfq_repo.suggestions(s, _inquiry(s, inquiry_id))


@router.get("/inquiries/{inquiry_id}/rfqs", response_model=list[RfqItem])
def get_log(inquiry_id: uuid.UUID, principal: Reader, engine: Eng) -> object:
    """Return the RFQ log of an inquiry."""
    with scope(principal, engine) as s:
        _inquiry(s, inquiry_id)
        return rfq_repo.log(s, inquiry_id)


@router.post("/inquiries/{inquiry_id}/rfqs", response_model=list[RfqItem], status_code=201)
def create_rfqs(
    inquiry_id: uuid.UUID, body: RfqCreate, principal: Writer, engine: Eng, now: Now
) -> object:
    """One draft per recipient, all or none; the deadline becomes the inquiry's."""
    with scope(principal, engine) as s:
        inq = _inquiry(s, inquiry_id, lock=True)  # serializes concurrent creates
        if Status(inq.status) not in CREATABLE:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Inquiry is {inq.status}")
        if inq.buyer_id is None:
            field, message = "buyer_id", "Assign a buyer before creating RFQs"
            raise unprocessable(field, message)
        _future(body.deadline, now, "deadline")
        _check_recipients(s, inq.id, body.recipients)
        created = [
            Rfq(
                id=uuid.uuid4(),
                organization_id=inq.organization_id,
                inquiry_id=inq.id,
                counterparty_id=r.counterparty_id,
                contact_id=r.contact_id,
                status=RfqStatus.DRAFT.value,
                response_deadline=body.deadline,
                generated_at=now,
                version=1,
                created_at=now,
                created_by=principal.user_id,
                updated_at=now,
            )
            for r in body.recipients
        ]
        s.add_all(created)
        s.flush()
        for rfq in created:
            _audit(
                s, principal, rfq, None,
                {
                    "inquiry_id": inq.id,
                    "counterparty_id": rfq.counterparty_id,
                    "contact_id": rfq.contact_id,
                    "status": rfq.status,
                    "response_deadline": rfq.response_deadline,
                },
            )  # fmt: skip
        if inq.rfq_deadline != body.deadline:
            before = {"rfq_deadline": inq.rfq_deadline}
            inq.rfq_deadline = body.deadline
            bump_and_audit(
                s, principal, now, inq, "update", before, {"rfq_deadline": body.deadline},
            )  # fmt: skip
        return rfq_repo.log(s, inq.id, {r.id for r in created})


@router.get("/rfqs/{rfq_id}/preview", response_model=PreviewOut)
def get_preview(rfq_id: uuid.UUID, principal: Reader, engine: Eng) -> object:
    """Return the exact text and mail link: live for a draft, frozen once sent."""
    with scope(principal, engine) as s:
        try:
            return rfq_repo.preview(s, _rfq(s, rfq_id))
        except ValueError as exc:  # a stored address that cannot go into a mail link
            field = "contact_id"
            raise unprocessable(field, "Contact e-mail cannot be used in a mail link") from exc


@router.patch("/rfqs/{rfq_id}", response_model=RfqItem)
def update_rfq(
    rfq_id: uuid.UUID, body: RfqPatch, principal: Writer, engine: Eng, now: Now
) -> object:
    """Change the contact or the deadline of a draft. A no-op writes nothing."""
    with scope(principal, engine) as s:
        rfq = _rfq(s, rfq_id, lock=True)
        if rfq.version != body.version:
            raise conflict()
        if rfq.status != RfqStatus.DRAFT:
            raise HTTPException(status.HTTP_409_CONFLICT, "RFQ is not a draft")
        new = {
            k: v
            for k in ("contact_id", "response_deadline")
            if (v := getattr(body, k)) is not None and getattr(rfq, k) != v
        }
        if "contact_id" in new:
            problem = contact_problem(s.get(Contact, new["contact_id"]), rfq.counterparty_id)
            if problem:
                field = "contact_id"
                raise unprocessable(field, problem)
        if "response_deadline" in new:
            _future(new["response_deadline"], now, "response_deadline")
        if new:
            before = {k: getattr(rfq, k) for k in new}
            for k, v in new.items():
                setattr(rfq, k, v)
            rfq.version += 1
            rfq.updated_at = now
            s.flush()
            _audit(s, principal, rfq, before, new)
        return rfq_repo.log(s, rfq.inquiry_id, {rfq.id})[0]


# --- send, withdraw, decline, history ----------------------------------------------------------


def _done(  # noqa: PLR0913, PLR0917
    s: Session,
    principal: Principal,
    now: datetime,
    rfq: Rfq,
    action: Action,
    values: dict[str, Any],
) -> object:
    finish(s, principal, now, rfq, action, values)
    return rfq_repo.log(s, rfq.inquiry_id, {rfq.id})[0]


@router.post("/rfqs/{rfq_id}/mark-sent", response_model=RfqItem)
def mark_sent(
    rfq_id: uuid.UUID, body: VersionIn, principal: Writer, engine: Eng, now: Now
) -> object:
    """Freeze the live text and address; the first send moves a Draft inquiry to RFQ sent."""
    with scope(principal, engine) as s:
        inq, rfq = lock_pair(s, Rfq, rfq_id, body.version)
        move(rfq, RfqStatus.SENT, can_rfq_transition)
        if Status(inq.status) not in CREATABLE:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Inquiry is {inq.status}")
        problem = contact_problem(s.get(Contact, rfq.contact_id), rfq.counterparty_id)
        if problem:
            field = "contact_id"
            raise unprocessable(field, problem)
        if not s.get(Counterparty, rfq.counterparty_id).active:  # type: ignore[union-attr]
            field = "counterparty_id"
            raise unprocessable(field, "Inactive counterparty")
        if inq.buyer_id is None:
            field = "buyer_id"
            raise unprocessable(field, "Assign a buyer before sending")
        if rfq.response_deadline <= now:
            field, message = "response_deadline", "Deadline has passed"
            raise unprocessable(field, message)
        if not ready_to_leave_draft(inq.eta, inq.etd):
            field, message = "eta", "Set ETA and ETD before sending"
            raise unprocessable(field, message)
        ctx = rfq_repo.build_context(s, rfq)
        subject, text_ = render_rfq(ctx)
        if Status(inq.status) is Status.DRAFT:
            advance(s, principal, now, inq, Status.RFQ_SENT)
        values = {  # after the bump: a version the inquiry had while this RFQ was sent
            "status": RfqStatus.SENT.value,
            "sent_at": now,
            "sent_to_email": ctx.recipient_email,
            "sent_subject": subject,
            "sent_body": text_,
            "inquiry_version_at_send": inq.version,
        }
        return _done(s, principal, now, rfq, "send", values)


@router.post("/rfqs/{rfq_id}/withdraw", response_model=RfqItem)
def withdraw(
    rfq_id: uuid.UUID, body: VersionIn, principal: Writer, engine: Eng, now: Now
) -> object:
    """Withdraw a draft; its counterparty may then get a new RFQ."""
    with scope(principal, engine) as s:
        _, rfq = lock_pair(s, Rfq, rfq_id, body.version)
        move(rfq, RfqStatus.WITHDRAWN, can_rfq_transition)
        return _done(s, principal, now, rfq, "withdraw", {"status": RfqStatus.WITHDRAWN.value})


@router.post("/rfqs/{rfq_id}/decline", response_model=RfqItem)
def decline(rfq_id: uuid.UUID, body: VersionIn, principal: Writer, engine: Eng, now: Now) -> object:
    """Record that the supplier declined a sent RFQ."""
    with scope(principal, engine) as s:
        inq, rfq = lock_pair(s, Rfq, rfq_id, body.version)
        if s.scalar(
            select(Offer.id).where(Offer.id == inq.winner_offer_id, Offer.rfq_id == rfq.id)
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "Offer is the selected winner")  # R8
        move(rfq, RfqStatus.DECLINED, can_rfq_transition)
        return _done(s, principal, now, rfq, "decline", {"status": RfqStatus.DECLINED.value})


@router.get("/rfqs/{rfq_id}/history", response_model=list[HistoryOut])
def rfq_history(rfq_id: uuid.UUID, principal: Reader, engine: Eng) -> object:
    """Audit entries of the RFQ, newest first."""
    with scope(principal, engine) as s:
        _rfq(s, rfq_id)
        return [HistoryOut.model_validate(e) for e in history(s, "rfq", rfq_id)]
