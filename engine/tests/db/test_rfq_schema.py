"""RFQ schema: constraints, one-active index, contact FK, immutability, RLS (B3-R01/R02)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from nautical_deliverance.persistence.db import org_session
from tests.db.test_inquiry_schema import Ids, _inquiry, _ins, _setup

NOW = datetime(2026, 12, 1, tzinfo=UTC)
SENT = {
    "sent_at": NOW,
    "sent_to_email": "a@b.c",
    "sent_subject": "s",
    "sent_body": "b",
    "inquiry_version_at_send": 1,
}


def _supplier(s: Session, org: uuid.UUID, ids: Ids, name: str = "S") -> None:
    o = {"organization_id": org}
    cp = _ins(s, "counterparty", **o, name=name, type="physical_supplier")
    ids["cp"] = cp
    ids["contact"] = _ins(s, "contact", **o, counterparty_id=cp, name="C", email="c@s.com")


def _rfq(s: Session, org: uuid.UUID, ids: Ids, inq: uuid.UUID, **over: Any) -> uuid.UUID:  # noqa: ANN401
    vals: dict[str, Any] = {
        "organization_id": org,
        "inquiry_id": inq,
        "counterparty_id": ids["cp"],
        "contact_id": ids["contact"],
        "response_deadline": NOW,
        "generated_at": NOW,
        "created_by": ids["user"],
    }
    return _ins(s, "rfq", **{**vals, **over})


@pytest.fixture
def org(app_engine: Engine) -> tuple[uuid.UUID, Ids]:
    """One populated org with a supplier and contact."""
    o = uuid.uuid4()
    ids = _setup(app_engine, o)
    with org_session(o, app_engine) as s:
        _supplier(s, o, ids)
    return o, ids


RFQ_ACCEPT: list[dict[str, Any]] = [
    {},
    {"status": "withdrawn"},
    {"status": "sent", **SENT},
    {"status": "declined", **SENT},
]
RFQ_REJECT: list[tuple[str, dict[str, Any]]] = [
    ("rfq_status_valid", {"status": "bogus"}),
    ("rfq_sent_consistent", {"status": "sent"}),
    ("rfq_sent_consistent", {"status": "declined", **SENT, "sent_body": None}),
    ("rfq_sent_consistent", {"status": "sent", **SENT, "sent_at": None}),
    ("rfq_sent_consistent", {"status": "withdrawn", **SENT}),
    ("rfq_sent_consistent", {"status": "draft", "sent_subject": "s"}),
    ("rfq_sent_consistent", {"status": "withdrawn", "sent_to_email": "a@b.c"}),
    ("rfq_sent_consistent", {"status": "sent", **SENT, "inquiry_version_at_send": None}),
]


@pytest.mark.req("B3-R01")
@pytest.mark.parametrize("over", RFQ_ACCEPT)
def test_rfq_accepts(app_engine: Engine, org: tuple[uuid.UUID, Ids], over: dict[str, Any]) -> None:
    """A valid rfq variant is accepted."""
    o, ids = org
    with org_session(o, app_engine) as s:
        _rfq(s, o, ids, _inquiry(s, o, ids), **over)


@pytest.mark.req("B3-R01")
@pytest.mark.parametrize(("constraint", "over"), RFQ_REJECT)
def test_rfq_rejects(
    app_engine: Engine, org: tuple[uuid.UUID, Ids], constraint: str, over: dict[str, Any]
) -> None:
    """Each rfq check rejects its violating row by name."""
    o, ids = org
    with org_session(o, app_engine) as s:
        inq = _inquiry(s, o, ids)
        with pytest.raises(IntegrityError, match=constraint):
            _rfq(s, o, ids, inq, **over)


@pytest.mark.req("B3-R01")
def test_one_active_rfq_per_pair_and_withdrawn_frees_it(
    app_engine: Engine, org: tuple[uuid.UUID, Ids]
) -> None:
    """A second non-withdrawn rfq for the pair is rejected; withdrawing frees the pair."""
    o, ids = org
    with org_session(o, app_engine) as s:
        inq = _inquiry(s, o, ids)
        first = _rfq(s, o, ids, inq)
    with (
        org_session(o, app_engine) as s,
        pytest.raises(IntegrityError, match="rfq_one_active_idx"),
    ):
        _rfq(s, o, ids, inq)
    with org_session(o, app_engine) as s:
        s.execute(text("UPDATE rfq SET status = 'withdrawn' WHERE id = :i"), {"i": first})
        _rfq(s, o, ids, inq)
        _rfq(s, o, ids, inq, status="withdrawn")
    with org_session(o, app_engine) as s:  # a different supplier on the same inquiry is fine
        _supplier(s, o, ids, "S2")
        _rfq(s, o, ids, inq)


@pytest.mark.req("B3-R01")
def test_contact_must_belong_to_counterparty(
    app_engine: Engine, org: tuple[uuid.UUID, Ids]
) -> None:
    """A contact of another supplier is rejected by the composite FK."""
    o, ids = org
    with org_session(o, app_engine) as s:
        inq = _inquiry(s, o, ids)
        other = dict(ids)
        _supplier(s, o, other, "S2")
        with pytest.raises(IntegrityError, match="rfq_contact_fk"):
            _rfq(s, o, ids, inq, contact_id=other["contact"])


@pytest.mark.req("B3-R01")
def test_foreign_keys_cannot_cross_organizations(
    app_engine: Engine, org: tuple[uuid.UUID, Ids]
) -> None:
    """Org B cannot reference org A's supplier or inquiry."""
    _, ids_a = org
    org_a2, org_b = uuid.uuid4(), uuid.uuid4()
    ids_a2, ids_b = _setup(app_engine, org_a2), _setup(app_engine, org_b)
    with org_session(org_a2, app_engine) as s:
        inq_a = _inquiry(s, org_a2, ids_a2)
    with org_session(org_b, app_engine) as s:
        _supplier(s, org_b, ids_b)
        inq_b = _inquiry(s, org_b, ids_b)
    with (
        pytest.raises(IntegrityError, match="rfq_counterparty_fk"),
        org_session(org_b, app_engine) as s,
    ):
        _rfq(s, org_b, ids_b, inq_b, counterparty_id=ids_a["cp"])
    with (
        pytest.raises(IntegrityError, match="rfq_inquiry_fk"),
        org_session(org_b, app_engine) as s,
    ):
        _rfq(s, org_b, ids_b, inq_a)


