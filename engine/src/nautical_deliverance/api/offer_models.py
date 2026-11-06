"""Offer request and response models (B4 spec section 4). Amounts are decimal strings (D-074)."""

import re
import uuid  # noqa: TC003  (pydantic runtime)
from datetime import datetime  # noqa: TC003
from decimal import Decimal
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints

from nautical_deliverance.api.common import Strict, check
from nautical_deliverance.api.inquiry_models import DecisionOut  # noqa: TC001  (pydantic runtime)
from nautical_deliverance.domain.inquiry import DENSITY_MAX, DENSITY_MIN, MAX_LINES
from nautical_deliverance.domain.offer import (  # noqa: TC001  (pydantic runtime)
    DecisionReason,
    DeliveryMethod,
)

COSTS = ("barging_cost", "port_call_cost", "agent_cost", "surveyor_cost", "other_cost")
FIELDS = (
    "valid_until", "payment_terms", "delivery_from", "delivery_to", "delivery_method",
    "physical_supplier", "supplier_comment", *COSTS,
)  # fmt: skip

_MONEY = re.compile(r"[0-9]{1,10}(\.[0-9]{1,2})?")  # numeric(12,2)
_PRICE = re.compile(r"[0-9]{1,9}(\.[0-9]{1,3})?")  # numeric(12,3)
_DENSITY = re.compile(r"[0-9]{1,4}(\.[0-9])?")  # numeric(6,1)

Money = Annotated[
    str,
    check(_MONEY.fullmatch, "Must be an amount of 0 or more with up to 2 decimals"),
]
Price = Annotated[
    str,
    check(
        lambda v: _PRICE.fullmatch(v) and Decimal(v) > 0,
        "Must be a positive price with up to 9 digits and 3 decimals",
    ),
]
Density = Annotated[
    str,
    check(
        lambda v: _DENSITY.fullmatch(v) and DENSITY_MIN <= Decimal(v) <= DENSITY_MAX,
        f"Must be {DENSITY_MIN} to {DENSITY_MAX} kg/m3 with at most 1 decimal",
    ),
]
Text200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Text2000 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class OfferLineIn(Strict):
    """The price (and density for an m3 line without one) offered for one inquiry line."""

    inquiry_line_id: uuid.UUID
    price_per_mt: Price
    density: Density | None = None


class _Fields(Strict):
    """Optional offer fields shared by create and patch."""

    payment_terms: Text200 | None = None
    delivery_from: AwareDatetime | None = None
    delivery_to: AwareDatetime | None = None
    delivery_method: DeliveryMethod | None = None
    physical_supplier: Text200 | None = None
    supplier_comment: Text2000 | None = None
    barging_cost: Money | None = None
    port_call_cost: Money | None = None
    agent_cost: Money | None = None
    surveyor_cost: Money | None = None
    other_cost: Money | None = None


class OfferIn(_Fields):
    """Enter the offer of a sent RFQ; absent fixed costs are 0."""

    valid_until: AwareDatetime
    lines: Annotated[list[OfferLineIn], Field(max_length=MAX_LINES)] = []  # noqa: RUF012


class OfferPatch(_Fields):
    """Change an offer: absent fields stay, null clears an optional one, `lines` replaces."""

    version: int = Field(ge=1)
    valid_until: AwareDatetime | None = None
    lines: Annotated[list[OfferLineIn], Field(max_length=MAX_LINES)] | None = None


class OfferLineOut(BaseModel):
    """One inquiry line with the offered price and the computed cost."""

    inquiry_line_id: uuid.UUID
    product: str
    price_per_mt: str | None
    density: str | None
    qty_mt: str | None
    line_cost: str | None
    in_total: bool


class OfferOut(BaseModel):
    """An offer with its computed lines, total and completeness."""

    id: uuid.UUID
    rfq_id: uuid.UUID
    inquiry_id: uuid.UUID
    rfq_status: str
    counterparty_name: str
    selected: bool
    currency: str
    valid_until: datetime
    payment_terms: str | None
    delivery_from: datetime | None
    delivery_to: datetime | None
    delivery_method: str | None
    physical_supplier: str | None
    supplier_comment: str | None
    barging_cost: str
    port_call_cost: str
    agent_cost: str
    surveyor_cost: str
    other_cost: str
    lines: list[OfferLineOut]
    total: str
    complete: bool
    received_at: datetime
    version: int


class ComparisonRow(OfferOut):
    """An offer in the comparison with its ranking flags."""

    offer_id: uuid.UUID
    lowest: bool
    delta_to_lowest: str | None
    expired: bool
    expiring_soon: bool


class ComparisonOut(BaseModel):
    """Offers ordered complete first, then cheapest first, and the decision (or null)."""

    rows: list[ComparisonRow]
    decision: DecisionOut | None


class SelectWinnerIn(Strict):
    """Select the winner; a reason is needed unless the offer is the lowest."""

    version: int = Field(ge=1)
    offer_id: uuid.UUID
    reason: DecisionReason | None = None
    note: Text2000 | None = None
