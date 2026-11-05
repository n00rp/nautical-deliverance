"""Coverage queries: who covers a port for all / some products (B1-R09)."""

import uuid

import pytest
from sqlalchemy import Engine, text

from nautical_deliverance.persistence.db import org_session
from nautical_deliverance.persistence.master_repo import counterparties_covering


@pytest.fixture
def world(app_engine: Engine) -> tuple[uuid.UUID, uuid.UUID, list[uuid.UUID], dict[str, uuid.UUID]]:
    """Org with 4 counterparties of mixed coverage at one port."""
    org, port = uuid.uuid4(), uuid.uuid4()
    prods = [uuid.uuid4() for _ in range(3)]
    cps = {n: uuid.uuid4() for n in "ABCD"}
    other_port = uuid.uuid4()
    with org_session(org, app_engine) as s:
        s.execute(text("INSERT INTO organization (id, name) VALUES (:o, 'o')"), {"o": org})
        for p, loc in ((port, "NLRTM"), (other_port, "SGSIN")):
            s.execute(
                text(
                    "INSERT INTO port (id, organization_id, locode, name, country, time_zone)"
                    " VALUES (:i, :o, :l, 'p', 'XX', 'UTC')"
                ),
                {"i": p, "o": org, "l": loc},
            )
        for i, p in enumerate(prods):
            s.execute(
                text("INSERT INTO product (id, organization_id, name) VALUES (:i, :o, :n)"),
                {"i": p, "o": org, "n": f"P{i}"},
            )
        for n, c in cps.items():
            s.execute(
                text(
                    "INSERT INTO counterparty (id, organization_id, name, type)"
                    " VALUES (:i, :o, :n, 'trader')"
                ),
                {"i": c, "o": org, "n": n},
            )
        # A: p0+p1; B: p0 only; C: other port only; D: p0+p1 but deactivated below
        cover = [
            ("A", port, 0),
            ("A", port, 1),
            ("B", port, 0),
            ("C", other_port, 0),
            ("D", port, 0),
            ("D", port, 1),
        ]
        for n, pt, k in cover:
            s.execute(
                text(
                    "INSERT INTO coverage (organization_id, counterparty_id, port_id, product_id)"
                    " VALUES (:o, :c, :pt, :pr)"
                ),
                {"o": org, "c": cps[n], "pt": pt, "pr": prods[k]},
            )
        s.execute(text("UPDATE counterparty SET active = false WHERE id = :i"), {"i": cps["D"]})
    return org, port, prods, cps


@pytest.mark.req("B1-R09")
def test_all_and_some_sets_exclude_deactivated(
    app_engine: Engine,
    world: tuple[uuid.UUID, uuid.UUID, list[uuid.UUID], dict[str, uuid.UUID]],
) -> None:
    """Exact all/some sets; deactivated, other-port and empty-request cases."""
    org, port, prods, cps = world
    with org_session(org, app_engine) as s:
        req = prods[:2]
        all_ = {c.id for c in counterparties_covering(s, port, req, mode="all")}
        some = {c.id for c in counterparties_covering(s, port, req, mode="some")}
        assert all_ == {cps["A"]}
        assert some == {cps["B"]}  # partial only; D inactive; C wrong port
        assert counterparties_covering(s, port, [], mode="all") == []
        assert {
            c.id for c in counterparties_covering(s, port, [prods[0], prods[0]], mode="all")
        } == {
            cps["A"],
            cps["B"],
        }
