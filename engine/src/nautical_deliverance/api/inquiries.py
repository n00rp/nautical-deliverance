"""Inquiry REST API under /api/v1/inquiries (B2-D12): create, read, list, edit.

Create: admin, bunker buyer, operator. Edit: admin, bunker buyer. Read: every role.
Edits carry the client's `version`; lines are replaced as a set; after Draft only the
EDITABLE_AFTER_DRAFT fields may change. Every change is audited in the same transaction.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import NoneType
from typing import TYPE_CHECKING, Annotated, Any, Literal, NoReturn, cast, get_args

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    StringConstraints,
    ValidationInfo,
    create_model,
    field_validator,
)
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session  # noqa: TC002  (FastAPI runtime)

from nautical_deliverance.api.common import Strict, check, conflict, email_ok, scope, unprocessable
from nautical_deliverance.api.users import current_user, get_users_engine
from nautical_deliverance.domain.identity import Principal, Role
from nautical_deliverance.domain.inquiry import (
    DENSITY_MAX,
    DENSITY_MIN,
    LOCKED_AFTER_DRAFT,
    MAX_LINES,
    LineUnit,
    Status,
)
from nautical_deliverance.persistence.audit import record_change
from nautical_deliverance.persistence.inquiry_repo import (
    detail,
    line_rows,
    line_text,
    list_rows,
    next_reference,
)
from nautical_deliverance.persistence.models import (
    AppUser,
    BunkeringReason,
    Inquiry,
    InquiryLine,
    IsoSpecVersion,
    LegalEntity,
    Port,
    Product,
    Vessel,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy import Row

router = APIRouter(prefix="/inquiries")

ETA_WARNING_WINDOW = timedelta(hours=48)
LOCKED_MESSAGE = "Locked after Draft"
OPERATOR_ROLES = frozenset({Role.OPERATOR, Role.ADMIN})
BUYER_ROLES = frozenset({Role.BUNKER_BUYER, Role.ADMIN})
USER_ROLES = {"operator_id": OPERATOR_ROLES, "buyer_id": BUYER_ROLES}  # requester: any user
MASTER: dict[str, tuple[Any, str]] = {
    "vessel_id": (Vessel, "vessel"),
    "legal_entity_id": (LegalEntity, "legal entity"),
    "port_id": (Port, "port"),
    "bunkering_reason_id": (BunkeringReason, "bunkering reason"),
}
QUANTITY = re.compile(r"[0-9]{1,9}(\.[0-9]{1,3})?")  # numeric(12,3)
DENSITY = re.compile(r"[0-9]{1,4}(\.[0-9])?")  # numeric(6,1)


def get_now() -> datetime:
    """Return the clock (overridable in tests): references follow its UTC month."""
    return datetime.now(UTC)


def _allow(*roles: Role) -> Callable[..., Principal]:
    def dependency(principal: Annotated[Principal, Depends(current_user)]) -> Principal:
        if not principal.roles & set(roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
        return principal

    return dependency


Reader = Annotated[Principal, Depends(_allow(*Role))]
Creator = Annotated[Principal, Depends(_allow(Role.ADMIN, Role.BUNKER_BUYER, Role.OPERATOR))]
Editor = Annotated[Principal, Depends(_allow(Role.ADMIN, Role.BUNKER_BUYER))]
Eng = Annotated[Engine, Depends(get_users_engine)]
Now = Annotated[datetime, Depends(get_now)]

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


# --- validation --------------------------------------------------------------------------------


def _reject(field: str, message: str) -> NoReturn:
    raise unprocessable(field, message)


def _check_lines(lines: Sequence[LineIn]) -> None:
    seen: set[uuid.UUID] = set()
    for i, line in enumerate(lines):
        if line.product_id in seen:
            _reject(f"lines[{i}].product_id", "Duplicate product")
        seen.add(line.product_id)


def _check_times(eta: datetime, etd: datetime) -> None:
    if etd < eta:
        _reject("etd", "ETD must not be before ETA")


def _check_refs(session: Session, values: dict[str, Any]) -> None:
    """Master data must exist and be active; users must exist and hold the needed role."""
    for field, (model, noun) in MASTER.items():
        if field in values:
            row = session.get(model, values[field])
            if row is None:
                _reject(field, f"Unknown {noun}")
            if not row.active:
                _reject(field, f"Inactive {noun}")
    for field in ("operator_id", "buyer_id", "requester_id"):
        if values.get(field) is None:
            continue
        user = session.get(AppUser, values[field])
        if user is None:
            _reject(field, "Unknown user")
        needed = USER_ROLES.get(field)
        if needed and not needed & set(user.roles):
            _reject(field, "Needs the " + " or ".join(sorted(needed)) + " role")


def _resolve_lines(
    session: Session, lines: Sequence[LineIn], current: Sequence[Row[Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate references and return InquiryLine values plus their audit texts.

    A product or ISO version the inquiry already uses may stay even if now inactive.
    """
    product_ids = {line.product_id for line in lines}
    iso_ids = {line.iso_spec_version_id for line in lines}
    products = {
        p.id: p for p in session.scalars(select(Product).where(Product.id.in_(product_ids)))
    }
    isos = {
        i.id: i
        for i in session.scalars(select(IsoSpecVersion).where(IsoSpecVersion.id.in_(iso_ids)))
    }
    kept = {
        "product_id": {r.InquiryLine.product_id for r in current},
        "iso_spec_version_id": {r.InquiryLine.iso_spec_version_id for r in current},
    }
    rows: list[dict[str, Any]] = []
    problems: list[dict[str, str]] = []
    for i, line in enumerate(lines):
        for field, found in (("product_id", products), ("iso_spec_version_id", isos)):
            ident = getattr(line, field)
            if ident not in found:
                problems.append({"field": f"lines[{i}].{field}", "message": "Unknown reference"})
            elif not found[ident].active and ident not in kept[field]:
                problems.append({"field": f"lines[{i}].{field}", "message": "Inactive reference"})
        rows.append(
            {
                "position": i + 1,
                "product_id": line.product_id,
                "quantity": Decimal(line.quantity),
                "unit": line.unit,
                "density": None if line.density is None else Decimal(line.density),
                "spec_notes": line.spec_notes,
                "iso_spec_version_id": line.iso_spec_version_id,
            }
        )
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problems)
    texts = [
        line_text(
            products[r["product_id"]].name,
            r["quantity"],
            r["unit"],
            r["density"],
            isos[r["iso_spec_version_id"]].name,
            r["spec_notes"],
        )
        for r in rows
    ]
    return rows, texts


