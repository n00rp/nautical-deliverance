"""Master-data REST API: role matrix, validation, lifecycle, concurrency, audit."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text

from nautical_deliverance.api.auth import get_principal
from nautical_deliverance.api.master import get_master_engine
from nautical_deliverance.domain.identity import Principal, Role
from nautical_deliverance.main import create_app
from nautical_deliverance.persistence.db import org_session
from nautical_deliverance.persistence.models import AuditEntry, Coverage

if TYPE_CHECKING:
    from httpx import Response

    from nautical_deliverance.settings import Settings

type Json = Any

BASE = "/api/v1/master"
STALE = {"detail": "Record was changed by someone else"}
SECOND = 2
OK, CREATED, CONFLICT, UNPROCESSABLE = (
    HTTPStatus.OK,
    HTTPStatus.CREATED,
    HTTPStatus.CONFLICT,
    HTTPStatus.UNPROCESSABLE_ENTITY,
)
TYPES = (
    "legal-entities",
    "vessels",
    "ports",
    "counterparties",
    "products",
    "iso-spec-versions",
    "bunkering-reasons",
)


class Api:
    """A client acting as one principal in one organization."""

    def __init__(  # noqa: D107
        self,
        settings: Settings,
        engine: Engine,
        org: uuid.UUID,
        roles: frozenset[Role] = frozenset({Role.ADMIN}),
        user: uuid.UUID | None = None,
    ) -> None:
        self.org, self.user, self.engine = org, user or uuid.uuid4(), engine
        app = create_app(settings)
        principal = Principal(self.user, org, roles)
        app.dependency_overrides[get_principal] = lambda: principal
        app.dependency_overrides[get_master_engine] = lambda: engine
        self.app = app
        self.http = TestClient(app)

    def post(self, path: str, body: object, expect: int = CREATED) -> Json:  # noqa: D102
        r = self.http.post(f"{BASE}/{path}", json=body)
        assert r.status_code == expect, r.text
        return r.json()

    def patch(self, path: str, body: object, expect: int = OK) -> Json:  # noqa: D102
        r = self.http.patch(f"{BASE}/{path}", json=body)
        assert r.status_code == expect, r.text
        return r.json()

    def put(self, path: str, body: object, expect: int = OK) -> Json:  # noqa: D102
        r = self.http.put(f"{BASE}/{path}", json=body)
        assert r.status_code == expect, r.text
        return r.json()

    def get(self, path: str, expect: int = OK) -> Json:  # noqa: D102
        r = self.http.get(f"{BASE}/{path}")
        assert r.status_code == expect, r.text
        return r.json()

    def entries(self, entity: str) -> list[AuditEntry]:  # noqa: D102
        with org_session(self.org, self.engine) as s:
            rows = s.scalars(select(AuditEntry).where(AuditEntry.entity_type == entity)).all()
            s.expunge_all()
            return list(rows)


@pytest.fixture
def org(app_engine: Engine) -> uuid.UUID:
    """Create a fresh organization."""
    org_id = uuid.uuid4()
    with org_session(org_id, app_engine) as s:
        s.execute(text("INSERT INTO organization (id, name) VALUES (:o, 'o')"), {"o": org_id})
    return org_id


@pytest.fixture
def admin(settings: Settings, app_engine: Engine, org: uuid.UUID) -> Api:
    """Admin of the fresh organization."""
    return Api(settings, app_engine, org)


@pytest.fixture
def other(settings: Settings, app_engine: Engine) -> Api:
    """Admin of a second organization."""
    org_id = uuid.uuid4()
    with org_session(org_id, app_engine) as s:
        s.execute(text("INSERT INTO organization (id, name) VALUES (:o, 'b')"), {"o": org_id})
    return Api(settings, app_engine, org_id)


def _imo(six: str) -> str:
    weighted = sum(int(d) * w for d, w in zip(six, range(7, 1, -1), strict=True))
    return f"{six}{weighted % 10}"


def entity(api: Api, code: str = "LE1") -> Json:  # noqa: D103
    return api.post("legal-entities", {"name": "Entity", "code": code})


def vessel_body(le_id: str, imo: str = "907472") -> Json:  # noqa: D103
    return {
        "name": "V",
        "imo": _imo(imo),
        "vessel_type": "tanker",
        "dwt": 50000,
        "flag": "PA",
        "legal_entity_id": le_id,
    }


def vessel(api: Api, imo: str = "907472") -> Json:  # noqa: D103
    return api.post("vessels", vessel_body(entity(api, f"L{imo}")["id"], imo))


def port(api: Api, locode: str = "NLRTM") -> Json:  # noqa: D103
    return api.post(
        "ports",
        {"locode": locode, "name": "P", "country": locode[:2], "time_zone": "Europe/Amsterdam"},
    )


def product(api: Api, name: str = "HSFO") -> Json:  # noqa: D103
    return api.post("products", {"name": name, "default_unit": "mt"})


def counterparty(api: Api, name: str = "CP") -> Json:  # noqa: D103
    return api.post("counterparties", {"name": name, "type": "trader"})


def fields(r: Response) -> dict[str, str]:
    """Map field -> message of a 422 response."""
    assert r.status_code == UNPROCESSABLE, r.text
    return {e["field"]: e["message"] for e in r.json()["detail"]}


# --- B1-R05: role matrix -------------------------------------------------------------------


def _master_routes(api: Api) -> list[tuple[str, str]]:
    """List (method, full path) of every route under BASE, flattening included routers."""
    found: list[tuple[str, str]] = []
    top: Any
    for top in api.app.routes:
        prefix, routes = "", [top]
        if hasattr(top, "original_router"):  # FastAPI >= 0.16x wraps include_router()
            prefix, routes = top.include_context.prefix, top.original_router.routes
        for route in routes:
            if isinstance(route, APIRoute) and (prefix + route.path).startswith(BASE):
                methods = sorted((route.methods or set()) - {"HEAD", "OPTIONS"})
                found.extend((m, prefix + route.path) for m in methods)
    return found


@pytest.mark.req("B1-R05")
@pytest.mark.parametrize("role", list(Role))
def test_role_matrix_over_every_registered_route(
    settings: Settings, app_engine: Engine, org: uuid.UUID, role: Role
) -> None:
    """All roles read; only admin writes; routes come from app.routes so none can escape."""
    api = Api(settings, app_engine, org, frozenset({role}))
    routes = _master_routes(api)
    assert len(routes) > 40  # noqa: PLR2004 - guards against an empty/shrunken enumeration
    for method, path in routes:
        url = path.replace("{item_id}", str(uuid.uuid4())).replace(
            "{contact_id}", str(uuid.uuid4())
        )
        status = api.http.request(method, url, json={}).status_code
        if method == "GET" or role is Role.ADMIN:
            assert status != HTTPStatus.FORBIDDEN, (method, path)
        else:
            assert status == HTTPStatus.FORBIDDEN, (method, path)
        assert status < HTTPStatus.INTERNAL_SERVER_ERROR, (method, path)


@pytest.mark.req("B1-R05")
def test_no_roles_cannot_read(settings: Settings, app_engine: Engine, org: uuid.UUID) -> None:
    """A principal without any known role is forbidden even for reads."""
    api = Api(settings, app_engine, org, frozenset())
    assert api.http.get(f"{BASE}/ports").status_code == HTTPStatus.FORBIDDEN


@pytest.mark.req("B1-R05")
def test_writes_by_non_admin_leave_no_trace(
    settings: Settings, app_engine: Engine, admin: Api
) -> None:
    """A viewer's POST is rejected and creates nothing."""
    viewer = Api(settings, app_engine, admin.org, frozenset({Role.VIEWER}))
    r = viewer.http.post(f"{BASE}/products", json={"name": "X"})
    assert r.status_code == HTTPStatus.FORBIDDEN
    assert admin.get("products") == []


