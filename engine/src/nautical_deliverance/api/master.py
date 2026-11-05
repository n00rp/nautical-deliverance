"""Versioned master-data REST API under /api/v1/master (B1-D4, D11, D12).

Reads: any known role. Writes: admin only. Records are never deleted, only deactivated.
Every update carries the client's `version` (optimistic concurrency); every change is
audited in the same transaction with the caller as actor.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    create_model,
)
from sqlalchemy import Engine, func, or_, select
from sqlalchemy.orm import Session  # noqa: TC002  (FastAPI runtime)

from nautical_deliverance.api.common import (
    Strict,
    check,
    conflict,
    email_ok,
    scope,
    unprocessable,
)
from nautical_deliverance.api.users import current_user, get_users_engine
from nautical_deliverance.domain.identity import Principal, Role
from nautical_deliverance.domain.master import (
    CounterpartyType,
    Unit,
    imo_valid,
    locode_valid,
    tz_valid,
)
from nautical_deliverance.persistence.audit import Action, record_change
from nautical_deliverance.persistence.master_repo import counterparties_covering
from nautical_deliverance.persistence.models import (
    AuditEntry,
    BunkeringReason,
    Contact,
    Counterparty,
    Coverage,
    IsoSpecVersion,
    LegalEntity,
    Port,
    Product,
    Vessel,
    VesselApprovedFuel,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


router = APIRouter(prefix="/master")

_NOT_FOUND = "Not found"


# The same dependency object as current_user uses, so overriding either covers both.
get_master_engine = get_users_engine


def require_reader(principal: Annotated[Principal, Depends(current_user)]) -> Principal:
    """Any caller with a known role may read."""
    if not principal.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    return principal


def require_admin(principal: Annotated[Principal, Depends(current_user)]) -> Principal:
    """Only admins may write."""
    if Role.ADMIN not in principal.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    return principal


Reader = Annotated[Principal, Depends(require_reader)]
Admin = Annotated[Principal, Depends(require_admin)]
Eng = Annotated[Engine, Depends(get_master_engine)]
ActiveFilter = Annotated[Literal["true", "false", "all"], Query()]


# --- errors ----------------------------------------------------------------------------------


# --- request/response models -----------------------------------------------------------------


_Trim = StringConstraints(strip_whitespace=True, min_length=1)
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Imo = Annotated[str, _Trim, check(imo_valid, "Invalid IMO number")]
Locode = Annotated[str, _Trim, check(locode_valid, "Invalid UN/LOCODE (e.g. NLRTM)")]
TimeZone = Annotated[str, _Trim, check(tz_valid, "Unknown IANA time zone")]
Country = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Z]{2}$")]
Email = Annotated[str, _Trim, check(email_ok, "Invalid e-mail address")]
Dwt = Annotated[int, Field(gt=0, le=2_000_000_000)]


class LegalEntityIn(Strict):
    """Legal entity fields."""

    name: Name
    code: Short


class VesselIn(Strict):
    """Vessel fields."""

    name: Name
    imo: Imo
    vessel_type: Short
    dwt: Dwt
    flag: Short
    legal_entity_id: uuid.UUID
    default_operator: uuid.UUID | None = None


class PortIn(Strict):
    """Port fields."""

    locode: Locode
    name: Name
    country: Country
    time_zone: TimeZone


class CounterpartyIn(Strict):
    """Counterparty fields."""

    name: Name
    type: CounterpartyType
    notes: Note | None = None


class ProductIn(Strict):
    """Product fields."""

    name: Name
    default_unit: Unit = Unit.MT


class NameIn(Strict):
    """Reference data that is just a name (ISO spec versions, bunkering reasons)."""

    name: Name


class ContactIn(Strict):
    """Contact fields."""

    name: Name
    email: Email
    phone: Short | None = None
    is_primary: bool = False


class VersionIn(Strict):
    """Body of deactivate/reactivate."""

    version: int = Field(ge=1)


class CoverageItem(Strict):
    """A port/product pair a counterparty supplies."""

    port_id: uuid.UUID
    product_id: uuid.UUID


class FuelItem(Strict):
    """A product a vessel may take."""

    product_id: uuid.UUID


class CoverageIn(Strict):
    """Replacement coverage set."""

    version: int = Field(ge=1)
    items: list[CoverageItem]


class ApprovedFuelsIn(Strict):
    """Replacement approved-fuel set."""

    version: int = Field(ge=1)
    items: list[FuelItem]


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SetOut(BaseModel):
    """Current set and the parent's version."""

    version: int
    items: list[dict[str, uuid.UUID]]


