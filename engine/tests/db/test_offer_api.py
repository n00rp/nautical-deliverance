"""Offer entry API: create, read, patch, history, first offer (B4-R01..R03, R07, R10, R11)."""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import Engine, select, update

from nautical_deliverance.domain.identity import Role
from nautical_deliverance.domain.offer import evaluate_offer
from nautical_deliverance.domain.rfq import render_rfq
from nautical_deliverance.persistence import offer_repo, rfq_repo
from nautical_deliverance.persistence.db import org_session
from nautical_deliverance.persistence.models import Inquiry, Offer, OfferLine, Rfq
from tests.db.test_inquiry_api import (
    CONFLICT,
    CREATED,
    FORBIDDEN,
    NOT_FOUND,
    OK,
    errors,
    line,
)
from tests.db.test_rfq_api import Rc, rfq_world

if TYPE_CHECKING:
    from types import SimpleNamespace

    from nautical_deliverance.settings import Settings

type Json = Any

VALID = "2026-11-12T08:00:00Z"
LATER = "2026-11-13T08:00:00Z"
NOT_SENT = "RFQ is not sent"
MONEY = "Must be an amount of 0 or more with up to 2 decimals"
METHODS = "Input should be 'barge', 'truck', 'pipeline' or 'ex_wharf'"


class Oc(Rc):
    """Client with offer helpers."""

    def sent(self, *keys: tuple[str, str], **over: Any) -> tuple[Json, list[Json]]:  # noqa: ANN401
        """Return an inquiry (HSFO and MGO, 500 mt each) and its sent RFQs."""
        inq = self.inquiry(**over)
        out = []
        for item in self.make(inq["id"], *(keys or (("Alpha", "a1"),))):
            r = self.http.post(f"/api/v1/rfqs/{item['id']}/mark-sent", json={"version": 1})
            assert r.status_code == OK, r.text
            out.append(r.json())
        return self.fresh(inq), out

    def put(self, rfq_id: str, **over: Any) -> Any:  # noqa: ANN401
        """POST /rfqs/{id}/offer with a valid body unless overridden."""
        return self.http.post(f"/api/v1/rfqs/{rfq_id}/offer", json={"valid_until": VALID} | over)

    def offer(self, rfq_id: str, **over: Any) -> Json:  # noqa: ANN401
        """Create an offer, expecting 201."""
        r = self.put(rfq_id, **over)
        assert r.status_code == CREATED, r.text
        return r.json()

    def trail(self, entity: str, ident: str) -> list[Any]:
        """Audit entries of one entity."""
        return self.audit(entity, [ident])


def prices(inq: Json, *amounts: str) -> list[dict[str, Any]]:
    """Offer lines for the first inquiry lines."""
    return [
        {"inquiry_line_id": ln["id"], "price_per_mt": a}
        for ln, a in zip(inq["lines"], amounts, strict=False)
    ]


@pytest.fixture
def world(app_engine: Engine) -> SimpleNamespace:
    """World with suppliers."""
    return rfq_world(app_engine)


@pytest.fixture
def admin(settings: Settings, app_engine: Engine, world: SimpleNamespace) -> Oc:
    """Admin client."""
    return Oc(settings, app_engine, world, Role.ADMIN)


def set_status(admin: Oc, inq_id: str, status: str) -> None:
    """Move an inquiry directly in the database."""
    reason = "because" if status == "cancelled" else None
    with org_session(admin.w.org, admin.engine) as s:
        s.execute(
            update(Inquiry)
            .where(Inquiry.id == uuid.UUID(inq_id))
            .values(status=status, cancel_reason=reason)
        )


# --- B4-R01: values and rules -------------------------------------------------------------------