# --- B1-R06: no delete, soft deactivation ----------------------------------------------------


@pytest.mark.req("B1-R06")
def test_no_delete_routes(admin: Api) -> None:
    """No DELETE method is registered anywhere under /api/v1/master."""
    assert not [r for m, r in _master_routes(admin) if m == "DELETE"]


@pytest.mark.req("B1-R06")
@pytest.mark.parametrize("kind", TYPES)
def test_deactivate_hides_by_default_but_resolves_by_id(admin: Api, kind: str) -> None:
    """Default list hides inactive rows; active=false|all show them; id still resolves."""
    le = entity(admin)
    makers: dict[str, Any] = {
        "legal-entities": lambda: le,
        "vessels": lambda: admin.post("vessels", vessel_body(le["id"])),
        "ports": lambda: port(admin),
        "counterparties": lambda: counterparty(admin),
        "products": lambda: product(admin),
        "iso-spec-versions": lambda: admin.post("iso-spec-versions", {"name": "ISO 8217:2017"}),
        "bunkering-reasons": lambda: admin.post("bunkering-reasons", {"name": "Bunkers"}),
    }
    row = makers[kind]()
    assert row["active"] is True

    done = admin.post(f"{kind}/{row['id']}/deactivate", {"version": row["version"]}, OK)

    assert done["active"] is False
    assert done["version"] == row["version"] + 1
    assert row["id"] not in [r["id"] for r in admin.get(kind)]
    assert row["id"] not in [r["id"] for r in admin.get(f"{kind}?active=true")]
    assert row["id"] in [r["id"] for r in admin.get(f"{kind}?active=false")]
    assert row["id"] in [r["id"] for r in admin.get(f"{kind}?active=all")]
    assert admin.get(f"{kind}/{row['id']}")["active"] is False

    back = admin.post(f"{kind}/{row['id']}/reactivate", {"version": done["version"]}, OK)
    assert back["active"] is True
    assert back["version"] == done["version"] + 1
    assert row["id"] in [r["id"] for r in admin.get(kind)]