class HistoryOut(_Out):
    """One audit entry."""

    id: uuid.UUID
    actor: uuid.UUID
    at: datetime
    action: str
    changes: dict[str, dict[str, str | None]]
    entity: str | None = None  # label of a related record (e.g. "Contact Ann"); None = this record


class SuggestOut(BaseModel):
    """Suppliers covering all, or only some, of the requested products."""

    all: list[Any]
    some: list[Any]


def _out(name: str, inp: type[BaseModel]) -> type[BaseModel]:
    """Response model: the writable fields plus id, active, version and timestamps."""
    extra: dict[str, Any] = {
        "id": (uuid.UUID, ...),
        "active": (bool, ...),
        "version": (int, ...),
        "created_at": (datetime, ...),
        "updated_at": (datetime, ...),
    }
    fields: dict[str, Any] = {k: (f.annotation, ...) for k, f in inp.model_fields.items()}
    return create_model(f"{name}Out", __base__=_Out, **fields, **extra)


def _patch(name: str, inp: type[BaseModel]) -> type[BaseModel]:
    """Partial-update model: every field optional (but never null unless nullable)."""
    optional: dict[str, Any] = {
        k: (Annotated[(f.annotation, *f.metadata)] if f.metadata else f.annotation, None)
        for k, f in inp.model_fields.items()
    }
    return create_model(
        f"{name}Patch",
        __base__=Strict,
        version=(Annotated[int, Field(ge=1)], ...),
        **optional,
    )


def _split(body: BaseModel) -> tuple[dict[str, Any], int]:
    """Split a PATCH body into the fields the client sent and its version."""
    sent = {k: getattr(body, k) for k in body.model_fields_set if k != "version"}
    return sent, body.version  # type: ignore[attr-defined]


# --- generic mutation helpers ------------------------------------------------------------------


def _load(session: Session, model: type, item_id: uuid.UUID, *, lock: bool = False) -> Any:  # noqa: ANN401
    row = session.get(model, item_id, with_for_update=lock)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    return row


def _bump(row: Any) -> None:  # noqa: ANN401
    row.version += 1
    row.updated_at = func.now()


def _apply(  # noqa: PLR0913, PLR0917
    session: Session,
    principal: Principal,
    entity: str,
    row: Any,  # noqa: ANN401
    values: dict[str, Any],
    action: Action,
    version: int,
) -> None:
    """Check the version, apply changed values, bump, audit. No-op when nothing differs."""
    if row.version != version:
        raise conflict()
    changed = {k: v for k, v in values.items() if getattr(row, k) != v}
    if not changed:
        return
    before = {k: getattr(row, k) for k in changed}
    for k, v in changed.items():
        setattr(row, k, v)
    _bump(row)
    session.flush()
    session.refresh(row)
    record_change(
        session,
        actor=principal.user_id,
        entity_type=entity,
        entity_id=row.id,
        action=action,
        before=before,
        after=changed,
    )


def _create(
    session: Session,
    principal: Principal,
    entity: str,
    model: type,
    data: dict[str, Any],
) -> Any:  # noqa: ANN401
    row = model(organization_id=principal.organization_id, **data)
    session.add(row)
    session.flush()
    session.refresh(row)
    record_change(
        session,
        actor=principal.user_id,
        entity_type=entity,
        entity_id=row.id,
        action="create",
        before=None,
        after={**data, "active": True},
    )
    return row


def _listing(
    session: Session,
    model: Any,  # noqa: ANN401
    active: str,
    q: str | None,
    search: Sequence[str],
) -> Sequence[Any]:
    # ponytail: unpaginated; add limit/offset when a list outgrows a screenful.
    stmt = select(model).order_by(model.name if hasattr(model, "name") else model.id, model.id)
    if active != "all":
        stmt = stmt.where(model.active == (active == "true"))
    if q:
        stmt = stmt.where(or_(*(getattr(model, c).icontains(q, autoescape=True) for c in search)))
    return session.scalars(stmt).all()


