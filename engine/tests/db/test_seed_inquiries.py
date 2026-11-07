# ruff: noqa: PLR2004, S608
"""Demo users and inquiries (B2-R14): realistic, relative to seed time, idempotent."""

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    import uuid

from nautical_deliverance.domain.inquiry import eta_warning
from nautical_deliverance.domain.nomination import render_nomination
from nautical_deliverance.domain.offer import evaluate_offer, lowest
from nautical_deliverance.domain.rfq import render_rfq
from nautical_deliverance.persistence import dashboard_repo, nomination_repo, offer_repo, seed
from nautical_deliverance.persistence.models import Nomination, Offer, Rfq
from nautical_deliverance.persistence.rfq_repo import build_context, changed_since_sent

REALM = Path(__file__).parents[3] / "infra/keycloak/realm-dev.json"
REF = re.compile(r"INQ-(\d{4})-(\d{3})")
NOW = datetime.now(UTC)


@pytest.fixture(scope="module")
def seeded(owner_engine: Engine) -> Engine:
    """Engine with orgs, master data, users and inquiries seeded at NOW."""
    seed.seed_orgs(owner_engine)
    seed.seed_demo_master(owner_engine)
    seed.seed_demo_inquiries(owner_engine, NOW)
    return owner_engine


def q(engine: Engine, org: uuid.UUID, sql: str) -> list[dict[str, Any]]:
    """Run ``sql`` scoped to ``org`` and return dict rows."""
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(org)})
        return [dict(r) for r in conn.execute(text(sql)).mappings()]


@pytest.mark.req("B2-R14")
def test_users_match_realm(seeded: Engine) -> None:
    """The 8 realm users, with realm id (the Keycloak sub), name, e-mail and roles."""
    realm = json.loads(REALM.read_text(encoding="utf-8"))["users"]
    assert len(realm) == 8
    got: dict[str, dict[str, Any]] = {}
    for org in seed.DEV_ORGS:
        got |= {str(r["id"]): r for r in q(seeded, org, "SELECT * FROM app_user")}
    for u in realm:
        row = got[u["id"]]
        assert str(row["organization_id"]) == u["attributes"]["org_id"][0]
        assert row["name"] == f"{u['firstName']} {u['lastName']}"
        assert row["email"] == u["email"]
        assert row["roles"] == u["realmRoles"]


@pytest.mark.req("B2-R14")
@pytest.mark.parametrize("org", list(seed.DEV_ORGS))
def test_inquiry_variety(seeded: Engine, org: uuid.UUID) -> None:
    """>= 6 inquiries covering draft, unassigned, cancelled, m3+density, ETA < 48 h, warning."""
    inq = q(seeded, org, "SELECT * FROM inquiry")
    assert len(inq) >= 6
    drafts = [i for i in inq if i["status"] == "draft"]
    assert len(drafts) >= 3
    assert any(i["buyer_id"] is None for i in drafts)
    assert any(i["status"] == "cancelled" and i["cancel_reason"].strip() for i in inq)
    assert q(seeded, org, "SELECT 1 FROM inquiry_line WHERE unit = 'm3' AND density IS NOT NULL")
    assert any(NOW <= i["eta"] <= NOW + timedelta(hours=48) for i in inq)
    assert all(i["eta"] and i["etd"] and i["eta"] > NOW for i in inq if i["status"] != "cancelled")
    unapproved = q(
        seeded,
        org,
        "SELECT 1 FROM inquiry_line l JOIN inquiry i ON i.id = l.inquiry_id WHERE NOT EXISTS"
        " (SELECT 1 FROM vessel_approved_fuel f WHERE f.vessel_id = i.vessel_id"
        " AND f.product_id = l.product_id)",
    )
    assert unapproved
    per = q(seeded, org, "SELECT count(*) AS n FROM inquiry_line GROUP BY inquiry_id")
    assert all(1 <= p["n"] <= 10 for p in per)


@pytest.mark.req("B2-R14")
@pytest.mark.parametrize("org", list(seed.DEV_ORGS))
def test_references_and_counters(seeded: Engine, org: uuid.UUID) -> None:
    """References are INQ-yymm-nnn, gap-free per month, and match the counter."""
    month = NOW.strftime("%y%m")
    refs = sorted(r["reference"] for r in q(seeded, org, "SELECT reference FROM inquiry"))
    nums = [int(m[2]) for r in refs if (m := REF.fullmatch(r)) and m[1] == month]
    assert len(nums) == len(refs)
    assert nums == list(range(1, len(refs) + 1))
    counter = q(
        seeded,
        org,
        f"SELECT next_value FROM inquiry_reference_counter WHERE year_month = '{month}'",
    )
    assert counter[0]["next_value"] == len(refs) + 1