@pytest.mark.req("B1-R06")
def test_bad_active_filter_and_unknown_ids(admin: Api, other: Api) -> None:
    """Unknown filter is 422; unknown or foreign ids are 404."""
    assert admin.http.get(f"{BASE}/ports?active=maybe").status_code == UNPROCESSABLE
    assert admin.http.get(f"{BASE}/ports/{uuid.uuid4()}").status_code == HTTPStatus.NOT_FOUND
    foreign = port(other)
    assert admin.http.get(f"{BASE}/ports/{foreign['id']}").status_code == HTTPStatus.NOT_FOUND
    assert admin.http.get(f"{BASE}/ports/{foreign['id']}/history").status_code == (
        HTTPStatus.NOT_FOUND
    )


@pytest.mark.req("B1-R06")
def test_search_filters_by_text(admin: Api) -> None:
    """Q matches case-insensitively and treats wildcards literally."""
    product(admin, "Marine Gas Oil")
    product(admin, "HSFO")
    assert [p["name"] for p in admin.get("products?q=gas")] == ["Marine Gas Oil"]
    assert admin.get("products?q=%25") == []


# --- B1-R02: validation ----------------------------------------------------------------------


@pytest.mark.req("B1-R02")
def test_duplicate_locode_is_422_on_locode(admin: Api) -> None:
    """A second port with the same LOCODE is a field error."""
    port(admin)
    r = admin.http.post(
        f"{BASE}/ports",
        json={"locode": "NLRTM", "name": "P2", "country": "NL", "time_zone": "UTC"},
    )
    assert list(fields(r)) == ["locode"]


@pytest.mark.req("B1-R02")
def test_duplicate_imo_and_legal_entity_code_are_422(admin: Api) -> None:
    """Duplicate IMO and duplicate legal-entity code map to their own fields."""
    v = vessel(admin)
    r = admin.http.post(f"{BASE}/vessels", json=vessel_body(v["legal_entity_id"]))
    assert list(fields(r)) == ["imo"]
    r = admin.http.post(f"{BASE}/legal-entities", json={"name": "E", "code": "L907472"})
    assert list(fields(r)) == ["code"]


@pytest.mark.req("B1-R02")
def test_duplicate_names_are_422_on_name(admin: Api) -> None:
    """Products, ISO versions and reasons are unique by name per organization."""
    for kind in ("products", "iso-spec-versions", "bunkering-reasons"):
        admin.post(kind, {"name": "Same"})
        assert list(fields(admin.http.post(f"{BASE}/{kind}", json={"name": "Same"}))) == ["name"]


