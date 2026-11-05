"""Inquiry API: create, read, list, edit; references, edit lock, warnings, audit, work list."""

import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text, update

from nautical_deliverance.api.auth import get_principal
from nautical_deliverance.api.inquiries import get_now
from nautical_deliverance.api.inquiry_models import InquiryPatch
from nautical_deliverance.api.users import get_users_engine
from nautical_deliverance.domain.identity import Principal, Role
from nautical_deliverance.domain.inquiry import PATCHABLE_FIELDS
from nautical_deliverance.main import create_app
from nautical_deliverance.persistence.db import org_session
from nautical_deliverance.persistence.models import (
    AppUser,
    AuditEntry,
    BunkeringReason,
    Inquiry,
    IsoSpecVersion,
    LegalEntity,
    Port,
    Product,
    Vessel,
    VesselApprovedFuel,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from nautical_deliverance.settings import Settings

type Json = Any

OK, CREATED, FORBIDDEN, NOT_FOUND, CONFLICT, UNPROCESSABLE = (
    HTTPStatus.OK,
    HTTPStatus.CREATED,
    HTTPStatus.FORBIDDEN,
    HTTPStatus.NOT_FOUND,
    HTTPStatus.CONFLICT,
    HTTPStatus.UNPROCESSABLE_ENTITY,
)
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
URL = "/api/v1/inquiries"
LOCKED = "Locked after Draft"
PERF_BUDGET_S = 0.3


def _imo(six: str) -> str:
    """Imo."""
    weighted = sum(int(d) * w for d, w in zip(six, range(7, 1, -1), strict=True))
    return f"{six}{weighted % 10}"


def _add(session: Any, model: type, **kw: Any) -> uuid.UUID:  # noqa: ANN401
    """Add."""
    kw.setdefault("id", uuid.uuid4())
    session.add(model(**kw))
    ident: uuid.UUID = kw["id"]
    return ident


def make_world(engine: Engine, name: str = "") -> SimpleNamespace:
    """Build a fresh organization with master data and one user per role."""
    org = uuid.uuid4()
    w = SimpleNamespace(org=org)
    with org_session(org, engine) as s:
        s.execute(text("INSERT INTO organization (id, name) VALUES (:o, 'o')"), {"o": org})
        w.users = {}
        for role in Role:
            uid = uuid.uuid4()
            who = f"{name}{role.value}"
            _add(
                s,
                AppUser,
                id=uid,
                organization_id=org,
                last_seen_at=NOW,
                name=f"User {who}",
                email=f"{who}@x.example",
                roles=[role.value],
            )
            w.users[role] = Principal(
                uid, org, frozenset({role}), f"User {who}", f"{who}@x.example"
            )
        w.le, w.le2 = (_add(s, LegalEntity, organization_id=org, name=n, code=n) for n in "AB")
        w.reason, w.reason2 = (
            _add(s, BunkeringReason, organization_id=org, name=n) for n in ("Voyage", "Dry dock")
        )
        w.iso = _add(s, IsoSpecVersion, organization_id=org, name="ISO 8217:2024")
        w.port = _add(
            s,
            Port,
            organization_id=org,
            locode="NLRTM",
            name="Rotterdam",
            country="NL",
            time_zone="Europe/Amsterdam",
        )
        w.port2 = _add(
            s,
            Port,
            organization_id=org,
            locode="SGSIN",
            name="Singapore",
            country="SG",
            time_zone="Asia/Singapore",
        )
        w.hsfo, w.mgo = (_add(s, Product, organization_id=org, name=n) for n in ("HSFO", "MGO"))
        w.many = [_add(s, Product, organization_id=org, name=f"P{i}") for i in range(10)]
        w.v1 = _add(
            s, Vessel, organization_id=org, name="Vessel A", imo=_imo("907472"),
            vessel_type="t", dwt=1, flag="PA", legal_entity_id=w.le,
        )  # fmt: skip
        w.v2 = _add(
            s, Vessel, organization_id=org, name="Vessel B", imo=_imo("907473"),
            vessel_type="t", dwt=1, flag="PA", legal_entity_id=w.le2,
            default_operator=w.users[Role.OPERATOR].user_id,
        )  # fmt: skip
        w.v3 = _add(  # default operator that is not a user of the org
            s, Vessel, organization_id=org, name="Vessel C", imo=_imo("907474"),
            vessel_type="t", dwt=1, flag="PA", legal_entity_id=w.le, default_operator=uuid.uuid4(),
        )  # fmt: skip
        s.flush()
        _add(s, VesselApprovedFuel, organization_id=org, vessel_id=w.v1, product_id=w.hsfo)
        _add(s, VesselApprovedFuel, organization_id=org, vessel_id=w.v2, product_id=w.mgo)
    return w


class Client:
    """The app acting as one principal of one world, with an injectable clock."""

    def __init__(
        self,
        settings: Settings,
        engine: Engine,
        w: SimpleNamespace,
        role: Role = Role.ADMIN,
    ) -> None:
        """Build the client."""
        self.w, self.engine, self.now = w, engine, NOW
        self.principal: Principal = w.users[role]
        app = create_app(settings)
        app.dependency_overrides[get_principal] = lambda: self.principal
        app.dependency_overrides[get_users_engine] = lambda: engine
        app.dependency_overrides[get_now] = lambda: self.now
        self.http = TestClient(app)

    def create(self, **over: Any) -> Json:  # noqa: ANN401
        """Create."""
        r = self.http.post(URL, json=body(self.w, **over))
        assert r.status_code == CREATED, r.text
        return r.json()

    def patch(self, inq: Json, **over: Any) -> Json:  # noqa: ANN401
        """Patch."""
        r = self.http.patch(f"{URL}/{inq['id']}", json={"version": inq["version"], **over})
        assert r.status_code == OK, r.text
        return r.json()

    def get(self, inq_id: str) -> Json:
        """Get."""
        r = self.http.get(f"{URL}/{inq_id}")
        assert r.status_code == OK, r.text
        return r.json()

    def listing(self, **params: str) -> list[Json]:
        """List the work list."""
        r = self.http.get(URL, params=params)
        assert r.status_code == OK, r.text
        rows: list[Json] = r.json()
        return rows

    def entries(self, inq_id: str) -> list[AuditEntry]:
        """Entries."""
        with org_session(self.w.org, self.engine) as s:
            rows = s.scalars(
                select(AuditEntry)
                .where(AuditEntry.entity_id == uuid.UUID(inq_id))
                .order_by(AuditEntry.at)
            ).all()
            s.expunge_all()
            return list(rows)

    def set_status(self, inq_id: str, status: str) -> None:
        """Move an inquiry directly in the database (B2 has no API path to these states)."""
        reason = "because" if status == "cancelled" else None
        with org_session(self.w.org, self.engine) as s:
            s.execute(
                update(Inquiry)
                .where(Inquiry.id == uuid.UUID(inq_id))
                .values(status=status, cancel_reason=reason)
            )


def line(w: SimpleNamespace, **over: Any) -> dict[str, Any]:  # noqa: ANN401
    """Line."""
    return {
        "product_id": str(w.hsfo),
        "quantity": "500",
        "unit": "mt",
        "iso_spec_version_id": str(w.iso),
    } | over


def body(w: SimpleNamespace, **over: Any) -> dict[str, Any]:  # noqa: ANN401
    """Body."""
    return {
        "vessel_id": str(w.v1),
        "operator_id": str(w.users[Role.OPERATOR].user_id),
        "port_id": str(w.port),
        "eta": "2026-11-20T08:00:00Z",
        "etd": "2026-11-21T08:00:00Z",
        "bunkering_reason_id": str(w.reason),
        "lines": [line(w)],
    } | over


def errors(r: Any) -> dict[str, str]:  # noqa: ANN401
    """Errors."""
    assert r.status_code == UNPROCESSABLE, r.text
    return {e["field"]: e["message"] for e in r.json()["detail"]}


@pytest.fixture
def world(app_engine: Engine) -> SimpleNamespace:
    """World."""
    return make_world(app_engine)


@pytest.fixture
def admin(settings: Settings, app_engine: Engine, world: SimpleNamespace) -> Client:
    """Admin."""
    return Client(settings, app_engine, world)


# --- B2-R02: constraints ------------------------------------------------------------------------

BAD = [
    ("lines[0].quantity", {"quantity": "0"}),
    ("lines[0].quantity", {"quantity": "abc"}),
    ("lines[0].quantity", {"quantity": "-1"}),
    ("lines[0].quantity", {"quantity": "1.2345"}),
    ("lines[0].quantity", {"quantity": "1000000000"}),
    ("lines[0].quantity", {"quantity": 0.1}),
    ("lines[0].density", {"unit": "mt", "density": "850"}),
    ("lines[0].density", {"unit": "m3", "density": "599.9"}),
    ("lines[0].density", {"unit": "m3", "density": "1100.1"}),
    ("lines[0].density", {"unit": "m3", "density": "x"}),
    ("lines[0].unit", {"unit": "kg"}),
    ("lines[0].spec_notes", {"spec_notes": "x" * 501}),
]


@pytest.mark.req("B2-R02")
@pytest.mark.parametrize(("field", "over"), BAD)
def test_bad_line_values_are_422_on_the_line_field(
    admin: Client, world: SimpleNamespace, field: str, over: dict[str, Any]
) -> None:
    """Bad line values are 422 on the line field."""
    r = admin.http.post(URL, json=body(world, lines=[line(world, **over)]))
    assert field in errors(r)
    assert admin.listing(status="all") == []


@pytest.mark.req("B2-R02")
def test_other_constraints_are_422_on_their_field(admin: Client, world: SimpleNamespace) -> None:
    """Other constraints are 422 on their field."""
    two = [line(world), line(world, quantity="2")]
    cases: dict[str, list[dict[str, Any]]] = {
        "lines": [
            {"lines": []},
            {"lines": [line(world, product_id=str(p)) for p in world.many] + [line(world)]},
        ],
        "lines[1].product_id": [{"lines": two}],
        "etd": [{"etd": "2026-11-19T08:00:00Z"}],
        "agent_email": [{"agent_email": "nope"}],
        "voyage": [{"voyage": "v" * 41}],
        "eta": [{"eta": "2026-11-20T08:00:00"}],  # no time zone
        "unknown": [{"unknown": 1}],
    }
    for field, variants in cases.items():
        for over in variants:
            r = admin.http.post(URL, json=body(world, **over))
            assert (field in errors(r)) or field == "unknown", (field, r.text)


@pytest.mark.req("B2-R02")
def test_boundary_values_are_accepted(admin: Client, world: SimpleNamespace) -> None:
    """Boundary values are accepted."""
    ten = [line(world, product_id=str(p)) for p in world.many]
    assert len(admin.create(lines=ten, voyage="v" * 40)["lines"]) == 10  # noqa: PLR2004
    for density in ("600", "1100"):
        admin.create(lines=[line(world, unit="m3", density=density)])


@pytest.mark.req("B2-R02")
def test_defaults_on_create(admin: Client, settings: Settings, app_engine: Engine,
                            world: SimpleNamespace) -> None:  # fmt: skip
    """Defaults on create."""
    users = world.users
    # admin caller: buyer + requester = caller, legal entity from the vessel
    made = admin.create(vessel_id=str(world.v2))
    assert made["legal_entity_id"] == str(world.le2)
    assert made["requester_id"] == made["buyer_id"] == str(users[Role.ADMIN].user_id)
    assert made["status"] == "draft"
    assert made["version"] == 1
    assert made["created_by"] == str(users[Role.ADMIN].user_id)
    # operator: not a buyer -> unassigned; vessel default operator wins (Vessel B)
    op = Client(settings, app_engine, world, Role.OPERATOR)
    made = op.create(vessel_id=str(world.v2), operator_id=None)
    assert made["buyer_id"] is None
    assert made["buyer_name"] is None
    assert made["operator_id"] == str(users[Role.OPERATOR].user_id)
    assert made["requester_name"] == "User operator"
    # explicit null buyer stays unassigned for a buyer caller
    buyer = Client(settings, app_engine, world, Role.BUNKER_BUYER)
    assert buyer.create()["buyer_id"] == str(users[Role.BUNKER_BUYER].user_id)
    assert buyer.create(buyer_id=None)["buyer_id"] is None


@pytest.mark.req("B2-R02")
def test_operator_fallbacks(admin: Client, settings: Settings, app_engine: Engine,
                            world: SimpleNamespace) -> None:  # fmt: skip
    # no default operator, admin caller: 422 on operator_id
    """Operator fallbacks."""
    r = admin.http.post(URL, json=body(world, operator_id=None))
    assert "operator_id" in errors(r)
    # default operator that is not a user of the org counts as absent -> caller operator
    op = Client(settings, app_engine, world, Role.OPERATOR)
    made = op.create(vessel_id=str(world.v3), operator_id=None)
    assert made["operator_id"] == str(world.users[Role.OPERATOR].user_id)
    r = admin.http.post(URL, json=body(world, vessel_id=str(world.v3), operator_id=None))
    assert "operator_id" in errors(r)
    # a default operator without the operator/admin role falls back too
    with org_session(world.org, app_engine) as s:
        s.execute(update(Vessel).where(Vessel.id == world.v3)
                  .values(default_operator=world.users[Role.VIEWER].user_id))  # fmt: skip
    r = admin.http.post(URL, json=body(world, vessel_id=str(world.v3), operator_id=None))
    assert "operator_id" in errors(r)


@pytest.mark.req("B2-R02")
def test_references_must_exist_be_active_and_users_have_the_role(
    admin: Client, app_engine: Engine, world: SimpleNamespace
) -> None:
    """References must exist be active and users have the role."""
    users = world.users
    ghost = str(uuid.uuid4())
    for field in ("vessel_id", "legal_entity_id", "port_id", "bunkering_reason_id",
                  "operator_id", "buyer_id", "requester_id"):  # fmt: skip
        assert field in errors(admin.http.post(URL, json=body(world, **{field: ghost})))
    lines_bad = [line(world, product_id=ghost), line(world, product_id=str(world.mgo),
                                                     iso_spec_version_id=ghost)]  # fmt: skip
    assert set(errors(admin.http.post(URL, json=body(world, lines=lines_bad)))) == {
        "lines[0].product_id",
        "lines[1].iso_spec_version_id",
    }
    # roles: a viewer cannot be operator or buyer, an operator cannot be buyer
    viewer, op = str(users[Role.VIEWER].user_id), str(users[Role.OPERATOR].user_id)
    assert "operator_id" in errors(admin.http.post(URL, json=body(world, operator_id=viewer)))
    assert "buyer_id" in errors(admin.http.post(URL, json=body(world, buyer_id=op)))
    assert admin.create(requester_id=viewer)["requester_id"] == viewer  # any user may request
    # inactive master data is rejected
    with org_session(world.org, app_engine) as s:
        for model, ident in ((Vessel, world.v2), (Port, world.port2), (Product, world.mgo),
                             (LegalEntity, world.le2), (BunkeringReason, world.reason2),
                             (IsoSpecVersion, world.iso)):  # fmt: skip
            s.execute(update(model).where(model.id == ident).values(active=False))
    for field, value in (("vessel_id", world.v2), ("port_id", world.port2),
                         ("legal_entity_id", world.le2),
                         ("bunkering_reason_id", world.reason2)):  # fmt: skip
        assert field in errors(admin.http.post(URL, json=body(world, **{field: str(value)})))
    lines_off = [line(world, product_id=str(world.mgo))]
    assert "lines[0].product_id" in errors(admin.http.post(URL, json=body(world, lines=lines_off)))
    assert "lines[0].iso_spec_version_id" in errors(admin.http.post(URL, json=body(world)))


@pytest.mark.req("B2-R02")
def test_unchanged_inactive_reference_may_stay_on_patch(
    admin: Client, app_engine: Engine, world: SimpleNamespace
) -> None:
    """Unchanged inactive reference may stay on patch."""
    inq = admin.create()
    with org_session(world.org, app_engine) as s:
        for model, ident in ((Vessel, world.v1), (Port, world.port), (Port, world.port2),
                             (Product, world.hsfo), (IsoSpecVersion, world.iso)):  # fmt: skip
            s.execute(update(model).where(model.id == ident).values(active=False))
    got = admin.get(inq["id"])
    assert got["vessel_inactive"] is got["port_inactive"] is True
    assert (
        got["lines"][0]["product_inactive"] is got["lines"][0]["iso_spec_version_inactive"] is True
    )
    assert got["legal_entity_inactive"] is got["bunkering_reason_inactive"] is False
    # same vessel/port/lines resent: fine; a new inactive choice is not
    done = admin.patch(inq, vessel_id=str(world.v1), lines=[line(world, quantity="9")],
                       internal_comments="hello")  # fmt: skip
    assert done["lines"][0]["quantity"] == "9"
    r = admin.http.patch(f"{URL}/{inq['id']}", json={"version": done["version"],
                                                     "port_id": str(world.port2)})  # fmt: skip
    assert "port_id" in errors(r)


@pytest.mark.req("B2-R02")
def test_not_found_stale_and_validation_on_patch(
    admin: Client, settings: Settings, app_engine: Engine
) -> None:
    """Not found stale and validation on patch."""
    inq = admin.create()
    ghost = f"{URL}/{uuid.uuid4()}"
    assert admin.http.get(ghost).status_code == NOT_FOUND
    assert admin.http.patch(ghost, json={"version": 1}).status_code == NOT_FOUND
    foreign = Client(settings, app_engine, make_world(app_engine, "f"))
    assert foreign.http.get(f"{URL}/{inq['id']}").status_code == NOT_FOUND
    assert foreign.http.patch(f"{URL}/{inq['id']}", json={"version": 1}).status_code == NOT_FOUND
    admin.patch(inq, internal_comments="x")
    r = admin.http.patch(f"{URL}/{inq['id']}", json={"version": 1, "agent_name": "n"})
    assert (r.status_code, r.json()) == (CONFLICT, {"detail": "Record was changed by someone else"})
    overs: list[dict[str, Any]] = [{"vessel_id": None}, {"eta": None}, {"lines": []}]
    overs.append({"voyage": "v" * 41})
    for over in overs:
        r = admin.http.patch(f"{URL}/{inq['id']}", json={"version": 2, **over})
        assert next(iter(over)) in errors(r)
    # etd before the (new) eta
    r = admin.http.patch(f"{URL}/{inq['id']}", json={"version": 2, "eta": "2026-11-22T08:00:00Z"})
    assert "etd" in errors(r)
    both = {"eta": "2026-11-22T08:00:00Z", "etd": "2026-11-23T08:00:00Z"}
    assert admin.patch({"id": inq["id"], "version": 2}, **both)["etd"].startswith("2026-11-23")
    # clearing optional fields
    cleared = admin.patch(admin.get(inq["id"]), internal_comments=None, voyage=None)
    assert cleared["internal_comments"] is None


@pytest.mark.req("B2-R07")
def test_patch_model_covers_exactly_the_patchable_fields() -> None:
    """Patch model covers exactly the patchable fields."""
    assert set(InquiryPatch.model_fields) - {"version"} == PATCHABLE_FIELDS


# --- B2-R04: permissions ------------------------------------------------------------------------

ALLOWED = {
    "list": set(Role),
    "get": set(Role),
    "create": {Role.ADMIN, Role.BUNKER_BUYER, Role.OPERATOR},
    "patch": {Role.ADMIN, Role.BUNKER_BUYER},
    "take": {Role.ADMIN, Role.BUNKER_BUYER},
    "cancel": {Role.ADMIN, Role.BUNKER_BUYER},
    "duplicate": {Role.ADMIN, Role.BUNKER_BUYER, Role.OPERATOR},
    "history": set(Role),
}


@pytest.mark.req("B2-R04")
@pytest.mark.parametrize("role", list(Role))
def test_role_matrix(
    settings: Settings, app_engine: Engine, world: SimpleNamespace, admin: Client, role: Role
) -> None:
    """Role matrix."""
    inq = admin.create()
    c = Client(settings, app_engine, world, role)

    def live() -> int:  # earlier calls in the loop bump the version
        version: int = admin.get(inq["id"])["version"]
        return version

    calls: dict[str, Callable[[], Any]] = {
        "list": lambda: c.http.get(URL),
        "get": lambda: c.http.get(f"{URL}/{inq['id']}"),
        "create": lambda: c.http.post(URL, json=body(world)),
        "patch": lambda: c.http.patch(
            f"{URL}/{inq['id']}", json={"version": 1, "internal_comments": "c"}
        ),
        "take": lambda: c.http.post(f"{URL}/{inq['id']}/take", json={"version": live()}),
        "cancel": lambda: c.http.post(
            f"{URL}/{inq['id']}/cancel", json={"version": live(), "reason": "r"}
        ),
        "duplicate": lambda: c.http.post(f"{URL}/{inq['id']}/duplicate", json={"version": live()}),
        "history": lambda: c.http.get(f"{URL}/{inq['id']}/history"),
    }
    for name, call in calls.items():
        r = call()
        created = name in {"create", "duplicate"}
        want = (CREATED if created else OK) if role in ALLOWED[name] else FORBIDDEN
        assert r.status_code == want, (name, role, r.text)


# --- B2-R05: references -------------------------------------------------------------------------


@pytest.mark.req("B2-R05")
def test_twenty_concurrent_creates_get_distinct_gap_free_references(admin: Client) -> None:
    """Twenty concurrent creates get distinct gap free references."""

    def go(_: int) -> tuple[int, str]:
        """Go."""
        r = admin.http.post(URL, json=body(admin.w))
        return r.status_code, r.json().get("reference", r.text)

    with ThreadPoolExecutor(10) as pool:
        results = list(pool.map(go, range(20)))
    assert {code for code, _ in results} == {CREATED}
    assert {ref for _, ref in results} == {f"INQ-2611-{n:03d}" for n in range(1, 21)}


@pytest.mark.req("B2-R05")
def test_each_organization_has_its_own_sequence(
    admin: Client, settings: Settings, app_engine: Engine
) -> None:
    """Each organization has its own sequence."""
    other = Client(settings, app_engine, make_world(app_engine, "o"))
    assert admin.create()["reference"] == "INQ-2611-001"
    assert admin.create()["reference"] == "INQ-2611-002"
    assert other.create()["reference"] == "INQ-2611-001"


@pytest.mark.req("B2-R05")
def test_reference_follows_the_utc_month_of_creation(admin: Client) -> None:
    """Reference follows the utc month of creation."""
    admin.now = datetime(2026, 10, 31, 23, 59, 59, tzinfo=UTC)
    assert admin.create()["reference"] == "INQ-2610-001"
    admin.now += timedelta(seconds=1)
    first = admin.create()
    assert first["reference"] == "INQ-2611-001"
    assert first["created_at"].startswith("2026-11-01T00:00:00")
    admin.now = datetime(2026, 10, 31, 23, 59, 59, tzinfo=UTC)
    assert admin.create()["reference"] == "INQ-2610-002"


@pytest.mark.req("B2-R05")
def test_cancelled_numbers_are_not_reused(admin: Client) -> None:
    """Cancelled numbers are not reused."""
    first = admin.create()
    admin.set_status(first["id"], "cancelled")
    assert admin.create()["reference"] == "INQ-2611-002"


# --- B2-R07: edit lock --------------------------------------------------------------------------

LOCKED_CHANGES: dict[str, Callable[[SimpleNamespace], Any]] = {
    "vessel_id": lambda w: str(w.v2),
    "legal_entity_id": lambda w: str(w.le2),
    "port_id": lambda w: str(w.port2),
    "bunkering_reason_id": lambda w: str(w.reason2),
    "lines": lambda w: [line(w, quantity="1")],
    "voyage": lambda _: "NEW",
    "operator_id": lambda w: str(w.users[Role.ADMIN].user_id),
    "requester_id": lambda w: str(w.users[Role.OPERATOR].user_id),
}
EDITABLE_CHANGES: dict[str, Callable[[SimpleNamespace], Any]] = {
    "eta": lambda _: "2026-11-20T09:00:00Z",
    "etd": lambda _: "2026-11-25T08:00:00Z",
    "agent_name": lambda _: "Agent Smith",
    "agent_email": lambda _: "smith@agent.example",
    "buyer_id": lambda w: str(w.users[Role.BUNKER_BUYER].user_id),
    "internal_comments": lambda _: "later",
}


@pytest.mark.req("B2-R07")
def test_change_sets_cover_the_domain_sets() -> None:
    """Change sets cover the domain sets."""
    assert set(LOCKED_CHANGES) | set(EDITABLE_CHANGES) == PATCHABLE_FIELDS


@pytest.mark.req("B2-R07")
@pytest.mark.parametrize("field", sorted(LOCKED_CHANGES))
def test_locked_fields_are_422_after_draft(
    admin: Client, world: SimpleNamespace, field: str
) -> None:
    """Locked fields are 422 after draft."""
    inq = admin.create()
    admin.set_status(inq["id"], "rfq_sent")
    r = admin.http.patch(
        f"{URL}/{inq['id']}", json={"version": 1, field: LOCKED_CHANGES[field](world)}
    )
    assert errors(r) == {field: LOCKED}
    assert admin.get(inq["id"])["version"] == 1


@pytest.mark.req("B2-R07")
@pytest.mark.parametrize("field", sorted(EDITABLE_CHANGES))
def test_editable_fields_save_after_draft(
    admin: Client, world: SimpleNamespace, field: str
) -> None:
    """Editable fields save after draft."""
    inq = admin.create(buyer_id=None)
    admin.set_status(inq["id"], "rfq_sent")
    value = EDITABLE_CHANGES[field](world)
    done = admin.patch(inq, **{field: value})
    assert done[field] == value or done[field].startswith(value[:16])
    assert done["version"] == 2  # noqa: PLR2004


@pytest.mark.req("B2-R07")
def test_resending_an_unchanged_locked_value_is_not_a_change(
    admin: Client, world: SimpleNamespace
) -> None:
    """Resending an unchanged locked value is not a change."""
    inq = admin.create()
    admin.set_status(inq["id"], "offers_received")
    done = admin.patch(inq, vessel_id=str(world.v1), lines=[line(world)], agent_name="A")
    assert done["agent_name"] == "A"


@pytest.mark.req("B2-R06")
def test_cancelled_inquiry_cannot_be_edited(admin: Client) -> None:
    """Cancelled inquiry cannot be edited."""
    inq = admin.create()
    admin.set_status(inq["id"], "cancelled")
    r = admin.http.patch(f"{URL}/{inq['id']}", json={"version": 1, "agent_name": "A"})
    assert (r.status_code, r.json()) == (CONFLICT, {"detail": "Inquiry is cancelled"})
    assert admin.get(inq["id"])["status"] == "cancelled"
    assert admin.get(inq["id"])["cancel_reason"] == "because"


# --- B2-R09: lines ------------------------------------------------------------------------------


@pytest.mark.req("B2-R09")
@pytest.mark.parametrize("qty", ["0.1", "999999999.999", "1", "0.001", "1234.5"])
def test_quantities_round_trip_exactly_as_strings(
    admin: Client, world: SimpleNamespace, qty: str
) -> None:
    """Quantities round trip exactly as strings."""
    made = admin.create(lines=[line(world, quantity=qty)])
    assert made["lines"][0]["quantity"] == qty
    assert admin.get(made["id"])["lines"][0]["quantity"] == qty
    assert isinstance(made["lines"][0]["quantity"], str)


@pytest.mark.req("B2-R09")
def test_density_round_trips_and_m3_without_density_is_not_in_total(
    admin: Client, world: SimpleNamespace
) -> None:
    """Density round trips and m3 without density is not in total."""
    lines = [
        line(world, product_id=str(world.hsfo), unit="m3", density="850.5", spec_notes="  note "),
        line(world, product_id=str(world.mgo), unit="m3"),
        line(world, product_id=str(world.many[0]), unit="mt"),
    ]
    got = admin.create(lines=lines)["lines"]
    assert [(g["density"], g["not_in_total"], g["position"]) for g in got] == [
        ("850.5", False, 1),
        (None, True, 2),
        (None, False, 3),
    ]
    assert got[0]["spec_notes"] == "note"
    assert got[0]["product_name"] == "HSFO"
    assert got[0]["iso_spec_version_name"] == "ISO 8217:2024"


@pytest.mark.req("B2-R09")
def test_switching_a_density_line_to_mt_keeps_density_is_422(
    admin: Client, world: SimpleNamespace
) -> None:
    """Switching a density line to mt keeps density is 422."""
    inq = admin.create(lines=[line(world, unit="m3", density="850")])
    r = admin.http.patch(
        f"{URL}/{inq['id']}",
        json={"version": 1, "lines": [line(world, unit="mt", density="850")]},
    )
    assert "lines[0].density" in errors(r)
    ok = admin.patch(inq, lines=[line(world, unit="mt")])
    assert ok["lines"][0]["density"] is None
    assert ok["lines"][0]["unit"] == "mt"


# --- B2-R10: approved fuel warnings --------------------------------------------------------------


@pytest.mark.req("B2-R10")
def test_unapproved_fuel_warns_but_saves(admin: Client, world: SimpleNamespace) -> None:
    """Unapproved fuel warns but saves."""
    made = admin.create(lines=[line(world), line(world, product_id=str(world.mgo))])
    assert made["warnings"] == [
        {
            "field": "lines[1].product_id",
            "code": "not_approved_fuel",
            "message": "MGO is not an approved fuel for Vessel A",
        }
    ]
    assert admin.get(made["id"])["warnings"] == made["warnings"]
    assert admin.create()["warnings"] == []


@pytest.mark.req("B2-R10")
def test_changing_the_vessel_on_a_draft_recomputes_warnings(
    admin: Client, world: SimpleNamespace
) -> None:
    """Changing the vessel on a draft recomputes warnings."""
    made = admin.create(lines=[line(world)])
    assert made["warnings"] == []
    moved = admin.patch(made, vessel_id=str(world.v2))
    assert [w["message"] for w in moved["warnings"]] == [
        "HSFO is not an approved fuel for Vessel B"
    ]
    assert moved["vessel_name"] == "Vessel B"
    # operator and legal entity are not silently rewritten by the API
    assert moved["legal_entity_id"] == made["legal_entity_id"]
    assert moved["operator_id"] == made["operator_id"]
    # a deactivated approval no longer counts
    with org_session(world.org, admin.engine) as s:
        s.execute(update(VesselApprovedFuel).values(active=False))
    assert [w["code"] for w in admin.get(made["id"])["warnings"]] == ["not_approved_fuel"]


# --- B2-R11: audit ------------------------------------------------------------------------------


@pytest.mark.req("B2-R11")
def test_create_and_patch_write_one_entry_each(admin: Client, world: SimpleNamespace) -> None:
    """Create and patch write one entry each."""
    made = admin.create()
    [created] = admin.entries(made["id"])
    assert (created.action, created.entity_type) == ("create", "inquiry")
    assert created.actor == world.users[Role.ADMIN].user_id
    assert created.changes["reference"] == {"before": None, "after": made["reference"]}
    assert created.changes["status"]["after"] == "draft"
    admin.patch(made, voyage="V1", internal_comments="hi")
    entries = admin.entries(made["id"])
    assert [e.action for e in entries] == ["create", "update"]
    assert entries[1].changes == {
        "voyage": {"before": None, "after": "V1"},
        "internal_comments": {"before": None, "after": "hi"},
    }


@pytest.mark.req("B2-R11")
def test_line_changes_are_recorded_with_before_and_after(
    admin: Client, world: SimpleNamespace
) -> None:
    """Line changes are recorded with before and after."""
    made = admin.create()
    admin.patch(made, lines=[line(world, quantity="750"), line(world, product_id=str(world.mgo))])
    change = admin.entries(made["id"])[1].changes
    assert set(change) == {"lines"}
    assert "HSFO" in (change["lines"]["before"] or "")
    assert "750" in (change["lines"]["after"] or "")
    assert "MGO" in (change["lines"]["after"] or "")
    # a change that only touches the spec notes still differs
    again = admin.get(made["id"])
    notes = [line(world, quantity="750"), line(world, product_id=str(world.mgo))]
    admin.patch(again, lines=[n | {"spec_notes": "n"} for n in notes])
    assert len(admin.entries(made["id"])) == 3  # noqa: PLR2004


@pytest.mark.req("B2-R11")
def test_noop_patch_writes_nothing(admin: Client, world: SimpleNamespace) -> None:
    """Noop patch writes nothing."""
    made = admin.create()
    same = admin.patch(made, voyage=None, vessel_id=made["vessel_id"], lines=[line(world)])
    assert same == made
    assert len(admin.entries(made["id"])) == 1


@pytest.mark.req("B2-R11")
def test_failed_patch_writes_nothing(admin: Client, world: SimpleNamespace) -> None:
    """Failed patch writes nothing."""
    made = admin.create()
    admin.http.patch(f"{URL}/{made['id']}", json={"version": 1, "voyage": "x" * 41})
    admin.http.patch(f"{URL}/{made['id']}", json={"version": 9, "voyage": "ok"})
    admin.http.patch(
        f"{URL}/{made['id']}",
        json={"version": 1, "voyage": "ok", "buyer_id": str(world.users[Role.VIEWER].user_id)},
    )
    assert len(admin.entries(made["id"])) == 1
    got = admin.get(made["id"])
    assert (got["version"], got["voyage"]) == (1, None)


# --- B2-R12: work list --------------------------------------------------------------------------


@pytest.mark.req("B2-R12")
def test_eta_warning_boundary(admin: Client) -> None:
    """Eta warning boundary."""
    cases = {
        "exact48": NOW + timedelta(hours=48),
        "inside": NOW + timedelta(hours=47, minutes=59),
        "now": NOW,
        "past": NOW - timedelta(minutes=1),
    }
    ids = {}
    for name, eta in cases.items():
        ids[name] = admin.create(eta=eta.isoformat(), etd=(eta + timedelta(days=1)).isoformat())[
            "id"
        ]
    got = {i["id"]: i["eta_warning"] for i in admin.listing()}
    assert {n: got[i] for n, i in ids.items()} == {
        "exact48": False,
        "inside": True,
        "now": True,
        "past": False,
    }
    for status in ("nominated", "cancelled"):
        admin.set_status(ids["inside"], status)
        row = next(i for i in admin.listing(status="all") if i["id"] == ids["inside"])
        assert row["eta_warning"] is False
    admin.set_status(ids["inside"], "rfq_sent")
    row = next(i for i in admin.listing() if i["id"] == ids["inside"])
    assert row["eta_warning"] is True


@pytest.mark.req("B2-R12")
def test_list_item_fields(admin: Client) -> None:
    """List item fields."""
    made = admin.create(port_id=str(admin.w.port2))
    [item] = admin.listing()
    assert item == {
        "id": made["id"],
        "reference": "INQ-2611-001",
        "status": "draft",
        "vessel_name": "Vessel A",
        "port_name": "Singapore",
        "port_time_zone": "Asia/Singapore",
        "eta": made["eta"],
        "buyer_name": "User admin",
        "eta_warning": False,
    }


@pytest.mark.req("B2-R12")
def test_status_filter_search_mine_and_sort(
    admin: Client, settings: Settings, app_engine: Engine, world: SimpleNamespace
) -> None:
    """Status filter search mine and sort."""
    buyer = Client(settings, app_engine, world, Role.BUNKER_BUYER)
    a = admin.create(eta="2026-12-03T08:00:00Z", etd="2026-12-04T08:00:00Z")
    b = buyer.create(vessel_id=str(world.v2), port_id=str(world.port2),
                     eta="2026-12-01T08:00:00Z", etd="2026-12-04T08:00:00Z")  # fmt: skip
    c = admin.create(eta="2026-12-02T08:00:00Z", etd="2026-12-04T08:00:00Z")
    admin.set_status(c["id"], "cancelled")
    ref = {a["id"]: a["reference"], b["id"]: b["reference"], c["id"]: c["reference"]}

    def refs(**params: str) -> list[str]:
        """Refs."""
        return [ref[i["id"]] for i in admin.listing(**params)]

    assert refs() == [b["reference"], a["reference"]]  # default: no cancelled, by ETA
    assert refs(status="all") == [b["reference"], c["reference"], a["reference"]]
    assert refs(status="cancelled") == [c["reference"]]
    assert refs(status="draft", sort="reference") == [a["reference"], b["reference"]]
    assert refs(sort="reference", status="all") == sorted(ref.values())
    assert refs(q=a["reference"].lower()) == [a["reference"]]
    assert refs(q="vessel b") == [b["reference"]]
    assert refs(q="SINGAP") == [b["reference"]]
    assert refs(q="no such thing") == []
    assert refs(q="%") == []  # wildcards are literal
    assert refs(q="vessel", status="draft") == [b["reference"], a["reference"]]
    mine = buyer.listing(mine="true")
    assert [i["id"] for i in mine] == [b["id"]]
    assert len(buyer.listing(mine="false")) == 2  # noqa: PLR2004
    assert admin.http.get(URL, params={"status": "bogus"}).status_code == UNPROCESSABLE
    assert admin.http.get(URL, params={"sort": "bogus"}).status_code == UNPROCESSABLE


@pytest.mark.req("B2-R12")
def test_work_list_of_200_inquiries_answers_fast(
    admin: Client, app_engine: Engine, world: SimpleNamespace
) -> None:
    """Work list of 200 inquiries answers fast."""
    me = world.users[Role.ADMIN].user_id
    with org_session(world.org, app_engine) as s:
        for n in range(200):
            _add(
                s,
                Inquiry,
                organization_id=world.org,
                reference=f"INQ-2611-{n + 1:03d}",
                status="draft",
                vessel_id=world.v1,
                legal_entity_id=world.le,
                port_id=world.port,
                bunkering_reason_id=world.reason,
                operator_id=me,
                requester_id=me,
                buyer_id=me,
                eta=NOW + timedelta(hours=n),
                etd=NOW + timedelta(hours=n + 24),
                created_by=me,
            )
    runs = []
    for _ in range(5):
        start = time.perf_counter()
        r = admin.http.get(URL)
        runs.append(time.perf_counter() - start)
        assert r.status_code == OK
        assert len(r.json()) == 200  # noqa: PLR2004
    median = statistics.median(runs)
    print(  # noqa: T201
        f"perf: GET /inquiries x200 median {median * 1000:.1f} ms, "
        f"runs {[round(x * 1000, 1) for x in runs]} ms"
    )
    assert median < PERF_BUDGET_S


# --- another organization's ids -----------------------------------------------------------------


@pytest.mark.req("B2-R04")
def test_other_organizations_ids_are_422_on_their_field_and_404_as_inquiry(
    settings: Settings, app_engine: Engine, world: SimpleNamespace, admin: Client
) -> None:
    """Real ids of org B: 422 on the field in org A; B's inquiry is 404 for every route."""
    other = make_world(app_engine, "o")
    theirs = Client(settings, app_engine, other).create()
    mine = admin.create()
    for field, value in {
        "vessel_id": other.v1,
        "port_id": other.port,
        "legal_entity_id": other.le,
        "bunkering_reason_id": other.reason,
        "operator_id": other.users[Role.OPERATOR].user_id,
        "buyer_id": other.users[Role.BUNKER_BUYER].user_id,
        "requester_id": other.users[Role.ADMIN].user_id,
    }.items():
        assert field in errors(admin.http.post(URL, json=body(world, **{field: str(value)})))
        r = admin.http.patch(f"{URL}/{mine['id']}", json={"version": 1, field: str(value)})
        assert field in errors(r)
    bad = line(world, product_id=str(other.hsfo))
    assert "lines[0].product_id" in errors(admin.http.post(URL, json=body(world, lines=[bad])))
    bad = line(world, iso_spec_version_id=str(other.iso))
    r = admin.http.patch(f"{URL}/{mine['id']}", json={"version": 1, "lines": [bad]})
    assert "lines[0].iso_spec_version_id" in errors(r)
    path = f"{URL}/{theirs['id']}"
    calls = [
        admin.http.get(path),
        admin.http.patch(path, json={"version": 1, "voyage": "x"}),
        admin.http.post(f"{path}/take", json={"version": 1}),
        admin.http.post(f"{path}/cancel", json={"version": 1, "reason": "r"}),
        admin.http.post(f"{path}/duplicate", json={"version": 1}),
        admin.http.get(f"{path}/history"),
    ]
    assert [r.status_code for r in calls] == [NOT_FOUND] * 6
