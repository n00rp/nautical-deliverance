"""Inquiry queries: reference counter, work list, detail with display names and warnings."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased

from nautical_deliverance.domain.inquiry import format_reference
from nautical_deliverance.domain.rfq import RfqStatus
from nautical_deliverance.persistence.models import (
    AppUser,
    BunkeringReason,
    Counterparty,
    Inquiry,
    InquiryLine,
    InquiryReferenceCounter,
    IsoSpecVersion,
    LegalEntity,
    Nomination,
    Offer,
    Port,
    Product,
    Rfq,
    Vessel,
    VesselApprovedFuel,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence
    from decimal import Decimal

    from sqlalchemy import ColumnElement, Row
    from sqlalchemy.orm import Session

Counter = InquiryReferenceCounter


def next_reference(session: Session, org_id: uuid.UUID, now: datetime) -> str:
    """Take the next number of the organization's UTC month (row-locked until commit)."""
    month = now.astimezone(UTC).strftime("%y%m")
    taken = session.scalar(
        insert(Counter)
        .values(organization_id=org_id, year_month=month, next_value=2)
        .on_conflict_do_update(
            index_elements=[Counter.organization_id, Counter.year_month],
            set_={"next_value": Counter.next_value + 1},
        )
        .returning(Counter.next_value - 1)
    )
    assert taken is not None  # noqa: S101  (RETURNING always yields the row)
    return format_reference(now, taken)


def _shown(user: Any) -> Any:  # noqa: ANN401
    """Display name of a user alias, falling back to the e-mail when the name is empty."""
    return func.coalesce(func.nullif(user.name, ""), user.email)


def is_active_rfq() -> ColumnElement[bool]:
    """Return the one definition of an active RFQ: anything not withdrawn."""
    return Rfq.status != RfqStatus.WITHDRAWN.value


def _rfq_count(*where: ColumnElement[bool]) -> Any:  # noqa: ANN401
    """Correlated count of the inquiry's RFQs that satisfy every condition."""
    return select(func.count()).where(Rfq.inquiry_id == Inquiry.id, *where).scalar_subquery()


def _offer_count() -> Any:  # noqa: ANN401
    """Correlated number of offers entered for the inquiry."""
    return select(func.count()).where(Offer.inquiry_id == Inquiry.id).scalar_subquery()


def _nomination_count() -> Any:  # noqa: ANN401
    """Correlated number of sent nomination versions of the inquiry."""
    return (
        select(func.count())
        .where(Nomination.inquiry_id == Inquiry.id, Nomination.status == "sent")
        .scalar_subquery()
    )


def _winner_name() -> Any:  # noqa: ANN401
    """Correlated name of the selected offer's counterparty (kept even once it is inactive)."""
    return (
        select(Counterparty.name)
        .join(Rfq, Rfq.counterparty_id == Counterparty.id)
        .join(Offer, Offer.rfq_id == Rfq.id)
        .where(Offer.id == Inquiry.winner_offer_id)
        .scalar_subquery()
    )


def list_rows(
    session: Session, *, status: str | None, q: str | None, buyer: uuid.UUID | None, sort: str
) -> Sequence[Row[Any]]:
    """Work-list rows. `status` None = all but cancelled; "all" = everything."""
    stmt = (
        select(
            Inquiry.id,
            Inquiry.reference,
            Inquiry.status,
            Vessel.name.label("vessel_name"),
            Port.name.label("port_name"),
            Port.time_zone.label("port_time_zone"),
            Inquiry.eta,
            _shown(AppUser).label("buyer_name"),
            # Active RFQs; "sent" is the active ones that left Draft (a declined one was sent).
            _rfq_count(is_active_rfq()).label("rfq_total"),
            _rfq_count(is_active_rfq(), Rfq.status != RfqStatus.DRAFT.value).label("rfq_sent"),
            _offer_count().label("offer_total"),
            _winner_name().label("winner_counterparty_name"),
            _nomination_count().label("nomination_sent"),
        )
        .join(Vessel, Vessel.id == Inquiry.vessel_id)
        .join(Port, Port.id == Inquiry.port_id)
        .outerjoin(AppUser, AppUser.id == Inquiry.buyer_id)
    )
    if status is None:
        stmt = stmt.where(Inquiry.status != "cancelled")
    elif status != "all":
        stmt = stmt.where(Inquiry.status == status)
    if buyer is not None:
        stmt = stmt.where(Inquiry.buyer_id == buyer)
    if q:
        stmt = stmt.where(
            Inquiry.reference.icontains(q, autoescape=True)
            | Vessel.name.icontains(q, autoescape=True)
            | Port.name.icontains(q, autoescape=True)
        )
    # ponytail: unpaginated; reference sorts as text, so INQ-yymm-1000 sorts before -999.
    order = Inquiry.reference if sort == "reference" else Inquiry.eta.asc().nulls_last()
    return session.execute(stmt.order_by(order, Inquiry.id)).all()


def dec(value: Decimal | None) -> str | None:
    """Exact decimal string without trailing zeros ("0.100" -> "0.1", 500 -> "500")."""
    return None if value is None else format(value.normalize(), "f")


