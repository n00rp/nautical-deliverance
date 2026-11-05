"""Inquiry schema: constraints, isolation, grants, audit actions (B2-R02, B2-R03)."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from nautical_deliverance.persistence.db import org_session

if TYPE_CHECKING:
    from sqlalchemy import CursorResult

Ids = dict[str, uuid.UUID]
TABLES = ["inquiry", "inquiry_line", "inquiry_reference_counter"]
ETA = datetime(2026, 12, 1, tzinfo=UTC)


def _ins(s: Session, table: str, **vals: Any) -> uuid.UUID:  # noqa: ANN401
    vals.setdefault("id", uuid.uuid4())
    cols = ", ".join(vals)
    binds = ", ".join(f":{k}" for k in vals)
    s.execute(text(f"INSERT INTO {table} ({cols}) VALUES ({binds})"), vals)  # noqa: S608
    return cast("uuid.UUID", vals["id"])


def _setup(engine: Engine, org: uuid.UUID) -> Ids:
    """Insert an org with all parents of an inquiry; return their ids."""
    o = {"organization_id": org}
    with org_session(org, engine) as s:
        _ins(s, "organization", id=org, name="o")
        ids: Ids = {
            "user": _ins(s, "app_user", **o, last_seen_at=ETA),
            "legal_entity": _ins(s, "legal_entity", **o, name="LE", code="LE1"),
            "product": _ins(s, "product", **o, name="HSFO"),
            "product2": _ins(s, "product", **o, name="VLSFO"),
            "port": _ins(s, "port", **o, locode="NLRTM", name="R", country="NL", time_zone="UTC"),
            "iso": _ins(s, "iso_spec_version", **o, name="ISO"),
            "reason": _ins(s, "bunkering_reason", **o, name="BR"),
        }
        ids["vessel"] = _ins(
            s,
            "vessel",
            **o,
            name="V",
            imo="9074729",
            vessel_type="tanker",
            dwt=1,
            flag="PA",
            legal_entity_id=ids["legal_entity"],
        )
    return ids


def _inquiry(s: Session, org: uuid.UUID, ids: Ids, **over: Any) -> uuid.UUID:  # noqa: ANN401
    vals: dict[str, Any] = {
        "organization_id": org,
        "reference": "R1",
        "status": "draft",
        "vessel_id": ids["vessel"],
        "legal_entity_id": ids["legal_entity"],
        "port_id": ids["port"],
        "bunkering_reason_id": ids["reason"],
        "operator_id": ids["user"],
        "requester_id": ids["user"],
        "eta": ETA,
        "etd": ETA + timedelta(days=1),
        "created_by": ids["user"],
    }
    return _ins(s, "inquiry", **{**vals, **over})


def _line(s: Session, org: uuid.UUID, ids: Ids, inq: uuid.UUID, **over: Any) -> uuid.UUID:  # noqa: ANN401
    vals: dict[str, Any] = {
        "organization_id": org,
        "inquiry_id": inq,
        "position": 2,
        "product_id": ids["product2"],
        "quantity": Decimal(100),
        "unit": "mt",
        "iso_spec_version_id": ids["iso"],
    }
    return _ins(s, "inquiry_line", **{**vals, **over})


@pytest.fixture
def org(app_engine: Engine) -> tuple[uuid.UUID, Ids]:
    """One populated org."""
    o = uuid.uuid4()
    return o, _setup(app_engine, o)


# Inquiry rejects first insert a base row with reference R0; candidates default to R1.
INQ_ACCEPT: list[dict[str, Any]] = [
    {"status": "rfq_sent"},
    {"voyage": "x" * 40},
    {"etd": ETA},
    {"eta": None, "etd": None},
    {"eta": ETA, "etd": None},
    {"status": "cancelled", "cancel_reason": "x", "eta": None, "etd": None},
    {"internal_comments": "x" * 4000},
    {"status": "cancelled", "cancel_reason": "no longer needed"},
]
INQ_REJECT: list[tuple[str, dict[str, Any]]] = [
    ("inquiry_org_reference_key", {"reference": "R0"}),
    ("inquiry_status_valid", {"status": "bogus"}),
    ("inquiry_voyage_len", {"voyage": "x" * 41}),
    ("inquiry_etd_after_eta", {"etd": ETA - timedelta(seconds=1)}),
    ("inquiry_eta_etd_set", {"status": "rfq_sent", "eta": None}),
    ("inquiry_eta_etd_set", {"status": "nominated", "etd": None}),
    ("inquiry_comments_len", {"internal_comments": "x" * 4001}),
    ("inquiry_cancel_reason_consistent", {"status": "cancelled"}),
    ("inquiry_cancel_reason_consistent", {"status": "cancelled", "cancel_reason": "  "}),
    ("inquiry_cancel_reason_consistent", {"cancel_reason": "why"}),
]
# Line tests first insert position 1 / "product"; a string value names an id in ``ids``.
LINE_ACCEPT: list[dict[str, Any]] = [
    {"position": 10},
    {"quantity": Decimal("0.001")},
    {"unit": "m3"},
    {"unit": "m3", "density": Decimal(600)},
    {"unit": "m3", "density": Decimal(1100)},
    {"spec_notes": "x" * 500},
]
LINE_REJECT: list[tuple[str, dict[str, Any]]] = [
    ("inquiry_line_inquiry_product_key", {"product_id": "product"}),
    ("inquiry_line_inquiry_position_key", {"position": 1}),
    ("inquiry_line_position_range", {"position": 0}),
    ("inquiry_line_position_range", {"position": 11}),
    ("inquiry_line_quantity_positive", {"quantity": Decimal(0)}),
    ("inquiry_line_unit_valid", {"unit": "kg"}),
    ("inquiry_line_density_range", {"unit": "m3", "density": Decimal(599)}),
    ("inquiry_line_density_range", {"unit": "m3", "density": Decimal(1101)}),
    ("inquiry_line_density_only_m3", {"unit": "mt", "density": Decimal(800)}),
    ("inquiry_line_spec_notes_len", {"spec_notes": "x" * 501}),
]


@pytest.mark.req("B2-R02")
@pytest.mark.parametrize("over", INQ_ACCEPT)
def test_inquiry_accepts(
    app_engine: Engine, org: tuple[uuid.UUID, Ids], over: dict[str, Any]
) -> None:
    """A valid inquiry variant is accepted."""
    o, ids = org
    with org_session(o, app_engine) as s:
        _inquiry(s, o, ids, **over)


@pytest.mark.req("B2-R02")
@pytest.mark.parametrize(("constraint", "over"), INQ_REJECT)
def test_inquiry_rejects(
    app_engine: Engine, org: tuple[uuid.UUID, Ids], constraint: str, over: dict[str, Any]
) -> None:
    """Each inquiry constraint rejects its violating row by name."""
    o, ids = org
    with org_session(o, app_engine) as s:
        _inquiry(s, o, ids, reference="R0")
        with pytest.raises(IntegrityError, match=constraint):
            _inquiry(s, o, ids, **over)


def _resolve(over: dict[str, Any], ids: Ids) -> dict[str, Any]:
    return {k: ids[v] if isinstance(v, str) and v in ids else v for k, v in over.items()}


@pytest.mark.req("B2-R02")
@pytest.mark.parametrize("over", LINE_ACCEPT)
def test_line_accepts(app_engine: Engine, org: tuple[uuid.UUID, Ids], over: dict[str, Any]) -> None:
    """A valid line variant is accepted."""
    o, ids = org
    with org_session(o, app_engine) as s:
        inq = _inquiry(s, o, ids)
        _line(s, o, ids, inq, position=1, product_id=ids["product"])
        _line(s, o, ids, inq, **over)


@pytest.mark.req("B2-R02")
@pytest.mark.parametrize(("constraint", "over"), LINE_REJECT)
def test_line_rejects(
    app_engine: Engine, org: tuple[uuid.UUID, Ids], constraint: str, over: dict[str, Any]
) -> None:
    """Each line constraint rejects its violating row by name."""
    o, ids = org
    with org_session(o, app_engine) as s:
        inq = _inquiry(s, o, ids)
        _line(s, o, ids, inq, position=1, product_id=ids["product"])
        with pytest.raises(IntegrityError, match=constraint):
            _line(s, o, ids, inq, **_resolve(over, ids))


@pytest.mark.req("B2-R02")
def test_foreign_keys_cannot_cross_organizations(
    app_engine: Engine, org: tuple[uuid.UUID, Ids]
) -> None:
    """Org B cannot reference org A's vessel, user or product."""
    _, ids_a = org
    org_b = uuid.uuid4()
    ids_b = _setup(app_engine, org_b)
    for col, key, name in (
        ("vessel_id", "vessel", "inquiry_vessel_fk"),
        ("operator_id", "user", "inquiry_operator_fk"),
    ):
        with pytest.raises(IntegrityError, match=name), org_session(org_b, app_engine) as s:
            _inquiry(s, org_b, ids_b, **{col: ids_a[key]})
    with org_session(org_b, app_engine) as s:
        inq_b = _inquiry(s, org_b, ids_b)
    with (
        pytest.raises(IntegrityError, match="inquiry_line_product_fk"),
        org_session(org_b, app_engine) as s,
    ):
        _line(s, org_b, ids_b, inq_b, product_id=ids_a["product"])


