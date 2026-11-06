"""Offer schema: constraints, same-inquiry FKs, density trigger, decisions, RLS (B4-R01/R02)."""

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from nautical_deliverance.persistence.db import org_session
from tests.db.test_inquiry_schema import Ids, _inquiry, _ins, _line, _setup
from tests.db.test_rfq_schema import NOW, SENT, _rfq, _supplier

LATER = NOW + timedelta(days=2)


def _offer(s: Session, org: uuid.UUID, ids: Ids, inq: uuid.UUID, **over: Any) -> uuid.UUID:  # noqa: ANN401
    """Insert a sent RFQ (unless rfq_id is given) and an offer for it."""
    rfq = over.pop("rfq_id", None) or _rfq(s, org, ids, inq, status="sent", **SENT)
    vals: dict[str, Any] = {
        "organization_id": org,
        "rfq_id": rfq,
        "inquiry_id": inq,
        "valid_until": LATER,
        "created_by": ids["user"],
    }
    return _ins(s, "offer", **{**vals, **over})


def _oline(
    s: Session,
    org: uuid.UUID,
    off: uuid.UUID,
    inq: uuid.UUID,
    il: uuid.UUID,
    **over: Any,  # noqa: ANN401
) -> uuid.UUID:
    vals: dict[str, Any] = {
        "organization_id": org,
        "offer_id": off,
        "inquiry_id": inq,
        "inquiry_line_id": il,
        "price_per_mt": Decimal("612.345"),
    }
    return _ins(s, "offer_line", **{**vals, **over})


@pytest.fixture
def org(app_engine: Engine) -> tuple[uuid.UUID, Ids]:
    """One populated org with a supplier and contact."""
    o = uuid.uuid4()
    ids = _setup(app_engine, o)
    with org_session(o, app_engine) as s:
        _supplier(s, o, ids)
    return o, ids


OFFER_ACCEPT: list[dict[str, Any]] = [
    {},
    {"delivery_method": "ex_wharf", "delivery_from": NOW, "delivery_to": NOW},
    {"delivery_from": NOW},
    {"payment_terms": "x" * 200, "physical_supplier": "x" * 200, "supplier_comment": "x" * 2000},
    {"barging_cost": Decimal("0.00"), "other_cost": Decimal("9999999999.99")},
]
OFFER_REJECT: list[tuple[str, dict[str, Any]]] = [
    ("offer_currency_usd", {"currency": "EUR"}),
    ("offer_payment_terms_len", {"payment_terms": "x" * 201}),
    ("offer_physical_supplier_len", {"physical_supplier": "x" * 201}),
    ("offer_supplier_comment_len", {"supplier_comment": "x" * 2001}),
    ("offer_delivery_order", {"delivery_from": LATER, "delivery_to": NOW}),
    ("offer_delivery_method_valid", {"delivery_method": "ship"}),
    ("offer_barging_cost_nonneg", {"barging_cost": Decimal(-1)}),
    ("offer_port_call_cost_nonneg", {"port_call_cost": Decimal(-1)}),
    ("offer_agent_cost_nonneg", {"agent_cost": Decimal(-1)}),
    ("offer_surveyor_cost_nonneg", {"surveyor_cost": Decimal(-1)}),
    ("offer_other_cost_nonneg", {"other_cost": Decimal("-0.01")}),
    ("valid_until", {"valid_until": None}),
    ("numeric field overflow", {"agent_cost": Decimal("10000000000.00")}),
]


@pytest.mark.req("B4-R01")
@pytest.mark.parametrize("over", OFFER_ACCEPT)
def test_offer_accepts(
    app_engine: Engine, org: tuple[uuid.UUID, Ids], over: dict[str, Any]
) -> None:
    """A valid offer variant is accepted."""
    o, ids = org
    with org_session(o, app_engine) as s:
        _offer(s, o, ids, _inquiry(s, o, ids), **over)


@pytest.mark.req("B4-R01")
@pytest.mark.parametrize(("constraint", "over"), OFFER_REJECT)
def test_offer_rejects(
    app_engine: Engine, org: tuple[uuid.UUID, Ids], constraint: str, over: dict[str, Any]
) -> None:
    """Each offer check rejects its violating row by name."""
    o, ids = org
    with org_session(o, app_engine) as s:
        inq = _inquiry(s, o, ids)
        with pytest.raises((IntegrityError, DBAPIError), match=constraint):
            _offer(s, o, ids, inq, **over)


