"""Nomination schema: constraints, indexes, FKs, triggers, immutability, RLS (B5-R01/R02)."""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from nautical_deliverance.persistence.db import org_session
from tests.db.test_inquiry_schema import Ids, _inquiry, _ins, _setup
from tests.db.test_offer_schema import _offer
from tests.db.test_rfq_schema import NOW, SENT, _supplier


@dataclass
class Fx:
    """Committed fixtures: org, inquiry, the offer and its supplier's contact."""

    org: uuid.UUID
    ids: Ids
    inq: uuid.UUID
    offer: uuid.UUID


def _nom(s: Session, fx: Fx, **over: Any) -> uuid.UUID:  # noqa: ANN401
    vals: dict[str, Any] = {
        "organization_id": fx.org,
        "inquiry_id": fx.inq,
        "offer_id": fx.offer,
        "contact_id": fx.ids["contact"],
        "created_by": fx.ids["user"],
    }
    return _ins(s, "nomination", **{**vals, **over})


def _make(app_engine: Engine) -> Fx:
    o = uuid.uuid4()
    ids = _setup(app_engine, o)
    with org_session(o, app_engine) as s:
        _supplier(s, o, ids)
        inq = _inquiry(s, o, ids)
        off = _offer(s, o, ids, inq)
    return Fx(o, ids, inq, off)


@pytest.fixture
def fx(app_engine: Engine) -> Fx:
    """Commit an org with a supplier, inquiry and offer."""
    return _make(app_engine)


SENT_N = {**SENT, "sequence": 1}
ACCEPT: list[dict[str, Any]] = [
    {},
    {"status": "withdrawn"},
    {"status": "sent", **SENT_N},
    {"status": "sent", **SENT_N, "sequence": 7},
]
REJECT: list[tuple[str, dict[str, Any]]] = [
    ("nomination_status_valid", {"status": "bogus"}),
    ("nomination_sequence_positive", {"status": "sent", **SENT_N, "sequence": 0}),
    ("nomination_sequence_consistent", {"status": "sent", **SENT}),
    ("nomination_sequence_consistent", {"status": "draft", "sequence": 1}),
    ("nomination_sequence_consistent", {"status": "withdrawn", "sequence": 1}),
    ("nomination_sent_consistent", {"status": "sent", **SENT_N, "sent_body": None}),
    ("nomination_sent_consistent", {"status": "sent", **SENT_N, "sent_at": None}),
    ("nomination_sent_consistent", {"status": "sent", **SENT_N, "inquiry_version_at_send": None}),
    ("nomination_sent_consistent", {"status": "withdrawn", **SENT}),
    ("nomination_sent_consistent", {"status": "draft", "sent_subject": "s"}),
    ("nomination_sent_consistent", {"status": "draft", "sent_to_email": "a@b.c"}),
]


@pytest.mark.req("B5-R01")
@pytest.mark.parametrize("over", ACCEPT)
def test_nomination_accepts(app_engine: Engine, fx: Fx, over: dict[str, Any]) -> None:
    """A valid nomination variant is accepted."""
    with org_session(fx.org, app_engine) as s:
        _nom(s, fx, **over)


@pytest.mark.req("B5-R01")
@pytest.mark.parametrize(("constraint", "over"), REJECT)
def test_nomination_rejects(
    app_engine: Engine, fx: Fx, constraint: str, over: dict[str, Any]
) -> None:
    """Each nomination check rejects its violating row by name."""
    with pytest.raises(IntegrityError, match=constraint), org_session(fx.org, app_engine) as s:
        _nom(s, fx, **over)


@pytest.mark.req("B5-R01")
def test_one_draft_per_inquiry(app_engine: Engine, fx: Fx) -> None:
    """A second draft is rejected; sent and withdrawn rows do not count; withdrawing frees it."""
    with org_session(fx.org, app_engine) as s:
        first = _nom(s, fx)
        _nom(s, fx, status="withdrawn")
        _nom(s, fx, status="sent", **SENT_N)
    with (
        org_session(fx.org, app_engine) as s,
        pytest.raises(IntegrityError, match="nomination_one_draft_idx"),
    ):
        _nom(s, fx)
    with org_session(fx.org, app_engine) as s:
        s.execute(text("UPDATE nomination SET status = 'withdrawn' WHERE id = :i"), {"i": first})
        _nom(s, fx)


