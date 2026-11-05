"""RFQ domain: render, confidentiality, mailto and transitions (B3-R05..R12)."""

import dataclasses
import itertools
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import unquote

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nautical_deliverance.domain.rfq import (
    MAILTO_MAX,
    RFQ_TRANSITIONS,
    RfqContext,
    RfqLine,
    RfqStatus,
    build_mailto,
    can_rfq_transition,
    format_instant,
    render_rfq,
)

R = RfqStatus
_TABLE = {(R.DRAFT, R.SENT), (R.DRAFT, R.WITHDRAWN), (R.SENT, R.DECLINED)}
AMS = "Europe/Amsterdam"
TO = "a@x.example"


def _ctx(**kw: object) -> RfqContext:
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
            RfqLine("VLSFO", Decimal("1200.500"), "mt", None, "max 0.5% S", "ISO 8217:2024"),
            RfqLine("MGO", Decimal(300), "m3", Decimal("850.5"), None, "ISO 8217:2024"),
        ),
        "response_deadline": datetime(2026, 11, 12, 6, 0, tzinfo=UTC),
        "recipient_name": "Anna Seller",
        "recipient_email": "anna@seller.example",
        "buyer_name": "Bo Buyer",
    }
    return RfqContext(**{**base, **kw})  # type: ignore[arg-type]


@pytest.mark.req("B3-R07")
def test_golden_render() -> None:
    """One fixed context renders exactly the expected text."""
    subject, body = render_rfq(_ctx())
    assert subject == "RFQ INQ-2611-001 – Stena Example – Rotterdam"  # noqa: RUF001
    assert body == (
        "Dear Anna Seller,\n\n"
        "Please quote for the following bunker delivery:\n\n"
        "Vessel: Stena Example (IMO 9123456)\n"
        "Port: Rotterdam (NLRTM)\n"
        "ETA / ETD: 29 Mar 00:30 UTC · 01:30 local / 29 Mar 01:30 UTC · 03:30 local\n"
        "Agent: Agent Co\n"
        "Products:\n"
        "  - VLSFO: 1200.500 mt, ISO 8217:2024, max 0.5% S\n"
        "  - MGO: 300 m3, density 850.5 kg/m3, ISO 8217:2024\n\n"
        "Please state price per mt (USD), all additional costs (barging, port, agent, "
        "surveyor, other), offer validity, payment terms, delivery window and method, "
        "and the physical supplier if you are a trader.\n\n"
        "Response requested by 12 Nov 06:00 UTC · 07:00 local.\n\n"
        "Kind regards,\nBo Buyer\nBunker desk"
    )


@pytest.mark.req("B3-R07")
@pytest.mark.parametrize("buyer", ["", "Bunker desk"])
def test_signature_without_buyer_name_is_desk_once(buyer: str) -> None:
    """No buyer name (or the desk itself): the signature is 'Bunker desk', printed once."""
    _, body = render_rfq(_ctx(buyer_name=buyer))
    assert body.endswith("Kind regards,\nBunker desk")
    assert body.count("Bunker desk") == 1


@pytest.mark.req("B3-R07")
def test_missing_eta_etd_agent_to_be_advised() -> None:
    """Absent ETA/ETD/agent print as to be advised."""
    _, body = render_rfq(_ctx(eta=None, etd=None, agent_name=None))
    assert "ETA / ETD: to be advised / to be advised\n" in body
    assert "Agent: to be advised\n" in body


@pytest.mark.req("B3-R07")
def test_format_instant_across_dst() -> None:
    """UTC and local time match the web formatInstant, before and after DST changes."""
    cases = [
        ((2026, 3, 29, 0, 30), "29 Mar 00:30 UTC · 01:30 local"),
        ((2026, 3, 29, 1, 30), "29 Mar 01:30 UTC · 03:30 local"),
        ((2026, 10, 25, 0, 30), "25 Oct 00:30 UTC · 02:30 local"),
        ((2026, 10, 25, 1, 30), "25 Oct 01:30 UTC · 02:30 local"),
        ((2026, 11, 12, 6, 0), "12 Nov 06:00 UTC · 07:00 local"),
    ]
    for ymdhm, expected in cases:
        assert format_instant(datetime(*ymdhm, tzinfo=UTC), AMS) == expected
    with pytest.raises(ValueError, match="timezone-aware"):
        format_instant(datetime(2026, 1, 1), AMS)  # noqa: DTZ001