@pytest.mark.req("B4-R01")
def test_offer_defaults(app_engine: Engine, org: tuple[uuid.UUID, Ids]) -> None:
    """Currency defaults to USD, costs to 0, version to 1."""
    o, ids = org
    with org_session(o, app_engine) as s:
        off = _offer(s, o, ids, _inquiry(s, o, ids))
        row = s.execute(
            text(
                "SELECT currency, barging_cost, port_call_cost, agent_cost, surveyor_cost,"
                " other_cost, version FROM offer WHERE id = :i"
            ),
            {"i": off},
        ).one()
    assert tuple(row) == ("USD", 0, 0, 0, 0, 0, 1)


@pytest.mark.req("B4-R01")
def test_one_offer_per_rfq(app_engine: Engine, org: tuple[uuid.UUID, Ids]) -> None:
    """A second offer for the same RFQ is rejected."""
    o, ids = org
    with org_session(o, app_engine) as s:
        inq = _inquiry(s, o, ids)
        rfq = _rfq(s, o, ids, inq, status="sent", **SENT)
        _offer(s, o, ids, inq, rfq_id=rfq)
        with pytest.raises(IntegrityError, match="offer_rfq_id_key"):
            _offer(s, o, ids, inq, rfq_id=rfq)


@pytest.mark.req("B4-R01")
def test_offer_inquiry_must_equal_rfq_inquiry(
    app_engine: Engine, org: tuple[uuid.UUID, Ids]
) -> None:
    """An offer whose inquiry differs from its RFQ's inquiry is rejected by the composite FK."""
    o, ids = org
    with org_session(o, app_engine) as s:
        a = _inquiry(s, o, ids)
        b = _inquiry(s, o, ids, reference="R2")
        rfq_a = _rfq(s, o, ids, a, status="sent", **SENT)
        with pytest.raises(IntegrityError, match="offer_rfq_fk"):
            _offer(s, o, ids, b, rfq_id=rfq_a)


@pytest.mark.req("B4-R01")
def test_offer_line_accepts_and_defaults(app_engine: Engine, org: tuple[uuid.UUID, Ids]) -> None:
    """Valid lines (3-decimal price, m3 line density at the range ends) are accepted."""
    o, ids = org
    with org_session(o, app_engine) as s:
        inq = _inquiry(s, o, ids)
        off = _offer(s, o, ids, inq)
        mt = _line(s, o, ids, inq)
        m3 = _line(s, o, ids, inq, position=3, product_id=ids["product"], unit="m3")
        _oline(s, o, off, inq, mt, price_per_mt=Decimal("0.001"))
        _oline(s, o, off, inq, m3, density=Decimal("600.0"))
    with org_session(o, app_engine) as s:
        assert s.execute(text("SELECT count(*) FROM offer_line")).scalar_one() == len((mt, m3))


LINE_REJECT: list[tuple[str, dict[str, Any]]] = [
    ("offer_line_price_positive", {"price_per_mt": Decimal(0)}),
    ("offer_line_price_positive", {"price_per_mt": Decimal(-1)}),
    ("offer_line_density_range", {"density": Decimal("599.9")}),
    ("offer_line_density_range", {"density": Decimal("1100.1")}),
]


@pytest.mark.req("B4-R01")
@pytest.mark.parametrize(("constraint", "over"), LINE_REJECT)
def test_offer_line_rejects(
    app_engine: Engine, org: tuple[uuid.UUID, Ids], constraint: str, over: dict[str, Any]
) -> None:
    """Price and density range checks reject by name (density range on an m3 line)."""
    o, ids = org
    with org_session(o, app_engine) as s:
        inq = _inquiry(s, o, ids)
        off = _offer(s, o, ids, inq)
        il = _line(s, o, ids, inq, unit="m3")
        with pytest.raises(IntegrityError, match=constraint):
            _oline(s, o, off, inq, il, **over)


