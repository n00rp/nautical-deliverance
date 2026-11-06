"""Nomination API: create, list, preview, patch, send, withdraw, history (B5-R01..R04, R06, R10)."""

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

import pytest
from sqlalchemy import Engine, select, update

from nautical_deliverance.domain.identity import Role
from nautical_deliverance.persistence.db import org_session
from nautical_deliverance.persistence.models import (
    AppUser,
    Contact,
    Inquiry,
    LegalEntity,
    Nomination,
)
from tests.db.test_inquiry_api import CONFLICT, CREATED, FORBIDDEN, NOT_FOUND, OK, errors
from tests.db.test_offer_api import Oc, set_status
from tests.db.test_offer_decision import pick, two
from tests.db.test_rfq_api import deactivate, rfq_world
from tests.unit.test_nomination_domain import FORBIDDEN as FORBIDDEN_FIELDS

if TYPE_CHECKING:
    from types import SimpleNamespace

    from nautical_deliverance.settings import Settings

type Json = Any

NOT_DRAFT = "Nomination is not a draft"
DUPLICATE = "A nomination draft already exists"
NO_CONTACT = "No active contact with e-mail"
SENT_VERSION, AMENDMENT = 2, 2


class Nc(Oc):
    """Client with nomination helpers."""

    def nom_post(self, inq_id: str, **body: Any) -> Any:  # noqa: ANN401
        """POST /inquiries/{id}/nominations."""
        return self.http.post(f"/api/v1/inquiries/{inq_id}/nominations", json=body)

    def nominate(self, inq_id: str, **body: Any) -> Json:  # noqa: ANN401
        """Create a draft, expecting 201."""
        r = self.nom_post(inq_id, **body)
        assert r.status_code == CREATED, r.text
        return r.json()

    def act(self, nom: Json, verb: str) -> Any:  # noqa: ANN401
        """POST mark-sent or withdraw with the nomination's version."""
        return self.http.post(
            f"/api/v1/nominations/{nom['id']}/{verb}", json={"version": nom["version"]}
        )

    def send(self, nom: Json) -> Json:
        """Mark sent, expecting 200."""
        r = self.act(nom, "mark-sent")
        assert r.status_code == OK, r.text
        return r.json()

    def preview(self, nom_id: str) -> Json:
        """GET the preview, expecting 200."""
        return self.api(f"/nominations/{nom_id}/preview")

    def items(self, inq_id: str) -> list[Json]:
        """GET the list of versions."""
        rows: list[Json] = self.api(f"/inquiries/{inq_id}/nominations")
        return rows

    def tick(self, **kw: float) -> None:
        """Move the clock."""
        self.now += timedelta(**kw)


@pytest.fixture
def world(app_engine: Engine) -> SimpleNamespace:
    """World with suppliers."""
    return rfq_world(app_engine)


@pytest.fixture
def admin(settings: Settings, app_engine: Engine, world: SimpleNamespace) -> Nc:
    """Admin client."""
    return Nc(settings, app_engine, world, Role.ADMIN)


def won(admin: Nc) -> Json:
    """Inquiry with Alpha (lowest, 650,000.00) as winner; Beta also offered."""
    inq, low, _ = two(admin)
    assert pick(admin, inq, low["id"]).status_code == OK
    return admin.fresh(inq)


# --- B5-R01: rules ------------------------------------------------------------------------------


@pytest.mark.req("B5-R01")
def test_create_defaults_to_the_winning_contact(admin: Nc) -> None:
    """The winner's RFQ contact is used; the item has the list shape."""
    inq = won(admin)
    item = admin.nominate(inq["id"])
    assert set(item) == {
        *("id", "status", "sequence", "contact_name", "email", "sent_at"),
        *("changed_since_sent", "version"),
    }
    assert (item["status"], item["sequence"], item["version"]) == ("draft", None, 1)
    assert (item["contact_name"], item["email"]) == ("Name a1", "a1@alpha.example")
    assert (item["sent_at"], item["changed_since_sent"]) == (None, False)
    assert admin.items(inq["id"]) == [item]