def line_rows(session: Session, inquiry_id: uuid.UUID) -> Sequence[Any]:
    """Lines in position order with product and ISO version names and activity."""
    return session.execute(
        select(
            InquiryLine,
            Product.name.label("product_name"),
            Product.active.label("product_active"),
            IsoSpecVersion.name.label("iso_name"),
            IsoSpecVersion.active.label("iso_active"),
        )
        .join(Product, Product.id == InquiryLine.product_id)
        .join(IsoSpecVersion, IsoSpecVersion.id == InquiryLine.iso_spec_version_id)
        .where(InquiryLine.inquiry_id == inquiry_id)
        .order_by(InquiryLine.position)
    ).all()


def line_text(  # noqa: PLR0913, PLR0917
    product: str, quantity: Decimal, unit: str, density: Decimal | None, iso: str, notes: str | None
) -> str:
    """One line as readable audit text; equal text means an equal line."""
    parts = [f"{product} {dec(quantity)} {unit}"]
    if density is not None:
        parts.append(f"{dec(density)} kg/m3")
    parts.append(iso)
    if notes:
        parts.append(notes)
    return " | ".join(parts)


# The decision columns the Operator never sees; also the audited decision fields.
DECISION_COLUMNS = ("winner_offer_id", "decision_reason", "decision_note", "decided_total")


def decision(session: Session, inq: Inquiry) -> dict[str, Any] | None:
    """Return the recorded winner decision (commercial: never show it to an Operator)."""
    if inq.winner_offer_id is None or inq.decided_total is None:
        return None
    by = session.get(AppUser, inq.decided_by)
    assert by is not None  # noqa: S101  (FK)
    return {
        "winner_offer_id": inq.winner_offer_id,
        "reason": inq.decision_reason,
        "note": inq.decision_note,
        "decided_at": inq.decided_at,
        "decided_by_name": by.name or by.email,
        "decided_total": format(inq.decided_total, "f"),
        "currency": "USD",  # D-071: the system is USD-only
    }


def detail(session: Session, inq: Inquiry) -> dict[str, Any]:
    """Return the full inquiry record: columns, names, inactive flags, lines, warnings."""
    operator, buyer, requester = (aliased(AppUser) for _ in range(3))
    names = (
        session.execute(
            select(
                Vessel.name.label("vessel_name"),
                (~Vessel.active).label("vessel_inactive"),
                LegalEntity.name.label("legal_entity_name"),
                (~LegalEntity.active).label("legal_entity_inactive"),
                Port.name.label("port_name"),
                Port.locode.label("port_locode"),
                Port.time_zone.label("port_time_zone"),
                (~Port.active).label("port_inactive"),
                BunkeringReason.name.label("bunkering_reason_name"),
                (~BunkeringReason.active).label("bunkering_reason_inactive"),
                _shown(operator).label("operator_name"),
                _shown(buyer).label("buyer_name"),
                _shown(requester).label("requester_name"),
                _rfq_count(is_active_rfq()).label("rfq_total"),
                _rfq_count(is_active_rfq(), Rfq.status != RfqStatus.DRAFT.value).label("rfq_sent"),
                _winner_name().label("winner_counterparty_name"),
            )
            .select_from(Inquiry)
            .join(Vessel, Vessel.id == Inquiry.vessel_id)
            .join(LegalEntity, LegalEntity.id == Inquiry.legal_entity_id)
            .join(Port, Port.id == Inquiry.port_id)
            .join(BunkeringReason, BunkeringReason.id == Inquiry.bunkering_reason_id)
            .join(operator, operator.id == Inquiry.operator_id)
            .join(requester, requester.id == Inquiry.requester_id)
            .outerjoin(buyer, buyer.id == Inquiry.buyer_id)
            .where(Inquiry.id == inq.id)
        )
        .mappings()
        .one()
    )
    approved = set(
        session.scalars(
            select(VesselApprovedFuel.product_id).where(
                VesselApprovedFuel.vessel_id == inq.vessel_id, VesselApprovedFuel.active
            )
        )
    )
    lines: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    for i, (line, product, product_active, iso, iso_active) in enumerate(
        line_rows(session, inq.id)
    ):
        lines.append(
            {
                "id": line.id,
                "position": line.position,
                "product_id": line.product_id,
                "product_name": product,
                "product_inactive": not product_active,
                "quantity": dec(line.quantity),
                "unit": line.unit,
                "density": dec(line.density),
                "not_in_total": line.unit == "m3" and line.density is None,
                "spec_notes": line.spec_notes,
                "iso_spec_version_id": line.iso_spec_version_id,
                "iso_spec_version_name": iso,
                "iso_spec_version_inactive": not iso_active,
            }
        )
        if line.product_id not in approved:
            warnings.append(
                {
                    "field": f"lines[{i}].product_id",
                    "code": "not_approved_fuel",
                    "message": f"{product} is not an approved fuel for {names['vessel_name']}",
                }
            )
    columns = {c.key: getattr(inq, c.key) for c in Inquiry.__table__.columns}
    return {
        **columns, **names, "lines": lines, "warnings": warnings, "decision": decision(session, inq)
    }  # fmt: skip
