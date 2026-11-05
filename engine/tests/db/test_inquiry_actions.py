"""Inquiry take, cancel, duplicate and history (B2-R06, R08, R11)."""

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import Engine, update

from nautical_deliverance.domain import inquiry as inquiry_domain
from nautical_deliverance.domain.identity import Role
from nautical_deliverance.domain.inquiry import Status
from nautical_deliverance.persistence.db import org_session
from nautical_deliverance.persistence.models import Vessel
from tests.db.test_inquiry_api import (
    CONFLICT,
    CREATED,
    FORBIDDEN,
    OK,
    URL,
    Client,
    errors,
    line,
    make_world,
)

if TYPE_CHECKING:
    from types import SimpleNamespace

    from nautical_deliverance.settings import Settings

type Json = Any

V2 = 2


@pytest.fixture
def world(app_engine: Engine) -> SimpleNamespace:
    """Build a fresh organization."""
    return make_world(app_engine)


@pytest.fixture
def admin(settings: Settings, app_engine: Engine, world: SimpleNamespace) -> Client:
    """Admin client."""
    return Client(settings, app_engine, world)


def act(c: Client, inq: Json, verb: str, **extra: Any) -> Any:  # noqa: ANN401
    """POST /inquiries/{id}/{verb} at the inquiry's current version."""
    return c.http.post(f"{URL}/{inq['id']}/{verb}", json={"version": inq["version"], **extra})


@pytest.mark.req("B2-R08")
@pytest.mark.parametrize("reason", [None, "", "   ", "x" * 501])
def test_cancel_needs_a_reason(admin: Client, reason: str | None) -> None:
    """Missing, blank or too long reason is 422 on reason."""
    inq = admin.create()
    extra = {} if reason is None else {"reason": reason}
    assert "reason" in errors(act(admin, inq, "cancel", **extra))
    assert admin.get(inq["id"])["status"] == "draft"


@pytest.mark.req("B2-R08")
def test_cancel_sets_status_and_reason_shows_in_history(admin: Client) -> None:
    """Cancel stores the stripped reason, bumps the version, and history shows it."""
    inq = admin.create()
    r = act(admin, inq, "cancel", reason="  wrong vessel  ")
    assert r.status_code == OK, r.text
    done = r.json()
    assert (done["status"], done["cancel_reason"], done["version"]) == (
        "cancelled",
        "wrong vessel",
        2,
    )
    [entry, _] = admin.http.get(f"{URL}/{inq['id']}/history").json()
    assert entry["action"] == "cancel"
    assert entry["changes"]["cancel_reason"] == {"before": None, "after": "wrong vessel"}
    assert entry["changes"]["status"] == {"before": "draft", "after": "cancelled"}


@pytest.mark.req("B2-R06")
def test_cancelled_inquiry_rejects_take_cancel_and_patch(admin: Client) -> None:
    """Take, cancel and patch on a cancelled inquiry are 409."""
    inq = admin.create()
    done = act(admin, inq, "cancel", reason="r").json()
    for r in (
        act(admin, done, "take"),
        act(admin, done, "cancel", reason="again"),
        admin.http.patch(f"{URL}/{inq['id']}", json={"version": 2, "voyage": "x"}),
    ):
        assert r.status_code == CONFLICT, r.text
    assert len(admin.entries(inq["id"])) == len(["create", "cancel"])


@pytest.mark.req("B2-R06")
def test_stale_version_is_409_for_every_action(admin: Client) -> None:
    """A stale version conflicts on take, cancel and duplicate."""
    inq = admin.create()
    admin.patch(inq, voyage="V")
    for verb, extra in (("take", {}), ("cancel", {"reason": "r"}), ("duplicate", {})):
        assert act(admin, inq, verb, **extra).status_code == CONFLICT, verb


@pytest.mark.req("B2-R08")
def test_take_sets_the_caller_as_buyer(
    settings: Settings, app_engine: Engine, world: SimpleNamespace
) -> None:
    """Take by a buyer on an operator-created inquiry; taking again changes nothing."""
    inq = Client(settings, app_engine, world, Role.OPERATOR).create()
    assert inq["buyer_id"] is None
    buyer = Client(settings, app_engine, world, Role.BUNKER_BUYER)
    r = act(buyer, inq, "take")
    assert r.status_code == OK, r.text
    taken = r.json()
    assert taken["buyer_id"] == str(world.users[Role.BUNKER_BUYER].user_id)
    assert taken["version"] == V2
    again = act(buyer, taken, "take")
    assert (again.status_code, again.json()["version"]) == (OK, V2)
    assert [e.action for e in buyer.entries(inq["id"])] == ["create", "take"]


@pytest.mark.req("B2-R06")
def test_two_concurrent_takes_with_the_same_version(
    settings: Settings, app_engine: Engine, world: SimpleNamespace
) -> None:
    """Exactly one 200, one 409 and one audit entry for take."""
    inq = Client(settings, app_engine, world, Role.OPERATOR).create()
    clients = [
        Client(settings, app_engine, world, Role.BUNKER_BUYER),
        Client(settings, app_engine, world, Role.ADMIN),
    ]
    with ThreadPoolExecutor(2) as pool:
        codes = sorted(pool.map(lambda c: act(c, inq, "take").status_code, clients))
    assert codes == [OK, CONFLICT]
    assert [e.action for e in clients[0].entries(inq["id"])] == ["create", "take"]


