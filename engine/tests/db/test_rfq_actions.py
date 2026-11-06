"""RFQ mark sent, withdraw, decline and history (B3-R08..R11)."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import Engine, text, update
from sqlalchemy.exc import DBAPIError

from nautical_deliverance.domain.identity import Role
from nautical_deliverance.persistence.db import org_session
from nautical_deliverance.persistence.models import AppUser, Contact, Counterparty, Inquiry, Rfq
from tests.db.test_inquiry_api import CONFLICT, CREATED, NOT_FOUND, OK, UNPROCESSABLE, errors
from tests.db.test_rfq_api import Rc, make_client, rfq_world

if TYPE_CHECKING:
    from types import SimpleNamespace

    from nautical_deliverance.settings import Settings

type Json = Any


@pytest.fixture
def world(app_engine: Engine) -> SimpleNamespace:
    """World with suppliers."""
    return rfq_world(app_engine)


@pytest.fixture
def admin(settings: Settings, app_engine: Engine, world: SimpleNamespace) -> Rc:
    """Admin client."""
    return make_client(settings, app_engine, world, Role.ADMIN)


@pytest.fixture
def inq(admin: Rc) -> Json:
    """Create a draft inquiry with a buyer."""
    return admin.inquiry()


def act(c: Rc, rfq: Json, action: str, version: int | None = None) -> Any:  # noqa: ANN401
    """POST an RFQ action with the item's (or the given) version."""
    return c.http.post(
        f"/api/v1/rfqs/{rfq['id']}/{action}", json={"version": version or rfq["version"]}
    )


def send(c: Rc, rfq: Json) -> Json:
    """Mark sent, expecting 200; returns the item."""
    r = act(c, rfq, "mark-sent")
    assert r.status_code == OK, r.text
    item: Json = r.json()
    return item


def inquiry_row(c: Rc, inq_id: str) -> tuple[str, int]:
    """Inquiry (status, version) straight from the database."""
    with org_session(c.w.org, c.engine) as s:
        row = s.get(Inquiry, uuid.UUID(inq_id))
        assert row is not None
        return row.status, row.version


def set_inquiry(c: Rc, inq_id: str, **values: Any) -> None:  # noqa: ANN401
    """Change inquiry columns directly (the API locks most fields after Draft)."""
    with org_session(c.w.org, c.engine) as s:
        s.execute(update(Inquiry).where(Inquiry.id == uuid.UUID(inq_id)).values(**values))


@pytest.mark.req("B3-R09")
def test_first_send_moves_the_inquiry_once(admin: Rc, inq: Json) -> None:
    """Draft -> RFQ sent on the first send; the second send leaves the inquiry unchanged."""
    a, b = admin.make(inq["id"], ("Alpha", "a1"), ("Beta", "b1"))
    v0 = inquiry_row(admin, inq["id"])[1]
    item = send(admin, a)
    assert (item["status"], item["version"]) == ("sent", 2)
    assert item["sent_at"].startswith("2026-11-05T12:00:00")
    assert inquiry_row(admin, inq["id"]) == ("rfq_sent", v0 + 1)
    assert send(admin, b)["status"] == "sent"
    assert inquiry_row(admin, inq["id"]) == ("rfq_sent", v0 + 1)
    assert len(admin.audit("inquiry", [inq["id"]])) == 3  # create, rfq_deadline, status  # noqa: PLR2004
    with org_session(admin.w.org, admin.engine) as s:  # a version the inquiry had while sent
        assert s.get(Rfq, uuid.UUID(a["id"])).inquiry_version_at_send == v0 + 1  # type: ignore[union-attr]


@pytest.mark.req("B3-R09")
def test_send_needs_eta_and_future_deadline(admin: Rc, inq: Json) -> None:
    """422 on eta without ETA/ETD, 422 on response_deadline when it has passed."""
    rfq = admin.make(inq["id"], ("Alpha", "a1"))[0]
    set_inquiry(admin, inq["id"], eta=None)
    r = act(admin, rfq, "mark-sent")
    assert r.status_code == UNPROCESSABLE
    assert errors(r) == {"eta": "Set ETA and ETD before sending"}
    set_inquiry(admin, inq["id"], eta=datetime(2026, 11, 20, 8, tzinfo=UTC))
    admin.now = datetime(2026, 11, 10, 8, tzinfo=UTC)  # exactly the deadline
    r = act(admin, rfq, "mark-sent")
    assert r.status_code == UNPROCESSABLE
    assert errors(r) == {"response_deadline": "Deadline has passed"}
    assert inquiry_row(admin, inq["id"])[0] == "draft"
    assert admin.api(f"/inquiries/{inq['id']}/rfqs")[0]["status"] == "draft"


