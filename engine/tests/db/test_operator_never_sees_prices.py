"""B4-R09: an Operator can never obtain a price, cost, total, rationale or offer text.

Every route of the app is called as the Operator (403 and 404 bodies included) against inquiries
that carry unique marker values in every commercial field. The route list is read from the app, so
a route added later is swept too; a new kind of path parameter makes the test fail until it is
taught how to fill it in.
"""

import random
import re
import uuid
from typing import TYPE_CHECKING, Any

import pytest
from hypothesis import HealthCheck, given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

from nautical_deliverance.api.me import get_me_engine
from nautical_deliverance.api.offer_models import COSTS
from nautical_deliverance.domain.identity import Role
from nautical_deliverance.domain.offer import DecisionReason
from nautical_deliverance.main import create_app
from nautical_deliverance.settings import Settings
from tests.db.test_inquiry_api import FORBIDDEN, OK
from tests.db.test_offer_api import Oc, prices
from tests.db.test_offer_decision import pick
from tests.db.test_rfq_api import rfq_world

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy import Engine

PREFIX = "/api/v1"
WRITES = ("POST", "PUT", "PATCH")
IDS = {"inquiry_id", "rfq_id", "offer_id"}  # parameters the sweep fills with real rows
SERVER_ERROR = 500
NAMES = ["Alpha Marine", "Beta Marine", "Gamma Marine"]
EXPECTED = {  # the sweep must see at least these, so a broken enumeration cannot pass silently
    ("GET", "/inquiries"),
    ("GET", "/inquiries/{inquiry_id}"),
    ("GET", "/inquiries/{inquiry_id}/history"),
    ("GET", "/inquiries/{inquiry_id}/comparison"),
    ("POST", "/inquiries/{inquiry_id}/select-winner"),
    ("POST", "/inquiries/{inquiry_id}/rfqs"),
    ("POST", "/rfqs/{rfq_id}/offer"),
    ("GET", "/offers/{offer_id}"),
    ("PATCH", "/offers/{offer_id}"),
    ("GET", "/offers/{offer_id}/history"),
    ("GET", "/users"),
    ("GET", "/me"),
}


def route_table(app: FastAPI) -> set[tuple[str, str]]:
    """Return (method, path) of every route under /api/v1, read from `app.routes`."""
    found: set[tuple[str, str]] = set()
    routes: list[Any] = list(app.routes)
    for route in routes:
        include = getattr(route, "include_context", None)  # an included router, not a Route
        members: list[tuple[str, Any]] = (
            [(include.prefix, r) for r in route.original_router.routes]
            if include
            else [("", route)]
        )
        for prefix, member in members:
            path = prefix + member.path
            if path.startswith(PREFIX):
                found |= {(m, path) for m in member.methods if m != "HEAD"}
    return found


def commercial(path: str) -> bool:
    """Routes that exist only for buyers and viewers: the Operator must get 403."""
    return bool(re.search(r"/(rfqs|offers|comparison|select-winner)\b", path))


def test_route_table_is_not_empty() -> None:
    """The enumeration works: the openapi view and `app.routes` agree on every route."""
    app = create_app(
        Settings(
            git_sha="x",
            database_url="postgresql://t",
            oidc_issuer="i",
            oidc_audience="a",
            oidc_jwks_url="https://i.test/jwks",
        )
    )
    table = route_table(app)
    shown = {(m.upper(), p) for p, ops in app.openapi()["paths"].items() for m in ops}
    assert shown <= table
    assert {(m, p.removeprefix(PREFIX)) for m, p in table} >= EXPECTED


