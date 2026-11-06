"""Nomination domain: golden text, confidentiality pin, transitions, format_usd (B5-R04, B5-R05)."""

import dataclasses
import itertools
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import unquote

import pytest

from nautical_deliverance.domain.nomination import (
    NOMINATION_TRANSITIONS,
    NominationContext,
    NominationLine,
    NominationStatus,
    can_nomination_transition,
    render_nomination,
)
from nautical_deliverance.domain.offer import format_usd
from nautical_deliverance.domain.rfq import build_mailto

S = NominationStatus
AMS = "Europe/Amsterdam"


def _ctx(**kw: object) -> NominationContext:
    base: dict[str, object] = {
        "reference": "INQ-2611-001",
        "vessel_name": "Stena Example",
        "vessel_imo": "9123456",
        "port_name": "Rotterdam",
        "port_locode": "NLRTM",
        "port_time_zone": AMS,
        "eta": datetime(2026, 3, 29, 0, 30, tzinfo=UTC),
        "etd": datetime(2026, 3, 29, 1, 30, tzinfo=UTC),
        "agent_name": "Agent Co",
        "lines": (
            NominationLine(
                "VLSFO",
                Decimal("1200.500"),
                "mt",
                None,
                Decimal("1200.500"),
                Decimal("612.5"),
                Decimal("735306.25"),
                in_total=True,
            ),
            NominationLine(
                "MGO",
                Decimal("1000.001"),
                "m3",
                Decimal("850.5"),
                Decimal("850.5008505"),
                Decimal(700),
                Decimal("595350.60"),
                in_total=True,
            ),
            NominationLine(
                "HSFO", Decimal(20), "m3", None, None, Decimal(450), None, in_total=False
            ),
            NominationLine("LSMGO", Decimal(50), "mt", None, None, None, None, in_total=False),
        ),
        "barging_cost": Decimal(1500),
        "port_call_cost": Decimal(0),
        "agent_cost": Decimal("250.5"),
        "surveyor_cost": Decimal(300),
        "other_cost": Decimal(0),
        "total": Decimal("1332707.35"),
        "currency": "USD",
        "delivery_from": datetime(2026, 3, 29, 0, 30, tzinfo=UTC),
        "delivery_to": datetime(2026, 3, 29, 1, 30, tzinfo=UTC),
        "delivery_method": "barge",
        "physical_supplier": "Real Fuels BV",
        "payment_terms": "30 days",
        "recipient_name": "Anna Seller",
        "recipient_email": "anna@seller.example",
        "buyer_name": "Bo Buyer",
        "sequence": 1,
    }
    return NominationContext(**{**base, **kw})  # type: ignore[arg-type]


_COMMON = (
    "Vessel: Stena Example (IMO 9123456)\n"
    "Port: Rotterdam (NLRTM)\n"
    "ETA / ETD: 29 Mar 00:30 UTC · 01:30 local / 29 Mar 01:30 UTC · 03:30 local\n"
    "Agent: Agent Co\n"
    "Products:\n"
    "  - VLSFO: 1200.500 mt x USD 612.500/mt = USD 735,306.25\n"
    "  - MGO: 1000.001 m3, density 850.5 kg/m3 -> 850.5008505 mt x USD 700.000/mt"
    " = USD 595,350.60\n"
    "  - HSFO: 20 m3 x USD 450.000/mt, quantity in mt to be confirmed — not included in total\n"
    "  - LSMGO: not included in this nomination\n"
    "Additional costs:\n"
    "  - Barging: USD 1,500.00\n"
    "  - Port call: USD 0.00\n"
    "  - Agent: USD 250.50\n"
    "  - Surveyor: USD 300.00\n"
    "  - Other: USD 0.00\n"
    "Total: USD 1,332,707.35\n\n"
    "Delivery window: 29 Mar 00:30 UTC · 01:30 local to 29 Mar 01:30 UTC · 03:30 local\n"
    "Delivery method: barge\n"
    "Physical supplier: Real Fuels BV\n"
    "Payment terms: 30 days\n\n"
    "Kind regards,\nBo Buyer\nBunker desk"
)


@pytest.mark.req("B5-R05")
def test_golden_version_1() -> None:
    """First nomination renders exactly the expected subject and body."""
    subject, body = render_nomination(_ctx())
    assert subject == "Nomination INQ-2611-001 – Stena Example – Rotterdam"  # noqa: RUF001
    assert body == "Dear Anna Seller,\n\nWe confirm the following nomination:\n\n" + _COMMON


@pytest.mark.req("B5-R05")
def test_golden_version_2_amended() -> None:
    """An amendment has its own subject and wording."""
    subject, body = render_nomination(_ctx(sequence=2))
    assert subject == "Amended nomination (2) INQ-2611-001 – Stena Example – Rotterdam"  # noqa: RUF001
    assert body == (
        "Dear Anna Seller,\n\nWe confirm the following amended nomination (version 2), "
        "which replaces any earlier nomination for this call:\n\n" + _COMMON
    )


@pytest.mark.req("B5-R05")
def test_missing_fields_and_signature() -> None:
    """Absent fields print as to be advised; no buyer name signs with the desk only."""
    _, body = render_nomination(
        _ctx(
            eta=None,
            etd=None,
            agent_name=None,
            delivery_from=None,
            delivery_to=None,
            delivery_method=None,
            physical_supplier=None,
            payment_terms=None,
            buyer_name="",
            lines=(),
            total=Decimal("2050.50"),
        )
    )
    assert "ETA / ETD: to be advised / to be advised\n" in body
    assert "Agent: to be advised\n" in body
    assert "Delivery window: to be advised\n" in body
    assert "Delivery method: to be advised\n" in body
    assert "Physical supplier: to be advised\n" in body
    assert "Payment terms: to be advised\n" in body
    assert body.endswith("Kind regards,\nBunker desk")


