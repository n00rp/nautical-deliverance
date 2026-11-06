"""B4-R09: an Operator can never obtain a price, cost, total, rationale or offer text.

Every route of the app is called as the Operator (403 and 404 bodies included) against inquiries
that carry unique marker values in every commercial field. The route list is read from the app, so
a route added later is swept too; a new kind of path parameter makes the test fail until it is
taught how to fill it in.
"""

import random
import re
import uuid
from decimal import ROUND_HALF_UP, Decimal
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
KINDS = ("ports", "products")
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
    """Return (method, path) of every operation under /api/v1 from the OpenAPI schema."""
    return {
        (method.upper(), path)
        for path, ops in app.openapi()["paths"].items()
        if path.startswith(PREFIX)
        for method in ops
        if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }


def commercial(path: str) -> bool:
    """Routes that exist only for buyers and viewers: the Operator must get 403."""
    return bool(re.search(r"/(rfqs|offers|comparison|select-winner)\b", path))


def test_route_table_is_not_empty() -> None:
    """The enumeration finds the routes the sweep must cover."""
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
    assert {(m, p.removeprefix(PREFIX)) for m, p in table} >= EXPECTED


def master_ids(operator: Oc, path: str) -> dict[str, str]:
    """Real master rows for {item_id} / {contact_id}, so a GET reaches its data (not a 404)."""
    m = re.search(r"(/master/[\w-]+)/{item_id}", path)
    if not m:
        return {}
    first = operator.http.get(f"{PREFIX}{m[1]}").json()
    assert first, f"no master rows for {m[1]}"
    found = {"item_id": first[0]["id"]}
    if "{contact_id}" in path:
        contacts = operator.http.get(f"{PREFIX}{m[1]}/{found['item_id']}/contacts").json()
        assert contacts, f"no contacts for {m[1]}"
        found["contact_id"] = contacts[0]["id"]
    return found


def url_for(operator: Oc, ids: dict[str, str], path: str) -> str:
    """Fill a path template with real rows, so a GET reaches its data."""
    found = {**ids, **master_ids(operator, path)}
    url = re.sub(r"{(\w+)}", lambda m: found.get(m[1], str(uuid.uuid4())), path)
    if path.endswith("/counterparties/suggest"):  # needs its query
        first = [operator.http.get(f"{PREFIX}/master/{k}").json()[0]["id"] for k in KINDS]
        url += "?" + "&".join(
            f"{q}={i}" for q, i in zip(("port_id", "product_id"), first, strict=True)
        )
    return url


def sweep(operator: Oc, ids: dict[str, str]) -> tuple[list[str], dict[tuple[str, str], int]]:
    """Call every route as the Operator; return all response bodies and each route's status."""
    bodies: list[str] = []
    statuses: dict[tuple[str, str], int] = {}  # what was actually requested, with the outcome
    for method, path in sorted(route_table(operator.http.app)):  # type: ignore[arg-type]
        params = set(re.findall(r"{(\w+)}", path))
        if re.search(r"/(inquiries|rfqs|offers)\b", path):
            assert params <= IDS, f"teach this test to fill {params - IDS} in {path}"
        resp = operator.http.request(
            method, url_for(operator, ids, path), json={} if method in WRITES else None
        )
        assert resp.status_code < SERVER_ERROR, (method, path, resp.text)
        if commercial(path):
            assert resp.status_code == FORBIDDEN, (method, path)
        bodies.append(resp.text)
        statuses[method, path] = resp.status_code
    return bodies, statuses


def checked_sweep(operator: Oc, ids: dict[str, str]) -> list[str]:
    """Sweep, then prove every documented route was requested and no GET missed its data."""
    expected = {  # built straight from the schema, independently of the sweep's own enumeration
        (method.upper(), path)
        for path, ops in operator.http.app.openapi()["paths"].items()  # type: ignore[attr-defined]
        for method in ops
    }
    bodies, statuses = sweep(operator, ids)
    assert set(statuses) == expected, f"routes not swept: {expected ^ set(statuses)}"
    for (method, path), code in statuses.items():  # a 404 means the data path was never reached
        if method == "GET":
            assert code == FORBIDDEN or 200 <= code < 300, (method, path, code)  # noqa: PLR2004
    return bodies


def comparison_markers(cmp: dict[str, Any]) -> set[str]:
    """Every money value the comparison shows, the decided total included."""
    found = {cmp["decision"]["decided_total"]}
    for row in cmp["rows"]:
        found |= {row["total"], row["delta_to_lowest"], *(ln["line_cost"] for ln in row["lines"])}
    return found


def variants(marker: str) -> set[str]:
    """Every way a decimal marker may be printed: raw, trailing zeros stripped, quantized."""
    if not re.fullmatch(r"-?\d+\.\d+", marker):
        return {marker}
    d = Decimal(marker)
    forms = {marker, format(d.normalize(), "f")}
    forms |= {format(d.quantize(Decimal(1).scaleb(-n), ROUND_HALF_UP), "f") for n in (2, 3)}
    return forms


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
    pool = random.Random(seed).sample(range(1_000_000, 9_999_999), 120)  # noqa: S311
    numbers = iter([n for n in pool if n % 10])  # last digit non-zero: stripping can't hide it

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
    r = pick(admin, inq, offers[winner]["id"], reason=reason.value, note=note)
    assert r.status_code == OK, r.text
    shown1 = admin.http.get(f"{PREFIX}/inquiries/{inq['id']}/comparison").json()
    first_total = shown1["decision"]["decided_total"]
    markers |= {note, *comparison_markers(shown1), *(o["id"] for o in offers)}
    # Re-select another winner: the history entry now carries the first decision in `before`.
    second = pick(
        admin, inq, offers[(winner + 1) % 3]["id"], reason=reason.value, note=(note2 := text())
    )
    assert second.status_code == OK, second.text
    chosen = offers[(winner + 1) % 3]
    shown = admin.http.get(f"{PREFIX}/inquiries/{inq['id']}/comparison")
    markers |= {note2, *comparison_markers(shown.json())}
    markers = {m for m in markers if m and len(m) >= 6}  # noqa: PLR2004  ("0.00" is not a marker)
    assert len(markers) >= 30  # noqa: PLR2004
    assert all(m in shown.text for m in markers - {note, first_total})  # scanner sees them
    scanned = {v for m in markers for v in variants(m) if len(v) >= 6}  # noqa: PLR2004

    ids = {"inquiry_id": inq["id"], "rfq_id": rfqs[0]["id"], "offer_id": chosen["id"]}
    bodies = checked_sweep(operator, ids)

    everything = "\n".join(bodies)
    assert [m for m in scanned if m in everything] == []
    got = operator.http.get(f"{PREFIX}/inquiries/{inq['id']}")
    assert got.status_code == OK
    final = (winner + 1) % 3  # the re-selected winner
    assert got.json()["winner_counterparty_name"] == NAMES[final]
    assert got.json()["decision"] is None
    assert NAMES[final] in got.text
    listed = operator.http.get(f"{PREFIX}/inquiries").json()
    assert [i["winner_counterparty_name"] for i in listed] == [NAMES[final]]
    assert [i["offer_total"] for i in listed] == [None]  # how many offers came in is commercial
    hist = operator.http.get(f"{PREFIX}/inquiries/{inq['id']}/history").text
    assert NAMES[final] in hist
    for word in ("decision_reason", "decision_note", "decided_total", "winner_offer_id"):
        assert word not in hist
