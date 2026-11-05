"""User directory: lazy upsert from token claims and GET /api/v1/users."""

import uuid
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text, update

from nautical_deliverance.api.auth import get_principal
from nautical_deliverance.api.users import get_users_engine
from nautical_deliverance.domain.identity import Principal, Role
from nautical_deliverance.main import create_app
from nautical_deliverance.persistence.db import org_session
from nautical_deliverance.persistence.models import AppUser

if TYPE_CHECKING:
    from nautical_deliverance.settings import Settings

URL = "/api/v1/users"
BUYER = frozenset({Role.BUNKER_BUYER})


def _org(owner_engine: Engine) -> uuid.UUID:
    org = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(org)})
        conn.execute(text("INSERT INTO organization (id, name) VALUES (:i, 'Org')"), {"i": org})
    return org


def _as(  # noqa: PLR0913, PLR0917
    settings: Settings,
    engine: Engine,
    org: uuid.UUID,
    roles: frozenset[Role] = BUYER,
    user: uuid.UUID | None = None,
    name: str = "",
    email: str = "",
) -> TestClient:
    app = create_app(settings)
    principal = Principal(user or uuid.uuid4(), org, roles, name, email)
    app.dependency_overrides[get_principal] = lambda: principal
    app.dependency_overrides[get_users_engine] = lambda: engine
    return TestClient(app)


def _row(engine: Engine, org: uuid.UUID, user: uuid.UUID) -> tuple[AppUser, str]:
    with org_session(org, engine) as s:
        row = s.scalars(select(AppUser).where(AppUser.id == user)).one()
        xmin = s.execute(text("SELECT xmin::text FROM app_user WHERE id = :i"), {"i": user})
        s.expunge(row)
        return row, xmin.scalar_one()


@pytest.mark.req("B2-R01")
def test_first_request_inserts_user(
    settings: Settings, owner_engine: Engine, app_engine: Engine
) -> None:
    """The first request stores name, email and roles from the token."""
    org, user = _org(owner_engine), uuid.uuid4()
    roles = frozenset({Role.BUNKER_BUYER, Role.ADMIN})

    response = _as(settings, app_engine, org, roles, user, "Ann Buyer", "ann@x.test").get(URL)

    assert response.status_code == HTTPStatus.OK
    row, _ = _row(app_engine, org, user)
    assert (row.name, row.email, row.roles) == (
        "Ann Buyer",
        "ann@x.test",
        ["admin", "bunker_buyer"],
    )


@pytest.mark.req("B2-R01")
def test_unchanged_claims_within_hour_write_nothing(
    settings: Settings, owner_engine: Engine, app_engine: Engine
) -> None:
    """A repeat request with the same claims leaves the row untouched."""
    org, user = _org(owner_engine), uuid.uuid4()
    client = _as(settings, app_engine, org, BUYER, user, "Ann", "ann@x.test")
    client.get(URL)
    before, xmin = _row(app_engine, org, user)

    client.get(URL)

    after, xmin_after = _row(app_engine, org, user)
    assert xmin_after == xmin
    assert after.last_seen_at == before.last_seen_at


@pytest.mark.req("B2-R01")
def test_stale_last_seen_is_refreshed(
    settings: Settings, owner_engine: Engine, app_engine: Engine
) -> None:
    """After an hour without a write, last_seen_at moves forward."""
    org, user = _org(owner_engine), uuid.uuid4()
    client = _as(settings, app_engine, org, BUYER, user, "Ann", "ann@x.test")
    client.get(URL)
    old = datetime.now(UTC) - timedelta(hours=2)
    with org_session(org, app_engine) as s:
        s.execute(update(AppUser).where(AppUser.id == user).values(last_seen_at=old))

    client.get(URL)

    row, _ = _row(app_engine, org, user)
    assert row.last_seen_at > old + timedelta(hours=1)


