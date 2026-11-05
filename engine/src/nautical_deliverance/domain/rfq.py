"""RFQ status flow, allow-listed render context, text and mailto rules (B3-R05..R12)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from urllib.parse import quote
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from collections.abc import Mapping
    from decimal import Decimal

MAILTO_MAX = 1800
TBA = "to be advised"
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class RfqStatus(StrEnum):
    """RFQ lifecycle status."""

    DRAFT = "draft"
    SENT = "sent"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"


RFQ_TRANSITIONS: Mapping[RfqStatus, frozenset[RfqStatus]] = {
    RfqStatus.DRAFT: frozenset({RfqStatus.SENT, RfqStatus.WITHDRAWN}),
    RfqStatus.SENT: frozenset({RfqStatus.DECLINED}),
    RfqStatus.DECLINED: frozenset(),
    RfqStatus.WITHDRAWN: frozenset(),
}


def can_rfq_transition(a: RfqStatus, b: RfqStatus) -> bool:
    """Return whether an RFQ may move from status ``a`` to ``b``."""
    return b in RFQ_TRANSITIONS[a]


@dataclass(frozen=True)
class RfqLine:
    """One requested product line."""

    product: str
    quantity: Decimal
    unit: str
    density: Decimal | None
    spec_notes: str | None
    iso_version: str


@dataclass(frozen=True)
class RfqContext:
    """The complete, allow-listed input of an RFQ text (B3-D9). Add fields deliberately."""

    reference: str
    vessel_name: str
    vessel_imo: str
    port_name: str
    port_locode: str
    port_time_zone: str
    eta: datetime | None
    etd: datetime | None
    agent_name: str | None
    lines: tuple[RfqLine, ...]
    response_deadline: datetime
    recipient_name: str
    recipient_email: str
    buyer_name: str


def format_instant(dt: datetime, tz: str) -> str:
    """Return ``DD Mon HH:MM UTC · HH:MM local``, as the web ``formatInstant``."""
    if dt.tzinfo is None:
        msg = "dt must be timezone-aware"
        raise ValueError(msg)
    u = dt.astimezone(UTC)
    local = u.astimezone(ZoneInfo(tz))
    return f"{u:%d} {_MONTHS[u.month - 1]} {u:%H:%M} UTC · {local:%H:%M} local"


def _line(line: RfqLine) -> str:
    parts = [f"{line.product}: {format(line.quantity, 'f')} {line.unit}"]
    if line.density is not None:
        parts.append(f"density {format(line.density, 'f')} kg/m3")
    parts.append(line.iso_version)
    if line.spec_notes:
        parts.append(line.spec_notes)
    return "  - " + ", ".join(parts)


def render_rfq(ctx: RfqContext) -> tuple[str, str]:
    """Return ``(subject, body)`` for one recipient."""
    tz = ctx.port_time_zone

    def when(dt: datetime | None) -> str:
        return TBA if dt is None else format_instant(dt, tz)

    subject = f"RFQ {ctx.reference} – {ctx.vessel_name} – {ctx.port_name}"  # noqa: RUF001
    products = "\n".join(_line(x) for x in ctx.lines)
    body = (
        f"Dear {ctx.recipient_name},\n\n"
        "Please quote for the following bunker delivery:\n\n"
        f"Vessel: {ctx.vessel_name} (IMO {ctx.vessel_imo})\n"
        f"Port: {ctx.port_name} ({ctx.port_locode})\n"
        f"ETA / ETD: {when(ctx.eta)} / {when(ctx.etd)}\n"
        f"Agent: {ctx.agent_name or TBA}\n"
        f"Products:\n{products}\n\n"
        "Please state price per mt (USD), all additional costs (barging, port, agent, "
        "surveyor, other), offer validity, payment terms, delivery window and method, "
        "and the physical supplier if you are a trader.\n\n"
        f"Response requested by {when(ctx.response_deadline)}.\n\n"
        f"Kind regards,\n{ctx.buyer_name}\nBunker desk"
    )
    return subject, body


def build_mailto(to: str, subject: str, body: str) -> tuple[str, bool]:
    """Return ``(url, body_included)``; the body is dropped if the link exceeds MAILTO_MAX."""
    local, _, domain = to.partition("@")
    if (
        not local
        or not domain
        or "@" in domain
        or any(c in to for c in ",;?")
        or any(c.isspace() for c in to)
    ):
        msg = "to must be a single e-mail address"
        raise ValueError(msg)
    head = f"mailto:{quote(to, safe='@')}?subject={quote(subject, safe='')}"
    full = f"{head}&body={quote(body, safe='')}"
    if len(full) <= MAILTO_MAX:
        return full, True
    return head, False
