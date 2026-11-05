"""Bearer-token authentication."""

import json
import time
import uuid
from http import HTTPStatus
from types import SimpleNamespace
from typing import TYPE_CHECKING, Annotated, Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from nautical_deliverance.api.auth import get_principal
from nautical_deliverance.api.me import get_me_engine
from nautical_deliverance.domain.identity import Principal, Role
from nautical_deliverance.main import create_app

if TYPE_CHECKING:
    from httpx import Response

    from nautical_deliverance.settings import Settings

USER = uuid.uuid4()
ORG = uuid.uuid4()
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _FakeJwks:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def get_signing_key_from_jwt(self, token: str) -> SimpleNamespace:  # noqa: ARG002
        if self.error:
            raise self.error
        return SimpleNamespace(key=KEY.public_key())


def _token(settings: Settings, drop: tuple[str, ...] = (), **overrides: object) -> str:
    claims: dict[str, Any] = {
        "iss": settings.oidc_issuer,
        "aud": settings.oidc_audience,
        "sub": str(USER),
        "org_id": str(ORG),
        "roles": ["viewer", "admin", "bogus"],
        "exp": int(time.time()) + 300,
    } | overrides
    for name in drop:
        del claims[name]
    return jwt.encode(claims, KEY, algorithm="RS256")


def _client(settings: Settings, jwks_error: Exception | None = None) -> TestClient:
    app = create_app(settings)
    app.state.jwks_client = _FakeJwks(jwks_error)

    @app.get("/_principal")
    def _principal(p: Annotated[Principal, Depends(get_principal)]) -> dict[str, Any]:
        return {
            "user": str(p.user_id),
            "org": str(p.organization_id),
            "roles": sorted(p.roles),
            "name": p.name,
            "email": p.email,
        }

    return TestClient(app)


def _get(client: TestClient, token: str | None) -> Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response: Response = client.get("/_principal", headers=headers)
    return response


def _assert_401(response: Response) -> None:
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.headers["www-authenticate"] == "Bearer"
    assert set(response.json()) == {"detail"}


@pytest.mark.req("S0-R03")
def test_missing_token_401(settings: Settings) -> None:
    """No Authorization header is rejected."""
    _assert_401(_get(_client(settings), None))


@pytest.mark.req("S0-R03")
def test_expired_token_401(settings: Settings) -> None:
    """An exp 60 s in the past is beyond the 10 s leeway."""
    _assert_401(_get(_client(settings), _token(settings, exp=int(time.time()) - 60)))


@pytest.mark.req("S0-R03")
def test_wrong_issuer_401(settings: Settings) -> None:
    """The issuer must equal the configured one."""
    _assert_401(_get(_client(settings), _token(settings, iss="https://evil.test")))


@pytest.mark.req("S0-R03")
def test_tampered_signature_401(settings: Settings) -> None:
    """Flipping a signature character invalidates the token."""
    token = _token(settings)
    head, sig = token.rsplit(".", 1)
    sig = ("B" if sig[10] == "A" else "A").join((sig[:10], sig[11:]))
    _assert_401(_get(_client(settings), f"{head}.{sig}"))


@pytest.mark.req("S0-R03")
def test_wrong_audience_401(settings: Settings) -> None:
    """The audience must contain the configured one."""
    _assert_401(_get(_client(settings), _token(settings, aud="other")))


@pytest.mark.req("S0-R03")
def test_alg_none_rejected_401(settings: Settings) -> None:
    """Unsigned tokens are rejected."""
    claims = {"iss": settings.oidc_issuer, "aud": "nd", "sub": str(USER), "exp": time.time() + 300}
    token = jwt.encode(claims, None, algorithm="none")  # type: ignore[arg-type]
    _assert_401(_get(_client(settings), token))


