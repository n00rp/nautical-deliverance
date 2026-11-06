"""Comparison and winner selection (B4-R05 API, R06, R07, R08, R11, Review Focus 1, 4, 5)."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import Engine, select, update

from nautical_deliverance.domain.identity import Role
from nautical_deliverance.domain.offer import evaluate_offer, lowest
from nautical_deliverance.persistence import offer_repo
from nautical_deliverance.persistence.db import org_session
from nautical_deliverance.persistence.models import Counterparty, Inquiry, Offer, Product
from tests.db.test_inquiry_api import CONFLICT, OK, errors
from tests.db.test_offer_api import VALID, Oc, prices, set_status
from tests.db.test_rfq_api import deactivate, rfq_world

if TYPE_CHECKING:
    from types import SimpleNamespace

    from nautical_deliverance.settings import Settings

type Json = Any

PAST = "2026-11-01T08:00:00Z"
SOON = "2026-11-06T00:00:00Z"  # 12 h after the test clock
UNPROCESSABLE = 422


@pytest.fixture
def world(app_engine: Engine) -> SimpleNamespace:
    """World with suppliers."""
    return rfq_world(app_engine)


@pytest.fixture
def admin(settings: Settings, app_engine: Engine, world: SimpleNamespace) -> Oc:
    """Admin client."""
    return Oc(settings, app_engine, world, Role.ADMIN)


def pick(admin: Oc, inq: Json, offer_id: str, **over: Any) -> Any:  # noqa: ANN401
    """POST select-winner with the inquiry's current version."""
    body = {"version": admin.fresh(inq)["version"], "offer_id": offer_id, **over}
    return admin.http.post(f"/api/v1/inquiries/{inq['id']}/select-winner", json=body)


def two(admin: Oc) -> tuple[Json, Json, Json]:
    """Inquiry with a lowest offer (650,000.00) and a dearer one (675,000.00)."""
    inq, rfqs = admin.sent(("Alpha", "a1"), ("Beta", "b1"))
    low = admin.offer(rfqs[0]["id"], lines=prices(inq, "600", "700"))
    high = admin.offer(rfqs[1]["id"], lines=prices(inq, "650", "700"))
    return admin.fresh(inq), low, high


# --- B4-R05: comparison -------------------------------------------------------------------------


@pytest.mark.req("B4-R05")
def test_comparison_flags_match_the_domain(admin: Oc) -> None:
    """Tie, partial, expired and expiring offers: flags, deltas and order follow the domain."""
    inq, rfqs = admin.sent(("Alpha", "a1"), ("Beta", "b1"), ("Gamma", "c1"))
    full = prices(inq, "600", "700")
    a = admin.offer(rfqs[0]["id"], lines=full)
    b = admin.offer(rfqs[1]["id"], lines=full, valid_until=SOON)
    p = admin.offer(rfqs[2]["id"], lines=prices(inq, "100"), valid_until=PAST)
    got = admin.api(f"/inquiries/{inq['id']}/comparison")
    with org_session(admin.w.org, admin.engine) as s:
        offers = s.scalars(select(Offer).where(Offer.inquiry_id == uuid.UUID(inq["id"]))).all()
        expected = lowest(evaluate_offer(offer_repo.inputs_for(s, o)) for o in offers)
    rows = got["rows"]
    assert {r["offer_id"] for r in rows if r["lowest"]} == set(expected) == {a["id"], b["id"]}
    assert [r["offer_id"] for r in rows] == [a["id"], b["id"], p["id"]]  # complete first
    assert [r["delta_to_lowest"] for r in rows] == ["0.00", "0.00", None]
    assert [r["expired"] for r in rows] == [False, False, True]
    assert [r["expiring_soon"] for r in rows] == [False, True, False]
    assert [r["complete"] for r in rows] == [True, True, False]
    assert {r["rfq_status"] for r in rows} == {"sent"}
    assert [r["counterparty_name"] for r in rows][:2] == ["Alpha Marine", "Beta Marine"]
    assert got["decision"] is None
    assert rows[2]["lines"][1]["price_per_mt"] is None  # partial offer keeps all lines


