"""Dashboard API: attention items, status counts, month figures, role filtering (B5-R03/R07/R08)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import update

from nautical_deliverance.domain.identity import Role
from nautical_deliverance.persistence import dashboard_repo
from nautical_deliverance.persistence.db import org_session
from nautical_deliverance.persistence.models import Inquiry, Offer, Rfq
from tests.db.test_inquiry_api import NOW, line
from tests.db.test_nomination_api import Nc, won
from tests.db.test_offer_api import prices, set_status
from tests.db.test_offer_decision import pick, two
from tests.db.test_rfq_api import rfq_world

if TYPE_CHECKING:
    from types import SimpleNamespace

    from sqlalchemy import Engine

    from nautical_deliverance.settings import Settings

type Json = Any

SEC = timedelta(seconds=1)
H24, H48 = timedelta(hours=24), timedelta(hours=48)
ETA, DEADLINE, VALIDITY, DRAFTS = (
    "eta_unnominated",
    "rfq_deadline",
    "offer_validity",
    "rfq_drafts_unsent",
)
OPEN = ("draft", "rfq_sent", "offers_received", "winner_selected")
ALPHA, BETA = ("Alpha", "a1"), ("Beta", "b1")
SECOND = 2


@pytest.fixture
def world(app_engine: Engine) -> SimpleNamespace:
    """World with suppliers."""
    return rfq_world(app_engine)


@pytest.fixture
def admin(settings: Settings, app_engine: Engine, world: SimpleNamespace) -> Nc:
    """Admin client."""
    return Nc(settings, app_engine, world, Role.ADMIN)


def setf(admin: Nc, model: type, row_id: str, **values: Any) -> None:  # noqa: ANN401
    """Set columns directly in the database (move a threshold without the API's rules)."""
    with org_session(admin.w.org, admin.engine) as s:
        s.execute(update(model).where(model.id == uuid.UUID(row_id)).values(**values))  # type: ignore[attr-defined]


def kinds(admin: Nc, inq: Json) -> set[str]:
    """Attention kinds the dashboard shows for one inquiry."""
    return {i["kind"] for i in admin.api("/dashboard")["attention"] if i["inquiry_id"] == inq["id"]}


# --- B5-R07: attention --------------------------------------------------------------------------


@pytest.mark.req("B5-R07")
def test_eta_threshold_and_passed_eta(admin: Nc) -> None:
    """B2 rule: within 48 h counts, exactly 48 h and later does not, a passed ETA still does."""
    inq = admin.create()
    for delta, shown in ((H48 - SEC, True), (H48, False), (H48 + SEC, False), (-3 * H48, True)):
        setf(admin, Inquiry, inq["id"], eta=NOW + delta)
        assert (kinds(admin, inq) == {ETA}) is shown, delta
    setf(admin, Inquiry, inq["id"], eta=None)
    assert kinds(admin, inq) == set()


@pytest.mark.req("B5-R07")
def test_rfq_deadline_threshold_and_answered(admin: Nc) -> None:
    """A sent RFQ without offer inside 24 h shows; an offer, or time beyond 24 h, removes it."""
    inq, [rfq] = admin.sent(ALPHA)
    for delta, shown in ((H24 - SEC, True), (H24, False), (H24 + SEC, False), (-H24, True)):
        setf(admin, Rfq, rfq["id"], response_deadline=NOW + delta)
        assert (kinds(admin, inq) == {DEADLINE}) is shown, delta
    setf(admin, Rfq, rfq["id"], response_deadline=NOW + H24 - SEC)
    item = next(i for i in admin.api("/dashboard")["attention"] if i["kind"] == DEADLINE)
    assert item["due_at"].startswith("2026-11-06T11:59:59")
    admin.offer(rfq["id"], lines=prices(inq, "600", "700"))
    assert kinds(admin, inq) == set()


@pytest.mark.req("B5-R07")
def test_validity_of_lowest_selectable_without_winner(admin: Nc) -> None:
    """Without a winner the lowest selectable offer counts; a dearer offer's validity does not."""
    inq, low, high = two(admin)
    setf(admin, Offer, high["id"], valid_until=NOW + SEC)
    assert kinds(admin, inq) == set()
    for delta, shown in ((H24 - SEC, True), (H24, False), (H24 + SEC, False)):
        setf(admin, Offer, low["id"], valid_until=NOW + delta)
        assert (kinds(admin, inq) == {VALIDITY}) is shown, delta


@pytest.mark.req("B5-R07")
def test_validity_of_winner_until_nominated(admin: Nc) -> None:
    """The selected offer counts, a dearer one does not; sending the nomination resolves it."""
    inq = won(admin)
    rows = admin.api(f"/inquiries/{inq['id']}/comparison")["rows"]
    winner, other = (
        next(r["id"] for r in rows if r["total"] == t) for t in ("650000.00", "675000.00")
    )
    setf(admin, Offer, other, valid_until=NOW + SEC)
    assert kinds(admin, inq) == set()
    for delta, shown in ((H24 - SEC, True), (H24 + SEC, False)):
        setf(admin, Offer, winner, valid_until=NOW + delta)
        assert (kinds(admin, inq) == {VALIDITY}) is shown, delta
    setf(admin, Offer, winner, valid_until=NOW + SEC)
    admin.send(admin.nominate(inq["id"]))
    assert kinds(admin, inq) == set()


@pytest.mark.req("B5-R07")
def test_eta_resolved_by_sending_the_nomination(admin: Nc) -> None:
    """An imminent ETA shows until the first nomination is sent."""
    inq = won(admin)
    setf(admin, Inquiry, inq["id"], eta=NOW + SEC)
    assert kinds(admin, inq) == {ETA}
    nom = admin.nominate(inq["id"])
    assert kinds(admin, inq) == {ETA}
    admin.send(nom)
    assert kinds(admin, inq) == set()


@pytest.mark.req("B5-R07")
def test_unsent_rfq_drafts(admin: Nc) -> None:
    """RFQ drafts show while the inquiry can still send them, and go once all are sent."""
    inq = admin.create()
    assert kinds(admin, inq) == set()
    [rfq] = admin.make(inq["id"], ALPHA)
    assert kinds(admin, inq) == {DRAFTS}
    admin.http.post(f"/api/v1/rfqs/{rfq['id']}/mark-sent", json={"version": 1})
    assert kinds(admin, inq) == set()


@pytest.mark.req("B5-R07")
def test_cancelled_inquiry_has_no_items(admin: Nc) -> None:
    """Review focus 3: whatever was due, a cancelled inquiry drops out of the list."""
    inq = admin.create()
    admin.make(inq["id"], ALPHA)
    setf(admin, Inquiry, inq["id"], eta=NOW + SEC)
    assert kinds(admin, inq) == {ETA, DRAFTS}
    set_status(admin, inq["id"], "cancelled")
    assert kinds(admin, inq) == set()
    assert admin.api("/dashboard")["status_counts"]["cancelled"] == 1


@pytest.mark.req("B5-R07")
def test_attention_is_ordered_by_due_time(admin: Nc) -> None:
    """Earliest due first; items without a due time (drafts) last."""
    a, b = admin.create(), admin.create()
    admin.make(b["id"], ALPHA)
    setf(admin, Inquiry, a["id"], eta=NOW + 2 * H24 - SEC)
    setf(admin, Inquiry, b["id"], eta=NOW + H24)
    got = [(i["inquiry_id"], i["kind"]) for i in admin.api("/dashboard")["attention"]]
    assert got == [(b["id"], ETA), (a["id"], ETA), (b["id"], DRAFTS)]


# --- B5-R08: figures ----------------------------------------------------------------------------

type Offers = list[tuple[tuple[str, str], tuple[str, ...]]]


def decide(admin: Nc, lines: list[Json], offers: Offers, **over: Any) -> Json:  # noqa: ANN401
    """Inquiry with `lines`, one sent RFQ and offer per entry (key, prices); the first one wins."""
    inq = admin.create(lines=lines)
    rfqs = admin.make(inq["id"], *[key for key, _ in offers])
    for r in rfqs:
        assert admin.http.post(f"/api/v1/rfqs/{r['id']}/mark-sent", json={"version": 1}).is_success
    made = [
        admin.offer(r["id"], lines=prices(inq, *p), **over)
        for r, (_, p) in zip(rfqs, offers, strict=True)
    ]
    assert pick(admin, inq, made[0]["id"], reason="other", note="n").is_success
    return admin.fresh(inq)


def nominate(admin: Nc, inq: Json) -> Json:
    """Create and send a nomination at the client's clock."""
    return admin.send(admin.nominate(inq["id"]))


def month_dataset(admin: Nc) -> None:
    """Build a fixed November: 3 nominated, 1 decided only, 1 older, a draft, a cancelled."""
    w = admin.w
    mgo = str(w.mgo)
    admin.now = datetime(2026, 10, 31, 12, tzinfo=UTC)
    nominate(admin, decide(admin, [line(w)], [(ALPHA, ("600",))]))  # decided, nominated in October
    e = decide(
        admin, [line(w), line(w, product_id=mgo)], [(ALPHA, ("600", "700")), (BETA, ("650", "700"))]
    )
    admin.now = NOW
    nominate(admin, e)  # E: decided in October, nominated in November
    a = decide(  # A: an m3 line with an exact, non-3-decimal conversion
        admin,
        [line(w), line(w, product_id=mgo, quantity="100.123", unit="m3", density="850.5")],
        [(ALPHA, ("600", "700")), (BETA, ("650", "700"))],
    )
    nominate(admin, a)
    b = decide(  # B: an m3 line with no density anywhere is left out of volume and cost
        admin,
        [line(w, quantity="200"), line(w, product_id=mgo, quantity="50", unit="m3")],
        [(ALPHA, ("610", "700"))],
    )
    nominate(admin, b)
    decide(admin, [line(w)], [(ALPHA, ("600",)), (BETA, ("650",))])  # C: decided, not nominated
    admin.create()  # F: draft
    set_status(admin, admin.create()["id"], "cancelled")  # G


@pytest.mark.req("B5-R08")
def test_month_figures_on_a_fixed_data_set(admin: Nc) -> None:
    """Exact mt (incl. m3 conversion), spend, counts and average offers."""
    month_dataset(admin)
    dash = admin.api("/dashboard")
    assert dash["month"] == {
        "period": "2026-11",
        "nominated_mt": "1785.1546115",  # 585.1546115 (A) + 200.000 (B) + 1000.000 (E)
        "mt_excluded_lines": 1,
        "nominated_spend": "1131608.23",  # 359,608.23 + 122,000.00 + 650,000.00
        "currency": "USD",
        "open_by_status": {"draft": 1, "rfq_sent": 0, "offers_received": 0, "winner_selected": 1},
        "avg_offers": "1.67",  # (A 2 + B 1 + C 2) / 3 decided in November
    }
    assert dash["status_counts"] == {
        "draft": 1,
        "rfq_sent": 0,
        "offers_received": 0,
        "winner_selected": 1,
        "nominated": 4,
        "cancelled": 1,
    }


@pytest.mark.req("B5-R08")
def test_empty_month(admin: Nc) -> None:
    """No decided inquiry: zero figures and a null average, never an error."""
    assert admin.api("/dashboard")["month"] == {
        "period": "2026-11",
        "nominated_mt": "0.000",
        "mt_excluded_lines": 0,
        "nominated_spend": "0.00",
        "currency": "USD",
        "avg_offers": None,
        "open_by_status": dict.fromkeys(OPEN, 0),
    }


@pytest.mark.req("B5-R08")
def test_month_boundary_follows_the_first_nomination(admin: Nc) -> None:
    """Review focus 4: 23:59:59 on 30 Nov is November; a December amendment moves nothing."""
    admin.now = NOW + timedelta(days=1)
    inq = decide(admin, [line(admin.w)], [(ALPHA, ("600",))], valid_until="2026-12-31T00:00:00Z")
    last = datetime(2026, 11, 30, 23, 59, 59, tzinfo=UTC)
    admin.now = last
    nominate(admin, inq)
    assert admin.api("/dashboard")["month"]["nominated_spend"] == "300000.00"
    admin.now = last + SEC
    december = admin.api("/dashboard")["month"]
    assert (december["period"], december["nominated_spend"]) == ("2026-12", "0.00")
    assert nominate(admin, inq)["sequence"] == SECOND
    assert admin.api("/dashboard")["month"]["nominated_spend"] == "0.00"
    admin.now = last
    assert admin.api("/dashboard")["month"]["nominated_spend"] == "300000.00"


@pytest.mark.req("B5-R08")
@pytest.mark.parametrize(
    ("total", "count", "expected"),
    [(0, 0, None), (5, 3, "1.67"), (13, 8, "1.63"), (1, 8, "0.13"), (4, 2, "2.00")],
)
def test_average_rounds_half_up(total: int, count: int, expected: str | None) -> None:
    """13/8 = 1.625 is 1.63 (half-up, not banker's); no inquiries gives None."""
    assert dashboard_repo.average(total, count) == expected


# --- B5-R03: roles ------------------------------------------------------------------------------


@pytest.mark.req("B5-R03")
@pytest.mark.parametrize("role", list(Role))
def test_dashboard_per_role(
    settings: Settings, app_engine: Engine, world: SimpleNamespace, admin: Nc, role: Role
) -> None:
    """Everyone may read it; the Operator gets status counts and ETA items only, no month."""
    inq, low, _ = two(admin)
    admin.make(admin.create()["id"], ALPHA)
    setf(admin, Inquiry, inq["id"], eta=NOW + SEC)
    setf(admin, Offer, low["id"], valid_until=NOW + SEC)
    dash = Nc(settings, app_engine, world, role).api("/dashboard")
    assert set(dash) == {"attention", "status_counts", "month"}
    if role is not Role.OPERATOR:
        assert {i["kind"] for i in dash["attention"]} == {ETA, VALIDITY, DRAFTS}
        assert dash["month"]["period"] == "2026-11"
        return
    assert dash["month"] is None
    [item] = dash["attention"]
    assert item["kind"] == ETA
    assert item["detail"] is None
    assert set(item) == {
        *("inquiry_id", "reference", "vessel_name", "port_name"),
        *("kind", "due_at", "detail"),
    }
    assert dash["status_counts"]["offers_received"] == 1
