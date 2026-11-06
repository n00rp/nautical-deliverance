"""Nomination queries: the only mapping from rows to NominationContext, list and preview."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from nautical_deliverance.domain.nomination import (
    NominationContext,
    NominationLine,
    render_nomination,
)
from nautical_deliverance.domain.offer import effective_density, evaluate_offer
from nautical_deliverance.domain.rfq import build_mailto
from nautical_deliverance.persistence import offer_repo, rfq_repo
from nautical_deliverance.persistence.models import (
    Contact,
    Inquiry,
    Nomination,
    Offer,
    Rfq,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session


class MailLinkError(ValueError):
    """The recipient address cannot go into a mail link."""


def next_sequence(session: Session, inquiry_id: uuid.UUID) -> int:
    """Return 1 plus the highest sequence sent for the inquiry (lock the inquiry first)."""
    top = session.scalar(
        select(func.max(Nomination.sequence)).where(Nomination.inquiry_id == inquiry_id)
    )
    return (top or 0) + 1


def offer_counterparty(session: Session, offer_id: uuid.UUID) -> uuid.UUID:
    """Return the counterparty that made the offer."""
    cp = session.scalar(select(Rfq.counterparty_id).join(Offer).where(Offer.id == offer_id))
    assert cp is not None  # noqa: S101  (FK)
    return cp


def build_nomination_context(session: Session, nom: Nomination) -> NominationContext:
    """Return the live, allow-listed render input of a nomination (B5-D7). Nothing else."""
    inq = session.get(Inquiry, nom.inquiry_id)
    offer = session.get(Offer, nom.offer_id)
    contact = session.get(Contact, nom.contact_id)
    assert inq is not None  # noqa: S101  (FK)
    assert offer is not None  # noqa: S101  (FK)
    assert contact is not None  # noqa: S101  (FK)
    rows = offer_repo.line_rows(session, offer)  # fetched once: the three sequences share an order
    given = offer_repo.inputs_for(session, offer, rows)
    result = evaluate_offer(given)
    lines = tuple(
        NominationLine(
            product=r.product,
            quantity=x.quantity,
            unit=x.unit,
            density=None if x.unit == "mt" else effective_density(x),
            qty_mt=res.qty_mt,
            price_per_mt=x.price_per_mt,
            line_cost=res.line_cost,
            in_total=res.in_total,
        )
        for r, x, res in zip(rows, given.lines, result.lines, strict=True)
    )
    return NominationContext(
        **rfq_repo.header(session, inq),
        lines=lines,
        barging_cost=offer.barging_cost,
        port_call_cost=offer.port_call_cost,
        agent_cost=offer.agent_cost,
        surveyor_cost=offer.surveyor_cost,
        other_cost=offer.other_cost,
        total=result.total,
        currency=offer.currency,
        delivery_from=offer.delivery_from,
        delivery_to=offer.delivery_to,
        delivery_method=offer.delivery_method,
        physical_supplier=offer.physical_supplier,
        payment_terms=offer.payment_terms,
        recipient_name=contact.name,
        recipient_email=contact.email,
        sequence=nom.sequence or next_sequence(session, nom.inquiry_id),
    )


def changed_since_sent(session: Session, nom: Nomination) -> bool:
    """Return whether the live render differs from the frozen text (a draft has none)."""
    if nom.sent_subject is None:
        return False
    return render_nomination(build_nomination_context(session, nom)) != (
        nom.sent_subject,
        nom.sent_body,
    )


def preview(session: Session, nom: Nomination) -> dict[str, Any]:
    """Recipient, text and mailto: live for a draft, frozen once sent."""
    if nom.sent_subject is None:
        subject, body = render_nomination(ctx := build_nomination_context(session, nom))
        to = ctx.recipient_email
    else:
        to, subject, body = str(nom.sent_to_email), nom.sent_subject, str(nom.sent_body)
    try:
        mailto, body_in_link = build_mailto(to, subject, body)
    except ValueError as exc:  # only this: render and total errors must surface as they are
        raise MailLinkError from exc
    return {
        "to": to,
        "subject": subject,
        "body": body,
        "mailto": mailto,
        "body_in_link": body_in_link,
    }


def items(
    session: Session, inquiry_id: uuid.UUID, only: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    """List items of an inquiry (or just `only`), newest first."""
    stmt = (
        select(Nomination, Contact.name, Contact.email)
        .join(Contact, Contact.id == Nomination.contact_id)
        .where(Nomination.inquiry_id == inquiry_id)
        .order_by(Nomination.created_at.desc(), Nomination.sequence.desc().nulls_first())
    )
    if only is not None:
        stmt = stmt.where(Nomination.id == only)
    return [
        {
            "id": nom.id,
            "status": nom.status,
            "sequence": nom.sequence,
            "contact_name": name,
            "email": nom.sent_to_email or email,
            "sent_at": nom.sent_at,
            "changed_since_sent": changed_since_sent(session, nom),
            "version": nom.version,
        }
        for nom, name, email in session.execute(stmt)
    ]


def contact_candidates(
    session: Session, offer_id: uuid.UUID, counterparty_id: uuid.UUID
) -> list[uuid.UUID]:
    """Contacts to try for a new draft: the winning RFQ's contact, then the counterparty's."""
    rfq_contact = session.scalar(select(Rfq.contact_id).join(Offer).where(Offer.id == offer_id))
    others = session.scalars(
        select(Contact.id)
        .where(Contact.counterparty_id == counterparty_id)
        .order_by(Contact.is_primary.desc(), Contact.name, Contact.id)
    )
    return [c for c in (rfq_contact, *others) if c is not None]