# --- the seven master types --------------------------------------------------------------------


@dataclass(frozen=True)
class _Spec:
    path: str
    entity: str
    model: type
    inp: type[BaseModel]
    search: tuple[str, ...]


SPECS = (
    _Spec("legal-entities", "legal_entity", LegalEntity, LegalEntityIn, ("name", "code")),
    _Spec("vessels", "vessel", Vessel, VesselIn, ("name", "imo", "flag", "vessel_type")),
    _Spec("ports", "port", Port, PortIn, ("name", "locode", "country")),
    _Spec("counterparties", "counterparty", Counterparty, CounterpartyIn, ("name",)),
    _Spec("products", "product", Product, ProductIn, ("name",)),
    _Spec("iso-spec-versions", "iso_spec_version", IsoSpecVersion, NameIn, ("name",)),
    _Spec("bunkering-reasons", "bunkering_reason", BunkeringReason, NameIn, ("name",)),
)
OUTS = {s.path: _out(s.entity.title().replace("_", ""), s.inp) for s in SPECS}
ContactOut = _out("Contact", ContactIn)
_ContactPatch = _patch("Contact", ContactIn)


def _register(spec: _Spec) -> None:
    path, entity, model = spec.path, spec.entity, spec.model
    out = OUTS[path]
    patch = _patch(entity.title().replace("_", ""), spec.inp)
    fields = tuple(spec.inp.model_fields)
    inp = spec.inp

    @router.get(f"/{path}", response_model=list[out])  # type: ignore[valid-type]
    def list_items(
        principal: Reader, engine: Eng, active: ActiveFilter = "true", q: str | None = None
    ) -> object:
        with scope(principal, engine) as s:
            return [out.model_validate(r) for r in _listing(s, model, active, q, spec.search)]

    @router.get(f"/{path}/{{item_id}}", response_model=out)
    def get_item(item_id: uuid.UUID, principal: Reader, engine: Eng) -> object:
        with scope(principal, engine) as s:
            return out.model_validate(_load(s, model, item_id))

    @router.post(f"/{path}", response_model=out, status_code=status.HTTP_201_CREATED)
    def create_item(body: inp, principal: Admin, engine: Eng) -> object:  # type: ignore[valid-type]
        with scope(principal, engine) as s:
            data = {k: getattr(body, k) for k in fields}
            return out.model_validate(_create(s, principal, entity, model, data))

    @router.patch(f"/{path}/{{item_id}}", response_model=out)
    def update_item(
        item_id: uuid.UUID,
        body: patch,  # type: ignore[valid-type]
        principal: Admin,
        engine: Eng,
    ) -> object:
        with scope(principal, engine) as s:
            row = _load(s, model, item_id, lock=True)
            values, version = _split(body)
            _apply(s, principal, entity, row, values, "update", version)
            return out.model_validate(row)

    _lifecycle(f"/{path}/{{item_id}}/deactivate", out, entity, model, "deactivate")
    _lifecycle(f"/{path}/{{item_id}}/reactivate", out, entity, model, "reactivate")

    @router.get(f"/{path}/{{item_id}}/history", response_model=list[HistoryOut])
    def history(item_id: uuid.UUID, principal: Reader, engine: Eng) -> object:
        with scope(principal, engine) as s:
            _load(s, model, item_id)
            own = (AuditEntry.entity_type == entity) & (AuditEntry.entity_id == item_id)
            if entity == "counterparty":  # B1-D6: its contacts' changes show here too
                own = own | (Contact.counterparty_id == item_id)
            stmt = (
                select(AuditEntry, Contact.name)
                .outerjoin(
                    Contact,
                    (AuditEntry.entity_type == "contact") & (AuditEntry.entity_id == Contact.id),
                )
                .where(own)
                .order_by(AuditEntry.at.desc(), AuditEntry.id)
            )
            return [
                HistoryOut.model_validate(e).model_copy(
                    update={"entity": f"Contact {name}" if name else None}
                )
                for e, name in s.execute(stmt)
            ]