# Strict superset of spec section 3 "Never".
FORBIDDEN = (
    "internal_comments",
    "cancel_reason",
    "operator_name",
    "requester_name",
    "legal_entity_name",
    "other_cp_name_1",
    "other_cp_name_2",
    "other_contact_email_1",
    "other_contact_email_2",
    "other_contact_name",
    "recipient_count",
    "price_expectation",
    "offer_price",
    "decision_rationale",
    "comparison_note",
    "agent_email",
    "recipient_counterparty_name",
    "voyage",
)
ALLOWED = (
    "reference",
    "vessel_name",
    "vessel_imo",
    "port_name",
    "port_locode",
    "port_time_zone",
    "eta",
    "etd",
    "agent_name",
    "lines",
    "response_deadline",
)


def to_context(d: dict[str, object], recipient: dict[str, str]) -> RfqContext:
    """Test-local mirror of the production builder: copies allowed keys only."""
    kw = {k: d[k] for k in ALLOWED}
    return RfqContext(
        **kw,  # type: ignore[arg-type]
        recipient_name=recipient["name"],
        recipient_email=recipient["email"],
        buyer_name=str(d["buyer_name"]),
    )


@pytest.mark.req("B3-R06")
@given(n=st.integers(1, 10**6), count=st.integers(1, 50))
def test_no_forbidden_marker_leaks(n: int, count: int) -> None:
    """No marker from any forbidden field reaches subject, body or mailto."""
    markers = {k: f"MK{n}-{i}-{k.upper()}" for i, k in enumerate(FORBIDDEN)}
    markers["recipient_count"] = f"COUNT-{count}"
    c = _ctx()
    d: dict[str, object] = {
        **markers,
        "reference": c.reference,
        "vessel_name": c.vessel_name,
        "vessel_imo": c.vessel_imo,
        "port_name": c.port_name,
        "port_locode": c.port_locode,
        "port_time_zone": c.port_time_zone,
        "eta": c.eta,
        "etd": c.etd,
        "agent_name": c.agent_name,
        "lines": c.lines,
        "response_deadline": c.response_deadline,
        "buyer_name": c.buyer_name,
    }
    ctx = to_context(d, {"name": "Anna", "email": "anna@seller.example"})
    subject, body = render_rfq(ctx)
    url, _ = build_mailto(ctx.recipient_email, subject, body)
    for m in markers.values():
        for text in (subject, body, url, unquote(url)):
            assert m not in text


@pytest.mark.req("B3-R05")
@given(
    local=st.text("abcdefghij.-_+", min_size=1, max_size=20),
    subject=st.text(max_size=100),
    body=st.text(max_size=2500),
)
def test_mailto_single_address_only_subject_body(local: str, subject: str, body: str) -> None:
    """One address before the ?, only subject and optionally body parameters."""
    url, _ = build_mailto(f"{local}@x.example", subject, body)
    head, _, query = url.partition("?")
    assert head.count("@") == 1
    params = [p.split("=", 1)[0] for p in query.split("&")]
    assert params in (["subject"], ["subject", "body"])
    assert "cc=" not in query.replace("subject=", "").replace("body=", "")


@pytest.mark.req("B3-R05")
@pytest.mark.parametrize(
    "to",
    [
        "a@x.example,b@y.example",
        "a@x.example;b@y.example",
        "a@x.example?cc=b",
        "a b@x.example",
        "",
        "nobody",
        "a@b@c.example",
        "@x.example",
        "a@",
    ],
)
def test_mailto_rejects_multiple_or_injected(to: str) -> None:
    """Separators, ?, whitespace in the address are rejected."""
    with pytest.raises(ValueError, match="single"):
        build_mailto(to, "s", "b")