@pytest.mark.req("B4-R01")
def test_worked_example(admin: Oc, world: SimpleNamespace) -> None:
    """Spec section 3: 306,172.50 + 86,241.00 + 2,000 fixed = 394,413.50, shown exactly."""
    inq = admin.inquiry()
    inq = admin.patch(
        inq, lines=[line(world), line(world, product_id=str(world.mgo), quantity="120", unit="m3")]
    )
    [rfq] = admin.make(inq["id"], ("Alpha", "a1"))
    admin.http.post(f"/api/v1/rfqs/{rfq['id']}/mark-sent", json={"version": 1})
    inq = admin.fresh(inq)
    lines = prices(inq, "612.345", "845.5")
    lines[1]["density"] = "850.0"
    body = {
        "payment_terms": "30 days", "delivery_method": "barge", "physical_supplier": "Shell",
        "supplier_comment": "ok", "barging_cost": "1200", "agent_cost": "350.00",
        "surveyor_cost": "450", "lines": lines,
    }  # fmt: skip
    out = admin.offer(rfq["id"], **body)
    assert [(ln["qty_mt"], ln["line_cost"], ln["in_total"]) for ln in out["lines"]] == [
        ("500.000", "306172.50", True),
        ("102.000", "86241.00", True),
    ]
    assert (out["total"], out["complete"], out["currency"]) == ("394413.50", True, "USD")
    assert (out["barging_cost"], out["port_call_cost"], out["surveyor_cost"]) == (
        "1200.00", "0.00", "450.00",
    )  # fmt: skip
    assert out["lines"][1]["density"] == "850.0"
    assert admin.http.get(f"/api/v1/offers/{out['id']}").json() == out


@pytest.mark.req("B4-R01")
def test_partial_offer_is_incomplete(admin: Oc) -> None:
    """A missing line price keeps the offer out of the complete set; the line is still listed."""
    inq, [rfq] = admin.sent()
    out = admin.offer(rfq["id"], lines=prices(inq, "600"))
    assert [ln["price_per_mt"] for ln in out["lines"]] == ["600.000", None]
    assert out["lines"][1]["in_total"] is False
    assert (out["total"], out["complete"]) == ("300000.00", False)
    empty = admin.sent()[1][0]
    assert admin.offer(empty["id"])["total"] == "0.00"


@pytest.mark.req("B4-R01")
def test_state_conflicts_and_duplicates(admin: Oc) -> None:
    """RFQ must be sent (409), one offer per RFQ (422 rfq_id), inquiry status gates (409)."""
    inq = admin.inquiry()
    [draft] = admin.make(inq["id"], ("Alpha", "a1"))
    r = admin.put(draft["id"])
    assert (r.status_code, r.json()["detail"]) == (CONFLICT, NOT_SENT)
    inq, [rfq] = admin.sent()
    admin.offer(rfq["id"])
    assert errors(admin.put(rfq["id"])) == {"rfq_id": "Offer already entered"}
    for state in ("nominated", "cancelled"):
        i2, [r2] = admin.sent()
        set_status(admin, i2["id"], state)
        r = admin.put(r2["id"])
        assert (r.status_code, r.json()["detail"]) == (CONFLICT, f"Inquiry is {state}")
    _, [r3] = admin.sent()
    admin.http.post(f"/api/v1/rfqs/{r3['id']}/decline", json={"version": 2})
    assert admin.put(r3["id"]).status_code == CONFLICT
    assert admin.put(str(uuid.uuid4())).status_code == NOT_FOUND


BAD: list[tuple[dict[str, Any], dict[str, str]]] = [
    ({"valid_until": None}, {"valid_until": "Input should be a valid datetime"}),
    ({"barging_cost": "-1"}, {"barging_cost": MONEY}),
    ({"other_cost": "1.234"}, {"other_cost": MONEY}),
    ({"delivery_method": "rocket"}, {"delivery_method": METHODS}),
    ({"payment_terms": "x" * 201}, {"payment_terms": "String should have at most 200 characters"}),
    (
        {"supplier_comment": "x" * 2001},
        {"supplier_comment": "String should have at most 2000 characters"},
    ),
    ({"currency": "EUR"}, {"currency": "Extra inputs are not permitted"}),
    (
        {"delivery_from": "2026-11-15T00:00:00Z", "delivery_to": "2026-11-14T00:00:00Z"},
        {"delivery_to": "Must not be before delivery_from"},
    ),
]  # fmt: skip


@pytest.mark.req("B4-R01")
@pytest.mark.parametrize(("over", "expected"), BAD)
def test_field_errors(admin: Oc, over: dict[str, Any], expected: dict[str, str]) -> None:
    """Each bad value is a 422 on its own field."""
    _, [rfq] = admin.sent()
    assert errors(admin.put(rfq["id"], **over)) == expected