@pytest.mark.req("B5-R01")
def test_create_falls_back_to_another_contact(
    admin: Nc, world: SimpleNamespace, app_engine: Engine
) -> None:
    """Review focus 1: a deactivated winner contact gives way to another active one."""
    inq = won(admin)
    deactivate(world, app_engine, Contact, world.ct["a1"])
    assert admin.nominate(inq["id"])["contact_name"] == "Name a2"


@pytest.mark.req("B5-R01")
def test_create_without_any_usable_contact(
    admin: Nc, world: SimpleNamespace, app_engine: Engine
) -> None:
    """No active contact with an e-mail left: 422 on contact_id."""
    inq = won(admin)
    for key in ("a1", "a2"):
        deactivate(world, app_engine, Contact, world.ct[key])
    r = admin.nom_post(inq["id"])
    assert errors(r) == {"contact_id": NO_CONTACT}
    assert admin.items(inq["id"]) == []


@pytest.mark.req("B5-R01")
@pytest.mark.parametrize(
    ("key", "message"),
    [
        ("b1", "Contact belongs to another counterparty"),
        ("a_off", "Inactive contact"),
        ("a_blank", "Contact has no e-mail address"),
        (None, "Unknown contact"),
    ],
)
def test_create_rejects_a_bad_contact(
    admin: Nc, world: SimpleNamespace, key: str | None, message: str
) -> None:
    """An explicit contact must be the winner's, active and with an address."""
    inq = won(admin)
    ident = uuid.uuid4() if key is None else world.ct[key]
    assert errors(admin.nom_post(inq["id"], contact_id=str(ident))) == {"contact_id": message}


@pytest.mark.req("B5-R01")
def test_create_accepts_another_contact_of_the_winner(admin: Nc, world: SimpleNamespace) -> None:
    """An explicit, valid contact is used."""
    inq = won(admin)
    item = admin.nominate(inq["id"], contact_id=str(world.ct["a2"]))
    assert item["contact_name"] == "Name a2"


@pytest.mark.req("B5-R01")
@pytest.mark.parametrize("state", ["draft", "rfq_sent", "offers_received", "cancelled"])
def test_create_needs_winner_selected_or_nominated(admin: Nc, state: str) -> None:
    """Only the two decided states allow a nomination."""
    inq = won(admin)
    set_status(admin, inq["id"], state)
    r = admin.nom_post(inq["id"])
    assert r.status_code == CONFLICT
    assert r.json()["detail"] == f"Inquiry is {state}"


@pytest.mark.req("B5-R01")
def test_create_needs_a_winner(admin: Nc) -> None:
    """Winner selected without a winner row: 422 on inquiry_id."""
    inq, _ = admin.sent()
    set_status(admin, inq["id"], "winner_selected")
    assert errors(admin.nom_post(inq["id"])) == {"inquiry_id": "No winning offer"}


@pytest.mark.req("B5-R01")
def test_one_draft_at_a_time(admin: Nc) -> None:
    """A second draft is 422 on inquiry_id; after withdrawing, a new one is fine."""
    inq = won(admin)
    first = admin.nominate(inq["id"])
    assert errors(admin.nom_post(inq["id"])) == {"inquiry_id": DUPLICATE}
    admin.tick(seconds=1)
    assert admin.act(first, "withdraw").status_code == OK
    admin.tick(seconds=1)
    admin.nominate(inq["id"])
    assert [i["status"] for i in admin.items(inq["id"])] == ["draft", "withdrawn"]


