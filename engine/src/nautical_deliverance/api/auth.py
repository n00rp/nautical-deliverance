"""OIDC bearer-token authentication (Keycloak-issued RS256 JWTs)."""

import json
import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nautical_deliverance.domain.identity import Principal, Role

_bearer = HTTPBearer(auto_error=False)
_LEEWAY_SECONDS = 10
_MISSING = "Missing bearer token"
_INVALID = "Invalid token"
_NO_ORG = "Token has no valid organization"
_NO_ROLES = "Token has no valid roles"
_IDP_DOWN = "Identity provider unavailable"


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, {"WWW-Authenticate": "Bearer"})


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail)


def _uuid(value: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    """Validate the bearer token and build the caller's principal."""
    if credentials is None:
        raise _unauthorized(_MISSING)
    settings = request.app.state.settings
    try:
        key = request.app.state.jwks_client.get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            key.key,
            algorithms=["RS256"],  # never derived from the token header
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,  # never derived from the token
            leeway=_LEEWAY_SECONDS,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except (jwt.PyJWKClientConnectionError, json.JSONDecodeError) as exc:  # JWKS down/garbage
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _IDP_DOWN) from exc
    except jwt.PyJWTError as exc:  # InvalidTokenError and unknown-key JWKS errors
        raise _unauthorized(_INVALID) from exc

    user_id = _uuid(claims["sub"])
    if user_id is None:
        raise _unauthorized(_INVALID)
    org_id = _uuid(claims.get("org_id"))
    if org_id is None:
        raise _forbidden(_NO_ORG)
    raw_roles = claims.get("roles")
    if not isinstance(raw_roles, list) or not all(isinstance(r, str) for r in raw_roles):
        raise _forbidden(_NO_ROLES)
    known = {r.value for r in Role}
    return Principal(
        user_id,
        org_id,
        frozenset(Role(r) for r in raw_roles if r in known),
        _text(claims.get("name")) or _text(claims.get("preferred_username")),
        _text(claims.get("email")),
    )