@pytest.mark.req("B1-R02")
def test_duplicate_coverage_triple_and_fuel_pair_are_422(admin: Api) -> None:
    """The same triple or pair twice in one PUT is a field error, not 500."""
    cp, p, pr, v = counterparty(admin), port(admin), product(admin), vessel(admin)
    item = {"port_id": p["id"], "product_id": pr["id"]}
    r = admin.http.put(
        f"{BASE}/counterparties/{cp['id']}/coverage",
        json={"version": cp["version"], "items": [item, item]},
    )
    assert list(fields(r)) == ["items"]
    r = admin.http.put(
        f"{BASE}/vessels/{v['id']}/approved-fuels",
        json={"version": v["version"], "items": [{"product_id": pr["id"]}] * 2},
    )
    assert list(fields(r)) == ["items"]


@pytest.mark.req("B1-R02")
def test_invalid_formats_are_422_with_field_names(admin: Api) -> None:
    """IMO, LOCODE, time zone, e-mail, flag, type, country, dwt, enums, extras."""
    le = entity(admin)
    bad_vessel = {**vessel_body(le["id"]), "imo": "1234568", "flag": " ", "vessel_type": "x" * 81}
    bad_vessel["dwt"] = 0
    f = fields(admin.http.post(f"{BASE}/vessels", json=bad_vessel))
    assert set(f) == {"imo", "flag", "vessel_type", "dwt"}

    f = fields(
        admin.http.post(
            f"{BASE}/ports",
            json={
                "locode": "nlrtm",
                "name": "P",
                "country": "Netherlands",
                "time_zone": "Mars/Base",
            },
        )
    )
    assert set(f) == {"locode", "country", "time_zone"}

    cp = counterparty(admin)
    for email in (
        "a",
        "a@b",
        "a b@c.de",
        "@c.de",
        "a@.de",
        "a@c.",
        "a@@c.de",
        "a@c.de" + "x" * 260,
    ):
        r = admin.http.post(
            f"{BASE}/counterparties/{cp['id']}/contacts", json={"name": "N", "email": email}
        )
        assert list(fields(r)) == ["email"], email

    f = fields(admin.http.post(f"{BASE}/counterparties", json={"name": "C", "type": "pirate"}))
    assert list(f) == ["type"]
    f = fields(admin.http.post(f"{BASE}/products", json={"name": "P", "default_unit": "kg"}))
    assert list(f) == ["default_unit"]
    f = fields(admin.http.post(f"{BASE}/products", json={"name": "  "}))
    assert list(f) == ["name"]
    f = fields(admin.http.post(f"{BASE}/products", json={"name": "P", "actor": str(uuid.uuid4())}))
    assert list(f) == ["actor"]


@pytest.mark.req("B1-R02")
def test_422_body_shape_and_patch_validation(admin: Api) -> None:
    """Errors are {detail: [{field, message}]}; PATCH validates too; null on required is 422."""
    v = vessel(admin)
    r = admin.http.patch(f"{BASE}/vessels/{v['id']}", json={"version": 1, "imo": "123"})
    assert set(r.json()) == {"detail"}
    assert set(r.json()["detail"][0]) == {"field", "message"}
    assert list(fields(r)) == ["imo"]
    r = admin.http.patch(f"{BASE}/vessels/{v['id']}", json={"version": 1, "name": None})
    assert list(fields(r)) == ["name"]
    r = admin.http.patch(f"{BASE}/vessels/{v['id']}", json={"name": "no version"})
    assert list(fields(r)) == ["version"]


