"""Inquiry request and response models (B2-D12)."""

import re
import uuid  # noqa: TC003  (pydantic runtime)
from datetime import datetime  # noqa: TC003
from decimal import Decimal
from types import NoneType
from typing import Annotated, Any, get_args

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    create_model,
    field_validator,
)

from nautical_deliverance.api.common import Strict, check, email_ok
from nautical_deliverance.domain.inquiry import DENSITY_MAX, DENSITY_MIN, MAX_LINES, LineUnit

QUANTITY = re.compile(r"[0-9]{1,9}(\.[0-9]{1,3})?")  # numeric(12,3)
DENSITY = re.compile(r"[0-9]{1,4}(\.[0-9])?")  # numeric(6,1)

# --- request models ----------------------------------------------------------------------------

_Trim = StringConstraints(strip_whitespace=True, min_length=1)
Voyage = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
AgentName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Comments = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
SpecNotes = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Email = Annotated[str, _Trim, check(email_ok, "Invalid e-mail address")]


class LineIn(Strict):
    """A product line; quantity and density are decimal strings (D-074)."""

    product_id: uuid.UUID
    quantity: str
    unit: LineUnit
    density: str | None = None
    spec_notes: SpecNotes | None = None
    iso_spec_version_id: uuid.UUID

    @field_validator("quantity")
    @staticmethod
    def _quantity(value: str) -> str:
        if not QUANTITY.fullmatch(value) or Decimal(value) <= 0:
            msg = "Must be a positive number with up to 9 digits and 3 decimals"
            raise ValueError(msg)
        return value

    @field_validator("density")
    @staticmethod
    def _density(value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        if info.data.get("unit") == LineUnit.MT:
            msg = "Only allowed for m3 lines"
            raise ValueError(msg)
        if not DENSITY.fullmatch(value) or not DENSITY_MIN <= Decimal(value) <= DENSITY_MAX:
            msg = f"Must be {DENSITY_MIN} to {DENSITY_MAX} kg/m3 with at most 1 decimal"
            raise ValueError(msg)
        return value


class InquiryIn(Strict):
    """Writable inquiry fields; omitted legal entity, operator, requester and buyer default."""

    vessel_id: uuid.UUID
    legal_entity_id: uuid.UUID | None = None
    voyage: Voyage | None = None
    operator_id: uuid.UUID | None = None
    buyer_id: uuid.UUID | None = None
    requester_id: uuid.UUID | None = None
    port_id: uuid.UUID
    eta: AwareDatetime
    etd: AwareDatetime
    agent_name: AgentName | None = None
    agent_email: Email | None = None
    bunkering_reason_id: uuid.UUID
    internal_comments: Comments | None = None
    lines: Annotated[list[LineIn], Field(min_length=1, max_length=MAX_LINES)]


def _patch_model() -> type[BaseModel]:
    """Every InquiryIn field optional; the ones the database requires may not be null."""
    never_null = {"legal_entity_id", "operator_id", "requester_id"}
    optional: dict[str, Any] = {}
    for name, field in InquiryIn.model_fields.items():
        kind = field.annotation
        if name in never_null:
            kind = next(a for a in get_args(kind) if a is not NoneType)
        optional[name] = (Annotated[(kind, *field.metadata)] if field.metadata else kind, None)
    return create_model(
        "InquiryPatch",
        __base__=Strict,
        version=(Annotated[int, Field(ge=1)], ...),
        **optional,
    )


InquiryPatch = _patch_model()


class VersionIn(Strict):
    """Body of take and duplicate."""

    version: int = Field(ge=1)


class CancelIn(VersionIn):
    """Body of cancel: the reason is required."""

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class HistoryOut(BaseModel):
    """One audit entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor: uuid.UUID
    at: datetime
    action: str
    changes: dict[str, dict[str, str | None]]


# --- response models ---------------------------------------------------------------------------


class LineOut(BaseModel):
    """A line with display names and the "not in total" flag (m3 without density)."""

    id: uuid.UUID
    position: int
    product_id: uuid.UUID
    product_name: str
    product_inactive: bool
    quantity: str
    unit: str
    density: str | None
    not_in_total: bool
    spec_notes: str | None
    iso_spec_version_id: uuid.UUID
    iso_spec_version_name: str
    iso_spec_version_inactive: bool


class WarningOut(BaseModel):
    """A non-blocking finding on a field."""

    field: str
    code: str
    message: str


class InquiryOut(BaseModel):
    """The full inquiry with display names, inactive flags, lines and warnings."""

    id: uuid.UUID
    reference: str
    status: str
    version: int
    vessel_id: uuid.UUID
    vessel_name: str
    vessel_inactive: bool
    legal_entity_id: uuid.UUID
    legal_entity_name: str
    legal_entity_inactive: bool
    voyage: str | None
    operator_id: uuid.UUID
    operator_name: str
    buyer_id: uuid.UUID | None
    buyer_name: str | None
    requester_id: uuid.UUID
    requester_name: str
    port_id: uuid.UUID
    port_name: str
    port_locode: str
    port_time_zone: str
    port_inactive: bool
    eta: datetime
    etd: datetime
    agent_name: str | None
    agent_email: str | None
    bunkering_reason_id: uuid.UUID
    bunkering_reason_name: str
    bunkering_reason_inactive: bool
    internal_comments: str | None
    cancel_reason: str | None
    created_at: datetime
    created_by: uuid.UUID
    updated_at: datetime
    lines: list[LineOut]
    warnings: list[WarningOut]


class InquiryListItem(BaseModel):
    """A work-list row."""

    id: uuid.UUID
    reference: str
    status: str
    vessel_name: str
    port_name: str
    port_time_zone: str
    eta: datetime
    buyer_name: str | None
    eta_warning: bool