@pytest.mark.req("B3-R01")
@pytest.mark.parametrize(
    "change",
    [
        {"sent_at": NOW + timedelta(seconds=1)},
        {"sent_to_email": "x@y.z"},
        {"sent_subject": "other"},
        {"sent_body": "other"},
        {"sent_body": None},
        {"inquiry_version_at_send": 2},
    ],
)
def test_sent_snapshot_is_immutable(
    app_engine: Engine, org: tuple[uuid.UUID, Ids], change: dict[str, Any]
) -> None:
    """Once sent, no snapshot field can change; status and version still can."""
    o, ids = org
    with org_session(o, app_engine) as s:
        rid = _rfq(s, o, ids, _inquiry(s, o, ids), status="sent", **SENT)
        s.execute(text("UPDATE rfq SET status = 'declined', version = 2 WHERE id = :i"), {"i": rid})
    col = next(iter(change))
    with pytest.raises(DBAPIError, match="rfq_sent_immutable"), org_session(o, app_engine) as s:
        s.execute(text(f"UPDATE rfq SET {col} = :v WHERE id = :i"), {"v": change[col], "i": rid})  # noqa: S608


@pytest.mark.req("B3-R01")
def test_draft_can_be_sent_once(app_engine: Engine, org: tuple[uuid.UUID, Ids]) -> None:
    """A draft is sent (snapshot filled in) in one update."""
    o, ids = org
    with org_session(o, app_engine) as s:
        rid = _rfq(s, o, ids, _inquiry(s, o, ids))
        s.execute(
            text(
                "UPDATE rfq SET status = 'sent', sent_at = :t, sent_to_email = 'a@b.c',"
                " sent_subject = 's', sent_body = 'b', inquiry_version_at_send = 1 WHERE id = :i"
            ),
            {"t": NOW, "i": rid},
        )


