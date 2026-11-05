"""Master-data schema: isolation, grants, constraints (B1-R02, R04, R06, R07)."""

import uuid
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from nautical_deliverance.persistence.db import org_session

if TYPE_CHECKING:
    from sqlalchemy import CursorResult

    Orgs = tuple[uuid.UUID, uuid.UUID, dict[str, uuid.UUID]]

MASTER = [
    "legal_entity",
    "vessel",
    "vessel_approved_fuel",
    "port",
    "counterparty",
    "contact",
    "coverage",
    "product",
    "iso_spec_version",
    "bunkering_reason",
]
ALL = [*MASTER, "audit_entry"]

# table -> (columns, {column: SQL literal, or the name of an earlier table whose id to use}).
# Dict order is insertion order, so parents come first.
ROWS: dict[str, tuple[str, dict[str, str]]] = {
    "legal_entity": ("name, code", {"name": "'LE'", "code": "'LE1'"}),
    "product": ("name, default_unit", {"name": "'HSFO'", "default_unit": "'mt'"}),
    "port": (
        "locode, name, country, time_zone",
        {
            "locode": "'NLRTM'",
            "name": "'Rotterdam'",
            "country": "'NL'",
            "time_zone": "'Europe/Amsterdam'",
        },
    ),
    "counterparty": ("name, type", {"name": "'CP'", "type": "'trader'"}),
    "iso_spec_version": ("name", {"name": "'ISO 8217:2017'"}),
    "bunkering_reason": ("name", {"name": "'Bunkers only'"}),
    "vessel": (
        "name, imo, vessel_type, dwt, flag, legal_entity_id",
        {
            "name": "'V'",
            "imo": "'9074729'",
            "vessel_type": "'tanker'",
            "dwt": "50000",
            "flag": "'PA'",
            "legal_entity_id": "legal_entity",
        },
    ),
    "vessel_approved_fuel": (
        "vessel_id, product_id",
        {"vessel_id": "vessel", "product_id": "product"},
    ),
    "contact": (
        "counterparty_id, name, email",
        {"counterparty_id": "counterparty", "name": "'C'", "email": "'c@x.example'"},
    ),
    "coverage": (
        "counterparty_id, port_id, product_id",
        {"counterparty_id": "counterparty", "port_id": "port", "product_id": "product"},
    ),
    "audit_entry": (
        "actor, entity_type, entity_id, action, changes",
        {
            "actor": "gen_random_uuid()",
            "entity_type": "'port'",
            "entity_id": "gen_random_uuid()",
            "action": "'create'",
            "changes": "'{}'::jsonb",
        },
    ),
}


def _insert(
    s: Session, org: uuid.UUID, table: str, ids: dict[str, uuid.UUID], **over: str
) -> uuid.UUID:
    cols, base = ROWS[table]
    vals = {**base, **over}
    exprs = [f":{v}" if v in ids else v for v in vals.values()]
    params = {v: ids[v] for v in vals.values() if v in ids}
    new = uuid.uuid4()
    s.execute(
        text(
            f"INSERT INTO {table} (id, organization_id, {cols})"  # noqa: S608
            f" VALUES (:id, :org, {', '.join(exprs)})"
        ),
        {"id": new, "org": org, **params},
    )
    return new


def _populate(engine: Engine, org: uuid.UUID) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    with org_session(org, engine) as s:
        s.execute(text("INSERT INTO organization (id, name) VALUES (:o, 'o')"), {"o": org})
        for table in ROWS:
            ids[table] = _insert(s, org, table, ids)
    return ids


@pytest.fixture
def orgs(app_engine: Engine) -> Orgs:
    """Two populated orgs; returns (A, B, B's row ids)."""
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    _populate(app_engine, org_a)
    return org_a, org_b, _populate(app_engine, org_b)


@pytest.mark.req("B1-R04")
@pytest.mark.parametrize("table", ALL)
def test_other_org_rows_invisible_and_immutable(app_engine: Engine, orgs: Orgs, table: str) -> None:
    """Org A sees its own row only; cannot update, nor insert into, org B."""
    org_a, org_b, ids_b = orgs
    with org_session(org_a, app_engine) as s:
        assert s.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 1  # noqa: S608
        found = s.execute(
            text(f"SELECT count(*) FROM {table} WHERE id = :i"),  # noqa: S608
            {"i": ids_b[table]},
        )
        assert found.scalar_one() == 0
        if table != "audit_entry":  # nd_app may not UPDATE the audit log at all
            upd = s.execute(
                text(f"UPDATE {table} SET organization_id = organization_id WHERE id = :i"),  # noqa: S608
                {"i": ids_b[table]},
            )
            assert cast("CursorResult[Any]", upd).rowcount == 0
    with pytest.raises(DBAPIError, match="row-level security"), org_session(org_a, app_engine) as s:
        _insert(s, org_b, table, ids_b)
    with Session(app_engine) as s:  # no org set: nothing visible
        assert s.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0  # noqa: S608