@pytest.mark.req("B4-R01")
def test_offer_line_unique_per_offer(app_engine: Engine, org: tuple[uuid.UUID, Ids]) -> None:
    """The same inquiry line cannot be priced twice in one offer."""
    o, ids = org
    with org_session(o, app_engine) as s:
        inq = _inquiry(s, o, ids)
        off = _offer(s, o, ids, inq)
        il = _line(s, o, ids, inq)
        _oline(s, o, off, inq, il)
        with pytest.raises(IntegrityError, match="offer_line_offer_line_key"):
            _oline(s, o, off, inq, il)


@pytest.mark.req("B4-R01")
def test_offer_line_must_belong_to_offers_inquiry(
    app_engine: Engine, org: tuple[uuid.UUID, Ids]
) -> None:
    """A line of another inquiry, or an inquiry_id other than the offer's, is rejected."""
    o, ids = org
    with org_session(o, app_engine) as s:
        a = _inquiry(s, o, ids)
        b = _inquiry(s, o, ids, reference="R2")
        off = _offer(s, o, ids, a)
        line_b = _line(s, o, ids, b)
        with pytest.raises(IntegrityError, match="offer_line_inquiry_line_fk"):
            _oline(s, o, off, a, line_b)
    with (
        org_session(o, app_engine) as s,
        pytest.raises(IntegrityError, match="offer_line_offer_fk"),
    ):
        _oline(s, o, off, b, line_b)


DENSITY_CASES = [
    ("mt", None, Decimal("850.0"), False),
    ("mt", None, None, True),
    ("m3", None, Decimal("850.0"), True),
    ("m3", None, None, True),
    ("m3", Decimal("840.0"), Decimal("850.0"), False),
    ("m3", Decimal("840.0"), None, True),
]


@pytest.mark.req("B4-R01")
@pytest.mark.parametrize("case", DENSITY_CASES)
def test_density_only_for_m3_line_without_density(
    app_engine: Engine,
    org: tuple[uuid.UUID, Ids],
    case: tuple[str, Decimal | None, Decimal | None, bool],
) -> None:
    """The trigger allows an offer density only for an m3 inquiry line lacking density."""
    o, ids = org
    unit, inq_density, density, ok = case
    with org_session(o, app_engine) as s:
        inq = _inquiry(s, o, ids)
        off = _offer(s, o, ids, inq)
        il = _line(s, o, ids, inq, unit=unit, density=inq_density)
        if ok:
            _oline(s, o, off, inq, il, density=density)
        else:
            with pytest.raises(DBAPIError, match="offer_line_density_allowed"):
                _oline(s, o, off, inq, il, density=density)


def _winner_update(s: Session, inq: uuid.UUID, **vals: Any) -> None:  # noqa: ANN401
    sets = ", ".join(f"{k} = :{k}" for k in vals)
    s.execute(text(f"UPDATE inquiry SET {sets} WHERE id = :id"), {**vals, "id": inq})  # noqa: S608


def _decision(ids: Ids, off: uuid.UUID, **over: Any) -> dict[str, Any]:  # noqa: ANN401
    base = {
        "winner_offer_id": off,
        "decided_at": NOW,
        "decided_by": ids["user"],
        "decided_total": Decimal("394413.50"),
    }
    return {**base, **over}


DECISION_ACCEPT: list[dict[str, Any]] = [
    {},
    {"decision_reason": "flexibility"},
    {"decision_reason": "other", "decision_note": "x" * 2000},
    {"decision_note": "note only"},
    {"decided_total": Decimal("999999999999.99")},
]
DECISION_REJECT: list[tuple[str, dict[str, Any]]] = [
    ("inquiry_decision_reason_valid", {"decision_reason": "cheap"}),
    ("inquiry_decision_note_len", {"decision_note": "x" * 2001}),
    ("inquiry_decision_consistent", {"decided_at": None}),
    ("inquiry_decision_consistent", {"decided_by": None}),
    ("inquiry_decision_consistent", {"decided_total": None}),
]