@pytest.mark.req("B3-R01")
def test_inquiry_rfq_deadline_nullable(app_engine: Engine, org: tuple[uuid.UUID, Ids]) -> None:
    """inquiry.rfq_deadline exists and is optional."""
    o, ids = org
    with org_session(o, app_engine) as s:
        a = _inquiry(s, o, ids)
        b = _inquiry(s, o, ids, reference="R2", rfq_deadline=NOW)
        rows = s.execute(text("SELECT id, rfq_deadline FROM inquiry")).all()
    assert {r[0]: r[1] for r in rows} == {a: None, b: NOW}


@pytest.mark.req("B3-R01")
@pytest.mark.parametrize("action", ["send", "withdraw", "decline"])
def test_audit_accepts_rfq_actions(
    app_engine: Engine, org: tuple[uuid.UUID, Ids], action: str
) -> None:
    """audit_entry.action allows the B3 actions."""
    o, ids = org
    with org_session(o, app_engine) as s:
        _ins(
            s,
            "audit_entry",
            organization_id=o,
            actor=ids["user"],
            entity_type="rfq",
            entity_id=uuid.uuid4(),
            action=action,
        )


@pytest.mark.req("B3-R02")
def test_other_org_rows_invisible_and_immutable(app_engine: Engine) -> None:
    """Org A sees only its rfq; cannot update, nor insert into, org B."""
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    all_ids = []
    for o in (org_a, org_b):
        ids = _setup(app_engine, o)
        with org_session(o, app_engine) as s:
            _supplier(s, o, ids)
            _rfq(s, o, ids, _inquiry(s, o, ids))
        all_ids.append(ids)
    with org_session(org_a, app_engine) as s:
        assert s.execute(text("SELECT count(*) FROM rfq")).scalar_one() == 1
        found = s.execute(text("SELECT count(*) FROM rfq WHERE organization_id = :b"), {"b": org_b})
        assert found.scalar_one() == 0
        upd = s.execute(text("UPDATE rfq SET version = 9 WHERE organization_id = :b"), {"b": org_b})
        assert cast("Any", upd).rowcount == 0
    with (
        pytest.raises(DBAPIError, match="row-level security"),
        org_session(org_a, app_engine) as s,
    ):
        _rfq(s, org_b, all_ids[1], _inquiry(s, org_b, all_ids[1], reference="R9"))
    with Session(app_engine) as s:  # no org set: nothing visible
        assert s.execute(text("SELECT count(*) FROM rfq")).scalar_one() == 0


@pytest.mark.req("B3-R02")
def test_rls_forced_and_privileges(owner_engine: Engine, app_engine: Engine) -> None:
    """RLS enabled, forced and policed; nd_app has no DELETE or TRUNCATE."""
    with owner_engine.connect() as c:
        row = c.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity,"
                " (SELECT count(*) FROM pg_policies WHERE tablename = 'rfq'),"
                " has_table_privilege('nd_app', 'rfq', 'SELECT'),"
                " has_table_privilege('nd_app', 'rfq', 'INSERT'),"
                " has_table_privilege('nd_app', 'rfq', 'UPDATE'),"
                " has_table_privilege('nd_app', 'rfq', 'DELETE'),"
                " has_table_privilege('nd_app', 'rfq', 'TRUNCATE')"
                " FROM pg_class WHERE relname = 'rfq'"
            )
        ).one()
    assert tuple(row) == (True, True, 1, True, True, True, False, False)
    with (
        pytest.raises(DBAPIError, match="permission denied"),
        org_session(uuid.uuid4(), app_engine) as s,
    ):
        s.execute(text("DELETE FROM rfq"))