@pytest.mark.req("B1-R02")
def test_cross_org_references_are_422_for_every_composite_fk(admin: Api, other: Api) -> None:
    """Another organization's parent id is rejected on every composite FK."""
    foreign = {
        "le": entity(other, "XL"),
        "cp": counterparty(other),
        "port": port(other),
        "product": product(other),
        "vessel": vessel(other, "123456"),
    }
    mine_cp, mine_port, mine_product = counterparty(admin), port(admin), product(admin)
    mine_vessel = vessel(admin)

    r = admin.http.post(f"{BASE}/vessels", json=vessel_body(foreign["le"]["id"], "765432"))
    assert list(fields(r)) == ["legal_entity_id"]
    r = admin.http.post(
        f"{BASE}/counterparties/{foreign['cp']['id']}/contacts",
        json={"name": "N", "email": "n@x.example"},
    )
    assert r.status_code == HTTPStatus.NOT_FOUND
    for item, expected in (
        ({"port_id": foreign["port"]["id"], "product_id": mine_product["id"]}, "items.port_id"),
        ({"port_id": mine_port["id"], "product_id": foreign["product"]["id"]}, "items.product_id"),
    ):
        r = admin.http.put(
            f"{BASE}/counterparties/{mine_cp['id']}/coverage",
            json={"version": mine_cp["version"], "items": [item]},
        )
        assert list(fields(r)) == [expected]
    r = admin.http.put(
        f"{BASE}/counterparties/{foreign['cp']['id']}/coverage",
        json={"version": 1, "items": []},
    )
    assert r.status_code == HTTPStatus.NOT_FOUND
    r = admin.http.put(
        f"{BASE}/vessels/{mine_vessel['id']}/approved-fuels",
        json={
            "version": mine_vessel["version"],
            "items": [{"product_id": foreign["product"]["id"]}],
        },
    )
    assert list(fields(r)) == ["items.product_id"]
    r = admin.http.put(
        f"{BASE}/vessels/{foreign['vessel']['id']}/approved-fuels",
        json={"version": 1, "items": []},
    )
    assert r.status_code == HTTPStatus.NOT_FOUND
    # nothing was written for the rejected requests
    assert admin.get(f"counterparties/{mine_cp['id']}/coverage")["items"] == []


# --- optimistic concurrency, audit --------------------------------------------------------------


@pytest.mark.req("B1-R07")
def test_patch_bumps_version_and_stale_write_is_409_without_audit(admin: Api) -> None:
    """Version +1 per update; stale version is 409 with the fixed body and no audit entry."""
    p = port(admin)
    first = admin.patch(f"ports/{p['id']}", {"version": 1, "name": "Rotterdam"})
    assert first["version"] == SECOND
    assert first["updated_at"] >= p["updated_at"]
    audits = len(admin.entries("port"))

    r = admin.http.patch(f"{BASE}/ports/{p['id']}", json={"version": 1, "name": "Stale"})
    assert (r.status_code, r.json()) == (CONFLICT, STALE)
    for action in ("deactivate", "reactivate"):
        r = admin.http.post(f"{BASE}/ports/{p['id']}/{action}", json={"version": 1})
        assert (r.status_code, r.json()) == (CONFLICT, STALE)

    assert len(admin.entries("port")) == audits
    assert admin.get(f"ports/{p['id']}")["name"] == "Rotterdam"


@pytest.mark.req("B1-R07")
def test_concurrent_patches_with_same_version_one_wins(admin: Api) -> None:
    """Two simultaneous PATCHes from the same version: exactly one 200, one 409."""
    p = port(admin)

    def go(name: str) -> int:
        return int(
            admin.http.patch(
                f"{BASE}/ports/{p['id']}", json={"version": 1, "name": name}
            ).status_code
        )

    with ThreadPoolExecutor(2) as pool:
        codes = sorted(pool.map(go, ["A", "B"]))

    assert codes == [OK, CONFLICT]
    assert admin.get(f"ports/{p['id']}")["version"] == SECOND
    assert len([e for e in admin.entries("port") if e.action == "update"]) == 1


@pytest.mark.req("B1-R07")
def test_noop_patch_is_200_unchanged_without_audit(admin: Api) -> None:
    """Same values: 200, same record and version, no audit entry."""
    p = port(admin)
    before = len(admin.entries("port"))
    same = admin.patch(f"ports/{p['id']}", {"version": 1, "name": p["name"]})
    assert same == p
    assert len(admin.entries("port")) == before


@pytest.mark.req("B1-R07")
def test_history_newest_first_with_actor_from_principal(admin: Api) -> None:
    """History lists create, update, deactivate newest first; actor is the caller."""
    p = port(admin)
    p = admin.patch(f"ports/{p['id']}", {"version": p["version"], "name": "Rtm"})
    admin.post(f"ports/{p['id']}/deactivate", {"version": p["version"]}, OK)

    history = admin.get(f"ports/{p['id']}/history")

    assert [h["action"] for h in history] == ["deactivate", "update", "create"]
    assert {h["actor"] for h in history} == {str(admin.user)}
    assert history[1]["changes"] == {"name": {"before": "P", "after": "Rtm"}}
    assert history[0]["changes"] == {"active": {"before": "true", "after": "false"}}