@pytest.mark.req("B3-R12")
@pytest.mark.parametrize("s", ["&", "?", "#", "%", "\n", '"', "Ünïcode – ok", "&cc=evil@x.example"])  # noqa: RUF001
def test_mailto_roundtrip_and_no_injection(s: str) -> None:
    """Subject and body survive percent-encoding; no extra parameter appears."""
    url, included = build_mailto(TO, s, s)
    assert included
    sub, body = url.partition("?")[2].split("&")
    assert sub.startswith("subject=")
    assert body.startswith("body=")
    assert unquote(sub[len("subject=") :]) == s
    assert unquote(body[len("body=") :]) == s
    ctx = _ctx(lines=(RfqLine("X", Decimal(1), "mt", None, s, "ISO"),))
    subj, text = render_rfq(ctx)
    u, _ = build_mailto(TO, subj, text)
    assert unquote(u.partition("body=")[2]) == text


@pytest.mark.req("B3-R12")
def test_body_dropped_exactly_above_limit() -> None:
    """Link of 1800 keeps the body; 1801 drops it."""
    base = len(build_mailto(TO, "s", "")[0])  # includes "&body="
    url, inc = build_mailto(TO, "s", "x" * (MAILTO_MAX - base))
    assert (len(url), inc) == (MAILTO_MAX, True)
    url, inc = build_mailto(TO, "s", "x" * (MAILTO_MAX - base + 1))
    assert not inc
    assert "body" not in url


@pytest.mark.req("B3-R09")
def test_rfq_transitions_exact() -> None:
    """Transition table is exact."""
    assert {(a, b) for a, bs in RFQ_TRANSITIONS.items() for b in bs} == _TABLE


@pytest.mark.req("B3-R09")
@given(pair=st.sampled_from(list(itertools.product(R, R))))
def test_can_rfq_transition_all_pairs(pair: tuple[RfqStatus, RfqStatus]) -> None:
    """All 16 pairs agree with the table."""
    assert can_rfq_transition(*pair) is (pair in _TABLE)


def _marker_dict(n: int, count: int) -> dict[str, str]:
    markers = {k: f"MK{n}-{i}-{k.upper()}" for i, k in enumerate(FORBIDDEN)}
    markers["recipient_count"] = f"COUNT-{count}"
    return markers


@pytest.mark.req("B3-R06")
def test_context_fields_pinned_and_disjoint_from_forbidden() -> None:
    """RfqContext holds exactly the allowed fields; none is a forbidden key."""
    names = {f.name for f in dataclasses.fields(RfqContext)}
    assert names == set(ALLOWED) | {"recipient_name", "recipient_email", "buyer_name"}
    assert names.isdisjoint(FORBIDDEN)
    assert {f.name for f in dataclasses.fields(RfqLine)} == {
        "product",
        "quantity",
        "unit",
        "density",
        "spec_notes",
        "iso_version",
    }


@pytest.mark.req("B3-R06")
@given(n=st.integers(1, 10**6), count=st.integers(1, 50))
def test_leak_scan_positive_control(n: int, count: int) -> None:
    """The scan can fail: a marker in an allowed field is found; markers are non-empty."""
    markers = _marker_dict(n, count)
    assert len(markers) == len(FORBIDDEN)
    assert all(m and m in repr(markers) for m in markers.values())
    m = markers["internal_comments"]
    line = RfqLine("X", Decimal(1), "mt", None, m, "ISO")
    subject, body = render_rfq(_ctx(lines=(line,)))
    url, _ = build_mailto(TO, subject, body)
    assert m in body
    assert m in unquote(url)


@pytest.mark.req("B3-R06")
def test_all_keys_context_would_leak() -> None:
    """Mutation check: copying every key (forbidden too) into a rendered field leaks."""
    markers = _marker_dict(1, 2)
    note = " ".join(markers.values())
    _, body = render_rfq(_ctx(lines=(RfqLine("X", Decimal(1), "mt", None, note, "ISO"),)))
    assert all(m in body for m in markers.values())


@pytest.mark.req("B3-R07")
def test_decimals_never_use_exponent() -> None:
    """Quantity and density print in plain notation."""
    line = RfqLine("X", Decimal("1E+3"), "m3", Decimal("8.5E+2"), None, "ISO")
    _, body = render_rfq(_ctx(lines=(line,)))
    assert "  - X: 1000 m3, density 850 kg/m3, ISO" in body