@pytest.mark.req("B4-R05")
def test_comparison_without_offers_and_unknown_inquiry(admin: Oc) -> None:
    """No offers is an empty list; an unknown inquiry is 404."""
    inq, _ = admin.sent()
    assert admin.api(f"/inquiries/{inq['id']}/comparison") == {"rows": [], "decision": None}
    r = admin.http.get(f"/api/v1/inquiries/{uuid.uuid4()}/comparison")
    assert r.status_code == 404  # noqa: PLR2004


# --- B4-R06: rationale --------------------------------------------------------------------------


@pytest.mark.req("B4-R06")
def test_rationale_rules_and_history(admin: Oc) -> None:
    """Lowest needs none; a dearer offer needs a reason; other needs a note; both are shown."""
    inq, low, high = two(admin)
    r = pick(admin, inq, high["id"])
    assert (r.status_code, errors(r)) == (
        UNPROCESSABLE,
        {"reason": "Required when the offer is not the lowest"},
    )
    r = pick(admin, inq, high["id"], reason="other")
    assert errors(r) == {"note": "Required for reason other"}
    r = pick(admin, inq, high["id"], reason="other", note="  ")
    assert errors(r) == {"note": "String should have at least 1 character"}
    r = pick(admin, inq, high["id"], reason="gut_feeling")
    assert "reason" in errors(r)
    assert admin.fresh(inq)["status"] == "offers_received"  # nothing happened
    r = pick(admin, inq, high["id"], reason="timing", note="Berth is free on the 12th")
    assert r.status_code == OK, r.text
    out = admin.fresh(inq)
    assert out["decision"]["reason"] == "timing"
    assert out["decision"]["note"] == "Berth is free on the 12th"
    assert out["decision"]["decided_total"] == "675000.00"
    assert out["winner_counterparty_name"] == "Beta Marine"
    hist = admin.api(f"/inquiries/{inq['id']}/history")[0]
    assert hist["action"] == "select_winner"
    assert hist["changes"]["decision_reason"] == {"before": None, "after": "timing"}
    assert hist["changes"]["decision_note"]["after"] == "Berth is free on the 12th"
    assert hist["changes"]["winner_counterparty"] == {"before": None, "after": "Beta Marine"}
    r = pick(admin, inq, low["id"])  # the lowest needs no reason, and clears the old one
    assert r.status_code == OK, r.text
    assert r.json()["decision"]["reason"] is None
    assert r.json()["decision"]["decided_total"] == "650000.00"


@pytest.mark.req("B4-R06")
def test_partial_offer_always_needs_a_reason(admin: Oc) -> None:
    """A partial offer is never the lowest, even when it is the only one."""
    inq, [rfq] = admin.sent()
    partial = admin.offer(rfq["id"], lines=prices(inq, "100"))
    assert "reason" in errors(pick(admin, inq, partial["id"]))
    assert pick(admin, inq, partial["id"], reason="availability").status_code == OK


@pytest.mark.req("B4-R06")
def test_tie_either_offer_needs_no_reason(admin: Oc) -> None:
    """Both members of a tie count as lowest."""
    inq, rfqs = admin.sent(("Alpha", "a1"), ("Beta", "b1"))
    ids = [admin.offer(r["id"], lines=prices(inq, "600", "700"))["id"] for r in rfqs]
    assert pick(admin, inq, ids[1]).status_code == OK


# --- B4-R07: status flow ------------------------------------------------------------------------


@pytest.mark.req("B4-R07")
def test_first_selection_transitions_and_reselection_keeps_status(admin: Oc) -> None:
    """Offers received -> Winner selected once; the second selection keeps the status."""
    inq, low, high = two(admin)
    r = pick(admin, inq, low["id"])
    assert r.status_code == OK, r.text
    first = r.json()
    assert (first["status"], first["version"]) == ("winner_selected", inq["version"] + 1)
    r = pick(admin, inq, high["id"], reason="reliability")
    second = r.json()
    assert (second["status"], second["version"]) == ("winner_selected", first["version"] + 1)
    assert second["winner_counterparty_name"] == "Beta Marine"
    rows = admin.api(f"/inquiries/{inq['id']}/comparison")["rows"]
    assert [(r["selected"], r["delta_to_lowest"]) for r in rows] == [
        (False, "0.00"),
        (True, "25000.00"),
    ]
    same = pick(admin, inq, high["id"], reason="reliability")  # same decision: no write
    assert same.json()["version"] == second["version"]
    assert [e.action for e in admin.trail("inquiry", inq["id"])][-2:] == [
        "select_winner",
        "select_winner",
    ]


