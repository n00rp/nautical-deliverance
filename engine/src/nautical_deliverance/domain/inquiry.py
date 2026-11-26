"""Inquiry status flow, reference format and field sets (B2-D5, B2-R05..R07)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from nautical_deliverance.domain.master import Unit

if TYPE_CHECKING:
    from collections.abc import Mapping

LineUnit = Unit  # same mt / m3 values as master data
ETA_WARNING_WINDOW = timedelta(hours=48)


class Status(StrEnum):
    """Inquiry lifecycle status."""

    DRAFT = "draft"
    RFQ_SENT = "rfq_sent"
    OFFERS_RECEIVED = "offers_received"
    WINNER_SELECTED = "winner_selected"
    NOMINATED = "nominated"
    CANCELLED = "cancelled"


PHASES: dict[str, frozenset[Status]] = {
    "list": frozenset({Status.DRAFT}),
    "market": frozenset({Status.RFQ_SENT, Status.OFFERS_RECEIVED, Status.WINNER_SELECTED}),
    "stemmed": frozenset({Status.NOMINATED}),
    "cancelled": frozenset({Status.CANCELLED}),
}  # work-list tabs (B7a-R01)


TRANSITIONS: Mapping[Status, frozenset[Status]] = {
    Status.DRAFT: frozenset({Status.RFQ_SENT, Status.CANCELLED}),
    Status.RFQ_SENT: frozenset({Status.OFFERS_RECEIVED, Status.CANCELLED}),
    Status.OFFERS_RECEIVED: frozenset({Status.WINNER_SELECTED, Status.CANCELLED}),
    Status.WINNER_SELECTED: frozenset({Status.NOMINATED, Status.CANCELLED}),
    Status.NOMINATED: frozenset({Status.CANCELLED}),
    Status.CANCELLED: frozenset(),
}

LOCKED_AFTER_DRAFT = frozenset(
    {
        "vessel_id",
        "legal_entity_id",
        "port_id",
        "bunkering_reason_id",
        "lines",
        "voyage",
        "operator_name",
        "requester_id",
    }
)
EDITABLE_AFTER_DRAFT = frozenset(
    {"eta", "etd", "agent_name", "agent_email", "buyer_id", "internal_comments"}
)
PATCHABLE_FIELDS = LOCKED_AFTER_DRAFT | EDITABLE_AFTER_DRAFT

DENSITY_MIN = Decimal(600)
DENSITY_MAX = Decimal(1100)
MAX_LINES = 10


def can_transition(a: Status, b: Status) -> bool:
    """Return whether an inquiry may move from status ``a`` to ``b``."""
    return b in TRANSITIONS[a]


def ready_to_leave_draft(eta: datetime | None, etd: datetime | None) -> bool:
    """Return whether ETA and ETD are both set, as leaving Draft requires (R5)."""
    return eta is not None and etd is not None


def format_reference(created_at: datetime, n: int) -> str:
    """Return ``INQ-yymm-nnn`` for the UTC month of ``created_at``."""
    if created_at.tzinfo is None:
        msg = "created_at must be timezone-aware"
        raise ValueError(msg)
    if n < 1:
        msg = "n must be >= 1"
        raise ValueError(msg)
    return f"INQ-{created_at.astimezone(UTC):%y%m}-{n:03d}"


def eta_warning(state: str, eta: datetime | None, now: datetime) -> bool:
    """Return the B2 ETA warning: an open inquiry whose ETA is inside the window (or passed)."""
    if eta is None:
        return False
    open_ = state not in (Status.NOMINATED, Status.CANCELLED)
    return open_ and eta < now + ETA_WARNING_WINDOW