@pytest.mark.req("B4-R01")
def test_line_errors(admin: Oc, world: SimpleNamespace) -> None:
    """Line price, density, duplicate, unknown and density-rule errors name lines[i].field."""
    inq = admin.inquiry()
    inq = admin.patch(
        inq,
        lines=[
            line(world),
            line(world, product_id=str(world.mgo), quantity="100", unit="m3"),
            line(world, product_id=str(world.many[0]), quantity="100", unit="m3", density="900"),
        ],
    )
    [rfq] = admin.make(inq["id"], ("Alpha", "a1"))
    admin.http.post(f"/api/v1/rfqs/{rfq['id']}/mark-sent", json={"version": 1})
    mt, m3, m3d = (ln["id"] for ln in inq["lines"])

    def bad(*lines: dict[str, Any]) -> dict[str, str]:
        return errors(admin.put(rfq["id"], lines=list(lines)))

    def ln(ident: str, price: str = "500", **kw: Any) -> dict[str, Any]:  # noqa: ANN401
        return {"inquiry_line_id": ident, "price_per_mt": price, **kw}

    assert bad(ln(mt, "0")) == {
        "lines[0].price_per_mt": "Must be a positive price with up to 9 digits and 3 decimals"
    }
    assert bad(ln(mt, "1.0005"))["lines[0].price_per_mt"].startswith("Must be a positive price")
    assert bad(ln(m3, density="599.9")) == {
        "lines[0].density": "Must be 600 to 1100 kg/m3 with at most 1 decimal"
    }
    assert bad(ln(m3, density="1100.1"))["lines[0].density"].startswith("Must be 600")
    assert bad(ln(mt, density="800")) == {"lines[0].density": "Only for an m3 line without density"}
    assert bad(ln(m3d, density="800")) == {
        "lines[0].density": "Only for an m3 line without density"
    }
    assert bad(ln(mt), ln(mt)) == {"lines[1].inquiry_line_id": "Duplicate line"}
    assert bad(ln(str(uuid.uuid4()))) == {"lines[0].inquiry_line_id": "Unknown inquiry line"}
    r = admin.put(rfq["id"], lines=[ln(mt)] * 11)
    assert errors(r) == {"lines": "List should have at most 10 items after validation, not 11"}
    ok = admin.offer(rfq["id"], lines=[ln(m3, "500", density="1100"), ln(m3d, "700.5")])
    assert [x["qty_mt"] for x in ok["lines"]] == ["500.000", "110.000", "90.000"]
    assert (ok["total"], ok["complete"]) == ("118045.00", False)


@pytest.mark.req("B4-R01")
def test_other_inquiry_line_is_422(admin: Oc) -> None:
    """A line of another inquiry in the same organization cannot be priced."""
    _, [rfq] = admin.sent()
    other = admin.sent()[0]
    r = admin.put(rfq["id"], lines=prices(other, "500"))
    assert errors(r) == {"lines[0].inquiry_line_id": "Unknown inquiry line"}


@pytest.mark.req("B4-R01")
def test_total_too_large_is_422_on_lines(admin: Oc, world: SimpleNamespace) -> None:
    """999,999,999.999 mt x 99,999,999.999 does not overflow silently (Review Focus 3)."""
    inq = admin.inquiry()
    inq = admin.patch(inq, lines=[line(world, quantity="999999999.999")])
    [rfq] = admin.make(inq["id"], ("Alpha", "a1"))
    admin.http.post(f"/api/v1/rfqs/{rfq['id']}/mark-sent", json={"version": 1})
    r = admin.put(rfq["id"], lines=prices(inq, "99999999.999"))
    assert errors(r) == {"lines": "Total too large"}
    with org_session(admin.w.org, admin.engine) as s:
        assert s.scalars(select(Offer)).first() is None  # rolled back, nothing half-written
    assert admin.fresh(inq)["status"] == "rfq_sent"