@pytest.mark.req("B2-R02")
def test_line_cascades_and_app_user_defaults(
    app_engine: Engine, owner_engine: Engine, org: tuple[uuid.UUID, Ids]
) -> None:
    """Deleting an inquiry removes its lines; the new app_user columns have defaults."""
    o, ids = org
    with org_session(o, app_engine) as s:
        inq = _inquiry(s, o, ids)
        _line(s, o, ids, inq)
        row = s.execute(
            text("SELECT name, email, roles FROM app_user WHERE id = :u"), {"u": ids["user"]}
        ).one()
        assert tuple(row) == ("", "", [])
    with owner_engine.begin() as c:
        c.execute(text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(o)})
        c.execute(text("DELETE FROM inquiry WHERE id = :i"), {"i": inq})
        assert c.execute(text("SELECT count(*) FROM inquiry_line")).scalar_one() == 0


@pytest.mark.req("B2-R02")
@pytest.mark.parametrize("action", ["take", "cancel", "duplicate"])
def test_audit_accepts_inquiry_actions(
    app_engine: Engine, org: tuple[uuid.UUID, Ids], action: str
) -> None:
    """audit_entry.action allows the B2 actions."""
    o, ids = org
    with org_session(o, app_engine) as s:
        _ins(
            s,
            "audit_entry",
            organization_id=o,
            actor=ids["user"],
            entity_type="inquiry",
            entity_id=uuid.uuid4(),
            action=action,
        )