@pytest.mark.req("B5-R01")
def test_patch_changes_contact_only_for_a_draft(admin: Nc, world: SimpleNamespace) -> None:
    """Patch validates the contact and the version, and a no-op writes nothing."""
    inq = won(admin)
    nom = admin.nominate(inq["id"])
    url = f"/api/v1/nominations/{nom['id']}"
    bad = admin.http.patch(url, json={"version": 1, "contact_id": str(world.ct["b1"])})
    assert errors(bad) == {"contact_id": "Contact belongs to another counterparty"}
    assert (
        admin.http.patch(url, json={"version": 9, "contact_id": str(world.ct["a2"])}).status_code
        == CONFLICT
    )
    same = admin.http.patch(url, json={"version": 1, "contact_id": str(world.ct["a1"])})
    assert (same.status_code, same.json()["version"]) == (OK, 1)
    assert len(admin.audit("nomination", [nom["id"]])) == 1  # create only
    changed = admin.http.patch(url, json={"version": 1, "contact_id": str(world.ct["a2"])})
    assert (changed.json()["contact_name"], changed.json()["version"]) == ("Name a2", 2)
    sent = admin.send(changed.json())
    r = admin.http.patch(url, json={"version": sent["version"], "contact_id": str(world.ct["a1"])})
    assert (r.status_code, r.json()["detail"]) == (CONFLICT, NOT_DRAFT)


@pytest.mark.req("B5-R01")
def test_mark_sent_rules(admin: Nc, world: SimpleNamespace, app_engine: Engine) -> None:
    """Stale version, wrong state, changed winner and unusable contact all stop a send."""
    inq = won(admin)
    nom = admin.nominate(inq["id"])
    assert (
        admin.http.post(
            f"/api/v1/nominations/{nom['id']}/mark-sent", json={"version": 5}
        ).status_code
        == CONFLICT
    )
    deactivate(world, app_engine, Contact, world.ct["a1"])
    r = admin.act(nom, "mark-sent")
    assert errors(r) == {"contact_id": "Inactive contact"}
    with org_session(world.org, app_engine) as s:
        s.execute(update(Contact).where(Contact.id == world.ct["a1"]).values(active=True))
    other = admin.api(f"/inquiries/{inq['id']}/comparison")["rows"]
    beta = next(r["offer_id"] for r in other if r["counterparty_name"] == "Beta Marine")
    fresh = admin.fresh(inq)
    assert pick(admin, fresh, beta, reason="timing").status_code == OK  # re-select: winner changed
    r = admin.act(nom, "mark-sent")
    assert (r.status_code, r.json()["detail"]) == (
        CONFLICT,
        "Winning offer changed; withdraw this draft",
    )
    assert admin.act(nom, "withdraw").status_code == OK
    r = admin.act({**nom, "version": 2}, "mark-sent")
    assert r.status_code == CONFLICT
    assert r.json()["detail"] == "Cannot move from withdrawn to sent"
    assert admin.act({**nom, "version": 2}, "withdraw").status_code == CONFLICT


@pytest.mark.req("B5-R01")
def test_cancelled_inquiry_cannot_send(admin: Nc) -> None:
    """Review focus 3: a draft survives cancel but can no longer be sent; it can be withdrawn."""
    inq = won(admin)
    nom = admin.nominate(inq["id"])
    r = admin.http.post(
        f"/api/v1/inquiries/{inq['id']}/cancel",
        json={"version": admin.fresh(inq)["version"], "reason": "gone"},
    )
    assert r.status_code == OK, r.text
    r = admin.act(nom, "mark-sent")
    assert (r.status_code, r.json()["detail"]) == (CONFLICT, "Inquiry is cancelled")
    assert admin.act(nom, "withdraw").status_code == OK
    assert admin.items(inq["id"])[0]["status"] == "withdrawn"


@pytest.mark.req("B5-R01")
def test_unusable_address_cannot_be_previewed(
    admin: Nc, world: SimpleNamespace, app_engine: Engine
) -> None:
    """A stored address that cannot go into a mail link is 422, not a crash."""
    inq = won(admin)
    nom = admin.nominate(inq["id"])
    with org_session(world.org, app_engine) as s:
        s.execute(
            update(Contact)
            .where(Contact.id == world.ct["a1"])
            .values(email="a@x.example,b@y.example")
        )
    r = admin.http.get(f"/api/v1/nominations/{nom['id']}/preview")
    assert errors(r) == {"contact_id": "Contact e-mail cannot be used in a mail link"}