@pytest.mark.req("B4-R01")
@pytest.mark.parametrize("over", DECISION_ACCEPT)
def test_decision_accepts(
    app_engine: Engine, org: tuple[uuid.UUID, Ids], over: dict[str, Any]
) -> None:
    """A complete decision, with optional reason and note, is accepted."""
    o, ids = org
    with org_session(o, app_engine) as s:
        inq = _inquiry(s, o, ids)
        _winner_update(s, inq, **_decision(ids, _offer(s, o, ids, inq), **over))


@pytest.mark.req("B4-R01")
@pytest.mark.parametrize(("constraint", "over"), DECISION_REJECT)
def test_decision_rejects(
    app_engine: Engine, org: tuple[uuid.UUID, Ids], constraint: str, over: dict[str, Any]
) -> None:
    """Reason/note checks and the all-or-nothing decision check reject by name."""
    o, ids = org
    with org_session(o, app_engine) as s:
        inq = _inquiry(s, o, ids)
        off = _offer(s, o, ids, inq)
        with pytest.raises(IntegrityError, match=constraint):
            _winner_update(s, inq, **_decision(ids, off, **over))


@pytest.mark.req("B4-R01")
@pytest.mark.parametrize(
    "over",
    [
        {"decided_at": NOW},
        {"decided_by": "user"},
        {"decided_total": Decimal(1)},
        {"decision_reason": "timing"},
        {"decision_note": "n"},
    ],
)
def test_decision_fields_without_winner_rejected(
    app_engine: Engine, org: tuple[uuid.UUID, Ids], over: dict[str, Any]
) -> None:
    """Any decision field without a winner violates the consistency check."""
    o, ids = org
    over = {k: ids["user"] if v == "user" else v for k, v in over.items()}
    with org_session(o, app_engine) as s:
        inq = _inquiry(s, o, ids)
        with pytest.raises(IntegrityError, match="inquiry_decision_consistent"):
            _winner_update(s, inq, **over)


@pytest.mark.req("B4-R01")
def test_winner_without_other_decision_fields_rejected(
    app_engine: Engine, org: tuple[uuid.UUID, Ids]
) -> None:
    """A winner alone (no decided_at/by/total) is rejected."""
    o, ids = org
    with org_session(o, app_engine) as s:
        inq = _inquiry(s, o, ids)
        off = _offer(s, o, ids, inq)
        with pytest.raises(IntegrityError, match="inquiry_decision_consistent"):
            _winner_update(s, inq, winner_offer_id=off)


@pytest.mark.req("B4-R01")
def test_winner_must_belong_to_inquiry(app_engine: Engine, org: tuple[uuid.UUID, Ids]) -> None:
    """The winner offer of another inquiry is rejected by the composite FK."""
    o, ids = org
    with org_session(o, app_engine) as s:
        a = _inquiry(s, o, ids)
        b = _inquiry(s, o, ids, reference="R2")
        off_b = _offer(s, o, ids, b)
        with pytest.raises(IntegrityError, match="inquiry_winner_fk"):
            _winner_update(s, a, **_decision(ids, off_b))


@pytest.mark.req("B4-R01")
def test_decided_by_must_be_org_user(app_engine: Engine, org: tuple[uuid.UUID, Ids]) -> None:
    """decided_by must reference a user of the same organization."""
    o, ids = org
    with org_session(o, app_engine) as s:
        inq = _inquiry(s, o, ids)
        off = _offer(s, o, ids, inq)
        with pytest.raises(IntegrityError, match="inquiry_decided_by_fk"):
            _winner_update(s, inq, **_decision(ids, off, decided_by=uuid.uuid4()))


@pytest.mark.req("B4-R01")
def test_foreign_keys_cannot_cross_organizations(
    app_engine: Engine, org: tuple[uuid.UUID, Ids]
) -> None:
    """Org B cannot attach an offer to org A's RFQ."""
    o_a, ids_a = org
    with org_session(o_a, app_engine) as s:
        inq_a = _inquiry(s, o_a, ids_a)
        rfq_a = _rfq(s, o_a, ids_a, inq_a, status="sent", **SENT)
    org_b = uuid.uuid4()
    ids_b = _setup(app_engine, org_b)
    with org_session(org_b, app_engine) as s:
        inq_b = _inquiry(s, org_b, ids_b)
        with pytest.raises(IntegrityError, match="offer_rfq_fk"):
            _offer(s, org_b, ids_b, inq_b, rfq_id=rfq_a)


