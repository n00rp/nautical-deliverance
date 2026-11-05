"""RFQ queries: suggestions, the only mapping from rows to RfqContext, log and preview."""

from collections import defaultdict
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from nautical_deliverance.domain.rfq import RfqContext, RfqLine, build_mailto, render_rfq
from nautical_deliverance.persistence.inquiry_repo import is_active_rfq, line_rows
from nautical_deliverance.persistence.master_repo import counterparties_covering
from nautical_deliverance.persistence.models import (
    AppUser,
    Contact,
    Counterparty,
    Coverage,
    Inquiry,
    InquiryLine,
    Port,
    Product,
    Rfq,
    Vessel,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection

    from sqlalchemy.orm import Session


def build_context(session: Session, rfq: Rfq) -> RfqContext:
    """Return the live, allow-listed render input of an RFQ (B3-D9). Nothing else may be added."""
    inq = session.get(Inquiry, rfq.inquiry_id)
    contact = session.get(Contact, rfq.contact_id)
    assert inq is not None  # noqa: S101  (FK)
    assert contact is not None  # noqa: S101  (FK)
    vessel = session.get(Vessel, inq.vessel_id)
    port = session.get(Port, inq.port_id)
    assert vessel is not None  # noqa: S101  (FK)
    assert port is not None  # noqa: S101  (FK)
    buyer = None if inq.buyer_id is None else session.get(AppUser, inq.buyer_id)
    return RfqContext(
        reference=inq.reference,
        vessel_name=vessel.name,
        vessel_imo=vessel.imo,
        port_name=port.name,
        port_locode=port.locode,
        port_time_zone=port.time_zone,
        eta=inq.eta,
        etd=inq.etd,
        agent_name=inq.agent_name,
        lines=tuple(
            RfqLine(
                product=r.product_name,
                quantity=r.InquiryLine.quantity,
                unit=r.InquiryLine.unit,
                density=r.InquiryLine.density,
                spec_notes=r.InquiryLine.spec_notes,
                iso_version=r.iso_name,
            )
            for r in line_rows(session, inq.id)
        ),
        response_deadline=rfq.response_deadline,
        recipient_name=contact.name,
        recipient_email=contact.email,
        buyer_name=(buyer.name if buyer else None) or "",
    )


def changed_since_sent(session: Session, rfq: Rfq) -> bool:
    """Return whether the live render differs from the frozen text (a draft has none)."""
    if rfq.sent_subject is None:
        return False
    return render_rfq(build_context(session, rfq)) != (rfq.sent_subject, rfq.sent_body)


def preview(session: Session, rfq: Rfq) -> dict[str, Any]:
    """Recipient, text and mailto: live for a draft, frozen once sent."""
    if rfq.sent_subject is None:
        subject, body = render_rfq(ctx := build_context(session, rfq))
        to = ctx.recipient_email
    else:
        to, subject, body = str(rfq.sent_to_email), rfq.sent_subject, str(rfq.sent_body)
    mailto, body_in_link = build_mailto(to, subject, body)
    return {
        "to": to,
        "subject": subject,
        "body": body,
        "mailto": mailto,
        "body_in_link": body_in_link,
    }


def log(
    session: Session, inquiry_id: uuid.UUID, only: Collection[uuid.UUID] | None = None
) -> list[dict[str, Any]]:
    """Log items of an inquiry (or just `only`), oldest first."""
    stmt = (
        select(Rfq, Counterparty.name, Contact.name, Contact.email)
        .join(Counterparty, Counterparty.id == Rfq.counterparty_id)
        .join(Contact, Contact.id == Rfq.contact_id)
        .where(Rfq.inquiry_id == inquiry_id)
        .order_by(Rfq.generated_at, Counterparty.name, Rfq.id)
    )
    if only is not None:
        stmt = stmt.where(Rfq.id.in_(only))
    return [
        {
            "id": rfq.id,
            "counterparty_name": cp_name,
            "contact_name": contact_name,
            "email": rfq.sent_to_email or email,
            "generated_at": rfq.generated_at,
            "sent_at": rfq.sent_at,
            "status": rfq.status,
            "response_deadline": rfq.response_deadline,
            "offer_received": False,  # ponytail: B4 sets this when an offer is entered
            "changed_since_sent": changed_since_sent(session, rfq),
            "version": rfq.version,
        }
        for rfq, cp_name, contact_name, email in session.execute(stmt)
    ]


def suggestions(session: Session, inquiry: Inquiry) -> dict[str, list[dict[str, Any]]]:
    """Active counterparties grouped by coverage of the inquiry's products at its port."""
    wanted = list(
        session.scalars(select(InquiryLine.product_id).where(InquiryLine.inquiry_id == inquiry.id))
    )
    full = counterparties_covering(session, inquiry.port_id, wanted, mode="all")
    some = counterparties_covering(session, inquiry.port_id, wanted, mode="some")
    listed = {c.id for c in (*full, *some)}
    rest = [
        c
        for c in session.scalars(
            select(Counterparty)
            .where(Counterparty.active)
            .order_by(Counterparty.name, Counterparty.id)
        )
        if c.id not in listed
    ]
    covered: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for cp_id, product_id in session.execute(
        select(Coverage.counterparty_id, Coverage.product_id)
        .join(Product, Product.id == Coverage.product_id)
        .join(Port, Port.id == Coverage.port_id)
        .where(
            Coverage.port_id == inquiry.port_id,
            Coverage.active,
            Product.active,
            Port.active,
            Coverage.product_id.in_(wanted),
        )
        .order_by(Product.name, Product.id)
    ):
        covered[cp_id].append(product_id)
    contacts: dict[uuid.UUID, list[Contact]] = defaultdict(list)
    for contact in session.scalars(
        select(Contact)
        .where(Contact.active, Contact.email != "")
        .order_by(Contact.is_primary.desc(), Contact.name, Contact.id)
    ):
        contacts[contact.counterparty_id].append(contact)
    active_rfq = dict(
        session.execute(
            select(Rfq.counterparty_id, Rfq.id).where(Rfq.inquiry_id == inquiry.id, is_active_rfq())
        ).all()
    )

    def entry(cp: Counterparty) -> dict[str, Any]:
        mine = contacts[cp.id]
        return {
            "counterparty_id": cp.id,
            "name": cp.name,
            "type": cp.type,
            "contacts": [
                {"id": c.id, "name": c.name, "email": c.email, "is_primary": c.is_primary}
                for c in mine
            ],
            "primary_contact_id": next((c.id for c in mine if c.is_primary), None),
            "covered_product_ids": covered.get(cp.id, []),
            "active_rfq_id": active_rfq.get(cp.id),
        }

    return {
        "covers_all": [entry(c) for c in full],
        "covers_some": [entry(c) for c in some],
        "not_listed": [entry(c) for c in rest],
    }
