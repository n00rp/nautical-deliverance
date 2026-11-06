"""Offer entry API (B4): enter, read, change and audit the offer of a sent RFQ.

Admin and Bunker Buyer write; Viewer reads; Operator gets 403 everywhere (B4-D14). The inquiry is
locked first, then the RFQ or offer (always this order). The first offer moves the inquiry from
RFQ sent to Offers received in the same transaction. Every change is audited.
"""

import uuid
from datetime import datetime  # noqa: TC003  (FastAPI runtime)
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session  # noqa: TC002  (FastAPI runtime)

from nautical_deliverance.api.access import Eng, Now, Reader, Writer  # noqa: TC001
from nautical_deliverance.api.common import conflict, scope, unprocessable
from nautical_deliverance.api.inquiries import (
    _lock_open,
    _reject,
    _transition,
    advance,
    bump_and_audit,
)
from nautical_deliverance.api.inquiries import _out as inquiry_out
from nautical_deliverance.api.inquiry_models import HistoryOut, InquiryOut
from nautical_deliverance.api.offer_models import (
    COSTS,
    ComparisonOut,
    OfferIn,
    OfferLineIn,
    OfferOut,
    OfferPatch,
    SelectWinnerIn,
)
from nautical_deliverance.api.offer_models import (
    FIELDS as FIELD_NAMES,
)
from nautical_deliverance.domain.identity import Principal  # noqa: TC001
from nautical_deliverance.domain.inquiry import Status
from nautical_deliverance.domain.offer import DecisionReason, evaluate_offer, rationale_required
from nautical_deliverance.domain.rfq import RfqStatus
from nautical_deliverance.persistence import offer_repo
from nautical_deliverance.persistence.audit import Action, history, record_change
from nautical_deliverance.persistence.inquiry_repo import dec
from nautical_deliverance.persistence.models import (
    Inquiry,
    InquiryLine,
    Offer,
    OfferLine,
    Rfq,
)

router = APIRouter()

OPEN = frozenset({Status.RFQ_SENT, Status.OFFERS_RECEIVED, Status.WINNER_SELECTED})
NOT_NULL = frozenset({"valid_until", *COSTS})  # null in a patch is an error, not a clear
CENT, MILLI, TENTH = Decimal("0.01"), Decimal("0.001"), Decimal("0.1")


LineKey = tuple[uuid.UUID, Decimal, Decimal | None]  # inquiry line, price, density


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


def _value(key: str, raw: Any) -> Any:  # noqa: ANN401
    """Request value -> column value (decimal strings to exact Decimals)."""
    return Decimal(raw).quantize(CENT) if key in COSTS and raw is not None else raw


def _check_inquiry(inq: Inquiry) -> None:
    if Status(inq.status) not in OPEN:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Inquiry is {inq.status}")


def _check_delivery(start: datetime | None, end: datetime | None) -> None:
    if start is not None and end is not None and end < start:
        field, message = "delivery_to", "Must not be before delivery_from"
        raise unprocessable(field, message)


def _line_keys(s: Session, inquiry_id: uuid.UUID, lines: list[OfferLineIn]) -> list[LineKey]:
    """Validate the lines against the inquiry's own lines (422 per line) and normalise them."""
    mine = {
        r.id: r for r in s.scalars(select(InquiryLine).where(InquiryLine.inquiry_id == inquiry_id))
    }
    seen: set[uuid.UUID] = set()
    problems: list[dict[str, str]] = []
    for i, ln in enumerate(lines):
        row = mine.get(ln.inquiry_line_id)
        if row is None:
            problems.append(
                {"field": f"lines[{i}].inquiry_line_id", "message": "Unknown inquiry line"}
            )
        elif ln.inquiry_line_id in seen:
            problems.append({"field": f"lines[{i}].inquiry_line_id", "message": "Duplicate line"})
        elif ln.density is not None and (row.unit != "m3" or row.density is not None):
            problems.append(
                {"field": f"lines[{i}].density", "message": "Only for an m3 line without density"}
            )
        seen.add(ln.inquiry_line_id)
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problems)
    return [
        (
            ln.inquiry_line_id,
            Decimal(ln.price_per_mt).quantize(MILLI),
            None if ln.density is None else Decimal(ln.density).quantize(TENTH),
        )
        for ln in lines
    ]


def _changes(offer: Offer, body: OfferPatch) -> dict[str, Any]:
    """Fields the patch really changes; null on a required field is 422."""
    new: dict[str, Any] = {}
    for k in FIELD_NAMES:  # field order: the first 422 is deterministic
        if k not in body.model_fields_set:
            continue
        raw = getattr(body, k)
        if raw is None and k in NOT_NULL:
            raise unprocessable(k, "Cannot be empty")
        if getattr(offer, k) != (v := _value(k, raw)):
            new[k] = v
    return new