@pytest.mark.req("S0-R03")
def test_hs256_rejected_401(settings: Settings) -> None:
    """Only RS256 is accepted."""
    claims = {"iss": settings.oidc_issuer, "aud": "nd", "sub": str(USER), "exp": time.time() + 300}
    _assert_401(_get(_client(settings), jwt.encode(claims, "x" * 32, algorithm="HS256")))


@pytest.mark.parametrize("drop", ["exp", "sub", "iss", "aud"])
def test_missing_required_claim_401(settings: Settings, drop: str) -> None:
    """exp, iss, aud and sub are mandatory."""
    _assert_401(_get(_client(settings), _token(settings, drop=(drop,))))


def test_non_uuid_sub_401(settings: Settings) -> None:
    """The sub must be a UUID."""
    _assert_401(_get(_client(settings), _token(settings, sub="not-a-uuid")))


def test_garbage_token_401(settings: Settings) -> None:
    """A malformed token is rejected."""
    _assert_401(_get(_client(settings), "garbage"))


def test_non_bearer_scheme_401(settings: Settings) -> None:
    """Only the Bearer scheme is accepted."""
    response = _client(settings).get("/_principal", headers={"Authorization": "Basic abc"})
    _assert_401(response)


@pytest.mark.req("S0-R03")
def test_valid_token_yields_principal(settings: Settings) -> None:
    """A valid token gives the exact principal; unknown roles are ignored."""
    response = _get(_client(settings), _token(settings))

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert Principal(
        uuid.UUID(body["user"]), uuid.UUID(body["org"]), frozenset(Role(r) for r in body["roles"])
    ) == Principal(USER, ORG, frozenset({Role.ADMIN, Role.VIEWER}))


def test_aud_list_containing_audience_ok(settings: Settings) -> None:
    """The aud may be a list."""
    response = _get(_client(settings), _token(settings, aud=["x", settings.oidc_audience]))
    assert response.status_code == HTTPStatus.OK


def test_missing_org_id_claim_403(settings: Settings) -> None:
    """A valid token without org_id is forbidden."""
    response = _get(_client(settings), _token(settings, drop=("org_id",)))
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert set(response.json()) == {"detail"}


def test_non_uuid_org_id_403(settings: Settings) -> None:
    """org_id must be a UUID."""
    response = _get(_client(settings), _token(settings, org_id="nope"))
    assert response.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.parametrize("roles", ["admin", None, {"a": 1}, [1, 2]])
def test_roles_not_a_list_403(settings: Settings, roles: object) -> None:
    """The roles must be a list of strings."""
    response = _get(_client(settings), _token(settings, roles=roles))
    assert response.status_code == HTTPStatus.FORBIDDEN


def test_jwks_unreachable_503(settings: Settings) -> None:
    """An unreachable JWKS endpoint is 503 and does not take the app down."""
    client = _client(settings, jwt.PyJWKClientConnectionError("down"))

    assert _get(client, _token(settings)).status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert client.get("/api/v1/health").status_code == HTTPStatus.OK


def test_unknown_signing_key_401(settings: Settings) -> None:
    """A kid the JWKS does not know is an invalid token."""
    _assert_401(_get(_client(settings, jwt.PyJWKClientError("no key")), _token(settings)))


def test_jwks_malformed_json_503(settings: Settings) -> None:
    """A JWKS endpoint returning garbage is 503, not a plain 500."""
    err = json.JSONDecodeError("bad", "", 0)
    response = _get(_client(settings, err), _token(settings))
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert set(response.json()) == {"detail"}


def test_me_db_unavailable_503(settings: Settings) -> None:
    """A database connection failure on /me is 503 with a JSON body."""
    app = create_app(settings)
    app.dependency_overrides[get_principal] = lambda: Principal(USER, ORG, frozenset())
    app.dependency_overrides[get_me_engine] = lambda: create_engine(
        "postgresql+psycopg://u:p@127.0.0.1:1/x", connect_args={"connect_timeout": 1}
    )

    response = TestClient(app).get("/api/v1/me")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert set(response.json()) == {"detail"}