def _insert_for(s: Session, table: str, o: uuid.UUID, ids: Ids) -> None:
    if table == "inquiry":
        _inquiry(s, o, ids)
    elif table == "inquiry_line":
        _line(s, o, ids, _inquiry(s, o, ids))
    else:
        s.execute(
            text(
                "INSERT INTO inquiry_reference_counter (organization_id, year_month, next_value)"
                " VALUES (:o, '2611', 2)"
            ),
            {"o": o},
        )


@pytest.mark.req("B2-R03")
@pytest.mark.parametrize("table", TABLES)
def test_other_org_rows_invisible_and_immutable(app_engine: Engine, table: str) -> None:
    """Org A sees only its row; cannot update, nor insert into, org B."""
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    ids_a, ids_b = _setup(app_engine, org_a), _setup(app_engine, org_b)
    for o, ids in ((org_a, ids_a), (org_b, ids_b)):
        with org_session(o, app_engine) as s:
            _insert_for(s, table, o, ids)
    with org_session(org_a, app_engine) as s:
        assert s.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 1  # noqa: S608
        found = s.execute(
            text(f"SELECT count(*) FROM {table} WHERE organization_id = :b"),  # noqa: S608
            {"b": org_b},
        )
        assert found.scalar_one() == 0
        upd = s.execute(
            text(
                f"UPDATE {table} SET organization_id = organization_id WHERE organization_id = :b"  # noqa: S608
            ),
            {"b": org_b},
        )
        assert cast("CursorResult[Any]", upd).rowcount == 0
    with (
        pytest.raises(DBAPIError, match="row-level security"),
        org_session(org_a, app_engine) as s,
    ):
        _insert_for(s, table, org_b, ids_b)
    with Session(app_engine) as s:  # no org set: nothing visible
        assert s.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0  # noqa: S608


@pytest.mark.req("B2-R03")
@pytest.mark.parametrize("table", TABLES)
def test_rls_forced_with_policy(owner_engine: Engine, table: str) -> None:
    """RLS enabled, forced and policed."""
    with owner_engine.connect() as c:
        row = c.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity,"
                " (SELECT count(*) FROM pg_policies WHERE tablename = :t)"
                " FROM pg_class WHERE relname = :t"
            ),
            {"t": table},
        ).one()
    assert tuple(row) == (True, True, 1)


@pytest.mark.req("B2-R03")
@pytest.mark.parametrize("table", TABLES)
def test_app_role_privileges(owner_engine: Engine, table: str) -> None:
    """nd_app: SELECT/INSERT/UPDATE; DELETE only on inquiry_line; never TRUNCATE."""

    def has(priv: str) -> bool:
        with owner_engine.connect() as c:
            return bool(
                c.execute(
                    text("SELECT has_table_privilege('nd_app', :t, :p)"), {"t": table, "p": priv}
                ).scalar_one()
            )

    assert has("SELECT")
    assert has("INSERT")
    assert has("UPDATE")
    assert has("DELETE") is (table == "inquiry_line")
    assert not has("TRUNCATE")


@pytest.mark.req("B2-R03")
@pytest.mark.parametrize("table", ["inquiry", "inquiry_reference_counter"])
def test_app_cannot_delete(app_engine: Engine, org: tuple[uuid.UUID, Ids], table: str) -> None:
    """DELETE on inquiry and the counter fails with permission denied."""
    o, _ = org
    with pytest.raises(DBAPIError, match="permission denied"), org_session(o, app_engine) as s:
        s.execute(text(f"DELETE FROM {table}"))  # noqa: S608
