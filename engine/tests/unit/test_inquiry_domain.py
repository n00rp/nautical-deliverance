"""Inquiry status transitions, reference format and field sets (B2-R05..R07)."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nautical_deliverance.domain.inquiry import (
    DENSITY_MAX,
    DENSITY_MIN,
    EDITABLE_AFTER_DRAFT,
    LOCKED_AFTER_DRAFT,
    MAX_LINES,
    PATCHABLE_FIELDS,
    TRANSITIONS,
    LineUnit,
    Status,
    can_transition,
    format_reference,
    ready_to_leave_draft,
)
from nautical_deliverance.domain.master import Unit

S = Status
_TABLE = {
    S.DRAFT: {S.RFQ_SENT, S.CANCELLED},
    S.RFQ_SENT: {S.OFFERS_RECEIVED, S.CANCELLED},
    S.OFFERS_RECEIVED: {S.WINNER_SELECTED, S.CANCELLED},
    S.WINNER_SELECTED: {S.NOMINATED, S.CANCELLED},
    S.NOMINATED: {S.CANCELLED},
    S.CANCELLED: set(),
}


@pytest.mark.req("B2-R06")
def test_transitions_exact() -> None:
    """Transitions exact."""
    assert {k: set(v) for k, v in TRANSITIONS.items()} == _TABLE
    assert [s.value for s in Status] == [
        "draft",
        "rfq_sent",
        "offers_received",
        "winner_selected",
        "nominated",
        "cancelled",
    ]


@pytest.mark.req("B2-R06")
def test_cancel_from_every_non_cancelled() -> None:
    """Cancel from every non cancelled."""
    for s in Status:
        assert can_transition(s, S.CANCELLED) is (s is not S.CANCELLED)


@pytest.mark.req("B2-R06")
def test_cancelled_is_terminal() -> None:
    """Cancelled is terminal."""
    assert TRANSITIONS[S.CANCELLED] == frozenset()


@pytest.mark.req("B2-R06")
@given(a=st.sampled_from(list(Status)), b=st.sampled_from(list(Status)))
def test_can_transition_matches_table(a: Status, b: Status) -> None:
    """Can transition matches table."""
    assert can_transition(a, b) == (b in TRANSITIONS[a])
    if a == b:
        assert not can_transition(a, b)


@pytest.mark.req("B2-R05")
def test_format_reference() -> None:
    """Format reference."""
    assert format_reference(datetime(2026, 10, 31, 23, 59, 59, tzinfo=UTC), 1) == "INQ-2610-001"
    assert format_reference(datetime(2026, 11, 1, tzinfo=UTC), 14) == "INQ-2611-014"
    assert format_reference(datetime(2026, 11, 1, tzinfo=UTC), 1000) == "INQ-2611-1000"


@pytest.mark.req("B2-R05")
def test_format_reference_rejects_bad_input() -> None:
    """Format reference rejects bad input."""
    with pytest.raises(ValueError, match="timezone"):
        format_reference(datetime(2026, 11, 1), 1)  # noqa: DTZ001
    with pytest.raises(ValueError, match="n"):
        format_reference(datetime(2026, 11, 1, tzinfo=UTC), 0)


@pytest.mark.req("B2-R05")
def test_format_reference_uses_utc() -> None:
    """Format reference uses utc."""
    plus2 = timezone(timedelta(hours=2))
    assert format_reference(datetime(2026, 11, 1, 1, 0, tzinfo=plus2), 2) == "INQ-2610-002"


@pytest.mark.req("B2-R07")
def test_field_sets() -> None:
    """Field sets."""
    assert LOCKED_AFTER_DRAFT.isdisjoint(EDITABLE_AFTER_DRAFT)
    assert PATCHABLE_FIELDS == LOCKED_AFTER_DRAFT | EDITABLE_AFTER_DRAFT
    assert {
        "vessel_id",
        "legal_entity_id",
        "port_id",
        "bunkering_reason_id",
        "lines",
        "voyage",
        "operator_name",
        "requester_id",
        "eta",
        "etd",
        "agent_name",
        "agent_email",
        "buyer_id",
        "internal_comments",
    } == PATCHABLE_FIELDS


@pytest.mark.req("B2-R07")
def test_constants() -> None:
    """Constants."""
    assert LineUnit is Unit
    assert (Decimal(600), Decimal(1100), 10) == (DENSITY_MIN, DENSITY_MAX, MAX_LINES)


def test_ready_to_leave_draft_needs_both_times() -> None:
    """Only ETA and ETD together allow leaving Draft."""
    t = datetime(2026, 11, 5, tzinfo=UTC)
    assert ready_to_leave_draft(t, t)
    assert not ready_to_leave_draft(None, t)
    assert not ready_to_leave_draft(t, None)
    assert not ready_to_leave_draft(None, None)