@pytest.mark.req("B5-R01")
def test_sequence_unique_per_inquiry_when_sent(app_engine: Engine, fx: Fx) -> None:
    """A sent sequence number cannot repeat within an inquiry, but can in another."""
    with org_session(fx.org, app_engine) as s:
        _nom(s, fx, status="sent", **SENT_N)
        _nom(s, fx, status="sent", **{**SENT_N, "sequence": 2})
    with (
        org_session(fx.org, app_engine) as s,
        pytest.raises(IntegrityError, match="nomination_sequence_idx"),
    ):
        _nom(s, fx, status="sent", **SENT_N)
    with org_session(fx.org, app_engine) as s:
        inq2 = _inquiry(s, fx.org, fx.ids, reference="R2")
        off2 = _offer(s, fx.org, fx.ids, inq2)
        _nom(s, fx, inquiry_id=inq2, offer_id=off2, status="sent", **SENT_N)


@pytest.mark.req("B5-R01")
def test_offer_must_belong_to_inquiry(app_engine: Engine, fx: Fx) -> None:
    """An offer of another inquiry is rejected by the composite FK."""
    with org_session(fx.org, app_engine) as s:
        inq2 = _inquiry(s, fx.org, fx.ids, reference="R2")
        other = _offer(s, fx.org, fx.ids, inq2)
    with (
        pytest.raises(IntegrityError, match="nomination_offer_fk"),
        org_session(fx.org, app_engine) as s,
    ):
        _nom(s, fx, offer_id=other)


@pytest.mark.req("B5-R01")
def test_contact_must_belong_to_offers_counterparty(app_engine: Engine, fx: Fx) -> None:
    """A contact of another supplier is rejected by the trigger; a sibling contact is fine."""
    with org_session(fx.org, app_engine) as s:
        sibling = _ins(
            s,
            "contact",
            organization_id=fx.org,
            counterparty_id=fx.ids["cp"],
            name="C2",
            email="c2@s.com",
        )
        other = dict(fx.ids)
        _supplier(s, fx.org, other, "S2")
    with (
        pytest.raises(DBAPIError, match="nomination_contact_counterparty"),
        org_session(fx.org, app_engine) as s,
    ):
        _nom(s, fx, contact_id=other["contact"])
    with org_session(fx.org, app_engine) as s:
        nid = _nom(s, fx, contact_id=sibling)
    with (  # also on UPDATE
        pytest.raises(DBAPIError, match="nomination_contact_counterparty"),
        org_session(fx.org, app_engine) as s,
    ):
        s.execute(
            text("UPDATE nomination SET contact_id = :c WHERE id = :i"),
            {"c": other["contact"], "i": nid},
        )


@pytest.mark.req("B5-R01")
def test_foreign_keys_cannot_cross_organizations(app_engine: Engine, fx: Fx) -> None:
    """Org B cannot reference org A's inquiry, offer or contact."""
    fb = _make(app_engine)
    for col, val, name in (
        ("inquiry_id", fx.inq, "nomination_inquiry_fk"),
        ("offer_id", fx.offer, "nomination_offer_fk"),
        ("contact_id", fx.ids["contact"], "nomination_contact_fk"),
        ("created_by", fx.ids["user"], "nomination_created_by_fk"),
    ):
        with pytest.raises(IntegrityError, match=name), org_session(fb.org, app_engine) as s:
            _nom(s, fb, **{col: val})


@pytest.mark.req("B5-R01")
@pytest.mark.parametrize(
    "change",
    [
        {"sent_at": NOW + timedelta(seconds=1)},
        {"sent_to_email": "x@y.z"},
        {"sent_subject": "other"},
        {"sent_body": "other"},
        {"sent_body": None},
        {"inquiry_version_at_send": 2},
        {"sequence": 2},
    ],
)
def test_sent_snapshot_is_immutable(app_engine: Engine, fx: Fx, change: dict[str, Any]) -> None:
    """Once sent, no snapshot field or the sequence can change; version still can."""
    with org_session(fx.org, app_engine) as s:
        nid = _nom(s, fx, status="sent", **SENT_N)
        s.execute(text("UPDATE nomination SET version = 2 WHERE id = :i"), {"i": nid})
    col = next(iter(change))
    with (
        pytest.raises(DBAPIError, match="nomination_sent_immutable"),
        org_session(fx.org, app_engine) as s,
    ):
        s.execute(
            text(f"UPDATE nomination SET {col} = :v WHERE id = :i"),  # noqa: S608
            {"v": change[col], "i": nid},
        )