@pytest.mark.req("B3-R09")
def test_disallowed_transitions_and_stale_version(admin: Rc, inq: Json) -> None:
    """Withdraw a sent RFQ and decline a draft are 409; so is a stale or repeated action."""
    a, b = admin.make(inq["id"], ("Alpha", "a1"), ("Beta", "b1"))
    sent = send(admin, a)
    r = act(admin, sent, "withdraw")
    assert (r.status_code, r.json()["detail"]) == (CONFLICT, "Cannot move from sent to withdrawn")
    r = act(admin, b, "decline")
    assert (r.status_code, r.json()["detail"]) == (CONFLICT, "Cannot move from draft to declined")
    r = act(admin, sent, "mark-sent")
    assert (r.status_code, r.json()["detail"]) == (CONFLICT, "Cannot move from sent to sent")
    r = act(admin, b, "mark-sent", version=7)
    assert r.status_code == CONFLICT
    assert r.json() == {"detail": "Record was changed by someone else"}
    assert act(admin, sent, "decline").json()["status"] == "declined"
    assert act(admin, {**sent, "id": str(uuid.uuid4())}, "decline").status_code == NOT_FOUND


@pytest.mark.req("B3-R09")
def test_cancelled_inquiry_cannot_send(admin: Rc, inq: Json) -> None:
    """An RFQ of a cancelled inquiry cannot be sent, but a draft can still be withdrawn."""
    rfq = admin.make(inq["id"], ("Alpha", "a1"))[0]
    set_inquiry(admin, inq["id"], status="cancelled", cancel_reason="x")
    r = act(admin, rfq, "mark-sent")
    assert (r.status_code, r.json()["detail"]) == (CONFLICT, "Inquiry is cancelled")
    assert act(admin, rfq, "withdraw").json()["status"] == "withdrawn"


@pytest.mark.req("B3-R08")
def test_frozen_text_and_changed_since_sent(admin: Rc, inq: Json, world: SimpleNamespace) -> None:
    """The sent text never moves; ETA, agent and buyer changes flag it, comments do not."""
    rfq = admin.make(inq["id"], ("Alpha", "a1"))[0]
    before = admin.api(f"/rfqs/{rfq['id']}/preview")
    assert send(admin, rfq)["changed_since_sent"] is False
    frozen = admin.api(f"/rfqs/{rfq['id']}/preview")
    assert frozen == before

    def flag() -> bool:
        return bool(admin.api(f"/inquiries/{inq['id']}/rfqs")[0]["changed_since_sent"])

    set_inquiry(admin, inq["id"], internal_comments="new private note")
    assert flag() is False
    set_inquiry(admin, inq["id"], eta=datetime(2026, 11, 21, 7, tzinfo=UTC))
    assert flag() is True
    set_inquiry(admin, inq["id"], eta=datetime(2026, 11, 20, 8, tzinfo=UTC))
    assert flag() is False
    set_inquiry(admin, inq["id"], agent_name="New Agent")
    assert flag() is True
    set_inquiry(admin, inq["id"], agent_name=None)
    assert flag() is False
    # Review Focus #2: another buyer changes the signature.
    other = world.users[Role.VIEWER].user_id
    with org_session(world.org, admin.engine) as s:
        s.execute(update(AppUser).where(AppUser.id == other).values(name="Other Buyer"))
    set_inquiry(admin, inq["id"], buyer_id=other)
    assert flag() is True
    assert admin.api(f"/rfqs/{rfq['id']}/preview") == frozen
    assert "Other Buyer" not in frozen["body"]


@pytest.mark.req("B3-R08")
def test_trigger_blocks_sent_text_updates(admin: Rc, inq: Json, world: SimpleNamespace) -> None:
    """Direct SQL cannot change the frozen text."""
    rfq = send(admin, admin.make(inq["id"], ("Alpha", "a1"))[0])
    with pytest.raises(DBAPIError), org_session(world.org, admin.engine) as s:
        s.execute(text("UPDATE rfq SET sent_body = 'tampered' WHERE id = :i"), {"i": rfq["id"]})


@pytest.mark.req("B3-R08")
def test_deactivated_contact_keeps_the_logged_address(
    admin: Rc, inq: Json, world: SimpleNamespace
) -> None:
    """Review Focus #1: the address of a sent RFQ survives the contact's deactivation."""
    rfq = send(admin, admin.make(inq["id"], ("Alpha", "a1"))[0])
    with org_session(world.org, admin.engine) as s:
        s.execute(
            update(Contact)
            .where(Contact.id == world.ct["a1"])
            .values(active=False, email="gone@alpha.example")
        )
    log = admin.api(f"/inquiries/{inq['id']}/rfqs")
    assert (log[0]["id"], log[0]["email"]) == (rfq["id"], "a1@alpha.example")
    assert admin.api(f"/rfqs/{rfq['id']}/preview")["to"] == "a1@alpha.example"
    sug = admin.api(f"/inquiries/{inq['id']}/suggestions")
    ids = [c["id"] for e in sug["covers_all"] for c in e["contacts"]]
    assert str(world.ct["a1"]) not in ids