def sweep(operator: Oc, ids: dict[str, str]) -> list[str]:
    """Call every route as the Operator and return all response bodies, errors included."""
    bodies: list[str] = []
    for method, path in sorted(route_table(operator.http.app)):  # type: ignore[arg-type]
        params = set(re.findall(r"{(\w+)}", path))
        if re.search(r"/(inquiries|rfqs|offers)\b", path):
            assert params <= IDS, f"teach this test to fill {params - IDS} in {path}"
        url = re.sub(r"{(\w+)}", lambda m: ids.get(m[1], str(uuid.uuid4())), path)
        resp = operator.http.request(method, url, json={} if method in WRITES else None)
        assert resp.status_code < SERVER_ERROR, (method, path, resp.text)
        if commercial(path):
            assert resp.status_code == FORBIDDEN, (method, path)
        bodies.append(resp.text)
    return bodies


@pytest.mark.req("B4-R09")
@hyp_settings(
    max_examples=6, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    seed=st.integers(0, 2**32),
    winner=st.integers(0, 2),
    reason=st.sampled_from(list(DecisionReason)),
)
def test_operator_never_sees_commercial_data(
    settings: Settings, app_engine: Engine, seed: int, winner: int, reason: DecisionReason
) -> None:
    """No marker of any price, cost, total, rationale or offer text is in any Operator response."""
    numbers = iter(random.Random(seed).sample(range(1_000_000, 9_999_999), 40))  # noqa: S311

    def price() -> str:
        n = next(numbers)
        return f"{n // 1000}.{n % 1000:03d}"  # e.g. 777.123

    def money() -> str:
        n = next(numbers)
        return f"{n // 100}.{n % 100:02d}"

    def text() -> str:
        return f"mk{next(numbers)}z"

    world = rfq_world(app_engine)
    admin, operator = (Oc(settings, app_engine, world, r) for r in (Role.ADMIN, Role.OPERATOR))
    operator.http.app.dependency_overrides[get_me_engine] = lambda: app_engine  # type: ignore[attr-defined]
    inq, rfqs = admin.sent(("Alpha", "a1"), ("Beta", "b1"), ("Gamma", "c1"))
    markers: set[str] = set()
    offers: list[dict[str, Any]] = []
    for rfq in rfqs:
        lines = prices(inq, price(), price())
        extra = {c: money() for c in COSTS} | {
            k: text() for k in ("payment_terms", "physical_supplier", "supplier_comment")
        }
        offers.append(admin.offer(rfq["id"], lines=lines, **extra))
        markers |= {*extra.values(), *(ln["price_per_mt"] for ln in lines)}
    note = text()
    chosen = offers[winner]
    r = pick(admin, inq, chosen["id"], reason=reason.value, note=note)
    assert r.status_code == OK, r.text
    shown = admin.http.get(f"{PREFIX}/inquiries/{inq['id']}/comparison")
    cmp = shown.json()
    markers |= {note, *(o["id"] for o in offers)}
    for row in cmp["rows"]:
        markers |= {row["total"], row["delta_to_lowest"], *(ln["line_cost"] for ln in row["lines"])}
    markers |= {cmp["decision"]["decided_total"]}
    markers = {m for m in markers if m and len(m) >= 6}  # noqa: PLR2004  ("0.00" is not a marker)
    assert len(markers) >= 30  # noqa: PLR2004
    assert all(m in shown.text for m in markers)  # the scanner can see them where they belong

    ids = {"inquiry_id": inq["id"], "rfq_id": rfqs[0]["id"], "offer_id": chosen["id"]}
    bodies = sweep(operator, ids)

    everything = "\n".join(bodies)
    assert [m for m in markers if m in everything] == []
    got = operator.http.get(f"{PREFIX}/inquiries/{inq['id']}")
    assert got.status_code == OK
    assert got.json()["winner_counterparty_name"] == NAMES[winner]
    assert got.json()["decision"] is None
    assert NAMES[winner] in got.text
    listed = operator.http.get(f"{PREFIX}/inquiries").json()
    assert [i["winner_counterparty_name"] for i in listed] == [NAMES[winner]]
    hist = operator.http.get(f"{PREFIX}/inquiries/{inq['id']}/history").text
    assert NAMES[winner] in hist
    for word in ("decision_reason", "decision_note", "decided_total", "winner_offer_id"):
        assert word not in hist