@pytest.mark.req("B4-R07")
@pytest.mark.parametrize("state", ["draft", "nominated", "cancelled"])
def test_wrong_status_is_409_for_entry_and_selection(admin: Oc, state: str) -> None:
    """Draft, Nominated and Cancelled inquiries take neither offers nor a winner."""
    inq, rfqs = admin.sent(("Alpha", "a1"), ("Beta", "b1"))
    off = admin.offer(rfqs[0]["id"], lines=prices(inq, "600", "700"))
    set_status(admin, inq["id"], state)
    r = admin.put(rfqs[1]["id"])
    assert (r.status_code, r.json()["detail"]) == (CONFLICT, f"Inquiry is {state}")
    r = pick(admin, inq, off["id"])
    assert (r.status_code, r.json()["detail"]) == (CONFLICT, f"Inquiry is {state}")


@pytest.mark.req("B4-R07")
def test_selection_needs_offers_received_and_a_current_version(admin: Oc) -> None:
    """A stale version is 409; an unknown inquiry is 404."""
    inq, low, _ = two(admin)
    body = {"version": inq["version"] - 1, "offer_id": low["id"]}
    r = admin.http.post(f"/api/v1/inquiries/{inq['id']}/select-winner", json=body)
    assert r.status_code == CONFLICT
    r = admin.http.post(f"/api/v1/inquiries/{uuid.uuid4()}/select-winner", json=body)
    assert r.status_code == 404  # noqa: PLR2004


# --- B4-R08: validity, locking, decided total ---------------------------------------------------


@pytest.mark.req("B4-R08")
def test_expired_offer_is_422_until_extended(admin: Oc) -> None:
    """valid_until in the past: 422 on offer_id; extending it makes it selectable."""
    inq, rfqs = admin.sent()
    off = admin.offer(rfqs[0]["id"], lines=prices(inq, "600", "700"), valid_until=PAST)
    r = pick(admin, inq, off["id"])
    assert (r.status_code, errors(r)) == (UNPROCESSABLE, {"offer_id": "Offer has expired"})
    r = admin.http.patch(f"/api/v1/offers/{off['id']}", json={"version": 1, "valid_until": VALID})
    assert r.status_code == OK
    assert pick(admin, inq, off["id"]).status_code == OK


@pytest.mark.req("B4-R08")
def test_offer_of_another_inquiry_is_422(admin: Oc) -> None:
    """An offer id from elsewhere (or random) is 422 on offer_id."""
    inq, _, _ = two(admin)
    other_inq, [rfq] = admin.sent()
    foreign = admin.offer(rfq["id"], lines=prices(other_inq, "600", "700"))
    for ident in (foreign["id"], str(uuid.uuid4())):
        r = pick(admin, inq, ident)
        assert errors(r) == {"offer_id": "Not an offer of this inquiry"}


@pytest.mark.req("B4-R08")
def test_selected_offer_is_locked_and_decided_total_is_frozen(admin: Oc) -> None:
    """The winner cannot be edited (409); editing another offer leaves decided_total alone."""
    inq, low, high = two(admin)
    assert pick(admin, inq, low["id"]).status_code == OK
    url = f"/api/v1/offers/{low['id']}"
    r = admin.http.patch(url, json={"version": 1, "barging_cost": "5"})
    assert (r.status_code, r.json()["detail"]) == (CONFLICT, "Selected offer is locked")
    r = admin.http.patch(
        f"/api/v1/offers/{high['id']}", json={"version": 1, "lines": prices(inq, "1", "1")}
    )
    assert r.status_code == OK
    assert admin.fresh(inq)["decision"]["decided_total"] == "650000.00"
    assert admin.api(f"/inquiries/{inq['id']}/comparison")["decision"]["decided_total"] == (
        "650000.00"
    )
    # Re-selecting after the other offer got cheaper needs a reason now, and updates the total.
    assert pick(admin, inq, low["id"]).status_code == UNPROCESSABLE


