"""Migration 0007 copies the operators' names before dropping the id columns (B7-D10)."""

import uuid
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

from tests.db.conftest import ROOT

if TYPE_CHECKING:
    from sqlalchemy import Connection


def _cfg() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(ROOT / "src/nautical_deliverance/persistence/migrations")
    )
    return cfg


def _put(conn: Connection, sql: str, **kw: object) -> uuid.UUID:
    ident = uuid.uuid4()
    conn.execute(text(sql), {"id": ident, **kw})
    return ident


def _column(conn: Connection, table: str, column: str) -> str | None:
    return conn.execute(
        text(
            "SELECT is_nullable FROM information_schema.columns"
            " WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).scalar()


def _scope(conn: Connection, org: uuid.UUID) -> None:
    conn.execute(text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(org)})


def _seed_at_0006(conn: Connection, org: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """One org with two operator users (named, unnamed), two inquiries and one vessel."""
    _scope(conn, org)
    conn.execute(text("INSERT INTO organization (id, name) VALUES (:o, 'm7')"), {"o": org})
    user = "INSERT INTO app_user (id, organization_id, last_seen_at, name, email)"
    named = _put(conn, user + " VALUES (:id, :o, now(), 'Olga Operator', 'olga@x.example')", o=org)
    unnamed = _put(conn, user + " VALUES (:id, :o, now(), '', 'ops@x.example')", o=org)
    le = _put(
        conn,
        "INSERT INTO legal_entity (id, organization_id, name, code) VALUES (:id, :o, 'L', 'L')",
        o=org,
    )
    vessel = _put(
        conn,
        "INSERT INTO vessel (id, organization_id, name, imo, vessel_type, dwt, flag,"
        " legal_entity_id, default_operator) VALUES (:id, :o, 'V', '9074729', 't', 1, 'PA', :le,"
        " :op)",
        o=org, le=le, op=named,
    )  # fmt: skip
    port = _put(
        conn,
        "INSERT INTO port (id, organization_id, locode, name, country, time_zone)"
        " VALUES (:id, :o, 'NLRTM', 'R', 'NL', 'Europe/Amsterdam')",
        o=org,
    )
    reason = _put(
        conn, "INSERT INTO bunkering_reason (id, organization_id, name) VALUES (:id, :o, 'B')",
        o=org,
    )  # fmt: skip
    made = []
    for n, op in enumerate((named, unnamed)):
        made.append(
            _put(
                conn,
                "INSERT INTO inquiry (id, organization_id, reference, vessel_id, legal_entity_id,"
                " port_id, bunkering_reason_id, operator_id, requester_id, created_by)"
                " VALUES (:id, :o, :ref, :v, :le, :p, :r, :op, :op, :op)",
                o=org, ref=f"M7-{n}", v=vessel, le=le, p=port, r=reason, op=op,
            )
        )  # fmt: skip
    return made[0], made[1], vessel


@pytest.mark.req("B7a-R04")
def test_0007_copies_operator_names(owner_engine: Engine) -> None:
    """Names (else e-mails) survive the upgrade; the downgrade brings back a nullable id."""
    cfg, org = _cfg(), uuid.uuid4()
    command.downgrade(cfg, "0006")
    try:
        with owner_engine.begin() as conn:
            olga, ops, vessel = _seed_at_0006(conn, org)
        command.upgrade(cfg, "0007")
        with owner_engine.begin() as conn:
            _scope(conn, org)
            rows = conn.execute(
                text("SELECT id, operator_name FROM inquiry WHERE organization_id = :o"),
                {"o": org},
            ).all()
            default = conn.execute(
                text("SELECT default_operator_name FROM vessel WHERE id = :v"), {"v": vessel}
            ).scalar()
        names = {r.id: r.operator_name for r in rows}
        assert names == {olga: "Olga Operator", ops: "ops@x.example"}
        assert default == "Olga Operator"
        with owner_engine.connect() as conn:
            forced = conn.execute(
                text("SELECT relname, relforcerowsecurity FROM pg_class WHERE relname IN"
                     " ('inquiry', 'vessel', 'app_user') AND relkind = 'r'")
            ).all()  # fmt: skip
            assert dict(forced) == {"inquiry": True, "vessel": True, "app_user": True}
            assert _column(conn, "inquiry", "operator_id") is None
            assert _column(conn, "vessel", "default_operator") is None
        command.downgrade(cfg, "0006")
        with owner_engine.connect() as conn:
            assert _column(conn, "inquiry", "operator_id") == "YES"
            assert _column(conn, "vessel", "default_operator") == "YES"
            assert _column(conn, "inquiry", "operator_name") is None
            fk = conn.execute(
                text("SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                     " WHERE conname = 'inquiry_operator_fk'")
            ).scalar()  # fmt: skip
            assert fk == (
                "FOREIGN KEY (organization_id, operator_id)"
                " REFERENCES app_user(organization_id, id)"
            )
    finally:
        command.upgrade(cfg, "head")