@pytest.mark.req("B2-R01")
def test_changed_claims_are_updated(
    settings: Settings, owner_engine: Engine, app_engine: Engine
) -> None:
    """New roles, name or e-mail are written on the next request."""
    org, user = _org(owner_engine), uuid.uuid4()
    _as(settings, app_engine, org, BUYER, user, "Ann", "ann@x.test").get(URL)

    _as(settings, app_engine, org, frozenset({Role.OPERATOR}), user, "Ann B", "ab@x.test").get(URL)

    row, _ = _row(app_engine, org, user)
    assert (row.name, row.email, row.roles) == ("Ann B", "ab@x.test", ["operator"])


@pytest.mark.req("B2-R01")
def test_list_filters_by_role_sorted_by_name(
    settings: Settings, owner_engine: Engine, app_engine: Engine
) -> None:
    """Only the org's buyers, by name; without a filter every role-holder."""
    org = _org(owner_engine)
    zed, abe, viewer = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _as(settings, app_engine, org, BUYER, zed, "Zed", "z@x.test").get(URL)
    _as(settings, app_engine, org, BUYER, abe, "Abe", "a@x.test").get(URL)
    _as(settings, app_engine, org, frozenset({Role.VIEWER}), viewer, "Vic", "v@x.test").get(URL)

    client = _as(settings, app_engine, org, frozenset({Role.VIEWER}))
    buyers = client.get(URL, params={"role": "bunker_buyer"}).json()
    everyone = client.get(URL).json()

    assert buyers == [
        {"id": str(abe), "name": "Abe", "email": "a@x.test", "roles": ["bunker_buyer"]},
        {"id": str(zed), "name": "Zed", "email": "z@x.test", "roles": ["bunker_buyer"]},
    ]
    assert [u["name"] for u in everyone] == ["", "Abe", "Vic", "Zed"]  # "" is the caller


@pytest.mark.req("B2-R01")
def test_user_without_roles_is_hidden_but_kept(
    settings: Settings, owner_engine: Engine, app_engine: Engine
) -> None:
    """Losing every role drops a user from the directory; the row stays for history."""
    org, user = _org(owner_engine), uuid.uuid4()
    _as(settings, app_engine, org, BUYER, user, "Gone", "g@x.test").get(URL)
    # Roleless callers are refused by the route, but the directory still records the change.
    assert _as(settings, app_engine, org, frozenset(), user, "Gone", "g@x.test").get(
        URL
    ).status_code == (HTTPStatus.FORBIDDEN)

    listed = _as(settings, app_engine, org).get(URL).json()

    assert user not in {uuid.UUID(u["id"]) for u in listed}
    row, _ = _row(app_engine, org, user)
    assert (row.name, row.roles) == ("Gone", [])


@pytest.mark.req("B2-R01")
def test_other_orgs_users_invisible(
    settings: Settings, owner_engine: Engine, app_engine: Engine
) -> None:
    """The directory never shows another organization's users."""
    org_a, org_b = _org(owner_engine), _org(owner_engine)
    _as(settings, app_engine, org_b, BUYER, name="Other").get(URL)

    names = [u["name"] for u in _as(settings, app_engine, org_a, name="Mine").get(URL).json()]

    assert names == ["Mine"]


@pytest.mark.req("B2-R01")
def test_unknown_org_is_403(settings: Settings, app_engine: Engine) -> None:
    """An organization that is not in the database is 403, as for /me."""
    response = _as(settings, app_engine, uuid.uuid4()).get(URL)

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json() == {"detail": "Organization not accessible"}


@pytest.mark.req("B2-R01")
def test_user_bound_to_other_org_is_403(
    settings: Settings, owner_engine: Engine, app_engine: Engine
) -> None:
    """A subject already stored under another org is refused without saying why."""
    org_a, org_b, user = _org(owner_engine), _org(owner_engine), uuid.uuid4()
    assert _as(settings, app_engine, org_a, BUYER, user).get(URL).status_code == HTTPStatus.OK

    response = _as(settings, app_engine, org_b, BUYER, user).get(URL)

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json() == {"detail": "Organization not accessible"}
