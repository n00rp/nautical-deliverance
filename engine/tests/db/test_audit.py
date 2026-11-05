"""Audit helper: one entry per change, same transaction, per-field diff (B1-R07)."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Engine, select, text

from nautical_deliverance.persistence.audit import Action, record_change
from nautical_deliverance.persistence.db import org_session
from nautical_deliverance.persistence.models import AuditEntry

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

ACTOR = uuid.uuid4()
MAX_SKEW_S = 60


@pytest.fixture
def org(app_engine: Engine) -> uuid.UUID:
    """Create a fresh organization."""
    org_id = uuid.uuid4()
    with org_session(org_id, app_engine) as s:
        s.execute(text("INSERT INTO organization (id, name) VALUES (:o, 'o')"), {"o": org_id})
    return org_id


def _entries(engine: Engine, org: uuid.UUID, entity: uuid.UUID) -> list[AuditEntry]:
    with org_session(org, engine) as s:
        rows = s.scalars(select(AuditEntry).where(AuditEntry.entity_id == entity)).all()
        s.expunge_all()
        return list(rows)


@pytest.mark.req("B1-R07")
def test_create_update_deactivate_write_one_entry_each(app_engine: Engine, org: uuid.UUID) -> None:
    """Each change yields exactly one entry with the right per-field diff."""
    eid = uuid.uuid4()
    steps: list[tuple[Action, dict[str, object] | None, dict[str, object]]] = [
        ("create", None, {"name": "A", "active": True}),
        ("update", {"name": "A"}, {"name": "B"}),
        ("deactivate", {"active": True}, {"active": False}),
    ]
    for action, before, after in steps:
        with org_session(org, app_engine) as s:
            e = record_change(
                s,
                actor=ACTOR,
                entity_type="port",
                entity_id=eid,
                action=action,
                before=before,
                after=after,
            )
            assert e is not None
    entries = sorted(_entries(app_engine, org, eid), key=lambda e: e.at)
    assert [e.action for e in entries] == ["create", "update", "deactivate"]
    assert entries[0].changes == {
        "name": {"before": None, "after": "A"},
        "active": {"before": None, "after": "True"},
    }
    assert entries[1].changes == {"name": {"before": "A", "after": "B"}}
    assert entries[2].changes == {"active": {"before": "True", "after": "False"}}
    assert all(e.actor == ACTOR and e.organization_id == org for e in entries)
    assert all(abs((datetime.now(UTC) - e.at).total_seconds()) < MAX_SKEW_S for e in entries)


@pytest.mark.req("B1-R07")
def test_failure_after_change_leaves_neither_entry_nor_change(
    app_engine: Engine, org: uuid.UUID
) -> None:
    """An exception after the change rolls back both the row and its audit entry."""
    eid = uuid.uuid4()

    def change_then_fail(s: Session) -> None:
        s.execute(
            text("INSERT INTO product (id, organization_id, name) VALUES (:i, :o, 'X')"),
            {"i": eid, "o": org},
        )
        record_change(
            s,
            actor=ACTOR,
            entity_type="product",
            entity_id=eid,
            action="create",
            before=None,
            after={"name": "X"},
        )
        raise RuntimeError

    with pytest.raises(RuntimeError), org_session(org, app_engine) as s:
        change_then_fail(s)
    assert _entries(app_engine, org, eid) == []
    with org_session(org, app_engine) as s:
        assert (
            s.execute(text("SELECT count(*) FROM product WHERE id = :i"), {"i": eid}).scalar_one()
            == 0
        )


@pytest.mark.req("B1-R07")
def test_noop_update_writes_nothing_and_values_are_canonical(
    app_engine: Engine, org: uuid.UUID
) -> None:
    """Equal values write no entry; changed ones are serialized canonically."""
    eid = uuid.uuid4()
    same = {"qty": Decimal("10.50"), "when": datetime(2026, 1, 1, tzinfo=UTC)}
    with org_session(org, app_engine) as s:
        assert (
            record_change(
                s,
                actor=ACTOR,
                entity_type="x",
                entity_id=eid,
                action="update",
                before=same,
                after={"qty": Decimal("10.5"), "when": datetime(2026, 1, 1, tzinfo=UTC)},
            )
            is None
        )
        e = record_change(
            s,
            actor=ACTOR,
            entity_type="x",
            entity_id=eid,
            action="update",
            before={"qty": Decimal(10), "when": None},
            after=same,
        )
        assert e is not None
        assert e.changes == {
            "qty": {"before": "10", "after": "10.5"},
            "when": {"before": None, "after": "2026-01-01T00:00:00+00:00"},
        }
    assert len(_entries(app_engine, org, eid)) == 1