def _line_texts(s: Session, offer: Offer) -> list[str]:
    """Priced lines as readable audit text, in inquiry line order."""
    return [
        f"{r.product} {dec(r.price_per_mt)}"
        + ("" if r.density is None else f" {dec(r.density)} kg/m3")
        for r in offer_repo.line_rows(s, offer)
        if r.price_per_mt is not None
    ]


def _stored(s: Session, offer: Offer) -> list[LineKey]:
    rows = s.execute(
        select(OfferLine.inquiry_line_id, OfferLine.price_per_mt, OfferLine.density).where(
            OfferLine.offer_id == offer.id
        )
    )
    return sorted((line_id, price, density) for line_id, price, density in rows)


def _store_lines(s: Session, offer: Offer, keys: list[LineKey]) -> None:
    s.add_all(
        OfferLine(
            organization_id=offer.organization_id, offer_id=offer.id, inquiry_id=offer.inquiry_id,
            inquiry_line_id=line_id, price_per_mt=price, density=density,
        )
        for line_id, price, density in keys
    )  # fmt: skip
    s.flush()


def _out(s: Session, offer: Offer) -> object:
    """Return the offer record; 422 on `lines` when the total would exceed numeric(14,2)."""
    try:
        return offer_repo.detail(s, offer)
    except ValueError as exc:
        field, message = "lines", "Total too large"
        raise unprocessable(field, message) from exc


def _audit(  # noqa: PLR0913, PLR0917
    s: Session,
    principal: Principal,
    offer: Offer,
    before: dict[str, object] | None,
    after: dict[str, object],
    action: Action,
) -> None:
    record_change(
        s, actor=principal.user_id, entity_type="offer", entity_id=offer.id,
        action=action, before=before, after=after,
    )  # fmt: skip


# --- routes ------------------------------------------------------------------------------------


@router.post("/rfqs/{rfq_id}/offer", response_model=OfferOut, status_code=201)
def create_offer(
    rfq_id: uuid.UUID, body: OfferIn, principal: Writer, engine: Eng, now: Now
) -> object:
    """Enter the offer of a sent RFQ; the first one moves the inquiry to Offers received."""
    with scope(principal, engine) as s:
        inquiry_id = s.scalar(select(Rfq.inquiry_id).where(Rfq.id == rfq_id))
        if inquiry_id is None:
            raise _not_found()
        inq = s.get(Inquiry, inquiry_id, with_for_update=True)
        rfq = s.get(Rfq, rfq_id, with_for_update=True)
        assert inq is not None  # noqa: S101  (FK)
        assert rfq is not None  # noqa: S101  (locked above)
        if rfq.status != RfqStatus.SENT:
            raise HTTPException(status.HTTP_409_CONFLICT, "RFQ is not sent")
        _check_inquiry(inq)
        if s.scalar(select(Offer.id).where(Offer.rfq_id == rfq.id)) is not None:
            field, message = "rfq_id", "Offer already entered"
            raise unprocessable(field, message)
        _check_delivery(body.delivery_from, body.delivery_to)
        keys = _line_keys(s, inq.id, body.lines)
        values = {k: _value(k, getattr(body, k)) for k in FIELD_NAMES}
        values.update({c: values[c] or Decimal("0.00") for c in COSTS})
        offer = Offer(
            id=uuid.uuid4(), organization_id=inq.organization_id, rfq_id=rfq.id, inquiry_id=inq.id,
            received_at=now, version=1, created_at=now, created_by=principal.user_id,
            updated_at=now, **values,
        )  # fmt: skip
        s.add(offer)
        s.flush()
        _store_lines(s, offer, keys)
        out = _out(s, offer)  # 422 rolls everything back, including the transition below
        _audit(
            s, principal, offer, None,
            {**values, "rfq_id": rfq.id, "lines": _line_texts(s, offer)}, "create",
        )  # fmt: skip
        if Status(inq.status) is Status.RFQ_SENT:
            advance(s, principal, now, inq, Status.OFFERS_RECEIVED)
        return out


@router.get("/offers/{offer_id}", response_model=OfferOut)
def get_offer(offer_id: uuid.UUID, principal: Reader, engine: Eng) -> object:
    """Return the offer with computed lines and total; readable whatever its RFQ became."""
    with scope(principal, engine) as s:
        offer = s.get(Offer, offer_id)
        if offer is None:
            raise _not_found()
        return _out(s, offer)