@pytest.mark.req("B5-R01")
def test_unknown_ids_are_404(admin: Nc) -> None:
    """Unknown inquiry or nomination."""
    ghost = uuid.uuid4()
    nom = {"id": str(ghost), "version": 1}
    codes = [
        admin.http.get(f"/api/v1/inquiries/{ghost}/nominations").status_code,
        admin.nom_post(str(ghost)).status_code,
        admin.http.get(f"/api/v1/nominations/{ghost}/preview").status_code,
        admin.http.get(f"/api/v1/nominations/{ghost}/history").status_code,
        admin.http.patch(
            f"/api/v1/nominations/{ghost}", json={"version": 1, "contact_id": str(ghost)}
        ).status_code,
        admin.act(nom, "mark-sent").status_code,
        admin.act(nom, "withdraw").status_code,
    ]
    assert codes == [NOT_FOUND] * 7


# --- B5-R02: isolation --------------------------------------------------------------------------


@pytest.mark.req("B5-R02")
def test_foreign_ids_are_invisible(admin: Nc, settings: Settings, app_engine: Engine) -> None:
    """Another organization's inquiry, nomination and contact are 404 / 422."""
    inq = won(admin)
    nom = admin.nominate(inq["id"])
    other_world = rfq_world(app_engine, "x")
    other = Nc(settings, app_engine, other_world, Role.ADMIN)
    theirs = won(other)
    theirs_nom = other.nominate(theirs["id"])
    codes = [
        other.http.get(f"/api/v1/inquiries/{inq['id']}/nominations").status_code,
        other.nom_post(inq["id"]).status_code,
        other.http.get(f"/api/v1/nominations/{nom['id']}/preview").status_code,
        other.http.get(f"/api/v1/nominations/{nom['id']}/history").status_code,
        other.http.patch(
            f"/api/v1/nominations/{nom['id']}",
            json={"version": 1, "contact_id": str(other_world.ct["a2"])},
        ).status_code,
        other.act(nom, "mark-sent").status_code,
        other.act(nom, "withdraw").status_code,
    ]
    assert codes == [NOT_FOUND] * 7
    r = other.http.patch(
        f"/api/v1/nominations/{theirs_nom['id']}",
        json={"version": 1, "contact_id": str(admin.w.ct["a2"])},
    )
    assert errors(r) == {"contact_id": "Unknown contact"}
    assert admin.act(nom, "mark-sent").status_code == OK  # still sendable by its owner


# --- B5-R03: roles ------------------------------------------------------------------------------

ROUTES: list[tuple[str, str, bool]] = [
    ("GET", "/inquiries/{inq}/nominations", False),
    ("POST", "/inquiries/{inq}/nominations", True),
    ("GET", "/nominations/{nom}/preview", False),
    ("PATCH", "/nominations/{nom}", True),
    ("POST", "/nominations/{nom}/mark-sent", True),
    ("POST", "/nominations/{nom}/withdraw", True),
    ("GET", "/nominations/{nom}/history", False),
]


@pytest.mark.req("B5-R03")
@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize(("method", "path", "writes"), ROUTES)
def test_role_matrix(  # noqa: PLR0913
    settings: Settings, app_engine: Engine, world: SimpleNamespace,
    *, method: str, path: str, writes: bool, role: Role,
) -> None:  # fmt: skip
    """Operator gets 403 everywhere; Viewer reads but cannot write; Admin and Buyer do both."""
    admin = Nc(settings, app_engine, world, Role.ADMIN)
    inq = won(admin)
    creates = method == "POST" and path.endswith("/nominations")
    nom = None if creates else admin.nominate(inq["id"])
    url = "/api/v1" + path.format(inq=inq["id"], nom=nom and nom["id"])
    body: Json = None
    if writes:
        body = {"version": 1}
        if method == "PATCH":
            body["contact_id"] = str(world.ct["a2"])
        if creates:
            body = {}
    r = Nc(settings, app_engine, world, role).http.request(method, url, json=body)
    allowed = role is not Role.OPERATOR and not (writes and role is Role.VIEWER)
    expected = (CREATED if creates else OK) if allowed else FORBIDDEN
    assert r.status_code == expected, r.text