@pytest.mark.req("B5-R01")
@pytest.mark.parametrize("to", ["draft", "withdrawn"])
def test_sent_cannot_move_back(app_engine: Engine, fx: Fx, to: str) -> None:
    """A sent nomination cannot become draft or withdrawn, even with the snapshot cleared."""
    with org_session(fx.org, app_engine) as s:
        nid = _nom(s, fx, status="sent", **SENT_N)
    with pytest.raises(IntegrityError), org_session(fx.org, app_engine) as s:  # checks
        s.execute(text("UPDATE nomination SET status = :t WHERE id = :i"), {"t": to, "i": nid})
    clear = (
        "UPDATE nomination SET status = :t, sequence = NULL, sent_at = NULL, sent_to_email = NULL,"
        " sent_subject = NULL, sent_body = NULL, inquiry_version_at_send = NULL WHERE id = :i"
    )
    with (
        pytest.raises(DBAPIError, match="nomination_sent_immutable"),
        org_session(fx.org, app_engine) as s,
    ):
        s.execute(text(clear), {"t": to, "i": nid})


@pytest.mark.req("B5-R01")
def test_draft_can_be_sent_once(app_engine: Engine, fx: Fx) -> None:
    """A draft is sent (snapshot and sequence filled in) in one update."""
    with org_session(fx.org, app_engine) as s:
        nid = _nom(s, fx)
        s.execute(
            text(
                "UPDATE nomination SET status = 'sent', sequence = 1, sent_at = :t,"
                " sent_to_email = 'a@b.c', sent_subject = 's', sent_body = 'b',"
                " inquiry_version_at_send = 1 WHERE id = :i"
            ),
            {"t": NOW, "i": nid},
        )


@pytest.mark.req("B5-R01")
@pytest.mark.parametrize("action", ["create", "update", "send", "withdraw"])
def test_audit_accepts_nomination_actions(app_engine: Engine, fx: Fx, action: str) -> None:
    """The existing audit verbs cover nominations (ruling R1); no widening needed."""
    with org_session(fx.org, app_engine) as s:
        _ins(
            s,
            "audit_entry",
            organization_id=fx.org,
            actor=fx.ids["user"],
            entity_type="nomination",
            entity_id=uuid.uuid4(),
            action=action,
        )


@pytest.mark.req("B5-R02")
def test_other_org_rows_invisible_and_immutable(app_engine: Engine, fx: Fx) -> None:
    """Org A sees only its nomination; cannot update, nor insert into, org B."""
    fb = _make(app_engine)
    for f in (fx, fb):
        with org_session(f.org, app_engine) as s:
            _nom(s, f)
    with org_session(fx.org, app_engine) as s:
        assert s.execute(text("SELECT count(*) FROM nomination")).scalar_one() == 1
        found = s.execute(
            text("SELECT count(*) FROM nomination WHERE organization_id = :b"), {"b": fb.org}
        )
        assert found.scalar_one() == 0
        upd = s.execute(
            text("UPDATE nomination SET version = 9 WHERE organization_id = :b"), {"b": fb.org}
        )
        assert cast("Any", upd).rowcount == 0
    with (
        pytest.raises(DBAPIError, match="row-level security"),
        org_session(fx.org, app_engine) as s,
    ):
        _nom(s, fb, status="withdrawn")
    with Session(app_engine) as s:  # no org set: nothing visible
        assert s.execute(text("SELECT count(*) FROM nomination")).scalar_one() == 0


@pytest.mark.req("B5-R02")
def test_rls_forced_and_privileges(owner_engine: Engine, app_engine: Engine) -> None:
    """RLS enabled, forced and policed; nd_app has no DELETE or TRUNCATE."""
    with owner_engine.connect() as c:
        row = c.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity,"
                " (SELECT count(*) FROM pg_policies WHERE tablename = 'nomination'),"
                " has_table_privilege('nd_app', 'nomination', 'SELECT'),"
                " has_table_privilege('nd_app', 'nomination', 'INSERT'),"
                " has_table_privilege('nd_app', 'nomination', 'UPDATE'),"
                " has_table_privilege('nd_app', 'nomination', 'DELETE'),"
                " has_table_privilege('nd_app', 'nomination', 'TRUNCATE')"
                " FROM pg_class WHERE relname = 'nomination'"
            )
        ).one()
    assert tuple(row) == (True, True, 1, True, True, True, False, False)
    with (
        pytest.raises(DBAPIError, match="permission denied"),
        org_session(uuid.uuid4(), app_engine) as s,
    ):
        s.execute(text("DELETE FROM nomination"))