@router.patch("/offers/{offer_id}", response_model=OfferOut)
def update_offer(
    offer_id: uuid.UUID, body: OfferPatch, principal: Writer, engine: Eng, now: Now
) -> object:
    """Change an offer; `lines` replaces the set. A no-op writes and bumps nothing."""
    with scope(principal, engine) as s:
        inquiry_id = s.scalar(select(Offer.inquiry_id).where(Offer.id == offer_id))
        if inquiry_id is None:
            raise _not_found()
        inq = s.get(Inquiry, inquiry_id, with_for_update=True)
        offer = s.get(Offer, offer_id, with_for_update=True)
        assert inq is not None  # noqa: S101  (FK)
        assert offer is not None  # noqa: S101  (locked above)
        if offer.version != body.version:
            raise conflict()
        _check_inquiry(inq)
        if inq.winner_offer_id == offer.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Selected offer is locked")
        new = _changes(offer, body)
        _check_delivery(
            new.get("delivery_from", offer.delivery_from), new.get("delivery_to", offer.delivery_to)
        )
        keys = None if body.lines is None else _line_keys(s, inq.id, body.lines)
        if keys is not None and sorted(keys) == _stored(s, offer):
            keys = None
        if new or keys is not None:
            before: dict[str, object] = {k: getattr(offer, k) for k in new}
            after: dict[str, object] = dict(new)
            if keys is not None:
                before["lines"] = _line_texts(s, offer)
                s.execute(delete(OfferLine).where(OfferLine.offer_id == offer.id))
                _store_lines(s, offer, keys)
                after["lines"] = _line_texts(s, offer)
            for k, v in new.items():
                setattr(offer, k, v)
            offer.version += 1
            offer.updated_at = now
            s.flush()
            out = _out(s, offer)
            _audit(s, principal, offer, before, after, "update")
            return out
        return _out(s, offer)


@router.get("/offers/{offer_id}/history", response_model=list[HistoryOut])
def offer_history(offer_id: uuid.UUID, principal: Reader, engine: Eng) -> object:
    """Audit entries of the offer, newest first."""
    with scope(principal, engine) as s:
        if s.get(Offer, offer_id) is None:
            raise _not_found()
        return [HistoryOut.model_validate(e) for e in history(s, "offer", offer_id)]


# --- comparison and decision --------------------------------------------------------------------


@router.get("/inquiries/{inquiry_id}/comparison", response_model=ComparisonOut)
def comparison(inquiry_id: uuid.UUID, principal: Reader, engine: Eng, now: Now) -> object:
    """Every offer with its flags (complete first, cheapest first) and the decision."""
    with scope(principal, engine) as s:
        inq = s.get(Inquiry, inquiry_id)
        if inq is None:
            raise _not_found()
        return offer_repo.comparison(s, inq, now)


@router.post("/inquiries/{inquiry_id}/select-winner", response_model=InquiryOut)
def select_winner(
    inquiry_id: uuid.UUID, body: SelectWinnerIn, principal: Writer, engine: Eng, now: Now
) -> object:
    """Select (or re-select) the winner; a non-lowest offer needs a reason (B0-D4, B4-D13)."""
    with scope(principal, engine) as s:
        inq = _lock_open(s, inquiry_id, body.version)  # row lock: concurrent selections queue up
        if Status(inq.status) not in (Status.OFFERS_RECEIVED, Status.WINNER_SELECTED):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Inquiry is {inq.status}")
        offers = list(s.scalars(select(Offer).where(Offer.inquiry_id == inq.id)))
        chosen = next((o for o in offers if o.id == body.offer_id), None)
        rfq = None if chosen is None else s.get(Rfq, chosen.rfq_id)
        if chosen is None or rfq is None:
            _reject("offer_id", "Not an offer of this inquiry")
        if rfq.status != RfqStatus.SENT:
            _reject("offer_id", f"RFQ is {rfq.status}")
        if chosen.valid_until < now:
            _reject("offer_id", "Offer has expired")
        sent = set(
            s.scalars(select(Rfq.id).where(Rfq.inquiry_id == inq.id, Rfq.status == RfqStatus.SENT))
        )
        results = {  # Ruling R5: only offers that can be selected now compete for "lowest"
            str(o.id): evaluate_offer(offer_repo.inputs_for(s, o))
            for o in offers
            if o.rfq_id in sent and o.valid_until >= now
        }
        if body.reason is None and rationale_required(str(chosen.id), results.values()):
            _reject("reason", "Required when the offer is not the lowest")
        if body.reason == DecisionReason.OTHER and body.note is None:
            _reject("note", "Required for reason other")
        new = {
            "winner_offer_id": chosen.id, "decision_reason": body.reason,
            "decision_note": body.note,
            "decided_total": results[str(chosen.id)].total.quantize(CENT),
        }  # fmt: skip
        if all(getattr(inq, k) == v for k, v in new.items()):
            return inquiry_out(s, inq, principal)  # the same decision again: nothing to write
        before = {**offer_repo.decision_facts(s, inq), "status": inq.status}
        moved = (
            _transition(inq, Status.WINNER_SELECTED)
            if Status(inq.status) is Status.OFFERS_RECEIVED
            else {}
        )
        for k, v in {**new, **moved, "decided_at": now, "decided_by": principal.user_id}.items():
            setattr(inq, k, v)
        s.flush()  # the audit "after" reads the decision back from the database
        bump_and_audit(
            s, principal, now, inq, "select_winner", before,
            {**moved, **offer_repo.decision_facts(s, inq)},
        )  # fmt: skip
        return inquiry_out(s, inq, principal)