# --- B5-R04: confidentiality --------------------------------------------------------------------

# Where each domain-FORBIDDEN name has a database counterpart, its marker. Names without one are
# computed values or addressing the render never gets; they are listed so a new name must be placed.
DB_FIELDS = {
    "decision_reason", "decision_note", "internal_comments", "cancel_reason", "operator_name",
    "requester_name", "legal_entity_name", "other_offers", "prices", "offers", "operator_email",
    "requester_email", "agent_email", "operator", "requester", "legal_entity", "counterparty_name",
    "other_counterparties", "other_price", "other_prices", "other_supplier", "supplier_name",
    "comments", "internal_note", "buyer_email",
}  # fmt: skip
COMPUTED = {"offer_count", "rfq_count", "delta_to_lowest", "lowest", "cc", "bcc"}


def leaks(item: Json, preview: Json, markers: dict[str, str]) -> list[str]:
    """Names of the markers found in any text of one nomination version."""
    text_ = "\n".join([preview["subject"], preview["body"], unquote(preview["mailto"]), str(item)])
    return [name for name, m in markers.items() if m in text_]


@pytest.mark.req("B5-R04")
def test_no_marker_reaches_any_nomination_text(
    admin: Nc, world: SimpleNamespace, app_engine: Engine
) -> None:
    """Markers in every confidential field never appear in live or frozen text."""
    assert FORBIDDEN_FIELDS == DB_FIELDS | COMPUTED  # every domain-forbidden name is placed
    inq, low, high = two(admin)
    # Other offers' texts and the loser's counterparty and contacts.
    r = admin.http.patch(
        f"/api/v1/offers/{high['id']}",
        json={"version": high["version"], "supplier_comment": "MK-OTHER-COMMENT",
              "payment_terms": "MK-OTHER-TERMS", "physical_supplier": "MK-OTHER-SUPPLIER"},
    )  # fmt: skip
    assert r.status_code == OK, r.text
    own = admin.http.patch(  # the winner's own comment is not on the allow-list either
        f"/api/v1/offers/{low['id']}",
        json={"version": low["version"], "supplier_comment": "MK-WINNER-COMMENT"},
    )
    assert own.status_code == OK, own.text
    inq = admin.fresh(inq)
    r = pick(admin, inq, low["id"], reason="other", note="MK-NOTE")
    assert r.status_code == OK, r.text
    markers = {
        "decision_note": "MK-NOTE", "other_comment": "MK-OTHER-COMMENT",
        "other_terms": "MK-OTHER-TERMS", "other_supplier": "MK-OTHER-SUPPLIER",
        "other_counterparty": "Beta Marine", "other_contact": "Name b1",
        "other_contact_email": "b1@beta.example", "winner_name": "Alpha Marine",
        "second_contact": "Name a2", "buyer_email": "admin@x.example",
        "decision_reason_label": "reason",  # stored value "other" is not unique: look for the label
        "winner_comment": "MK-WINNER-COMMENT", "winner_offer": low["id"],
    }  # fmt: skip
    cmp_rows = admin.api(f"/inquiries/{inq['id']}/comparison")["rows"]
    other = next(row for row in cmp_rows if row["counterparty_name"] == "Beta Marine")
    markers["other_total"] = other["total"]
    markers["other_total_shown"] = f"{Decimal(other['total']):,.2f}"
    markers["other_price"] = "650.000"
    with org_session(world.org, app_engine) as s:
        for column, value in (
            ("internal_comments", "MK-INTERNAL"), ("agent_email", "mk-agent@x.example"),
        ):  # fmt: skip
            s.execute(
                update(Inquiry).where(Inquiry.id == uuid.UUID(inq["id"])).values({column: value})
            )
            markers[column] = value
        for role, tag in ((Role.OPERATOR, "operator"), (Role.VIEWER, "requester")):
            uid = world.users[role].user_id
            s.execute(
                update(AppUser).where(AppUser.id == uid)
                .values(name=f"MK-{tag}-name", email=f"mk-{tag}@x.example")
            )  # fmt: skip
            markers[f"{tag}_name"], markers[f"{tag}_email"] = (
                f"MK-{tag}-name",
                f"mk-{tag}@x.example",
            )
        s.execute(
            update(Inquiry).where(Inquiry.id == uuid.UUID(inq["id"]))
            .values(requester_id=world.users[Role.VIEWER].user_id)
        )  # fmt: skip
        s.execute(update(LegalEntity).where(LegalEntity.id == world.le).values(name="MK-LEGAL"))
        markers["legal_entity_name"] = "MK-LEGAL"
    draft = admin.nominate(inq["id"])
    live = admin.preview(draft["id"])
    assert "Name a1" in live["body"]  # positive control: the real recipient is there
    assert "Alpha" not in live["subject"]
    assert leaks(draft, live, markers) == []
    sent = admin.send(draft)
    frozen = admin.preview(sent["id"])
    assert frozen["body"] == live["body"]
    assert leaks(sent, frozen, markers) == []
    # A draft survives a cancel and still renders live: scan it with the cancel reason in place.
    admin.tick(minutes=1)
    amend = admin.nominate(inq["id"])
    cancel = {"version": admin.fresh(inq)["version"], "reason": "MK-CANCEL-REASON"}
    assert admin.http.post(f"/api/v1/inquiries/{inq['id']}/cancel", json=cancel).status_code == OK
    markers["cancel_reason"] = "MK-CANCEL-REASON"
    live_after = admin.preview(amend["id"])
    assert "Name a1" in live_after["body"]
    assert leaks(amend, live_after, markers) == []
    assert admin.act(amend, "mark-sent").status_code == CONFLICT
    again = admin.preview(sent["id"])
    assert again == frozen
    assert leaks(admin.items(inq["id"])[-1], again, markers) == []
    assert unquote(again["mailto"]).count("@") == 1  # exactly one recipient