@pytest.mark.req("B4-R08")
def test_declined_rfq_offer_can_be_edited_but_not_selected(admin: Oc) -> None:
    """Ruling R4: editing after a decline is allowed; selecting that offer is 422 on offer_id."""
    inq, rfqs = admin.sent(("Alpha", "a1"), ("Beta", "b1"))
    off = admin.offer(rfqs[0]["id"], lines=prices(inq, "600", "700"))
    admin.offer(rfqs[1]["id"], lines=prices(inq, "650", "700"))
    r = admin.http.post(f"/api/v1/rfqs/{rfqs[0]['id']}/decline", json={"version": 2})
    assert r.status_code == OK, r.text
    r = admin.http.patch(f"/api/v1/offers/{off['id']}", json={"version": 1, "payment_terms": "x"})
    assert r.status_code == OK
    r = pick(admin, inq, off["id"])
    assert (r.status_code, errors(r)) == (UNPROCESSABLE, {"offer_id": "RFQ is declined"})
    rows = admin.api(f"/inquiries/{inq['id']}/comparison")["rows"]
    assert {r["offer_id"]: r["rfq_status"] for r in rows}[off["id"]] == "declined"


# --- Review Focus 4 and 5 -----------------------------------------------------------------------


@pytest.mark.req("B4-R11")
def test_concurrent_selections_one_wins(admin: Oc) -> None:
    """Two buyers pick different winners at once: one 200, one 409, one decision, one entry."""
    inq, low, high = two(admin)
    before = len(admin.trail("inquiry", inq["id"]))

    def go(offer_id: str) -> int:
        body = {"version": inq["version"], "offer_id": offer_id, "reason": "timing"}
        r = admin.http.post(f"/api/v1/inquiries/{inq['id']}/select-winner", json=body)
        return int(r.status_code)

    with ThreadPoolExecutor(2) as pool:
        codes = sorted(pool.map(go, [low["id"], high["id"]]))
    assert codes == [OK, CONFLICT]
    entries = [e for e in admin.trail("inquiry", inq["id"]) if e.action == "select_winner"]
    assert len(entries) == 1
    assert len(admin.trail("inquiry", inq["id"])) == before + 1
    assert admin.fresh(inq)["version"] == inq["version"] + 1


@pytest.mark.req("B4-R11")
def test_one_audit_entry_per_selection(admin: Oc) -> None:
    """Each real selection writes exactly one inquiry entry with the status move on the first."""
    inq, low, high = two(admin)
    before = len(admin.trail("inquiry", inq["id"]))
    pick(admin, inq, low["id"])
    [first] = admin.trail("inquiry", inq["id"])[before:]
    assert first.action == "select_winner"
    assert first.changes["status"] == {"before": "offers_received", "after": "winner_selected"}
    assert first.changes["decided_total"]["after"] == "650000"
    pick(admin, inq, high["id"], reason="flexibility")
    [_, second] = admin.trail("inquiry", inq["id"])[before:]
    assert "status" not in second.changes
    assert second.changes["winner_counterparty"] == {
        "before": "Alpha Marine",
        "after": "Beta Marine",
    }


@pytest.mark.req("B4-R08")
def test_decision_survives_a_deactivated_counterparty(admin: Oc, world: SimpleNamespace) -> None:
    """Review focus 5: the decision and the name stay after the supplier is deactivated."""
    inq, low, _ = two(admin)
    pick(admin, inq, low["id"])
    deactivate(world, admin.engine, Counterparty, world.cp["Alpha"])
    out = admin.fresh(inq)
    assert out["winner_counterparty_name"] == "Alpha Marine"
    assert out["decision"]["decided_total"] == "650000.00"
    row = admin.api(f"/inquiries/{inq['id']}/comparison")["rows"][0]
    assert (row["counterparty_name"], row["selected"]) == ("Alpha Marine", True)
    assert admin.listing()[0]["winner_counterparty_name"] == "Alpha Marine"