def _lifecycle(url: str, out: type[BaseModel], entity: str, model: type, action: Action) -> None:
    active = action == "reactivate"

    @router.post(url, response_model=out, name=f"{action}_{entity}")
    def change(item_id: uuid.UUID, body: VersionIn, principal: Admin, engine: Eng) -> object:
        with scope(principal, engine) as s:
            row = _load(s, model, item_id, lock=True)
            _apply(s, principal, entity, row, {"active": active}, action, body.version)
            return out.model_validate(row)


# Registered before /counterparties/{item_id} so "suggest" is not read as an id.
@router.get("/counterparties/suggest", response_model=SuggestOut)
def suggest(
    port_id: uuid.UUID,
    product_id: Annotated[list[uuid.UUID], Query(min_length=1)],
    principal: Reader,
    engine: Eng,
) -> object:
    """Active suppliers at the port covering all, or only some, of the products."""
    out = OUTS["counterparties"]
    with scope(principal, engine) as s:
        return {
            mode: [
                out.model_validate(c)
                for c in counterparties_covering(s, port_id, product_id, mode=mode)
            ]
            for mode in ("all", "some")
        }


for _spec in SPECS:
    _register(_spec)


# --- contacts ----------------------------------------------------------------------------------

CONTACTS = "/counterparties/{item_id}/contacts"


def _contact(
    session: Session, cp_id: uuid.UUID, contact_id: uuid.UUID, *, lock: bool = False
) -> Any:  # noqa: ANN401
    _load(session, Counterparty, cp_id)
    row = _load(session, Contact, contact_id, lock=lock)
    if row.counterparty_id != cp_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    return row


@router.get(CONTACTS, response_model=list[ContactOut])  # type: ignore[valid-type]
def list_contacts(
    item_id: uuid.UUID, principal: Reader, engine: Eng, active: ActiveFilter = "true"
) -> object:
    """Contacts of one counterparty."""
    with scope(principal, engine) as s:
        _load(s, Counterparty, item_id)
        stmt = (
            select(Contact)
            .where(Contact.counterparty_id == item_id)
            .order_by(Contact.name, Contact.id)
        )
        if active != "all":
            stmt = stmt.where(Contact.active == (active == "true"))
        return [ContactOut.model_validate(c) for c in s.scalars(stmt)]


@router.get(CONTACTS + "/{contact_id}", response_model=ContactOut)
def get_contact(
    item_id: uuid.UUID, contact_id: uuid.UUID, principal: Reader, engine: Eng
) -> object:
    """One contact."""
    with scope(principal, engine) as s:
        return ContactOut.model_validate(_contact(s, item_id, contact_id))


@router.post(CONTACTS, response_model=ContactOut, status_code=status.HTTP_201_CREATED)
def create_contact(item_id: uuid.UUID, body: ContactIn, principal: Admin, engine: Eng) -> object:
    """Add a contact."""
    with scope(principal, engine) as s:
        _load(s, Counterparty, item_id)
        data = {k: getattr(body, k) for k in ContactIn.model_fields}
        row = _create(s, principal, "contact", Contact, {**data, "counterparty_id": item_id})
        return ContactOut.model_validate(row)


@router.patch(CONTACTS + "/{contact_id}", response_model=ContactOut)
def update_contact(
    item_id: uuid.UUID,
    contact_id: uuid.UUID,
    body: _ContactPatch,  # type: ignore[valid-type]
    principal: Admin,
    engine: Eng,
) -> object:
    """Change a contact."""
    with scope(principal, engine) as s:
        row = _contact(s, item_id, contact_id, lock=True)
        values, version = _split(body)
        _apply(s, principal, "contact", row, values, "update", version)
        return ContactOut.model_validate(row)


def _contact_lifecycle(verb: Literal["deactivate", "reactivate"]) -> None:
    active = verb == "reactivate"

    @router.post(
        CONTACTS + f"/{{contact_id}}/{verb}", response_model=ContactOut, name=f"{verb}_contact"
    )
    def change(
        item_id: uuid.UUID, contact_id: uuid.UUID, body: VersionIn, principal: Admin, engine: Eng
    ) -> object:
        with scope(principal, engine) as s:
            row = _contact(s, item_id, contact_id, lock=True)
            _apply(s, principal, "contact", row, {"active": active}, verb, body.version)
            return ContactOut.model_validate(row)


_contact_lifecycle("deactivate")
_contact_lifecycle("reactivate")