# --- B5-R06: flow and amendments ----------------------------------------------------------------


@pytest.mark.req("B5-R06")
def test_total_must_match_the_decision(
    admin: Nc, world: SimpleNamespace, app_engine: Engine
) -> None:
    """Ruling R6: a text whose total differs from the decided total is never frozen."""
    inq = won(admin)
    draft = admin.nominate(inq["id"])
    with org_session(world.org, app_engine) as s:
        s.execute(
            update(Inquiry)
            .where(Inquiry.id == uuid.UUID(inq["id"]))
            .values(decided_total=Decimal("1.00"))
        )
    r = admin.act(draft, "mark-sent")
    assert (r.status_code, r.json()["detail"]) == (
        CONFLICT,
        "Nomination total differs from the decision",
    )
    assert admin.fresh(inq)["status"] == "winner_selected"
    assert admin.items(inq["id"])[0]["status"] == "draft"


@pytest.mark.req("B5-R06")
def test_first_send_nominates_and_an_amendment_keeps_it(admin: Nc) -> None:
    """Send 1 moves the inquiry; send 2 is an amendment with sequence 2; frozen text stays."""
    inq = won(admin)
    first = admin.send(admin.nominate(inq["id"]))
    assert (first["status"], first["sequence"], first["sent_at"]) == (
        "sent",
        1,
        "2026-11-05T12:00:00Z",
    )
    assert first["version"] == SENT_VERSION
    after = admin.fresh(inq)
    assert after["status"] == "nominated"
    assert after["version"] == inq["version"] + 1
    v1 = admin.preview(first["id"])
    assert v1["subject"].startswith("Nomination INQ-")
    assert v1["to"] == "a1@alpha.example"
    assert "USD 650,000.00" in v1["body"]
    admin.tick(minutes=5)
    draft = admin.nominate(inq["id"])  # allowed in nominated
    assert errors(admin.nom_post(inq["id"])) == {"inquiry_id": DUPLICATE}
    assert admin.preview(draft["id"])["subject"].startswith("Amended nomination (2) INQ-")
    second = admin.send(draft)
    assert second["sequence"] == AMENDMENT
    assert admin.fresh(inq)["version"] == after["version"]  # no second transition
    assert admin.fresh(inq)["status"] == "nominated"
    rows = admin.items(inq["id"])
    assert [(i["sequence"], i["status"]) for i in rows] == [(2, "sent"), (1, "sent")]
    assert admin.preview(first["id"]) == v1