@pytest.mark.req("B3-R09")
def test_send_needs_an_active_contact(admin: Rc, inq: Json, world: SimpleNamespace) -> None:
    """A draft whose contact was deactivated cannot be sent."""
    rfq = admin.make(inq["id"], ("Alpha", "a1"))[0]
    with org_session(world.org, admin.engine) as s:
        s.execute(update(Contact).where(Contact.id == world.ct["a1"]).values(active=False))
    r = act(admin, rfq, "mark-sent")
    assert (r.status_code, errors(r)) == (UNPROCESSABLE, {"contact_id": "Inactive contact"})


@pytest.mark.req("B3-R09")
def test_concurrent_first_sends_transition_once(
    settings: Settings, app_engine: Engine, world: SimpleNamespace, admin: Rc, inq: Json
) -> None:
    """Review Focus #4: two buyers send the first two RFQs together; one inquiry transition."""
    a, b = admin.make(inq["id"], ("Alpha", "a1"), ("Beta", "b1"))
    v0 = inquiry_row(admin, inq["id"])[1]
    buyers = [make_client(settings, app_engine, world, Role.BUNKER_BUYER) for _ in range(2)]
    with ThreadPoolExecutor(2) as pool:
        codes = list(
            pool.map(
                lambda p: act(p[0], p[1], "mark-sent").status_code, zip(buyers, (a, b), strict=True)
            )
        )
    assert codes == [OK, OK]
    assert inquiry_row(admin, inq["id"]) == ("rfq_sent", v0 + 1)
    moves = [
        e
        for e in admin.audit("inquiry", [inq["id"]])
        if e.action == "update" and "status" in e.changes
    ]
    assert [m.changes["status"] for m in moves] == [{"before": "draft", "after": "rfq_sent"}]
    assert {x["status"] for x in admin.api(f"/inquiries/{inq['id']}/rfqs")} == {"sent"}


@pytest.mark.req("B3-R10")
def test_withdraw_frees_the_counterparty(admin: Rc, inq: Json) -> None:
    """After withdraw, the same counterparty can get a new RFQ; a declined one cannot."""
    rfq = admin.make(inq["id"], ("Alpha", "a1"))[0]
    w = act(admin, rfq, "withdraw")
    assert (w.status_code, w.json()["status"], w.json()["version"]) == (OK, "withdrawn", 2)
    assert admin.post(inq["id"], [("Alpha", "a1")]).status_code == CREATED
    other = admin.make(inq["id"], ("Beta", "b1"))[0]
    declined = act(admin, send(admin, other), "decline").json()
    assert declined["status"] == "declined"
    assert declined["email"] == "b1@beta.example"
    assert admin.post(inq["id"], [("Beta", "b1")]).status_code == UNPROCESSABLE


@pytest.mark.req("B3-R11")
def test_every_action_is_audited_and_history_is_newest_first(
    admin: Rc, inq: Json, world: SimpleNamespace
) -> None:
    """One RFQ audit entry per action with the specified verb; history is newest first."""
    a, b, c = admin.make(inq["id"], ("Alpha", "a1"), ("Beta", "b1"), ("Gamma", "c1"))
    act(admin, send(admin, a), "decline")
    act(admin, b, "withdraw")
    hist = admin.api(f"/rfqs/{a['id']}/history")
    assert [h["action"] for h in hist] == ["decline", "send", "create"]
    assert hist[0]["changes"] == {"status": {"before": "sent", "after": "declined"}}
    assert hist[1]["changes"]["status"] == {"before": "draft", "after": "sent"}
    assert set(hist[1]["changes"]) == {
        "status", "sent_at", "sent_to_email", "sent_subject", "sent_body",
        "inquiry_version_at_send",
    }  # fmt: skip
    assert hist[1]["actor"] == str(world.users[Role.ADMIN].user_id)
    assert [h["action"] for h in admin.api(f"/rfqs/{b['id']}/history")] == ["withdraw", "create"]
    assert [h["action"] for h in admin.api(f"/rfqs/{c['id']}/history")] == ["create"]
    assert len(admin.audit("rfq", [a["id"]])) == len(hist)
    assert admin.http.get(f"/api/v1/rfqs/{uuid.uuid4()}/history").status_code == NOT_FOUND


@pytest.mark.req("B3-R08")
def test_mark_sent_rechecks_counterparty_and_buyer(
    admin: Rc, inq: Json, world: SimpleNamespace
) -> None:
    """A draft whose supplier was deactivated, or whose inquiry lost its buyer, is not sent."""
    a, b = admin.make(inq["id"], ("Alpha", "a1"), ("Beta", "b1"))
    with org_session(world.org, admin.engine) as s:
        s.execute(
            update(Counterparty).where(Counterparty.id == world.cp["Alpha"]).values(active=False)
        )
    assert errors(act(admin, a, "mark-sent")) == {"counterparty_id": "Inactive counterparty"}
    set_inquiry(admin, inq["id"], buyer_id=None)
    assert errors(act(admin, b, "mark-sent")) == {"buyer_id": "Assign a buyer before sending"}
    assert inquiry_row(admin, inq["id"])[0] == "draft"