@pytest.mark.req("B2-R08")
def test_duplicate_copies_exactly_the_b2_d10_fields(
    settings: Settings, app_engine: Engine, world: SimpleNamespace, admin: Client
) -> None:
    """Copied: vessel, legal entity, voyage, operator, requester, port, agent, reason, lines."""
    buyer = Client(settings, app_engine, world, Role.BUNKER_BUYER)
    src = buyer.create(
        legal_entity_id=str(world.le2),
        voyage="V9",
        requester_id=str(world.users[Role.VIEWER].user_id),
        agent_name="Agent",
        agent_email="a@x.example",
        internal_comments="secret",
        port_id=str(world.port2),
        bunkering_reason_id=str(world.reason2),
        lines=[
            line(world, quantity="12.5", spec_notes="low sulphur"),
            line(world, product_id=str(world.mgo), unit="m3", quantity="7", density="850.5"),
        ],
    )
    act(buyer, src, "cancel", reason="scope")  # duplicate is allowed from any status
    src = buyer.get(src["id"])
    r = act(admin, src, "duplicate")
    assert r.status_code == CREATED, r.text
    new = r.json()
    for f in (
        "vessel_id", "legal_entity_id", "voyage", "operator_id", "requester_id", "port_id",
        "agent_name", "agent_email", "bunkering_reason_id",
    ):  # fmt: skip
        assert new[f] == src[f], f
    keys = ("product_id", "quantity", "unit", "density", "spec_notes", "iso_spec_version_id")
    assert [{k: ln[k] for k in keys} for ln in new["lines"]] == [
        {k: ln[k] for k in keys} for ln in src["lines"]
    ]
    assert new["id"] != src["id"]
    assert (new["status"], new["version"], new["cancel_reason"]) == ("draft", 1, None)
    assert new["reference"] != src["reference"]
    assert new["internal_comments"] is None
    assert new["buyer_id"] == str(world.users[Role.ADMIN].user_id)  # the create default
    assert (new["eta"], new["etd"]) == (None, None)
    [entry] = admin.entries(new["id"])
    assert entry.action == "duplicate"
    assert entry.changes["duplicate_of"]["after"] == src["reference"]
    assert [e.action for e in admin.entries(src["id"])] == ["create", "cancel"]


@pytest.mark.req("B2-R08")
def test_duplicate_by_an_operator_is_forbidden(
    settings: Settings, app_engine: Engine, world: SimpleNamespace, admin: Client
) -> None:
    """Duplicate is for admin and bunker buyer only (B2-D12)."""
    src = admin.create()
    op = Client(settings, app_engine, world, Role.OPERATOR)
    r = act(op, src, "duplicate")
    assert r.status_code == FORBIDDEN


@pytest.mark.req("B2-R08")
def test_duplicate_of_an_inquiry_with_an_inactive_vessel_is_422(
    admin: Client, world: SimpleNamespace
) -> None:
    """The create checks apply: copied references must still be active."""
    src = admin.create()
    with org_session(world.org, admin.engine) as s:
        s.execute(update(Vessel).where(Vessel.id == world.v1).values(active=False))
    assert errors(act(admin, src, "duplicate")) == {"vessel_id": "Inactive vessel"}


@pytest.mark.req("B2-R11")
def test_each_action_writes_one_entry_and_history_is_newest_first(admin: Client) -> None:
    """Create, update, take, cancel: one entry each, newest first."""
    inq = admin.create(buyer_id=None)
    inq = admin.patch(inq, voyage="V")
    inq = act(admin, inq, "take").json()
    act(admin, inq, "cancel", reason="r")
    hist = admin.http.get(f"{URL}/{inq['id']}/history")
    assert hist.status_code == OK
    assert [e["action"] for e in hist.json()] == ["cancel", "take", "update", "create"]
    assert [e.action for e in admin.entries(inq["id"])] == ["create", "update", "take", "cancel"]
    assert admin.http.get(f"{URL}/{inq['id']}/history").json()[0]["actor"] == str(
        admin.principal.user_id
    )


@pytest.mark.req("B2-R08")
def test_duplicate_can_be_dated_by_patch_and_cancelled_while_undated(admin: Client) -> None:
    """A dated-less duplicate takes ETA/ETD by PATCH; the list sorts it last without warning."""
    src = admin.create()
    dup = act(admin, src, "duplicate").json()
    other = act(admin, src, "duplicate").json()
    rows = admin.listing()
    assert rows[0]["id"] == src["id"]
    assert {r["id"]: (r["eta"], r["eta_warning"]) for r in rows}[dup["id"]] == (None, False)
    done = admin.patch(dup, eta="2026-11-22T08:00:00Z", etd="2026-11-23T08:00:00Z")
    assert done["eta"].startswith("2026-11-22")
    other = admin.patch(other, voyage="v")
    assert other["eta"] is None
    assert act(admin, other, "cancel", reason="r").status_code == OK


@pytest.mark.req("B2-R06")
def test_cancel_goes_through_can_transition(admin: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    """A move the domain table forbids is 409 and writes nothing."""
    inq = admin.create()
    monkeypatch.setattr(inquiry_domain, "TRANSITIONS", {Status.DRAFT: frozenset()})
    r = act(admin, inq, "cancel", reason="r")
    assert (r.status_code, r.json()) == (
        CONFLICT,
        {"detail": "Cannot move from draft to cancelled"},
    )
    assert admin.get(inq["id"])["status"] == "draft"
    assert [e.action for e in admin.entries(inq["id"])] == ["create"]