@pytest.mark.req("B2-R14")
def test_idempotent_and_unaudited(seeded: Engine) -> None:
    """A second run changes no row and writes no audit entry."""
    tables = (
        "app_user",
        "inquiry",
        "inquiry_line",
        "inquiry_reference_counter",
        "rfq",
        "offer",
        "offer_line",
        "nomination",
    )

    def dump() -> str:
        return json.dumps(
            {
                f"{o}/{t}": q(seeded, o, f"SELECT * FROM {t} ORDER BY 1, 2")
                for o in seed.DEV_ORGS
                for t in tables
            },
            default=str,
        )

    before = dump()
    seed.seed_demo_inquiries(seeded, NOW + timedelta(days=40))
    assert dump() == before
    assert all(not q(seeded, o, "SELECT 1 FROM audit_entry") for o in seed.DEV_ORGS)


@pytest.mark.req("B3-R14")
@pytest.mark.parametrize("org", list(seed.DEV_ORGS))
def test_demo_rfqs(seeded: Engine, org: uuid.UUID) -> None:
    """Sent RFQs on rfq_sent/offers_received, 2 drafts on one Draft, a decline, frozen text."""
    rows = q(
        seeded,
        org,
        "SELECT r.*, i.status AS istatus, i.version AS iversion FROM rfq r"
        " JOIN inquiry i ON i.id = r.inquiry_id",
    )
    for st in ("rfq_sent", "offers_received"):
        assert any(r["istatus"] == st and r["status"] == "sent" for r in rows)
    drafts = [r["inquiry_id"] for r in rows if r["status"] == "draft"]
    assert len(drafts) == 2
    assert len(set(drafts)) == 1
    assert any(r["status"] == "declined" for r in rows)
    active = [(r["inquiry_id"], r["counterparty_id"]) for r in rows if r["status"] != "withdrawn"]
    assert len(active) == len(set(active))
    sent = [r for r in rows if r["status"] in ("sent", "declined")]
    # the nominated demo inquiry's ETA was amended after its RFQ went out: its text is stale
    stale = [r for r in sent if r["istatus"] == "nominated"]
    assert stale
    for r in sent:
        assert (r in stale) == (r["inquiry_version_at_send"] < r["iversion"])
    with seeded.begin() as conn:
        conn.execute(text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(org)})
        s = Session(conn)
        for r in sent:
            rfq = s.get(Rfq, r["id"])
            assert rfq is not None
            ctx = build_context(s, rfq)
            assert ((rfq.sent_subject, rfq.sent_body) != render_rfq(ctx)) == (r in stale)
            assert changed_since_sent(s, rfq) == (r in stale)
            assert rfq.sent_to_email == ctx.recipient_email
    assert all(r["sent_to_email"].endswith(".example") for r in sent)
    emails = q(seeded, org, "SELECT email FROM contact")
    assert all(e["email"].endswith(".example") for e in emails)


