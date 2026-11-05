"""Inquiry REST API under /api/v1/inquiries (B2-D12): create, read, list, edit.

Create: admin, bunker buyer, operator. Edit: admin, bunker buyer. Read: every role.
Edits carry the client's `version`; lines are replaced as a set; after Draft only the
EDITABLE_AFTER_DRAFT fields may change. Every change is audited in the same transaction.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Annotated, Any, Literal, NoReturn, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session  # noqa: TC002  (FastAPI runtime)

from nautical_deliverance.api.common import conflict, scope, unprocessable
from nautical_deliverance.api.inquiry_models import (
    CancelIn,
    HistoryOut,
    InquiryIn,
    InquiryListItem,
    InquiryOut,
    InquiryPatch,
    LineIn,
    VersionIn,
)
from nautical_deliverance.api.users import current_user, get_users_engine
from nautical_deliverance.domain.identity import Principal, Role
from nautical_deliverance.domain.inquiry import LOCKED_AFTER_DRAFT, Status, can_transition
from nautical_deliverance.persistence.audit import record_change
from nautical_deliverance.persistence.inquiry_repo import (
    dec,
    detail,
    line_rows,
    line_text,
    list_rows,
    next_reference,
)
from nautical_deliverance.persistence.models import (
    AppUser,
    AuditEntry,
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

    from pydantic import BaseModel
    from sqlalchemy import Row

router = APIRouter(prefix="/inquiries")

ETA_WARNING_WINDOW = timedelta(hours=48)
LOCKED_MESSAGE = "Locked after Draft"
OPERATOR_ROLES = frozenset({Role.OPERATOR, Role.ADMIN})
BUYER_ROLES = frozenset({Role.BUNKER_BUYER, Role.ADMIN})
RFQ_READERS = BUYER_ROLES | {Role.VIEWER}
USER_ROLES = {"operator_id": OPERATOR_ROLES, "buyer_id": BUYER_ROLES}  # requester: any user
MASTER: dict[str, tuple[Any, str]] = {
    "vessel_id": (Vessel, "vessel"),
    "legal_entity_id": (LegalEntity, "legal entity"),
    "port_id": (Port, "port"),
    "bunkering_reason_id": (BunkeringReason, "bunkering reason"),
}

DUPLICATED = (
    "vessel_id",
    "legal_entity_id",
    "voyage",
    "operator_id",
    "requester_id",
    "port_id",
    "agent_name",
    "agent_email",
    "bunkering_reason_id",
)  # fmt: skip  (B2-D10)


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


# --- validation --------------------------------------------------------------------------------


def _reject(field: str, message: str) -> NoReturn:
    raise unprocessable(field, message)


def _check_lines(lines: Sequence[LineIn]) -> None:
    seen: set[uuid.UUID] = set()
    for i, line in enumerate(lines):
        if line.product_id in seen:
            _reject(f"lines[{i}].product_id", "Duplicate product")
        seen.add(line.product_id)


def _check_times(eta: datetime | None, etd: datetime | None) -> None:
    if eta is not None and etd is not None and etd < eta:
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


def _lock_open(session: Session, inquiry_id: uuid.UUID, version: int) -> Inquiry:
    """Load with a row lock; 409 when cancelled or when the client's version is stale."""
    inq = _load(session, inquiry_id, lock=True)
    if inq.status == Status.CANCELLED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Inquiry is cancelled")
    if inq.version != version:
        raise conflict()
    return inq


def _transition(inq: Inquiry, to: Status) -> dict[str, Any]:
    """Return the status values for a move allowed by `can_transition`, else 409 (B2-D9)."""
    if not can_transition(Status(inq.status), to):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Cannot move from {inq.status} to {to.value}"
        )
    return {"status": to.value}


# --- routes ------------------------------------------------------------------------------------


def _eta_warning(state: str, eta: datetime | None, now: datetime) -> bool:
    if eta is None:
        return False
    open_ = state not in (Status.NOMINATED, Status.CANCELLED)
    return open_ and eta < now + ETA_WARNING_WINDOW


def _sees_rfqs(principal: Principal) -> bool:
    """Only RFQ readers may learn who or how many suppliers were contacted (R6)."""
    return bool(RFQ_READERS & principal.roles)


def _out(s: Session, inq: Inquiry, principal: Principal) -> InquiryOut:
    """Return the inquiry record; the RFQ deadline is hidden from the Operator."""
    hide = {} if _sees_rfqs(principal) else {"rfq_deadline": None}
    return InquiryOut(**{**detail(s, inq), **hide})


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
        hide = {} if _sees_rfqs(principal) else {"rfq_total": None, "rfq_sent": None}
        return [
            InquiryListItem(
                **{**r._asdict(), **hide}, eta_warning=_eta_warning(r.status, r.eta, now)
            )
            for r in rows
        ]


@router.get("/{inquiry_id}", response_model=InquiryOut)
def get_inquiry(inquiry_id: uuid.UUID, principal: Reader, engine: Eng) -> object:
    """One inquiry with lines, warnings and display names."""
    with scope(principal, engine) as s:
        return _out(s, _load(s, inquiry_id), principal)


