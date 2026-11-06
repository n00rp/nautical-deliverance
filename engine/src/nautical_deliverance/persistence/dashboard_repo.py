"""Dashboard queries (B5): attention items, status counts and the month's figures.

The month is the UTC calendar month of the clock. An inquiry belongs to it by its first sent
nomination (sequence 1; amendments never move it), except for the average of offers, which counts
inquiries by their decision time.
"""

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import exists, func, select

from nautical_deliverance.domain.inquiry import Status
from nautical_deliverance.domain.offer import evaluate_offer, format_qty_mt
from nautical_deliverance.domain.rfq import RfqStatus
from nautical_deliverance.persistence import offer_repo
from nautical_deliverance.persistence.models import (
    Inquiry,
    Nomination,
    Offer,
    Port,
    Rfq,
    Vessel,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy import Row
    from sqlalchemy.orm import Session

CENT = Decimal("0.01")
SOON = offer_repo.SOON
CLOSED = (Status.NOMINATED.value, Status.CANCELLED.value)
CURRENCY = "USD"


def average(total: int, count: int) -> str | None:
    """Return total / count with 2 decimals, half-up; None when there is nothing to average."""
    if count == 0:
        return None
    return format((Decimal(total) / count).quantize(CENT, ROUND_HALF_UP), "f")


def status_counts(session: Session) -> dict[str, int]:
    """Return the number of inquiries per status, every status present."""
    found = dict(
        session.execute(select(Inquiry.status, func.count()).group_by(Inquiry.status)).all()
    )
    return {s.value: found.get(s.value, 0) for s in Status}


def _inquiries(*cols: Any) -> Any:  # noqa: ANN401
    return (
        select(
            Inquiry.id,
            Inquiry.reference,
            Vessel.name.label("vessel"),
            Port.name.label("port"),
            Port.time_zone.label("tz"),
            *cols,
        )
        .join(Vessel, Vessel.id == Inquiry.vessel_id)
        .join(Port, Port.id == Inquiry.port_id)
    )


def _item(row: Row[Any], kind: str, due: datetime | None, detail: str | None) -> dict[str, Any]:
    return {
        "inquiry_id": row.id, "reference": row.reference, "vessel_name": row.vessel,
        "port_name": row.port, "port_time_zone": row.tz, "kind": kind, "due_at": due,
        "detail": detail,
    }  # fmt: skip


def eta_items(
    session: Session, now: datetime, warn: Callable[[str, datetime | None, datetime], bool]
) -> list[dict[str, Any]]:
    """Inquiries whose ETA warning (the B2 rule, passed in) is on; closed ones never match."""
    rows = session.execute(
        _inquiries(Inquiry.status, Inquiry.eta).where(
            Inquiry.eta.is_not(None), Inquiry.status.notin_(CLOSED)
        )
    )
    return [_item(r, "eta_unnominated", r.eta, None) for r in rows if warn(r.status, r.eta, now)]


def _grouped(session: Session, *where: Any) -> Sequence[Row[Any]]:  # noqa: ANN401
    """Per inquiry: its earliest RFQ deadline and the number of RFQs matching the conditions."""
    return session.execute(
        _inquiries(func.min(Rfq.response_deadline).label("due"), func.count().label("n"))
        .join(Rfq, Rfq.inquiry_id == Inquiry.id)
        .where(*where)
        .group_by(Inquiry.id, Vessel.name, Port.name, Port.time_zone)
    ).all()


def rfq_items(session: Session, now: datetime) -> list[dict[str, Any]]:
    """RFQs sent and unanswered with a deadline inside 24 h (or passed); RFQ drafts not sent."""
    answered = exists().where(Offer.rfq_id == Rfq.id)
    late = _grouped(
        session,
        Rfq.status == RfqStatus.SENT.value,
        ~answered,
        Rfq.response_deadline < now + SOON,
        Inquiry.status.in_((Status.RFQ_SENT.value, Status.OFFERS_RECEIVED.value)),
    )
    drafts = _grouped(
        session,
        Rfq.status == RfqStatus.DRAFT.value,
        Inquiry.status.in_(
            (Status.DRAFT.value, Status.RFQ_SENT.value, Status.OFFERS_RECEIVED.value)
        ),
    )
    return [
        *(_item(r, "rfq_deadline", r.due, f"{r.n} RFQ(s) without offer") for r in late),
        *(_item(r, "rfq_drafts_unsent", None, f"{r.n} RFQ draft(s) not sent") for r in drafts),
    ]


def validity_items(session: Session, now: datetime) -> list[dict[str, Any]]:
    """Return items for the selected (else lowest selectable) offer ending inside 24 h."""
    soon = exists().where(Offer.inquiry_id == Inquiry.id, Offer.valid_until < now + SOON)
    rows = session.execute(
        _inquiries().where(
            soon,
            Inquiry.status.in_(
                (Status.RFQ_SENT.value, Status.OFFERS_RECEIVED.value, Status.WINNER_SELECTED.value)
            ),
        )
    ).all()
    out = []
    for r in rows:  # ponytail: comparison() per candidate; the prefilter keeps it to a handful
        inq = session.get(Inquiry, r.id)
        assert inq is not None  # noqa: S101  (selected above)
        cmp = offer_repo.comparison(session, inq, now)["rows"]
        shown = [x for x in cmp if x["selected"]] or [x for x in cmp if x["lowest"]]
        target = min(shown, key=lambda x: x["valid_until"], default=None)
        if target is not None and target["valid_until"] < now + SOON:
            name = target["counterparty_name"]
            out.append(_item(r, "offer_validity", target["valid_until"], f"Offer from {name}"))
    return out


def _month(now: datetime) -> tuple[datetime, datetime]:
    start = now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, (start + timedelta(days=32)).replace(day=1)


def month_figures(session: Session, now: datetime) -> dict[str, Any]:
    """Volume, spend, open counts and the average number of offers for the clock's month."""
    start, end = _month(now)
    nominated = session.scalars(
        select(Inquiry)
        .join(Nomination, Nomination.inquiry_id == Inquiry.id)
        .where(
            Nomination.sequence == 1,
            Nomination.sent_at >= start,
            Nomination.sent_at < end,
            Inquiry.status == Status.NOMINATED.value,
        )
    ).all()
    mt, excluded = Decimal(0), 0
    for inq in nominated:
        offer = session.get(Offer, inq.winner_offer_id)
        assert offer is not None  # noqa: S101  (a nominated inquiry has its winner)
        for res in evaluate_offer(offer_repo.inputs_for(session, offer)).lines:
            mt += res.qty_mt if res.in_total and res.qty_mt is not None else 0
            excluded += res.qty_mt is None
    decided = (
        Inquiry.decided_at >= start,
        Inquiry.decided_at < end,
        Inquiry.status != Status.CANCELLED.value,
    )
    offers = session.scalar(
        select(func.count())
        .select_from(Offer)
        .join(Inquiry, Inquiry.id == Offer.inquiry_id)
        .where(*decided)
    )
    count = session.scalar(select(func.count()).select_from(Inquiry).where(*decided))
    counts = status_counts(session)
    spend = sum((i.decided_total for i in nominated if i.decided_total), Decimal(0))
    return {
        "period": f"{start:%Y-%m}",
        "nominated_mt": format_qty_mt(mt),
        "mt_excluded_lines": excluded,
        "nominated_spend": format(spend.quantize(CENT), "f"),
        "currency": CURRENCY,
        "open_by_status": {k: v for k, v in counts.items() if k not in CLOSED},
        "avg_offers": average(offers or 0, count or 0),
    }