@pytest.mark.req("B5-R06")
def test_reselecting_after_nominated_is_rejected(admin: Nc) -> None:
    """B5-D10: the decision is final once nominated."""
    inq = won(admin)
    admin.send(admin.nominate(inq["id"]))
    fresh = admin.fresh(inq)
    offer = admin.api(f"/inquiries/{inq['id']}/comparison")["rows"][0]["offer_id"]
    r = pick(admin, fresh, offer)
    assert (r.status_code, r.json()["detail"]) == (CONFLICT, "Inquiry is nominated")


@pytest.mark.req("B5-R06")
def test_eta_change_flags_sent_versions_and_updates_the_amendment(admin: Nc) -> None:
    """Review focus 2: frozen text unchanged, changed_since_sent true, the next draft is new."""
    inq = won(admin)
    sent = admin.send(admin.nominate(inq["id"]))
    frozen = admin.preview(sent["id"])
    assert admin.items(inq["id"])[0]["changed_since_sent"] is False
    admin.tick(minutes=1)
    admin.patch(admin.fresh(inq), eta="2026-11-22T08:00:00Z", etd="2026-11-23T08:00:00Z")
    assert admin.preview(sent["id"]) == frozen
    assert admin.items(inq["id"])[0]["changed_since_sent"] is True
    draft = admin.nominate(inq["id"])
    live = admin.preview(draft["id"])
    assert "22 Nov 08:00 UTC" in live["body"]
    assert "20 Nov 08:00 UTC" in frozen["body"]
    assert [i["changed_since_sent"] for i in admin.items(inq["id"])] == [False, True]


# --- B5-R10: audit ------------------------------------------------------------------------------


@pytest.mark.req("B5-R10")
def test_every_change_writes_one_audit_entry(admin: Nc, world: SimpleNamespace) -> None:
    """Create, patch, send, withdraw and the inquiry transition: one entry each, newest first."""
    inq = won(admin)
    before = len(admin.audit("inquiry", [inq["id"]]))
    nom = admin.nominate(inq["id"])
    admin.tick(seconds=1)
    url = f"/api/v1/nominations/{nom['id']}"
    patched = admin.http.patch(url, json={"version": 1, "contact_id": str(world.ct["a2"])}).json()
    admin.tick(seconds=1)
    sent = admin.send(patched)
    admin.tick(seconds=1)
    second = admin.nominate(inq["id"])
    admin.tick(seconds=1)
    assert admin.act(second, "withdraw").status_code == OK
    trail = admin.audit("nomination", [nom["id"]])
    assert [(e.action, e.actor) for e in trail] == [
        *(("create", admin.principal.user_id), ("update", admin.principal.user_id)),
        ("send", admin.principal.user_id),
    ]
    assert [e.action for e in admin.audit("nomination", [second["id"]])] == ["create", "withdraw"]
    inquiry_trail = admin.audit("inquiry", [inq["id"]])
    assert len(inquiry_trail) == before + 1
    assert inquiry_trail[-1].changes["status"] == {
        "before": "winner_selected",
        "after": "nominated",
    }
    hist = admin.api(f"/nominations/{nom['id']}/history")
    assert [h["action"] for h in hist] == ["send", "update", "create"]
    assert hist[0]["changes"]["status"] == {"before": "draft", "after": "sent"}
    assert sent["sequence"] == 1
    with org_session(admin.w.org, admin.engine) as s:
        row = s.scalar(select(Nomination).where(Nomination.id == uuid.UUID(nom["id"])))
        assert row is not None
        assert row.inquiry_version_at_send == admin.fresh(inq)["version"]