@pytest.mark.req("B1-R07")
def test_client_cannot_set_audit_fields(admin: Api) -> None:
    """actor/at in any body are rejected, never stored."""
    p = port(admin)
    for body in ({"version": 1, "at": "2020-01-01T00:00:00Z"}, {"version": 1, "actor": "x"}):
        assert admin.http.patch(f"{BASE}/ports/{p['id']}", json=body).status_code == UNPROCESSABLE
    assert (
        admin.http.post(
            f"{BASE}/ports/{p['id']}/deactivate", json={"version": 1, "actor": str(uuid.uuid4())}
        ).status_code
        == UNPROCESSABLE
    )


# --- nested: contacts, coverage, approved fuels --------------------------------------------------


@pytest.mark.req("B1-R02")
def test_contacts_crud_and_single_active_primary(admin: Api) -> None:
    """Contacts are created/updated/deactivated; at most one active primary per counterparty."""
    cp = counterparty(admin)
    path = f"counterparties/{cp['id']}/contacts"
    c1 = admin.post(path, {"name": "A", "email": "a@x.example", "is_primary": True})
    assert c1["is_primary"] is True

    r = admin.http.post(
        f"{BASE}/{path}", json={"name": "B", "email": "b@x.example", "is_primary": True}
    )
    assert list(fields(r)) == ["is_primary"]
    c2 = admin.post(path, {"name": "B", "email": "b@x.example"})
    r = admin.http.patch(f"{BASE}/{path}/{c2['id']}", json={"version": 1, "is_primary": True})
    assert list(fields(r)) == ["is_primary"]

    c1 = admin.post(f"{path}/{c1['id']}/deactivate", {"version": 1}, OK)
    c2 = admin.patch(f"{path}/{c2['id']}", {"version": 1, "is_primary": True})
    assert c2["version"] == SECOND
    r = admin.http.post(f"{BASE}/{path}/{c1['id']}/reactivate", json={"version": c1["version"]})
    assert list(fields(r)) == ["is_primary"]

    assert [c["name"] for c in admin.get(path)] == ["B"]
    assert {c["name"] for c in admin.get(f"{path}?active=all")} == {"A", "B"}
    stale = admin.http.patch(f"{BASE}/{path}/{c2['id']}", json={"version": 1, "name": "Z"})
    assert (stale.status_code, stale.json()) == (CONFLICT, STALE)
    assert {e.entity_type for e in admin.entries("contact")} == {"contact"}
    # a contact is addressed through its own counterparty only
    other_cp = counterparty(admin, "CP2")
    r = admin.http.get(f"{BASE}/counterparties/{other_cp['id']}/contacts/{c2['id']}")
    assert r.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.req("B1-R07")
def test_counterparty_history_includes_contact_and_coverage_changes(admin: Api) -> None:
    """B1-D6: contact and coverage changes show in the counterparty's history, labelled."""
    cp = counterparty(admin)
    path = f"counterparties/{cp['id']}"
    c = admin.post(f"{path}/contacts", {"name": "Ann", "email": "ann@x.example"})
    admin.patch(f"{path}/contacts/{c['id']}", {"version": c["version"], "email": "a2@x.example"})
    admin.put(f"{path}/coverage", {"version": cp["version"], "items": []})  # no-op: no entry
    p1, pr = port(admin), product(admin)
    admin.put(
        f"{path}/coverage",
        {"version": cp["version"], "items": [{"port_id": p1["id"], "product_id": pr["id"]}]},
    )
    stranger = counterparty(admin, "CP2")
    admin.post(f"counterparties/{stranger['id']}/contacts", {"name": "Z", "email": "z@x.example"})

    history = admin.get(f"{path}/history")

    assert [(h["entity"], h["action"]) for h in history] == [
        (None, "update"),
        ("Contact Ann", "update"),
        ("Contact Ann", "create"),
        (None, "create"),
    ]
    assert history[0]["changes"].keys() == {"coverage"}
    assert history[1]["changes"] == {"email": {"before": "ann@x.example", "after": "a2@x.example"}}


@pytest.mark.req("B1-R07")
def test_vessel_history_includes_approved_fuel_changes(admin: Api) -> None:
    """B1-D6: a vessel's approved-fuel changes show in its history."""
    v, pr = vessel(admin), product(admin)
    admin.put(
        f"vessels/{v['id']}/approved-fuels",
        {"version": v["version"], "items": [{"product_id": pr["id"]}]},
    )
    history = admin.get(f"vessels/{v['id']}/history")
    assert [h["action"] for h in history] == ["update", "create"]
    assert history[0]["changes"].keys() == {"approved_fuels"}