def _default_operator(session: Session, vessel: Vessel, principal: Principal) -> uuid.UUID:
    """Return the vessel's default operator (an operator/admin of the org), else the caller."""
    if vessel.default_operator is not None:
        user = session.get(AppUser, vessel.default_operator)
        if user is not None and OPERATOR_ROLES & set(user.roles):
            return vessel.default_operator
    if Role.OPERATOR in principal.roles:
        return principal.user_id
    _reject("operator_id", "Required: the vessel has no default operator")


def _load(session: Session, inquiry_id: uuid.UUID, *, lock: bool = False) -> Inquiry:
    inq = session.get(Inquiry, inquiry_id, with_for_update=lock)
    if inq is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return inq


# --- routes ------------------------------------------------------------------------------------


def _eta_warning(state: str, eta: datetime, now: datetime) -> bool:
    open_ = state not in (Status.NOMINATED, Status.CANCELLED)
    return open_ and now <= eta < now + ETA_WARNING_WINDOW


@router.get("", response_model=list[InquiryListItem])
def list_inquiries(  # noqa: PLR0913, PLR0917
    principal: Reader,
    engine: Eng,
    now: Now,
    state: Annotated[str | None, Query(alias="status")] = None,
    q: str | None = None,
    mine: bool = False,  # noqa: FBT001, FBT002
    sort: Literal["eta", "reference"] = "eta",
) -> object:
    """Work list: all but cancelled by default, `status=all` for everything."""
    if state not in (None, "all", *(s.value for s in Status)):
        _reject("status", "Unknown status")
    buyer = principal.user_id if mine else None
    with scope(principal, engine) as s:
        rows = list_rows(s, status=state, q=q, buyer=buyer, sort=sort)
        return [
            InquiryListItem(**r._asdict(), eta_warning=_eta_warning(r.status, r.eta, now))
            for r in rows
        ]


@router.get("/{inquiry_id}", response_model=InquiryOut)
def get_inquiry(inquiry_id: uuid.UUID, principal: Reader, engine: Eng) -> object:
    """One inquiry with lines, warnings and display names."""
    with scope(principal, engine) as s:
        return InquiryOut(**detail(s, _load(s, inquiry_id)))