@pytest.mark.req("B4-R01")
def test_patch_total_too_large_is_422_on_lines(admin: Oc, world: SimpleNamespace) -> None:
    """A patch that pushes the total past the limit is 422 on lines and changes nothing."""
    inq = admin.inquiry()
    inq = admin.patch(inq, lines=[line(world, quantity="999999999.999")])
    [rfq] = admin.make(inq["id"], ("Alpha", "a1"))
    admin.http.post(f"/api/v1/rfqs/{rfq['id']}/mark-sent", json={"version": 1})
    off = admin.offer(rfq["id"], lines=prices(inq, "1"))
    r = admin.http.patch(
        f"/api/v1/offers/{off['id']}",
        json={"version": 1, "payment_terms": "x", "lines": prices(inq, "99999999.999")},
    )
    assert errors(r) == {"lines": "Total too large"}
    assert admin.http.get(f"/api/v1/offers/{off['id']}").json() == off  # rolled back
    assert len(admin.trail("offer", off["id"])) == 1


@pytest.mark.req("B4-R01")
def test_patch_reports_the_first_empty_field_in_field_order(admin: Oc) -> None:
    """Two null required fields: the error is always the first one in field order."""
    _, [rfq] = admin.sent()
    off = admin.offer(rfq["id"])
    r = admin.http.patch(
        f"/api/v1/offers/{off['id']}", json={"version": 1, "other_cost": None, "valid_until": None}
    )
    assert errors(r) == {"valid_until": "Cannot be empty"}


# --- B4-R02: organization isolation -------------------------------------------------------------


@pytest.mark.req("B4-R02")
def test_other_org(settings: Settings, app_engine: Engine, admin: Oc) -> None:
    """Another organization's RFQ and offer ids are 404; its inquiry line id is a 422."""
    inq, [rfq] = admin.sent()
    off = admin.offer(rfq["id"], lines=prices(inq, "500"))
    other = Oc(settings, app_engine, rfq_world(app_engine, "o2"), Role.ADMIN)
    _, [mine_rfq] = other.sent()
    for method, path, body in (
        ("POST", f"/rfqs/{rfq['id']}/offer", {"valid_until": VALID}),
        ("GET", f"/offers/{off['id']}", None),
        ("PATCH", f"/offers/{off['id']}", {"version": 1}),
        ("GET", f"/offers/{off['id']}/history", None),
    ):
        assert other.http.request(method, "/api/v1" + path, json=body).status_code == NOT_FOUND
    r = other.put(mine_rfq["id"], lines=prices(inq, "500"))
    assert errors(r) == {"lines[0].inquiry_line_id": "Unknown inquiry line"}
    own = other.offer(mine_rfq["id"])
    r = other.http.patch(
        f"/api/v1/offers/{own['id']}", json={"version": 1, "lines": prices(inq, "500")}
    )
    assert errors(r) == {"lines[0].inquiry_line_id": "Unknown inquiry line"}


# --- B4-R03: roles ------------------------------------------------------------------------------

ROUTES: list[tuple[str, str, bool]] = [
    ("POST", "/rfqs/{rfq}/offer", True),
    ("GET", "/offers/{offer}", False),
    ("PATCH", "/offers/{offer}", True),
    ("GET", "/offers/{offer}/history", False),
    ("GET", "/inquiries/{inq}/comparison", False),
    ("POST", "/inquiries/{inq}/select-winner", True),
]


@pytest.mark.req("B4-R03")
@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize(("method", "path", "writes"), ROUTES)
def test_role_matrix(  # noqa: PLR0913
    settings: Settings, app_engine: Engine, world: SimpleNamespace,
    *, method: str, path: str, writes: bool, role: Role,
) -> None:  # fmt: skip
    """Operator gets 403 everywhere; Viewer reads but cannot write; Admin and Buyer do both."""
    admin = Oc(settings, app_engine, world, Role.ADMIN)
    inq, [rfq] = admin.sent()
    entering = path.startswith("/rfqs")
    off = rfq if entering else admin.offer(rfq["id"], lines=prices(inq, "500", "500"))
    url = "/api/v1" + path.format(rfq=rfq["id"], offer=off["id"], inq=inq["id"])
    body: Json = None
    if entering:
        body = {"valid_until": VALID}
    elif method == "PATCH":
        body = {"version": 1, "payment_terms": "net 30"}
    elif method == "POST":
        body = {"version": admin.fresh(inq)["version"], "offer_id": off["id"]}
    r = Oc(settings, app_engine, world, role).http.request(method, url, json=body)
    allowed = role is not Role.OPERATOR and not (writes and role is Role.VIEWER)
    expected = (CREATED if entering else OK) if allowed else FORBIDDEN
    assert r.status_code == expected, r.text