@pytest.mark.req("B1-R04")
def test_rls_forced_with_policy_on_every_table(owner_engine: Engine) -> None:
    """RLS enabled, forced and policed on every new table."""
    with owner_engine.connect() as c:
        for table in ALL:
            row = c.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity,"
                    " (SELECT count(*) FROM pg_policies WHERE tablename = :t) "
                    "FROM pg_class WHERE relname = :t"
                ),
                {"t": table},
            ).one()
            assert tuple(row) == (True, True, 1), table


@pytest.mark.req("B1-R06")
@pytest.mark.parametrize("table", ALL)
def test_app_role_privileges(owner_engine: Engine, table: str) -> None:
    """nd_app can read and insert everywhere; nothing is deletable; audit is append-only."""

    def has(priv: str) -> bool:
        with owner_engine.connect() as c:
            return bool(
                c.execute(
                    text("SELECT has_table_privilege('nd_app', :t, :p)"), {"t": table, "p": priv}
                ).scalar_one()
            )

    assert has("SELECT")
    assert has("INSERT")
    assert not has("DELETE")
    assert not has("TRUNCATE")
    assert has("UPDATE") is (table != "audit_entry")


@pytest.mark.req("B1-R07")
def test_audit_rows_cannot_be_rewritten(app_engine: Engine, orgs: Orgs) -> None:
    """UPDATE and DELETE on audit_entry fail with permission denied."""
    org_a = orgs[0]
    for sql in ("UPDATE audit_entry SET action = 'update'", "DELETE FROM audit_entry"):
        with (
            pytest.raises(DBAPIError, match="permission denied"),
            org_session(org_a, app_engine) as s,
        ):
            s.execute(text(sql))
    with org_session(org_a, app_engine) as s:
        assert s.execute(text("SELECT count(*) FROM audit_entry")).scalar_one() == 1


@pytest.mark.req("B1-R02")
@pytest.mark.parametrize("table", MASTER)
def test_housekeeping_columns(owner_engine: Engine, table: str) -> None:
    """Every master table has active, version, created_at, updated_at, organization_id."""
    with owner_engine.connect() as c:
        cols = {
            r[0]: (r[1], r[2])
            for r in c.execute(
                text(
                    "SELECT column_name, is_nullable, column_default"
                    " FROM information_schema.columns WHERE table_name = :t"
                ),
                {"t": table},
            )
        }
    assert cols["active"] == ("NO", "true")
    assert cols["version"] == ("NO", "1")
    assert cols["created_at"][0] == "NO"
    assert cols["updated_at"][0] == "NO"
    assert cols["organization_id"][0] == "NO"


# (constraint name expected in the message, table, column overrides on the populated row)
BAD: list[tuple[str, str, dict[str, str]]] = [
    ("legal_entity_org_code_key", "legal_entity", {}),
    ("vessel_org_imo_key", "vessel", {}),
    ("vessel_imo_format", "vessel", {"imo": "'123456'"}),
    ("vessel_imo_format", "vessel", {"imo": "'\uff11\uff12\uff13\uff14\uff15\uff16\uff17'"}),
    ("vessel_dwt_positive", "vessel", {"imo": "'9319466'", "dwt": "0"}),
    ("port_org_locode_key", "port", {}),
    ("port_locode_format", "port", {"locode": "'nlrtm'"}),
    ("port_locode_format", "port", {"locode": "'NL1TM'"}),
    ("port_country_format", "port", {"locode": "'NLAMS'", "country": "'nl'"}),
    ("counterparty_type_valid", "counterparty", {"type": "'broker'"}),
    ("product_default_unit_valid", "product", {"name": "'X'", "default_unit": "'kg'"}),
    ("coverage_org_cp_port_product_key", "coverage", {}),
    ("vessel_approved_fuel_org_vessel_product_key", "vessel_approved_fuel", {}),
    ("audit_entry_action_valid", "audit_entry", {"action": "'delete'"}),
]


@pytest.mark.req("B1-R02")
@pytest.mark.parametrize(("constraint", "table", "over"), BAD)
def test_constraint_rejects_bad_row(
    app_engine: Engine, orgs: Orgs, constraint: str, table: str, over: dict[str, str]
) -> None:
    """Each uniqueness/check constraint rejects its violating row, by name."""
    org_b, ids = orgs[1], orgs[2]
    with pytest.raises(IntegrityError, match=constraint), org_session(org_b, app_engine) as s:
        _insert(s, org_b, table, ids, **over)


@pytest.mark.req("B1-R02")
def test_foreign_key_cannot_cross_organizations(app_engine: Engine, orgs: Orgs) -> None:
    """A vessel in org B cannot point at org A's legal entity (composite FK)."""
    org_a, org_b, ids_b = orgs
    with org_session(org_a, app_engine) as s:
        le_a = s.execute(text("SELECT id FROM legal_entity")).scalar_one()
    with (
        pytest.raises(IntegrityError, match="vessel_legal_entity_fk"),
        org_session(org_b, app_engine) as s,
    ):
        _insert(s, org_b, "vessel", {**ids_b, "legal_entity": le_a}, imo="'9319466'")
