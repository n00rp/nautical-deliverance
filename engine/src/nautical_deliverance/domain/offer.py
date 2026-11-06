"""Exact offer cost rules, lowest offer and rationale (B4-R04..R06). Decimal only, never float."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Iterable

MAX_TOTAL = Decimal("999999999999.99")
_CENT = Decimal("0.01")
_THOUSAND = Decimal(1000)


class DeliveryMethod(StrEnum):
    """How the fuel is delivered."""

    BARGE = "barge"
    TRUCK = "truck"
    PIPELINE = "pipeline"
    EX_WHARF = "ex_wharf"


class DecisionReason(StrEnum):
    """Why a non-lowest offer was selected."""

    FLEXIBILITY = "flexibility"
    OPERATIONAL_FIT = "operational_fit"
    AVAILABILITY = "availability"
    RELIABILITY = "reliability"
    TIMING = "timing"
    PAYMENT_TERMS = "payment_terms"
    COMMERCIAL_JUDGEMENT = "commercial_judgement"
    OTHER = "other"


@dataclass(frozen=True)
class LineInput:
    """One inquiry line with its offered price."""

    line_id: str
    unit: Literal["mt", "m3"]
    quantity: Decimal
    inquiry_density: Decimal | None
    price_per_mt: Decimal | None
    offer_density: Decimal | None


@dataclass(frozen=True)
class OfferInput:
    """An offer: lines plus barging, port call, agent, surveyor and other costs."""

    offer_id: str
    lines: tuple[LineInput, ...]
    fixed: tuple[Decimal, Decimal, Decimal, Decimal, Decimal]


@dataclass(frozen=True)
class LineResult:
    """Computed line; ``in_total`` is False without price or density."""

    line_id: str
    qty_mt: Decimal | None
    line_cost: Decimal | None
    in_total: bool


@dataclass(frozen=True)
class OfferResult:
    """Computed offer."""

    offer_id: str
    lines: tuple[LineResult, ...]
    total: Decimal
    complete: bool


def quantity_mt(line: LineInput) -> Decimal | None:
    """Exact quantity in mt; None for m3 without any density."""
    if line.unit == "mt":
        return line.quantity
    density = line.inquiry_density if line.inquiry_density is not None else line.offer_density
    return None if density is None else line.quantity * density / _THOUSAND


def format_qty_mt(q: Decimal) -> str:
    """Shortest exact decimal string with at least 3 decimals (never rounds)."""
    whole, _, frac = format(q.normalize(), "f").partition(".")
    return f"{whole}.{frac.ljust(3, '0')}"


def line_cost(qty_mt: Decimal, price: Decimal) -> Decimal:
    """Line cost rounded half-up to 2 decimals (B4-D1)."""
    return (qty_mt * price).quantize(_CENT, ROUND_HALF_UP)


def evaluate_offer(o: OfferInput) -> OfferResult:
    """Compute line costs and total; ValueError when too large; no lines is incomplete."""
    results = []
    total = sum(o.fixed, Decimal(0))
    for line in o.lines:
        qty = quantity_mt(line)
        if qty is None or line.price_per_mt is None:
            results.append(LineResult(line.line_id, qty, None, in_total=False))
            continue
        cost = line_cost(qty, line.price_per_mt)
        total += cost
        results.append(LineResult(line.line_id, qty, cost, in_total=True))
    if abs(total) > MAX_TOTAL:
        msg = "total too large"
        raise ValueError(msg)
    return OfferResult(
        o.offer_id, tuple(results), total, bool(results) and all(r.in_total for r in results)
    )


def lowest(results: Iterable[OfferResult]) -> frozenset[str]:
    """Ids of the complete offers with the minimum total (all ties)."""
    complete = [r for r in results if r.complete]
    if not complete:
        return frozenset()
    low = min(r.total for r in complete)
    return frozenset(r.offer_id for r in complete if r.total == low)


def rationale_required(selected_id: str, results: Iterable[OfferResult]) -> bool:
    """Return whether a rationale is needed (selected offer is not lowest)."""
    return selected_id not in lowest(results)