# --- B4-R07: first offer moves the inquiry ------------------------------------------------------


@pytest.mark.req("B4-R07")
def test_first_offer_transitions_once(admin: Oc) -> None:
    """The first offer moves rfq_sent to offers_received (version +1); the second does not."""
    inq, rfqs = admin.sent(("Alpha", "a1"), ("Beta", "b1"))
    assert inq["status"] == "rfq_sent"
    admin.offer(rfqs[0]["id"])
    after = admin.fresh(inq)
    assert (after["status"], after["version"]) == ("offers_received", inq["version"] + 1)
    admin.offer(rfqs[1]["id"])
    again = admin.fresh(inq)
    assert (again["status"], again["version"]) == ("offers_received", after["version"])


@pytest.mark.req("B4-R07")
def test_offer_after_winner_selected_keeps_status(admin: Oc) -> None:
    """An offer may still arrive while a winner is selected; the status stays."""
    inq, rfqs = admin.sent(("Alpha", "a1"), ("Beta", "b1"))
    first = admin.offer(rfqs[0]["id"])
    select_winner(admin, inq["id"], first["id"])
    admin.offer(rfqs[1]["id"])
    assert admin.fresh(inq)["status"] == "winner_selected"


def select_winner(admin: Oc, inq_id: str, offer_id: str) -> None:
    """Make an offer the selected one directly in the database (Task 4 adds the endpoint)."""
    with org_session(admin.w.org, admin.engine) as s:
        s.execute(
            update(Inquiry)
            .where(Inquiry.id == uuid.UUID(inq_id))
            .values(
                status="winner_selected", winner_offer_id=uuid.UUID(offer_id),
                decided_at=admin.now, decided_by=admin.principal.user_id,
                decided_total=Decimal(1),
            )
        )  # fmt: skip


# --- B4-R11: audit ------------------------------------------------------------------------------


@pytest.mark.req("B4-R11")
def test_create_update_and_transition_are_audited(admin: Oc) -> None:
    """Create, patch and the inquiry transition write one entry each; a no-op patch none."""
    inq, [rfq] = admin.sent()
    before = len(admin.trail("inquiry", inq["id"]))
    off = admin.offer(rfq["id"], payment_terms="30 days", lines=prices(inq, "500"))
    [created] = admin.trail("offer", off["id"])
    assert created.action == "create"
    assert created.changes["payment_terms"] == {"before": None, "after": "30 days"}
    assert created.changes["valid_until"]["after"] == "2026-11-12T08:00:00Z"
    assert created.changes["lines"]["after"] == '["HSFO 500"]'
    inquiry_entries = admin.trail("inquiry", inq["id"])
    assert len(inquiry_entries) == before + 1
    assert inquiry_entries[-1].changes == {
        "status": {"before": "rfq_sent", "after": "offers_received"}
    }
    url = f"/api/v1/offers/{off['id']}"
    r = admin.http.patch(
        url, json={"version": 1, "payment_terms": "30 days", "lines": prices(inq, "500")}
    )
    assert r.status_code == OK
    assert r.json()["version"] == 1
    assert len(admin.trail("offer", off["id"])) == 1
    r = admin.http.patch(
        url, json={"version": 1, "payment_terms": "net 45", "lines": prices(inq, "510")}
    )
    assert r.json()["version"] == 2  # noqa: PLR2004
    [_, updated] = admin.trail("offer", off["id"])
    assert updated.action == "update"
    assert set(updated.changes) == {"payment_terms", "lines"}
    hist = admin.http.get(f"{url}/history").json()
    assert [h["action"] for h in hist] == ["update", "create"]
    assert len(admin.trail("inquiry", inq["id"])) == before + 1  # no second transition