@router.post("", response_model=InquiryOut, status_code=status.HTTP_201_CREATED)
def create_inquiry(body: InquiryIn, principal: Creator, engine: Eng, now: Now) -> object:
    """Create a Draft with the next reference of the month."""
    _check_lines(body.lines)
    _check_times(body.eta, body.etd)
    with scope(principal, engine) as s:
        vessel = s.get(Vessel, body.vessel_id)
        if vessel is None:
            _reject("vessel_id", "Unknown vessel")
        values = {k: getattr(body, k) for k in InquiryIn.model_fields if k != "lines"}
        values["legal_entity_id"] = body.legal_entity_id or vessel.legal_entity_id
        values["operator_id"] = body.operator_id or _default_operator(s, vessel, principal)
        values["requester_id"] = body.requester_id or principal.user_id
        if "buyer_id" not in body.model_fields_set:
            is_buyer = bool(BUYER_ROLES & principal.roles)
            values["buyer_id"] = principal.user_id if is_buyer else None
        _check_refs(s, values)
        line_values, texts = _resolve_lines(s, body.lines, ())
        inq = Inquiry(
            id=uuid.uuid4(),
            organization_id=principal.organization_id,
            reference=next_reference(s, principal.organization_id, now),
            status=Status.DRAFT.value,
            created_by=principal.user_id,
            created_at=now,
            updated_at=now,
            **values,
        )
        s.add(inq)
        s.flush()
        s.add_all(
            InquiryLine(organization_id=inq.organization_id, inquiry_id=inq.id, **v)
            for v in line_values
        )
        s.flush()
        record_change(
            s,
            actor=principal.user_id,
            entity_type="inquiry",
            entity_id=inq.id,
            action="create",
            before=None,
            after={**values, "reference": inq.reference, "status": inq.status, "lines": texts},
        )
        return InquiryOut(**detail(s, inq))


@router.patch("/{inquiry_id}", response_model=InquiryOut)
def update_inquiry(
    inquiry_id: uuid.UUID,
    body: InquiryPatch,  # type: ignore[valid-type]
    principal: Editor,
    engine: Eng,
    now: Now,
) -> object:
    """Partial update; lines (if sent) replace the whole set. A no-op writes nothing."""
    form = cast("BaseModel", body)
    sent = {k: getattr(form, k) for k in form.model_fields_set}
    version = sent.pop("version")
    with scope(principal, engine) as s:
        inq = _load(s, inquiry_id, lock=True)
        if inq.status == Status.CANCELLED:
            raise HTTPException(status.HTTP_409_CONFLICT, "Inquiry is cancelled")
        if inq.version != version:
            raise conflict()
        changed = {k: v for k, v in sent.items() if k != "lines" and getattr(inq, k) != v}
        current = line_rows(s, inq.id)
        old_texts = [
            line_text(r.product_name, r.InquiryLine.quantity, r.InquiryLine.unit,
                      r.InquiryLine.density, r.iso_name, r.InquiryLine.spec_notes)
            for r in current
        ]  # fmt: skip
        new_lines: list[dict[str, Any]] = []
        if "lines" in sent:
            _check_lines(sent["lines"])
            new_lines, texts = _resolve_lines(s, sent["lines"], current)
            if texts != old_texts:
                changed["lines"] = texts
        if not changed:
            return InquiryOut(**detail(s, inq))
        locked = [k for k in changed if k in LOCKED_AFTER_DRAFT]
        if inq.status != Status.DRAFT and locked:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                [{"field": k, "message": LOCKED_MESSAGE} for k in locked],
            )
        _check_refs(s, changed)
        _check_times(changed.get("eta", inq.eta), changed.get("etd", inq.etd))
        before = {k: old_texts if k == "lines" else getattr(inq, k) for k in changed}
        for k, v in changed.items():
            if k != "lines":
                setattr(inq, k, v)
        inq.version += 1
        inq.updated_at = now
        if "lines" in changed:
            s.execute(delete(InquiryLine).where(InquiryLine.inquiry_id == inq.id))
            s.add_all(
                InquiryLine(organization_id=inq.organization_id, inquiry_id=inq.id, **v)
                for v in new_lines
            )
        s.flush()
        record_change(
            s,
            actor=principal.user_id,
            entity_type="inquiry",
            entity_id=inq.id,
            action="update",
            before=before,
            after=changed,
        )
        return InquiryOut(**detail(s, inq))