def _create(  # noqa: PLR0913, PLR0917
    s: Session,
    principal: Principal,
    now: datetime,
    body: InquiryIn,
    action: Literal["create", "duplicate"] = "create",
    extra: dict[str, Any] | None = None,
) -> InquiryOut:
    """Validate and insert a Draft with its lines and one audit entry."""
    _check_lines(body.lines)
    _check_times(body.eta, body.etd)
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
        action=action,
        before=None,
        after={
            **values,
            "reference": inq.reference,
            "status": inq.status,
            "lines": texts,
            **(extra or {}),
        },
    )
    return _out(s, inq, principal)


@router.post("", response_model=InquiryOut, status_code=status.HTTP_201_CREATED)
def create_inquiry(body: InquiryIn, principal: Creator, engine: Eng, now: Now) -> object:
    """Create a Draft with the next reference of the month."""
    with scope(principal, engine) as s:
        return _create(s, principal, now, body)


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
        inq = _lock_open(s, inquiry_id, version)
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
            return _out(s, inq, principal)
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
        return _out(s, inq, principal)


def _change(  # noqa: PLR0913, PLR0917
    s: Session,
    principal: Principal,
    now: datetime,
    inq: Inquiry,
    action: Literal["take", "cancel"],
    values: dict[str, Any],
) -> object:
    """Apply a one-step action: set fields, bump the version, write one audit entry."""
    before = {k: getattr(inq, k) for k in values}
    for k, v in values.items():
        setattr(inq, k, v)
    inq.version += 1
    inq.updated_at = now
    s.flush()
    record_change(
        s,
        actor=principal.user_id,
        entity_type="inquiry",
        entity_id=inq.id,
        action=action,
        before=before,
        after=values,
    )
    return _out(s, inq, principal)


@router.post("/{inquiry_id}/take", response_model=InquiryOut)
def take_inquiry(
    inquiry_id: uuid.UUID, body: VersionIn, principal: Editor, engine: Eng, now: Now
) -> object:
    """Make the caller the buyer. Taking your own inquiry again is a no-op."""
    with scope(principal, engine) as s:
        inq = _lock_open(s, inquiry_id, body.version)
        if inq.buyer_id == principal.user_id:
            return _out(s, inq, principal)
        return _change(s, principal, now, inq, "take", {"buyer_id": principal.user_id})


@router.post("/{inquiry_id}/cancel", response_model=InquiryOut)
def cancel_inquiry(
    inquiry_id: uuid.UUID, body: CancelIn, principal: Editor, engine: Eng, now: Now
) -> object:
    """Cancel with a required reason (any open status may be cancelled)."""
    with scope(principal, engine) as s:
        inq = _lock_open(s, inquiry_id, body.version)
        values = {**_transition(inq, Status.CANCELLED), "cancel_reason": body.reason}
        return _change(s, principal, now, inq, "cancel", values)


@router.post("/{inquiry_id}/duplicate", response_model=InquiryOut, status_code=201)
def duplicate_inquiry(
    inquiry_id: uuid.UUID, body: VersionIn, principal: Editor, engine: Eng, now: Now
) -> object:
    """Create a Draft from the B2-D10 fields; ETA/ETD start empty (R5)."""
    with scope(principal, engine) as s:
        src = _load(s, inquiry_id)
        if src.version != body.version:
            raise conflict()
        lines = [
            LineIn(
                product_id=r.InquiryLine.product_id,
                quantity=cast("str", dec(r.InquiryLine.quantity)),
                unit=r.InquiryLine.unit,
                density=dec(r.InquiryLine.density),
                spec_notes=r.InquiryLine.spec_notes,
                iso_spec_version_id=r.InquiryLine.iso_spec_version_id,
            )
            for r in line_rows(s, src.id)
        ]
        copied = {k: getattr(src, k) for k in DUPLICATED}
        new = InquiryIn.model_construct(**copied, eta=None, etd=None, lines=lines)
        return _create(s, principal, now, new, "duplicate", {"duplicate_of": src.reference})


@router.get("/{inquiry_id}/history", response_model=list[HistoryOut])
def inquiry_history(inquiry_id: uuid.UUID, principal: Reader, engine: Eng) -> object:
    """Audit entries of the inquiry, newest first."""
    with scope(principal, engine) as s:
        _load(s, inquiry_id)
        stmt = (
            select(AuditEntry)
            .where(AuditEntry.entity_type == "inquiry", AuditEntry.entity_id == inquiry_id)
            .order_by(AuditEntry.at.desc())  # one entry per transaction, so `at` is unique
        )
        out = [HistoryOut.model_validate(e) for e in s.scalars(stmt)]
        if _sees_rfqs(principal):
            return out
        for e in out:  # the RFQ deadline reveals that suppliers were contacted
            e.changes.pop("rfq_deadline", None)
        return [e for e in out if e.changes]
