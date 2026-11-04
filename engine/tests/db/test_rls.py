"""Row-Level Security isolates organizations (D-034)."""

import uuid
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from nautical_deliverance.persistence.db import org_session

if TYPE_CHECKING:
    from sqlalchemy import CursorResult

Probe = tuple[uuid.UUID, uuid.UUID]


def _notes(engine: Engine, org: uuid.UUID) -> list[str]:
    with org_session(org, engine) as s:
        return list(s.scalars(text("SELECT note FROM _rls_probe ORDER BY id")))


@pytest.mark.req("S0-R04")
def test_select_sees_only_own_org(app_engine: Engine, probe: Probe) -> None:
    """Each org sees only its own rows."""
    org_a, org_b = probe
    assert _notes(app_engine, org_a) == ["a"]
    assert _notes(app_engine, org_b) == ["b"]


@pytest.mark.req("S0-R04")
def test_update_and_delete_cannot_touch_other_org(app_engine: Engine, probe: Probe) -> None:
    """Cross-org UPDATE and DELETE affect zero rows."""
    org_a, org_b = probe
    with org_session(org_a, app_engine) as s:
        upd = s.execute(
            text("UPDATE _rls_probe SET note = 'x' WHERE organization_id = :o"), {"o": org_b}
        )
        dele = s.execute(text("DELETE FROM _rls_probe WHERE organization_id = :o"), {"o": org_b})
        assert cast("CursorResult[Any]", upd).rowcount == 0
        assert cast("CursorResult[Any]", dele).rowcount == 0
    assert _notes(app_engine, org_b) == ["b"]


@pytest.mark.req("S0-R04")
def test_insert_for_other_org_rejected(app_engine: Engine, probe: Probe) -> None:
    """WITH CHECK blocks inserting a row for another org."""
    org_a, org_b = probe
    with pytest.raises(DBAPIError), org_session(org_a, app_engine) as s:
        s.execute(
            text("INSERT INTO _rls_probe (organization_id, note) VALUES (:o, 'evil')"),
            {"o": org_b},
        )
    assert _notes(app_engine, org_b) == ["b"]


@pytest.mark.req("S0-R04")
def test_update_cannot_move_row_to_other_org(app_engine: Engine, probe: Probe) -> None:
    """WITH CHECK blocks re-assigning a row to another org."""
    org_a, org_b = probe
    with pytest.raises(DBAPIError), org_session(org_a, app_engine) as s:
        s.execute(
            text("UPDATE _rls_probe SET organization_id = :b WHERE organization_id = :a"),
            {"a": org_a, "b": org_b},
        )
    assert _notes(app_engine, org_a) == ["a"]
    assert _notes(app_engine, org_b) == ["b"]


@pytest.mark.req("S0-R04")
def test_no_org_set_sees_nothing(app_engine: Engine, probe: Probe) -> None:
    """Without an org setting (even after pool reuse) no rows are visible."""
    _notes(app_engine, probe[0])  # leaves an empty-string setting on a pooled connection
    with Session(app_engine) as s:
        for table in ("_rls_probe", "organization", "app_user"):
            assert s.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0  # noqa: S608


@pytest.mark.req("S0-R04")
def test_identity_tables_isolated(app_engine: Engine) -> None:
    """Organization and app_user are isolated per org."""
    org_a, org_b, user_a, user_b = (uuid.uuid4() for _ in range(4))
    for org, user, name in ((org_a, user_a, "A"), (org_b, user_b, "B")):
        with org_session(org, app_engine) as s:
            s.execute(
                text("INSERT INTO organization (id, name) VALUES (:i, :n)"), {"i": org, "n": name}
            )
            s.execute(
                text(
                    "INSERT INTO app_user (id, organization_id, last_seen_at)"
                    " VALUES (:u, :o, now())"
                ),
                {"u": user, "o": org},
            )
    with org_session(org_a, app_engine) as s:
        assert list(s.scalars(text("SELECT id FROM app_user"))) == [user_a]
        assert list(s.scalars(text("SELECT id FROM organization"))) == [org_a]
    with pytest.raises(DBAPIError), org_session(org_a, app_engine) as s:
        s.execute(
            text("INSERT INTO app_user (id, organization_id, last_seen_at) VALUES (:u, :o, now())"),
            {"u": uuid.uuid4(), "o": org_b},
        )


@pytest.mark.req("S0-R04")
def test_app_role_cannot_bypass_rls(app_engine: Engine) -> None:
    """nd_app has no bypass, owns nothing, and cannot run DDL."""
    with Session(app_engine) as s:
        bypass = s.execute(
            text("SELECT rolbypassrls OR rolsuper FROM pg_roles WHERE rolname = 'nd_app'")
        ).scalar_one()
        owned = s.execute(text("SELECT count(*) FROM pg_tables WHERE tableowner = 'nd_app'"))
        assert bypass is False
        assert owned.scalar_one() == 0
        with pytest.raises(DBAPIError):
            s.execute(text("CREATE TABLE evil (id int)"))