@pytest.mark.req("B4-R01")
def test_audit_accepts_select_winner(app_engine: Engine, org: tuple[uuid.UUID, Ids]) -> None:
    """audit_entry.action allows select_winner and still rejects unknown actions."""
    o, ids = org
    kw: dict[str, Any] = {
        "organization_id": o,
        "actor": ids["user"],
        "entity_type": "inquiry",
        "entity_id": uuid.uuid4(),
    }
    with org_session(o, app_engine) as s:
        _ins(s, "audit_entry", **kw, action="select_winner")
    with org_session(o, app_engine) as s, pytest.raises(IntegrityError, match="audit_entry_action"):
        _ins(s, "audit_entry", **kw, action="bogus")


@pytest.mark.req("B4-R02")
def test_other_org_rows_invisible_and_immutable(app_engine: Engine) -> None:
    """Org A sees only its offers and lines; cannot update, nor insert into, org B."""
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    all_ids = []
    for o in (org_a, org_b):
        ids = _setup(app_engine, o)
        with org_session(o, app_engine) as s:
            _supplier(s, o, ids)
            inq = _inquiry(s, o, ids)
            off = _offer(s, o, ids, inq)
            _oline(s, o, off, inq, _line(s, o, ids, inq))
            _winner_update(s, inq, **_decision(ids, off))
        all_ids.append(ids)
    with org_session(org_a, app_engine) as s:
        for table in ("offer", "offer_line"):
            assert s.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 1  # noqa: S608
            q = text(f"SELECT count(*) FROM {table} WHERE organization_id = :b")  # noqa: S608
            assert s.execute(q, {"b": org_b}).scalar_one() == 0
        won = s.execute(text("SELECT count(*) FROM inquiry WHERE winner_offer_id IS NOT NULL"))
        assert won.scalar_one() == 1
        upd = s.execute(
            text("UPDATE offer SET version = 9 WHERE organization_id = :b"), {"b": org_b}
        )
        assert cast("Any", upd).rowcount == 0
        upd = s.execute(
            text("UPDATE inquiry SET decision_note = 'x' WHERE organization_id = :b"), {"b": org_b}
        )
        assert cast("Any", upd).rowcount == 0
        dele = s.execute(text("DELETE FROM offer_line WHERE organization_id = :b"), {"b": org_b})
        assert cast("Any", dele).rowcount == 0
    with (
        pytest.raises(DBAPIError, match="row-level security"),
        org_session(org_a, app_engine) as s,
    ):
        _inquiry(s, org_b, all_ids[1], reference="R9")
    with Session(app_engine) as s:  # no org set: nothing visible
        assert s.execute(text("SELECT count(*) FROM offer")).scalar_one() == 0
        assert s.execute(text("SELECT count(*) FROM offer_line")).scalar_one() == 0


@pytest.mark.req("B4-R02")
def test_rls_forced_and_privileges(owner_engine: Engine, app_engine: Engine) -> None:
    """RLS enabled, forced and policed; offer has no DELETE, offer_line may DELETE; no TRUNCATE."""
    rows = {}
    with owner_engine.connect() as c:
        for table in ("offer", "offer_line"):
            rows[table] = tuple(
                c.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity,"
                        " (SELECT count(*) FROM pg_policies WHERE tablename = :t),"
                        " has_table_privilege('nd_app', :t, 'SELECT'),"
                        " has_table_privilege('nd_app', :t, 'INSERT'),"
                        " has_table_privilege('nd_app', :t, 'UPDATE'),"
                        " has_table_privilege('nd_app', :t, 'DELETE'),"
                        " has_table_privilege('nd_app', :t, 'TRUNCATE')"
                        " FROM pg_class WHERE relname = :t"
                    ),
                    {"t": table},
                ).one()
            )
    assert rows["offer"] == (True, True, 1, True, True, True, False, False)
    assert rows["offer_line"] == (True, True, 1, True, True, True, True, False)
    with (
        pytest.raises(DBAPIError, match="permission denied"),
        org_session(uuid.uuid4(), app_engine) as s,
    ):
        s.execute(text("DELETE FROM offer"))
