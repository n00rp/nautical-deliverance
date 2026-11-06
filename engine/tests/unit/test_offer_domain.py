"""Offer cost rules, lowest and rationale (B4-R04..R06) against the shared vectors."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from nautical_deliverance.domain.offer import (
    MAX_TOTAL,
    LineInput,
    OfferInput,
    OfferResult,
    evaluate_offer,
    format_qty_mt,
    lowest,
    rationale_required,
)

ROOT = Path(__file__).resolve().parents[3]
VECTORS = json.loads((ROOT / "contracts/offer-cost-vectors.json").read_text(encoding="utf-8"))
CASES = VECTORS["cases"]


def _d(s: str | None) -> Decimal | None:
    return None if s is None else Decimal(s)


def _offer(offer_id: str, spec: dict[str, Any]) -> OfferInput:
    """Build an OfferInput from a vector offer."""
    lines = tuple(
        LineInput(
            line_id=x["line_id"],
            unit=x["unit"],
            quantity=Decimal(x["quantity"]),
            inquiry_density=_d(x["inquiry_density"]),
            price_per_mt=_d(x["price_per_mt"]),
            offer_density=_d(x["offer_density"]),
        )
        for x in spec["lines"]
    )
    a, b, c, d, e = (Decimal(x) for x in spec["fixed"])
    return OfferInput(offer_id, lines, (a, b, c, d, e))


@pytest.mark.req("B4-R04")
@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_vectors(case: dict[str, Any]) -> None:
    """Every shared vector gives exactly the expected strings."""
    offer = _offer("o", case["offer"])
    if "error" in case["expected"]:
        with pytest.raises(ValueError, match=case["expected"]["error"]):
            evaluate_offer(offer)
        return
    r = evaluate_offer(offer)
    got = {
        "lines": [
            {
                "line_id": x.line_id,
                "qty_mt": None if x.qty_mt is None else format_qty_mt(x.qty_mt),
                "line_cost": None if x.line_cost is None else str(x.line_cost),
                "in_total": x.in_total,
            }
            for x in r.lines
        ],
        "total": str(r.total),
        "complete": r.complete,
    }
    assert got == case["expected"]


@pytest.mark.req("B4-R04")
def test_zero_lines_incomplete() -> None:
    """An offer without lines is never complete."""
    assert not evaluate_offer(OfferInput("o", (), (Decimal(0),) * 5)).complete


@pytest.mark.req("B4-R04")
def test_format_qty_mt() -> None:
    """Shortest exact decimal, at least 3 decimals, no rounding."""
    assert format_qty_mt(Decimal(102)) == "102.000"
    assert format_qty_mt(Decimal("102.0000")) == "102.000"
    assert format_qty_mt(Decimal("9.125")) == "9.125"
    assert format_qty_mt(Decimal("850.5008505")) == "850.5008505"
    assert format_qty_mt(Decimal(0)) == "0.000"
    assert format_qty_mt(Decimal("1E+3")) == "1000.000"


@pytest.mark.req("B4-R04")
def test_worked_example() -> None:
    """The spec worked example totals 394413.50."""
    case = next(c for c in CASES if c["name"] == "spec worked example")
    assert str(evaluate_offer(_offer("o", case["offer"])).total) == "394413.50"


@pytest.mark.req("B4-R04")
def test_over_limit_raises() -> None:
    """A total above MAX_TOTAL raises."""
    line = LineInput("A", "mt", Decimal("999999999.999"), None, Decimal("99999.999"), None)
    with pytest.raises(ValueError, match="total too large"):
        evaluate_offer(OfferInput("o", (line,), (Decimal(0),) * 5))
    assert Decimal("999999999999.99") == MAX_TOTAL


@pytest.mark.req("B4-R04")
def test_no_float_in_source() -> None:
    """The domain module never calls float."""
    src = (ROOT / "engine/src/nautical_deliverance/domain/offer.py").read_text(encoding="utf-8")
    assert "float(" not in src


def _result(i: int, total: int, *, complete: bool) -> OfferResult:
    """Build a result without lines."""
    return OfferResult(f"o{i}", (), Decimal(total), complete)


_results = st.lists(st.tuples(st.integers(0, 5), st.booleans()), min_size=0, max_size=8).map(
    lambda xs: tuple(_result(i, t, complete=c) for i, (t, c) in enumerate(xs))
)


@pytest.mark.req("B4-R05")
@given(_results)
@example(
    (_result(0, 3, complete=True), _result(1, 3, complete=True), _result(2, 5, complete=True)),
)
@example(
    (_result(0, 1, complete=False), _result(1, 4, complete=True), _result(2, 6, complete=True))
)
@example((_result(0, 1, complete=False), _result(1, 2, complete=False)))
def test_lowest_property(results: tuple[OfferResult, ...]) -> None:
    """Lowest is exactly the minimum-total complete offers."""
    complete = [r for r in results if r.complete]
    expected = (
        frozenset()
        if not complete
        else frozenset(r.offer_id for r in complete if r.total == min(c.total for c in complete))
    )
    got = lowest(results)
    assert got == expected
    assert all(r.complete for r in results if r.offer_id in got)


@pytest.mark.req("B4-R06")
@given(_results)
def test_rationale_required(results: tuple[OfferResult, ...]) -> None:
    """Rationale is required exactly for offers outside lowest."""
    low = lowest(results)
    for r in results:
        assert rationale_required(r.offer_id, results) == (r.offer_id not in low)
