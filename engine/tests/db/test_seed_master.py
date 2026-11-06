# ruff: noqa: PLR2004, S608
"""The demo master-data seed (B1-R10): realistic, invented, idempotent, per organization."""

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import Engine, text

if TYPE_CHECKING:
    import uuid

from nautical_deliverance.domain.master import imo_valid, locode_valid, tz_valid
from nautical_deliverance.persistence import seed
from nautical_deliverance.persistence.db import org_session
from nautical_deliverance.persistence.master_repo import counterparties_covering

TABLES = (
    "product", "iso_spec_version", "bunkering_reason", "legal_entity", "vessel",
    "vessel_approved_fuel", "port", "counterparty", "contact", "coverage",
)  # fmt: skip
# Pilot company, plus the incumbent platforms (case-insensitive).
DENY = (
    "stena", "stormgeo", "zeronorth", "nereus", "maersk", "vitol", "monjasa", "glander",
    "peninsula", "minerva", "bunker holding", "tidewater",
)  # fmt: skip


@pytest.fixture(scope="module")
def seeded(owner_engine: Engine) -> Engine:
    """Engine with both dev organizations and their master data seeded."""
    seed.seed_dev_orgs(owner_engine)
    seed.seed_demo_master(owner_engine)
    return owner_engine


def q(engine: Engine, org: uuid.UUID, sql: str) -> list[dict[str, Any]]:
    """Run ``sql`` scoped to ``org`` and return dict rows."""
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(org)})
        return [dict(r) for r in conn.execute(text(sql)).mappings()]


@pytest.mark.req("B1-R10")
@pytest.mark.parametrize("org", list(seed.DEV_ORGS))
def test_counts_and_validity(seeded: Engine, org: uuid.UUID) -> None:
    """Minimum volumes, valid IMOs/LOCODEs/zones, `.example` e-mails."""
    n = {t: len(q(seeded, org, f"SELECT 1 FROM {t}")) for t in TABLES}
    assert n["product"] == 8
    assert n["iso_spec_version"] == 5
    assert n["bunkering_reason"] == 3
    assert n["legal_entity"] >= 2
    assert n["vessel"] >= 6
    assert n["port"] >= 10
    assert n["counterparty"] >= 8
    assert all(imo_valid(r["imo"]) for r in q(seeded, org, "SELECT imo FROM vessel"))
    ports = q(seeded, org, "SELECT locode, time_zone FROM port")
    assert all(locode_valid(p["locode"]) and tz_valid(p["time_zone"]) for p in ports)
    emails = q(seeded, org, "SELECT email FROM contact")
    assert emails
    assert all(e["email"].endswith(".example") for e in emails)
    types = {r["type"] for r in q(seeded, org, "SELECT type FROM counterparty")}
    assert types == {"physical_supplier", "trader", "both"}
    assert n["contact"] >= n["counterparty"]
    assert n["coverage"] > 0


@pytest.mark.req("B1-R10")
@pytest.mark.parametrize("org", list(seed.DEV_ORGS))
def test_domain_cases(seeded: Engine, org: uuid.UUID) -> None:
    """A non-biofuel vessel, a trader with a supplier relationship, all+some suggestions."""
    no_bio = q(
        seeded,
        org,
        "SELECT v.id FROM vessel v WHERE NOT EXISTS (SELECT 1 FROM vessel_approved_fuel f"
        " JOIN product p ON p.id = f.product_id WHERE f.vessel_id = v.id AND p.name ILIKE '%bio%')",
    )
    assert no_bio
    traders = q(seeded, org, "SELECT notes FROM counterparty WHERE type = 'trader'")
    assert any("supplier" in (t["notes"] or "").lower() for t in traders)
    ports = q(seeded, org, "SELECT id FROM port")
    prods = [
        p["id"]
        for p in q(seeded, org, "SELECT id FROM product WHERE name IN ('VLSFO 0.5%', 'DMA 0.1%')")
    ]
    assert len(prods) == 2
    with org_session(org, seeded) as s:
        found = [
            (
                counterparties_covering(s, p["id"], prods, mode="all"),
                counterparties_covering(s, p["id"], prods, mode="some"),
            )
            for p in ports
        ]
    assert any(a and b for a, b in found)


@pytest.mark.req("B1-R10")
@pytest.mark.parametrize("org", list(seed.DEV_ORGS))
def test_spec_catalogue_and_fictional_phones(seeded: Engine, org: uuid.UUID) -> None:
    """Spec §3.1 products (all mt) and reasons exactly; phones only Ofcom drama numbers (M5)."""
    prods = {(r["name"], r["default_unit"]) for r in q(seeded, org, "SELECT * FROM product")}
    assert prods == {
        (n, "mt")
        for n in (
            "HSFO 3.5%", "VLSFO 0.5%", "DMA 0.1%", "Biofuel", "B24", "B30", "B100",
            "Bio diesel FAME",
        )
    }  # fmt: skip
    reasons = {r["name"] for r in q(seeded, org, "SELECT name FROM bunkering_reason")}
    assert reasons == {"Bunkers only", "Working cargo", "Debunkering"}
    phones = [r["phone"] for r in q(seeded, org, "SELECT phone FROM contact")]
    assert all(p is None or re.fullmatch(r"\+44 20 7946 0\d{3}", p) for p in phones)


@pytest.mark.req("B1-R10")
def test_orgs_have_own_data(seeded: Engine) -> None:
    """Counterparty and vessel names differ between the two organizations."""
    a, b = seed.DEV_ORGS
    for sql in ("SELECT name FROM counterparty", "SELECT name FROM vessel"):
        assert {r["name"] for r in q(seeded, a, sql)}.isdisjoint(
            r["name"] for r in q(seeded, b, sql)
        )


@pytest.mark.req("B1-R10")
def test_idempotent_and_unaudited(seeded: Engine) -> None:
    """A second run changes no row; bootstrap data writes no audit entries."""

    def dump() -> str:
        return json.dumps(
            {
                f"{o}/{t}": q(seeded, o, f"SELECT * FROM {t} ORDER BY id")
                for o in seed.DEV_ORGS
                for t in (*TABLES, "audit_entry")
            },
            default=str,
        )

    before = dump()
    seed.seed_demo_master(seeded)
    assert dump() == before
    assert all(not q(seeded, o, "SELECT 1 FROM audit_entry") for o in seed.DEV_ORGS)


@pytest.mark.req("B1-R10")
def test_no_real_company_names(seeded: Engine) -> None:
    """No string the seed wrote contains a real company or platform name (D-066)."""
    for org in seed.DEV_ORGS:
        for t in (*TABLES, "organization"):
            blob = json.dumps(q(seeded, org, f"SELECT * FROM {t}"), default=str).lower()
            assert not [d for d in DENY if d in blob], t


@pytest.mark.req("B6-R04")
def test_seed_gate_defaults_to_off() -> None:
    """The entrypoint seeds only when ND_SEED is set (dev|pilot); unset means off."""
    script = (Path(__file__).parents[2] / "docker-entrypoint.sh").read_text(encoding="utf-8")
    assert 'case "${ND_SEED:-}" in' in script
    assert "dev|pilot)" in script
    assert "exit 1" in script
    assert "ND_SEED_DEV_DATA" not in script