@pytest.mark.req("B5-R05")
@pytest.mark.parametrize(
    ("value", "text"),
    [
        ("1234567.89", "USD 1,234,567.89"),
        ("0.01", "USD 0.01"),
        ("999", "USD 999.00"),
        ("-25000.00", "USD -25,000.00"),
        ("-0.05", "USD -0.05"),
        ("-0.00", "USD 0.00"),
        ("0", "USD 0.00"),
    ],
)
def test_format_usd_matches_web(value: str, text: str) -> None:
    """Same cases as web/src/money.test.ts."""
    assert format_usd(Decimal(value)) == text


@pytest.mark.req("B5-R05")
@pytest.mark.parametrize("value", ["1.999", "0.005", "-0.001", "1.001"])
def test_format_usd_rejects_more_than_two_decimals(value: str) -> None:
    """The web formatUsd throws on more than 2 decimals; so does this."""
    with pytest.raises(ValueError, match="decimals"):
        format_usd(Decimal(value))


@pytest.mark.req("B5-R05")
def test_total_guard_and_currency() -> None:
    """A text cannot state a total that differs from its lines plus fixed costs, or non-USD."""
    with pytest.raises(ValueError, match="total"):
        render_nomination(_ctx(total=Decimal("1332706.35")))
    with pytest.raises(ValueError, match="USD"):
        render_nomination(_ctx(currency="EUR"))


@pytest.mark.req("B5-R05")
def test_line_states_are_consistent() -> None:
    """in_total with no cost, a cost outside the total, or an unpriced line in total: impossible."""
    cost = Decimal(5)
    with pytest.raises(ValueError, match="in_total"):
        NominationLine("X", cost, "mt", None, cost, cost, cost, in_total=False)
    with pytest.raises(ValueError, match="in_total"):
        NominationLine("X", cost, "mt", None, cost, cost, None, in_total=True)
    with pytest.raises(ValueError, match="unpriced"):
        NominationLine("X", cost, "mt", None, cost, None, cost, in_total=True)


ALLOWED_CTX = {
    *("reference", "vessel_name", "vessel_imo", "port_name", "port_locode", "port_time_zone"),
    *("eta", "etd", "agent_name", "lines", "barging_cost", "port_call_cost", "agent_cost"),
    *("surveyor_cost", "other_cost", "total", "currency", "delivery_from", "delivery_to"),
    *("delivery_method", "physical_supplier", "payment_terms", "recipient_name"),
    *("recipient_email", "buyer_name", "sequence"),
}
ALLOWED_LINE = {
    *("product", "quantity", "unit", "density", "qty_mt", "price_per_mt", "line_cost", "in_total"),
}
FORBIDDEN = {
    *("decision_reason", "decision_note", "internal_comments", "internal_note", "cancel_reason"),
    *("operator_name", "requester_name", "legal_entity_name", "other_offers"),
    *("offer_count", "rfq_count", "delta_to_lowest", "lowest", "offers", "prices"),
    *("operator_email", "requester_email", "buyer_email", "agent_email", "cc", "bcc"),
    *("operator", "requester", "legal_entity", "counterparty_name", "other_counterparties"),
    *("other_price", "other_prices", "other_supplier", "supplier_name", "comments"),
}


@pytest.mark.req("B5-R04")
def test_context_field_set_is_pinned() -> None:
    """Adding a field to the nomination context is a deliberate, reviewed act."""
    ctx_names = {f.name for f in dataclasses.fields(NominationContext)}
    line_names = {f.name for f in dataclasses.fields(NominationLine)}
    assert ctx_names == ALLOWED_CTX
    assert line_names == ALLOWED_LINE
    assert not (ctx_names | line_names) & FORBIDDEN


@pytest.mark.req("B5-R04")
def test_positive_control_marker_reaches_body() -> None:
    """A marker in an allowed field is found, so the absence checks are meaningful."""
    _, body = render_nomination(_ctx(physical_supplier="MARKER-ZX81"))
    assert "MARKER-ZX81" in body
    _, clean = render_nomination(_ctx())
    assert "MARKER-ZX81" not in clean


@pytest.mark.req("B5-R04")
def test_mailto_single_address_subject_and_body_only() -> None:
    """One address, only subject and body parameters, round-trips the subject."""
    ctx = _ctx()
    subject, body = render_nomination(ctx)
    url, included = build_mailto(ctx.recipient_email, subject, body)
    head, _, query = url.partition("?")
    assert head == "mailto:anna@seller.example"
    names = [p.split("=", 1)[0] for p in query.split("&")]
    assert names == (["subject", "body"] if included else ["subject"])
    assert unquote(query.split("&")[0][len("subject=") :]) == subject


@pytest.mark.req("B5-R06")
def test_transition_table_exact() -> None:
    """Only draft to sent and draft to withdrawn are allowed."""
    allowed = {(S.DRAFT, S.SENT), (S.DRAFT, S.WITHDRAWN)}
    for a, b in itertools.product(S, S):
        assert can_nomination_transition(a, b) == ((a, b) in allowed)
    assert set(NOMINATION_TRANSITIONS) == set(S)
