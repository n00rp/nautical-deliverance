"""Nomination status flow, allow-listed render context and text (B5-R04, B5-R05)."""

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from nautical_deliverance.domain.offer import format_qty_mt, format_usd
from nautical_deliverance.domain.rfq import DESK, TBA, format_instant

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime
    from decimal import Decimal


class NominationStatus(StrEnum):
    """Nomination lifecycle status."""

    DRAFT = "draft"
    SENT = "sent"
    WITHDRAWN = "withdrawn"


NOMINATION_TRANSITIONS: Mapping[NominationStatus, frozenset[NominationStatus]] = {
    NominationStatus.DRAFT: frozenset({NominationStatus.SENT, NominationStatus.WITHDRAWN}),
    NominationStatus.SENT: frozenset(),
    NominationStatus.WITHDRAWN: frozenset(),
}


def can_nomination_transition(a: NominationStatus, b: NominationStatus) -> bool:
    """Return whether a nomination may move from status ``a`` to ``b``."""
    return b in NOMINATION_TRANSITIONS[a]


@dataclass(frozen=True)
class NominationLine:
    """One nominated product line."""

    product: str
    quantity: Decimal
    unit: str
    density: Decimal | None
    qty_mt: Decimal | None
    price_per_mt: Decimal
    line_cost: Decimal | None
    in_total: bool


@dataclass(frozen=True)
class NominationContext:
    """The complete, allow-listed input of a nomination text (B5-D7). Add fields deliberately."""

    reference: str
    vessel_name: str
    vessel_imo: str
    port_name: str
    port_locode: str
    port_time_zone: str
    eta: datetime | None
    etd: datetime | None
    agent_name: str | None
    lines: tuple[NominationLine, ...]
    barging_cost: Decimal
    port_call_cost: Decimal
    agent_cost: Decimal
    surveyor_cost: Decimal
    other_cost: Decimal
    total: Decimal
    currency: str
    delivery_from: datetime | None
    delivery_to: datetime | None
    delivery_method: str | None
    physical_supplier: str | None
    payment_terms: str | None
    recipient_name: str
    recipient_email: str
    buyer_name: str  # "" when the buyer has no name; the signature is then just the desk
    sequence: int  # 1 = first nomination, n >= 2 = amendment n


def _line(x: NominationLine) -> str:
    qty = f"{format(x.quantity, 'f')} {x.unit}"
    if x.density is not None:
        qty += f", density {format(x.density, 'f')} kg/m3"
    if x.qty_mt is None or x.line_cost is None:
        tail = "quantity in mt to be advised"
    else:
        tail = f"{format_qty_mt(x.qty_mt)} mt x USD {format_qty_mt(x.price_per_mt)}/mt"
        tail += f" = {format_usd(x.line_cost)}"
    note = "" if x.in_total else " (not included in total)"
    return f"  - {x.product}: {qty} -> {tail}{note}"


def render_nomination(ctx: NominationContext) -> tuple[str, str]:
    """Return ``(subject, body)`` for the one recipient."""
    tz = ctx.port_time_zone

    def when(dt: datetime | None) -> str:
        return TBA if dt is None else format_instant(dt, tz)

    place = f"{ctx.reference} – {ctx.vessel_name} – {ctx.port_name}"  # noqa: RUF001
    amended = ctx.sequence >= 2  # noqa: PLR2004
    subject = f"Amended nomination ({ctx.sequence}) {place}" if amended else f"Nomination {place}"
    signature = "\n".join(dict.fromkeys(n for n in (ctx.buyer_name, DESK) if n))
    costs = (
        ("Barging", ctx.barging_cost),
        ("Port call", ctx.port_call_cost),
        ("Agent", ctx.agent_cost),
        ("Surveyor", ctx.surveyor_cost),
        ("Other", ctx.other_cost),
    )
    cost_text = "\n".join(f"  - {n}: {format_usd(v)}" for n, v in costs)
    intro = (
        f"We confirm the following amended nomination (amendment {ctx.sequence}), "
        "which replaces any earlier nomination for this call:"
        if amended
        else "We confirm the following nomination:"
    )
    body = (
        f"Dear {ctx.recipient_name},\n\n"
        f"{intro}\n\n"
        f"Vessel: {ctx.vessel_name} (IMO {ctx.vessel_imo})\n"
        f"Port: {ctx.port_name} ({ctx.port_locode})\n"
        f"ETA / ETD: {when(ctx.eta)} / {when(ctx.etd)}\n"
        f"Agent: {ctx.agent_name or TBA}\n"
        f"Products:\n" + "\n".join(_line(x) for x in ctx.lines) + "\n"
        f"Additional costs:\n{cost_text}\n"
        f"Total: {format_usd(ctx.total)}\n\n"
        f"Delivery window: {when(ctx.delivery_from)} to {when(ctx.delivery_to)}\n"
        f"Delivery method: {ctx.delivery_method or TBA}\n"
        f"Physical supplier: {ctx.physical_supplier or TBA}\n"
        f"Payment terms: {ctx.payment_terms or TBA}\n\n"
        f"Kind regards,\n{signature}"
    )
    return subject, body
