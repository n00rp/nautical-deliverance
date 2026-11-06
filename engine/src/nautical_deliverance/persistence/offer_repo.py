"""Offer queries: the only mapping from rows to the domain's OfferInput, and the offer record."""

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from nautical_deliverance.domain.offer import (
    LineInput,
    OfferInput,
    OfferResult,
    evaluate_offer,
    format_qty_mt,
    lowest,
)
from nautical_deliverance.persistence.inquiry_repo import decision
from nautical_deliverance.persistence.models import (
    Counterparty,
    Inquiry,
    InquiryLine,
    Offer,
    OfferLine,
    Product,
    Rfq,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from sqlalchemy.orm import Session

CENT = Decimal("0.01")
DECISION_COLUMNS = ("winner_offer_id", "decision_reason", "decision_note", "decided_total")
COSTS = ("barging_cost", "port_call_cost", "agent_cost", "surveyor_cost", "other_cost")


def line_rows(session: Session, offer: Offer) -> Sequence[Any]:
    """Every inquiry line in position order with this offer's price and density (or None)."""
    return session.execute(
        select(
            InquiryLine, Product.name.label("product"), OfferLine.price_per_mt, OfferLine.density
        )
        .join(Product, Product.id == InquiryLine.product_id)
        .outerjoin(
            OfferLine,
            (OfferLine.inquiry_line_id == InquiryLine.id) & (OfferLine.offer_id == offer.id),
        )
        .where(InquiryLine.inquiry_id == offer.inquiry_id)
        .order_by(InquiryLine.position)
    ).all()


def _input(offer: Offer, rows: Sequence[Any]) -> OfferInput:
    return OfferInput(
        offer_id=str(offer.id),
        lines=tuple(
            LineInput(
                line_id=str(r.InquiryLine.id),
                unit=r.InquiryLine.unit,
                quantity=r.InquiryLine.quantity,
                inquiry_density=r.InquiryLine.density,
                price_per_mt=r.price_per_mt,
                offer_density=r.density,
            )
            for r in rows
        ),
        fixed=tuple(getattr(offer, c) for c in COSTS),
    )


def inputs_for(session: Session, offer: Offer) -> OfferInput:
    """Return the domain input of an offer: all inquiry lines, priced or not."""
    return _input(offer, line_rows(session, offer))


def _text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def detail(session: Session, offer: Offer) -> dict[str, Any]:
    """Return the offer record with computed lines (ValueError when the total is too large)."""
    rows = line_rows(session, offer)
    result = evaluate_offer(_input(offer, rows))
    rfq = session.get(Rfq, offer.rfq_id)
    inq = session.get(Inquiry, offer.inquiry_id)
    assert rfq is not None  # noqa: S101  (FK)
    assert inq is not None  # noqa: S101  (FK)
    name = session.scalar(select(Counterparty.name).where(Counterparty.id == rfq.counterparty_id))
    return {
        "id": offer.id,
        "rfq_id": offer.rfq_id,
        "inquiry_id": offer.inquiry_id,
        "rfq_status": rfq.status,
        "counterparty_name": name,
        "selected": inq.winner_offer_id == offer.id,
        "currency": offer.currency,
        "valid_until": offer.valid_until,
        "payment_terms": offer.payment_terms,
        "delivery_from": offer.delivery_from,
        "delivery_to": offer.delivery_to,
        "delivery_method": offer.delivery_method,
        "physical_supplier": offer.physical_supplier,
        "supplier_comment": offer.supplier_comment,
        **{c: _text(getattr(offer, c)) for c in COSTS},
        "lines": [
            {
                "inquiry_line_id": r.InquiryLine.id,
                "product": r.product,
                "price_per_mt": _text(r.price_per_mt),
                "density": _text(r.density),
                "qty_mt": None if res.qty_mt is None else format_qty_mt(res.qty_mt),
                "line_cost": _text(res.line_cost),
                "in_total": res.in_total,
            }
            for r, res in zip(rows, result.lines, strict=True)
        ],
        "total": _text(result.total.quantize(CENT)),
        "complete": result.complete,
        "received_at": offer.received_at,
        "version": offer.version,
    }


SOON = timedelta(hours=24)


def comparison(session: Session, inq: Inquiry, now: datetime) -> dict[str, Any]:
    """Every offer of the inquiry as a detail record plus lowest, delta and validity flags."""
    # ponytail: detail() per offer costs a few queries; fine for a handful of RFQs.
    rows = [
        detail(session, o) for o in session.scalars(select(Offer).where(Offer.inquiry_id == inq.id))
    ]
    totals = {r["id"]: Decimal(r["total"]) for r in rows}
    low = lowest(OfferResult(str(r["id"]), (), totals[r["id"]], r["complete"]) for r in rows)
    floor = min((totals[r["id"]] for r in rows if str(r["id"]) in low), default=None)
    for r in rows:
        r["offer_id"] = r["id"]
        r["lowest"] = str(r["id"]) in low
        r["delta_to_lowest"] = (
            _text(totals[r["id"]] - floor) if r["complete"] and floor is not None else None
        )
        r["expired"] = r["valid_until"] < now
        r["expiring_soon"] = now <= r["valid_until"] < now + SOON
    rows.sort(key=lambda r: (not r["complete"], totals[r["id"]], r["counterparty_name"], r["id"]))
    return {"rows": rows, "decision": decision(session, inq)}


def decision_facts(session: Session, inq: Inquiry) -> dict[str, Any]:
    """Return the decision columns plus the winner's counterparty name, for the audit entry."""
    name = None
    if inq.winner_offer_id is not None:
        name = session.scalar(
            select(Counterparty.name)
            .join(Rfq, Rfq.counterparty_id == Counterparty.id)
            .join(Offer, Offer.rfq_id == Rfq.id)
            .where(Offer.id == inq.winner_offer_id)
        )
    return {
        **{k: getattr(inq, k) for k in DECISION_COLUMNS},
        "winner_counterparty": name,
    }