@pytest.mark.req("B4-R13")
@pytest.mark.parametrize("org", list(seed.DEV_ORGS))
def test_demo_offers(seeded: Engine, org: uuid.UUID) -> None:
    """Offers on sent RFQs; complete, partial, expired; one decided non-lowest winner (B4-R13)."""
    offers = q(
        seeded,
        org,
        "SELECT o.*, r.status AS rstatus, i.status AS istatus FROM offer o"
        " JOIN rfq r ON r.id = o.rfq_id JOIN inquiry i ON i.id = o.inquiry_id",
    )
    assert {o["istatus"] for o in offers} >= {"offers_received", "winner_selected", "nominated"}
    assert all(o["rstatus"] == "sent" for o in offers)
    results: dict[Any, Any] = {}
    with seeded.begin() as conn:
        conn.execute(text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(org)})
        s = Session(conn)
        for o in offers:
            offer = s.get(Offer, o["id"])
            assert offer is not None
            results[o["id"]] = evaluate_offer(offer_repo.inputs_for(s, offer))
    assert any(r.complete for r in results.values())
    assert any(not r.complete for r in results.values())
    assert any(o["valid_until"] < NOW for o in offers)
    for o in offers:  # invented but plausible prices, USD per mt
        prices = q(seeded, org, f"SELECT price_per_mt FROM offer_line WHERE offer_id = '{o['id']}'")
        assert all(500 <= p["price_per_mt"] <= 1200 for p in prices)

    inquiries = q(seeded, org, "SELECT * FROM inquiry")
    for inq in inquiries:  # a selected or nominated inquiry always has its decision
        assert (inq["status"] in ("winner_selected", "nominated")) <= bool(inq["winner_offer_id"])
    non_lowest = 0
    for inq in (i for i in inquiries if i["winner_offer_id"]):
        assert inq["decided_at"]
        assert inq["decided_by"]
        winner = next(o for o in offers if o["id"] == inq["winner_offer_id"])
        assert winner["inquiry_id"] == inq["id"]
        assert inq["decided_total"] == results[winner["id"]].total
        selectable = [  # R5: complete offers selectable now
            o["id"]
            for o in offers
            if o["inquiry_id"] == inq["id"]
            and o["valid_until"] >= NOW
            and results[o["id"]].complete
        ]
        assert selectable
        if str(winner["id"]) not in lowest(results[i] for i in selectable):
            non_lowest += 1
            assert inq["status"] == "winner_selected"
            assert inq["decision_reason"]
            assert inq["decision_note"]
    assert non_lowest == 1


@pytest.mark.req("B4-R13")
def test_demo_offers_idempotent(seeded: Engine) -> None:
    """A second run adds no offer."""

    def count() -> int:
        return sum(q(seeded, o, "SELECT count(*) AS n FROM offer")[0]["n"] for o in seed.DEV_ORGS)

    before = count()
    assert before > 0
    seed.seed_demo_inquiries(seeded, NOW + timedelta(days=40))
    assert count() == before


@pytest.mark.req("B5-R12")
@pytest.mark.parametrize("org", list(seed.DEV_ORGS))
def test_demo_nominations(seeded: Engine, org: uuid.UUID) -> None:
    """DEMO-6 has sent nominations 1 and 2; 2 follows an ETA change; texts equal the render."""
    rows = q(
        seeded,
        org,
        "SELECT n.id, n.sequence, n.status, n.sent_at, n.inquiry_version_at_send, n.sent_body,"
        " i.version AS iversion, i.decided_total, i.voyage FROM nomination n"
        " JOIN inquiry i ON i.id = n.inquiry_id ORDER BY n.sequence",
    )
    assert [(r["voyage"], r["sequence"], r["status"]) for r in rows] == [
        ("DEMO-6", 1, "sent"),
        ("DEMO-6", 2, "sent"),
    ]
    one, two = rows
    assert one["inquiry_version_at_send"] < two["inquiry_version_at_send"] == two["iversion"]
    assert one["sent_at"]
    assert two["sent_at"]
    assert one["sent_body"] != two["sent_body"]
    with seeded.begin() as conn:
        conn.execute(text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(org)})
        s = Session(conn)
        for r in rows:
            nom = s.get(Nomination, r["id"])
            assert nom is not None
            ctx = nomination_repo.build_nomination_context(s, nom)
            assert ctx.total == r["decided_total"]
            if r["sequence"] == 2:
                assert (nom.sent_subject, nom.sent_body) == render_nomination(ctx)
        assert nomination_repo.changed_since_sent(s, s.get(Nomination, one["id"]))  # type: ignore[arg-type]
        assert not nomination_repo.changed_since_sent(s, s.get(Nomination, two["id"]))  # type: ignore[arg-type]


@pytest.mark.req("B5-R12")
@pytest.mark.parametrize("org", list(seed.DEV_ORGS))
def test_demo_dashboard_has_every_attention_kind(seeded: Engine, org: uuid.UUID) -> None:
    """On fresh demo data the dashboard shows at least one item of each kind."""
    with seeded.begin() as conn:
        conn.execute(text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(org)})
        s = Session(conn)
        found = {
            i["kind"]
            for i in (
                *dashboard_repo.eta_items(s, NOW, eta_warning),
                *dashboard_repo.rfq_items(s, NOW),
                *dashboard_repo.validity_items(s, NOW),
            )
        }
    assert found == {"eta_unnominated", "rfq_deadline", "offer_validity", "rfq_drafts_unsent"}