@pytest.mark.req("B4-R11")
def test_failed_create_writes_nothing(admin: Oc) -> None:
    """A rejected offer leaves no audit entry, offer or transition."""
    inq, [rfq] = admin.sent()
    n = len(admin.trail("inquiry", inq["id"]))
    assert admin.put(rfq["id"], barging_cost="-1").status_code == 422  # noqa: PLR2004
    assert admin.put(rfq["id"], lines=prices(inq, "500") * 2).status_code == 422  # noqa: PLR2004
    assert len(admin.trail("inquiry", inq["id"])) == n
    assert admin.fresh(inq)["status"] == "rfq_sent"
    assert admin.audit("offer") == []


# --- patch rules --------------------------------------------------------------------------------


@pytest.mark.req("B4-R01")
def test_patch_rules(admin: Oc) -> None:
    """Stale version 409; lines replaced as a set; null clears optional fields; cost null is 422."""
    inq, [rfq] = admin.sent()
    off = admin.offer(rfq["id"], payment_terms="a", lines=prices(inq, "500", "400"))
    url = f"/api/v1/offers/{off['id']}"
    assert admin.http.patch(url, json={"version": 9}).status_code == CONFLICT
    assert (
        admin.http.patch(f"/api/v1/offers/{uuid.uuid4()}", json={"version": 1}).status_code
        == NOT_FOUND
    )
    r = admin.http.patch(url, json={"version": 1, "valid_until": None})
    assert errors(r) == {"valid_until": "Cannot be empty"}
    r = admin.http.patch(url, json={"version": 1, "barging_cost": None})
    assert errors(r) == {"barging_cost": "Cannot be empty"}
    r = admin.http.patch(
        url,
        json={
            "version": 1,
            "delivery_to": "2026-11-01T00:00:00Z",
            "delivery_from": "2026-11-02T00:00:00Z",
        },
    )
    assert errors(r) == {"delivery_to": "Must not be before delivery_from"}
    out = admin.http.patch(
        url, json={"version": 1, "payment_terms": None, "lines": prices(inq, "450")}
    ).json()
    assert out["payment_terms"] is None
    assert [ln["price_per_mt"] for ln in out["lines"]] == ["450.000", None]
    assert out["version"] == 2  # noqa: PLR2004
    r = admin.http.patch(url, json={"version": 2, "delivery_from": "2026-11-15T00:00:00Z"})
    assert r.status_code == OK
    r = admin.http.patch(url, json={"version": 3, "delivery_to": "2026-11-14T00:00:00Z"})
    assert errors(r) == {"delivery_to": "Must not be before delivery_from"}
    with org_session(admin.w.org, admin.engine) as s:
        assert len(s.scalars(select(OfferLine)).all()) == 1


@pytest.mark.req("B4-R01")
def test_patch_by_inquiry_status(admin: Oc) -> None:
    """A nominated or cancelled inquiry's offers cannot change; they stay readable."""
    inq, [rfq] = admin.sent()
    off = admin.offer(rfq["id"])
    set_status(admin, inq["id"], "nominated")
    r = admin.http.patch(f"/api/v1/offers/{off['id']}", json={"version": 1, "payment_terms": "x"})
    assert (r.status_code, r.json()["detail"]) == (CONFLICT, "Inquiry is nominated")
    assert admin.http.get(f"/api/v1/offers/{off['id']}").status_code == OK


@pytest.mark.req("B4-R08")
def test_selected_offer_is_locked(admin: Oc) -> None:
    """Editing the selected offer is 409; another offer stays editable (B4-D12)."""
    inq, rfqs = admin.sent(("Alpha", "a1"), ("Beta", "b1"))
    a, b = (admin.offer(r["id"]) for r in rfqs)
    select_winner(admin, inq["id"], a["id"])
    r = admin.http.patch(f"/api/v1/offers/{a['id']}", json={"version": 1, "payment_terms": "x"})
    assert (r.status_code, r.json()["detail"]) == (CONFLICT, "Selected offer is locked")
    got = admin.http.get(f"/api/v1/offers/{a['id']}").json()
    assert got["selected"] is True
    r = admin.http.patch(f"/api/v1/offers/{b['id']}", json={"version": 1, "payment_terms": "x"})
    assert r.status_code == OK


# --- RFQ log, declined RFQ ----------------------------------------------------------------------