@pytest.mark.req("B1-R07")
def test_coverage_put_replaces_set_audited_once_and_reactivates(
    admin: Api, app_engine: Engine
) -> None:
    """PUT replaces; one audit update with before/after sets; re-adding reactivates the row."""
    cp = counterparty(admin)
    p1, p2 = port(admin), port(admin, "SGSIN")
    pr = product(admin)
    path = f"counterparties/{cp['id']}/coverage"
    item1 = {"port_id": p1["id"], "product_id": pr["id"]}
    item2 = {"port_id": p2["id"], "product_id": pr["id"]}

    one = admin.put(path, {"version": cp["version"], "items": [item1]})
    assert one["items"] == [item1]
    assert one["version"] == cp["version"] + 1
    audits = len(admin.entries("counterparty"))
    assert admin.put(path, {"version": one["version"], "items": [item1]}) == one  # no-op
    assert len(admin.entries("counterparty")) == audits

    two = admin.put(path, {"version": one["version"], "items": [item2]})
    assert two["items"] == [item2]
    update = max(admin.entries("counterparty"), key=lambda e: e.at)
    assert update.action == "update"
    assert set(update.changes) == {"coverage"}
    assert item1["port_id"] in str(update.changes["coverage"]["before"])
    assert item2["port_id"] in str(update.changes["coverage"]["after"])
    assert item1["port_id"] not in str(update.changes["coverage"]["after"])

    admin.put(path, {"version": two["version"], "items": []})
    third = admin.put(path, {"version": two["version"] + 1, "items": [item1]})
    assert third["items"] == [item1]
    with org_session(admin.org, app_engine) as s:
        rows = s.scalars(select(Coverage).where(Coverage.counterparty_id == uuid.UUID(cp["id"])))
        assert len(rows.all()) == 2  # noqa: PLR2004 - item1 reactivated, not duplicated

    stale = admin.http.put(f"{BASE}/{path}", json={"version": 1, "items": []})
    assert (stale.status_code, stale.json()) == (CONFLICT, STALE)
    assert admin.get(path)["items"] == [item1]


@pytest.mark.req("B1-R07")
def test_approved_fuels_put_reactivates_pair(admin: Api) -> None:
    """Vessel approved fuels use the same replace semantics, audited on the vessel."""
    v, pr = vessel(admin), product(admin)
    path = f"vessels/{v['id']}/approved-fuels"
    a = admin.put(path, {"version": v["version"], "items": [{"product_id": pr["id"]}]})
    b = admin.put(path, {"version": a["version"], "items": []})
    c = admin.put(path, {"version": b["version"], "items": [{"product_id": pr["id"]}]})
    assert c["items"] == [{"product_id": pr["id"]}]
    assert admin.get(path)["items"] == c["items"]
    assert len([e for e in admin.entries("vessel") if e.action == "update"]) == 3  # noqa: PLR2004


# --- suggest ----------------------------------------------------------------------------


@pytest.mark.req("B1-R09")
def test_suggest_returns_all_and_some(admin: Api) -> None:
    """Suppliers covering every requested product vs only some of them."""
    p = port(admin)
    h, m = product(admin, "HSFO"), product(admin, "MGO")
    full, partial = counterparty(admin, "Full"), counterparty(admin, "Partial")
    counterparty(admin, "None")
    for cp, prods in ((full, [h, m]), (partial, [h])):
        admin.put(
            f"counterparties/{cp['id']}/coverage",
            {
                "version": cp["version"],
                "items": [{"port_id": p["id"], "product_id": x["id"]} for x in prods],
            },
        )

    result = admin.get(
        f"counterparties/suggest?port_id={p['id']}&product_id={h['id']}&product_id={m['id']}"
    )

    assert set(result) == {"all", "some"}
    assert [c["name"] for c in result["all"]] == ["Full"]
    assert [c["name"] for c in result["some"]] == ["Partial"]
    bad = admin.http.get(f"{BASE}/counterparties/suggest?port_id={p['id']}")
    assert bad.status_code == UNPROCESSABLE