# --- replace-the-set children: coverage, approved fuels ----------------------------------------


def _replace_set(  # noqa: PLR0913, PLR0917
    session: Session,
    principal: Principal,
    parent: Any,  # noqa: ANN401
    parent_entity: str,
    child: Any,  # noqa: ANN401
    parent_col: str,
    key_cols: tuple[str, ...],
    items: Sequence[BaseModel],
    version: int,
) -> None:
    """Make the active children equal `items`; reactivate before inserting; audit once."""
    if parent.version != version:
        raise conflict()
    wanted = [tuple(getattr(i, c) for c in key_cols) for i in items]
    if len(set(wanted)) != len(wanted):
        raise unprocessable("items", "Duplicate entries")  # noqa: EM101
    wanted_set = set(wanted)
    existing = {
        tuple(getattr(r, c) for c in key_cols): r
        for r in session.scalars(select(child).where(getattr(child, parent_col) == parent.id))
    }
    current = {k for k, r in existing.items() if r.active}
    if current == wanted_set:
        return
    for key, row in existing.items():
        if row.active != (key in wanted_set):
            row.active = key in wanted_set
            _bump(row)
    for key in wanted_set - existing.keys():
        session.add(
            child(
                organization_id=principal.organization_id,
                **{parent_col: parent.id},
                **dict(zip(key_cols, key, strict=True)),
            )
        )
    _bump(parent)
    session.flush()  # surfaces unknown/foreign parents as constraint violations
    session.refresh(parent)
    label = "coverage" if child is Coverage else "approved_fuels"

    def as_text(keys: set[tuple[Any, ...]]) -> set[str]:
        return {":".join(map(str, k)) for k in keys}

    record_change(
        session,
        actor=principal.user_id,
        entity_type=parent_entity,
        entity_id=parent.id,
        action="update",
        before={label: as_text(current)},
        after={label: as_text(wanted_set)},
    )


def _current_set(
    session: Session,
    parent: Any,  # noqa: ANN401
    child: Any,  # noqa: ANN401
    parent_col: str,
    key_cols: tuple[str, ...],
) -> dict[str, Any]:
    rows = session.scalars(
        select(child)
        .where(getattr(child, parent_col) == parent.id, child.active)
        .order_by(*(getattr(child, c) for c in key_cols))
    )
    return {
        "version": parent.version,
        "items": [{c: getattr(r, c) for c in key_cols} for r in rows],
    }


@dataclass(frozen=True)
class _SetSpec:
    url: str
    parent_model: type
    parent_entity: str
    child: type
    parent_col: str
    key_cols: tuple[str, ...]
    body: type[BaseModel]


def _register_set(spec: _SetSpec) -> None:
    @router.get(spec.url, response_model=SetOut, name=f"get_{spec.url.rsplit('/', 1)[1]}")
    def read(item_id: uuid.UUID, principal: Reader, engine: Eng) -> object:
        with scope(principal, engine) as s:
            parent = _load(s, spec.parent_model, item_id)
            return _current_set(s, parent, spec.child, spec.parent_col, spec.key_cols)

    @router.put(spec.url, response_model=SetOut, name=f"put_{spec.url.rsplit('/', 1)[1]}")
    def replace(
        item_id: uuid.UUID,
        body: spec.body,  # type: ignore[name-defined]
        principal: Admin,
        engine: Eng,
    ) -> object:
        with scope(principal, engine) as s:
            parent = _load(s, spec.parent_model, item_id, lock=True)
            _replace_set(
                s,
                principal,
                parent,
                spec.parent_entity,
                spec.child,
                spec.parent_col,
                spec.key_cols,
                body.items,
                body.version,
            )
            return _current_set(s, parent, spec.child, spec.parent_col, spec.key_cols)


_register_set(
    _SetSpec(
        "/counterparties/{item_id}/coverage",
        Counterparty,
        "counterparty",
        Coverage,
        "counterparty_id",
        ("port_id", "product_id"),
        CoverageIn,
    )
)
_register_set(
    _SetSpec(
        "/vessels/{item_id}/approved-fuels",
        Vessel,
        "vessel",
        VesselApprovedFuel,
        "vessel_id",
        ("product_id",),
        ApprovedFuelsIn,
    )
)