@pytest.mark.req("B4-R01")
def test_log_shows_offer_received(admin: Oc) -> None:
    """offer_received is true exactly for the RFQ that has an offer."""
    inq, rfqs = admin.sent(("Alpha", "a1"), ("Beta", "b1"))
    assert [i["offer_received"] for i in admin.api(f"/inquiries/{inq['id']}/rfqs")] == [
        False,
        False,
    ]
    made = admin.offer(rfqs[0]["id"])
    log = admin.api(f"/inquiries/{inq['id']}/rfqs")
    assert {i["id"]: i["offer_received"] for i in log} == {
        rfqs[0]["id"]: True,
        rfqs[1]["id"]: False,
    }
    assert {i["id"]: i["offer_id"] for i in log} == {rfqs[0]["id"]: made["id"], rfqs[1]["id"]: None}


@pytest.mark.req("B4-R01")
def test_offer_of_declined_rfq_stays_readable(admin: Oc) -> None:
    """Review focus 1: declining the RFQ later does not hide the offer; it shows the RFQ status."""
    inq, [rfq] = admin.sent()
    off = admin.offer(rfq["id"], lines=prices(inq, "500"))
    r = admin.http.post(f"/api/v1/rfqs/{rfq['id']}/decline", json={"version": 2})
    assert r.status_code == OK, r.text
    got = admin.http.get(f"/api/v1/offers/{off['id']}")
    assert got.status_code == OK
    assert got.json()["rfq_status"] == "declined"
    assert got.json()["total"] == off["total"]
    assert admin.http.get(f"/api/v1/offers/{off['id']}/history").status_code == OK
    assert admin.api(f"/inquiries/{inq['id']}/rfqs")[0]["offer_received"] is True


# --- B4-R10: confidentiality --------------------------------------------------------------------


@pytest.mark.req("B4-R10")
def test_offers_never_reach_rfq_texts(admin: Oc, world: SimpleNamespace) -> None:
    """Live and frozen RFQ texts are byte-identical before and after marker offers are entered."""
    inq = admin.inquiry()
    items = admin.make(inq["id"], ("Alpha", "a1"), ("Beta", "b1"), ("Gamma", "c1"))
    for item in items[:2]:
        assert (
            admin.http.post(f"/api/v1/rfqs/{item['id']}/mark-sent", json={"version": 1}).status_code
            == OK
        )
    inq = admin.fresh(inq)

    def texts() -> dict[str, tuple[str, str, str, tuple[str, str]]]:
        out = {}
        with org_session(world.org, admin.engine) as s:
            for item in admin.api(f"/inquiries/{inq['id']}/rfqs"):
                p = admin.api(f"/rfqs/{item['id']}/preview")
                live = render_rfq(rfq_repo.build_context(s, s.get(Rfq, uuid.UUID(item["id"]))))  # type: ignore[arg-type]
                out[item["id"]] = (p["subject"], p["body"], p["mailto"], live)
        return out

    before = texts()
    marks = ["MK-TERMS-ZZ", "MK-SUPPLIER-ZZ", "MK-COMMENT-ZZ", "777.777", "4242.42"]
    for item in items[:2]:
        admin.offer(
            item["id"], payment_terms=marks[0], physical_supplier=marks[1],
            supplier_comment=marks[2], barging_cost=marks[4], lines=prices(inq, marks[3]),
        )  # fmt: skip
    after = texts()
    assert after == before
    blob = repr(after)
    assert not [m for m in marks if m in blob]


@pytest.mark.req("B4-R01")
def test_inputs_for_is_the_domain_mapping(admin: Oc) -> None:
    """offer_repo.inputs_for lists every inquiry line, priced or not, and the fixed costs."""
    inq, [rfq] = admin.sent()
    off = admin.offer(rfq["id"], other_cost="5", lines=prices(inq, "600"))
    with org_session(admin.w.org, admin.engine) as s:
        got = offer_repo.inputs_for(s, s.get(Offer, uuid.UUID(off["id"])))  # type: ignore[arg-type]
        assert [ln.price_per_mt for ln in got.lines] == [Decimal(600), None]
        assert got.fixed[4] == Decimal(5)
        assert str(evaluate_offer(got).total) == off["total"]
