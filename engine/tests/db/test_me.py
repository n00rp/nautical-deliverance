"""GET /api/v1/me reads the caller's organization under RLS."""

import uuid
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text

from nautical_deliverance.api.auth import get_principal
from nautical_deliverance.api.me import get_me_engine
from nautical_deliverance.domain.identity import Principal, Role
from nautical_deliverance.main import create_app
from nautical_deliverance.persistence.db import org_session
from nautical_deliverance.persistence.models import AppUser

if TYPE_CHECKING:
    from nautical_deliverance.settings import Settings


def _client(settings: Settings, engine: Engine, user: uuid.UUID, org: uuid.UUID) -> TestClient:
    app = create_app(settings)
    principal = Principal(user, org, frozenset({Role.VIEWER, Role.ADMIN}))
    app.dependency_overrides[get_principal] = lambda: principal
    app.dependency_overrides[get_me_engine] = lambda: engine
    return TestClient(app)


def _seed_org(owner_engine: Engine, org: uuid.UUID, name: str) -> None:
    with owner_engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.organization_id', :o, true)"), {"o": str(org)})
        conn.execute(
            text("INSERT INTO organization (id, name) VALUES (:i, :n)"), {"i": org, "n": name}
        )


@pytest.mark.req("S0-R03")
def test_me_returns_principal_and_org_name(
    settings: Settings, owner_engine: Engine, app_engine: Engine
) -> None:
    """The response carries ids, the organization name and sorted roles."""
    org, user = uuid.uuid4(), uuid.uuid4()
    _seed_org(owner_engine, org, "Harbor Co")

    response = _client(settings, app_engine, user, org).get("/api/v1/me")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "user_id": str(user),
        "organization": {"id": str(org), "name": "Harbor Co"},
        "roles": ["admin", "viewer"],
    }


@pytest.mark.req("S0-R03")
def test_me_records_last_seen(settings: Settings, owner_engine: Engine, app_engine: Engine) -> None:
    """Each call upserts app_user.last_seen_at."""
    org, user = uuid.uuid4(), uuid.uuid4()
    _seed_org(owner_engine, org, "Harbor Co")
    client = _client(settings, app_engine, user, org)

    def last_seen() -> datetime:
        with org_session(org, app_engine) as s:
            return s.scalars(select(AppUser.last_seen_at).where(AppUser.id == user)).one()

    before = datetime.now(UTC)
    client.get("/api/v1/me")
    first = last_seen()
    client.get("/api/v1/me")

    assert before - timedelta(seconds=5) <= first <= datetime.now(UTC)
    assert last_seen() > first


def test_me_org_not_in_db_403(settings: Settings, app_engine: Engine) -> None:
    """An org that is not visible under RLS is 403 with no other detail."""
    response = _client(settings, app_engine, uuid.uuid4(), uuid.uuid4()).get("/api/v1/me")

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert set(response.json()) == {"detail"}