@pytest.mark.req("B4-R08")
def test_inactive_product_does_not_break_the_comparison(admin: Oc, world: SimpleNamespace) -> None:
    """Review focus 2: totals stay computable when a product is deactivated afterwards."""
    inq, low, _ = two(admin)
    with org_session(admin.w.org, admin.engine) as s:
        s.execute(update(Product).where(Product.id == world.hsfo).values(active=False))
    rows = admin.api(f"/inquiries/{inq['id']}/comparison")["rows"]
    assert [r["total"] for r in rows] == ["650000.00", "675000.00"]
    assert pick(admin, inq, low["id"]).status_code == OK
    with org_session(admin.w.org, admin.engine) as s:
        assert s.get(Inquiry, uuid.UUID(inq["id"])) is not None


# --- Ruling R5: only selectable offers are ranked -----------------------------------------------


def lowest_ids(admin: Oc, inq: Json) -> tuple[set[str], dict[str, str | None]]:
    """Return the ids flagged lowest and every offer's delta."""
    rows = admin.api(f"/inquiries/{inq['id']}/comparison")["rows"]
    return (
        {r["offer_id"] for r in rows if r["lowest"]},
        {r["offer_id"]: r["delta_to_lowest"] for r in rows},
    )


@pytest.mark.req("B4-R05")
def test_expired_cheapest_offer_is_not_lowest(admin: Oc) -> None:
    """The next cheapest becomes lowest and needs no rationale; deltas follow it."""
    inq, rfqs = admin.sent(("Alpha", "a1"), ("Beta", "b1"), ("Gamma", "c1"))
    cheap = admin.offer(rfqs[0]["id"], lines=prices(inq, "600", "700"), valid_until=PAST)
    next_ = admin.offer(rfqs[1]["id"], lines=prices(inq, "650", "700"))
    dear = admin.offer(rfqs[2]["id"], lines=prices(inq, "700", "700"))
    low, deltas = lowest_ids(admin, inq)
    assert low == {next_["id"]}
    assert deltas == {cheap["id"]: "-25000.00", next_["id"]: "0.00", dear["id"]: "25000.00"}
    assert pick(admin, inq, cheap["id"]).status_code == UNPROCESSABLE
    assert pick(admin, inq, next_["id"]).status_code == OK
    assert pick(admin, inq, dear["id"]).status_code == UNPROCESSABLE  # needs a reason


@pytest.mark.req("B4-R05")
def test_declined_cheapest_offer_is_not_lowest(admin: Oc) -> None:
    """Same for an offer whose RFQ was declined."""
    inq, rfqs = admin.sent(("Alpha", "a1"), ("Beta", "b1"))
    cheap = admin.offer(rfqs[0]["id"], lines=prices(inq, "600", "700"))
    next_ = admin.offer(rfqs[1]["id"], lines=prices(inq, "650", "700"))
    r = admin.http.post(f"/api/v1/rfqs/{rfqs[0]['id']}/decline", json={"version": 2})
    assert r.status_code == OK, r.text
    low, _ = lowest_ids(admin, inq)
    assert low == {next_["id"]}
    assert pick(admin, inq, cheap["id"], reason="timing").status_code == UNPROCESSABLE
    assert pick(admin, inq, next_["id"]).status_code == OK


@pytest.mark.req("B4-R05")
def test_nothing_selectable_means_no_lowest(admin: Oc) -> None:
    """All complete offers expired or declined: no lowest, null deltas, nothing selectable."""
    inq, rfqs = admin.sent(("Alpha", "a1"), ("Beta", "b1"))
    old = admin.offer(rfqs[0]["id"], lines=prices(inq, "600", "700"), valid_until=PAST)
    gone = admin.offer(rfqs[1]["id"], lines=prices(inq, "650", "700"))
    admin.http.post(f"/api/v1/rfqs/{rfqs[1]['id']}/decline", json={"version": 2})
    low, deltas = lowest_ids(admin, inq)
    assert low == set()
    assert deltas == {old["id"]: None, gone["id"]: None}
    for off in (old, gone):
        r = pick(admin, inq, off["id"], reason="other", note="x")
        assert r.status_code == UNPROCESSABLE
        assert list(errors(r)) == ["offer_id"]
