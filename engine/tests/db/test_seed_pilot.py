# ruff: noqa: PLR2004, S608
"""The pilot seed mode (B6-R04): Pilot Demo Shipping with demo directory users, demo data only."""

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    import uuid

from nautical_deliverance.domain.inquiry import eta_warning
from nautical_deliverance.domain.master import imo_valid
from nautical_deliverance.persistence import dashboard_repo, seed

NOW = datetime.now(UTC)
PILOT = next(iter(seed.PILOT_ORGS))
TABLES = (
    "organization", "app_user", "product", "vessel", "counterparty", "contact", "inquiry",
    "inquiry_line", "rfq", "offer", "offer_line", "nomination",
)  # fmt: skip
DENY = (
    "stena", "stormgeo", "zeronorth", "nereus", "maersk", "vitol", "monjasa", "glander",
    "peninsula", "minerva", "bunker holding", "tidewater",
)  # fmt: skip


@pytest.fixture(scope="module")
def seeded(owner_engine: Engine) -> Engine:
    """Engine with the pilot organization seeded at NOW."""
    seed.seed(owner_engine, "pilot", NOW)
    return owner_engine


def q(engine: Engine, org: uuid.UUID, sql: str) -> list[dict[str, Any]]:
    """Run ``sql`` scoped to ``org`` and return dict rows."""
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(org)})
        return [dict(r) for r in conn.execute(text(sql)).mappings()]


@pytest.mark.req("B6-R04")
def test_pilot_org_and_demo_users(seeded: Engine) -> None:
    """One organization, named Pilot Demo Shipping, with one invented `.example` user per role."""
    assert [r["name"] for r in q(seeded, PILOT, "SELECT name FROM organization")] == [
        "Pilot Demo Shipping"
    ]
    users = q(seeded, PILOT, "SELECT * FROM app_user")
    assert sorted(r["roles"][0] for r in users) == ["admin", "bunker_buyer", "operator", "viewer"]
    assert all(r["email"].endswith(".example") for r in users)


@pytest.mark.req("B6-R04")
def test_pilot_has_full_demo_coverage(seeded: Engine) -> None:
    """Master data, inquiries, RFQs, offers, an amended nomination, every attention kind."""
    n = {t: len(q(seeded, PILOT, f"SELECT 1 FROM {t}")) for t in TABLES}
    assert n["product"] == 8
    assert n["vessel"] >= 6
    imos = q(seeded, PILOT, "SELECT imo FROM vessel")
    assert all(imo_valid(r["imo"]) for r in imos)
    assert n["counterparty"] >= 8
    assert n["inquiry"] == 8
    assert n["rfq"] > 0
    assert n["offer"] > 0
    noms = q(seeded, PILOT, "SELECT sequence FROM nomination ORDER BY sequence")
    assert [r["sequence"] for r in noms] == [1, 2]
    assert all(
        r["email"].endswith(".example") for r in q(seeded, PILOT, "SELECT email FROM contact")
    )
    operators = q(seeded, PILOT, "SELECT DISTINCT operator_name FROM inquiry")
    assert {r["operator_name"] for r in operators} <= {"Olga Operator", "Per Ops"}
    with seeded.begin() as conn:
        conn.execute(text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(PILOT)})
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


@pytest.mark.req("B6-R04")
def test_pilot_is_idempotent_and_clean(seeded: Engine) -> None:
    """A second run changes no row, and no string names a real company (D-066)."""

    def dump() -> str:
        return json.dumps(
            {t: q(seeded, PILOT, f"SELECT * FROM {t} ORDER BY 1, 2") for t in TABLES}, default=str
        )

    before = dump()
    seed.seed(seeded, "pilot", NOW + timedelta(days=40))
    assert dump() == before
    assert not [d for d in DENY if d in before.lower()]


@pytest.mark.req("B6-R04")
def test_modes(owner_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pilot seeds only the pilot org, dev the dev orgs; unset seeds nothing, unknown raises."""
    orgs: list[Any] = []
    monkeypatch.setattr(seed, "seed_orgs", lambda _e, o: orgs.append(set(o)))
    monkeypatch.setattr(seed, "seed_demo_master", lambda *_a: None)
    monkeypatch.setattr(seed, "seed_demo_inquiries", lambda *_a: None)
    for mode in (None, "", "pilot", "dev"):
        seed.seed(owner_engine, mode)
    with pytest.raises(ValueError, match="unknown seed mode"):
        seed.seed(owner_engine, "prod")
    assert orgs == [set(seed.PILOT_ORGS), set(seed.DEV_ORGS)]


@pytest.mark.req("B6-R04")
def test_pilot_has_no_dev_names(seeded: Engine) -> None:
    """No text of any pilot-org row (every table, every column) mentions Acme or Borealis."""
    tables = [
        r["table_name"]
        for r in q(
            seeded,
            PILOT,
            "SELECT table_name FROM information_schema.columns"
            " WHERE table_schema = 'public' AND column_name = 'organization_id'",
        )
    ]
    assert {"vessel", "inquiry", "rfq", "offer", "nomination"} <= set(tables)
    for t in tables:
        blob = json.dumps(q(seeded, PILOT, f"SELECT x::text AS r FROM {t} x")).lower()
        assert "acme" not in blob
        assert "borealis" not in blob, t
