"""Create a pilot user in Keycloak (B6-R05): temporary password, forced change, org_id, one role.

Talks only to the Keycloak admin REST API. In production that API is loopback-only, so run this on
the server (default --url) or through a tunnel: `ssh -L 8081:127.0.0.1:8081 <server>`.
The admin password comes from ND_KC_ADMIN_PASSWORD or a prompt, never from an argument. The
temporary password is printed once, on stdout, and nowhere else.
"""

import argparse
import getpass
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

HTTP_NOT_FOUND = 404
# Pilot Demo Shipping; test_pilot_user.py asserts it equals the engine's seed constant.
DEFAULT_ORG = "33333333-3333-4333-8333-333333333333"
EXIT_REFUSED = 2
ROLES = ("admin", "bunker_buyer", "operator", "viewer")
LOOPBACK = ("127.0.0.1", "localhost", "::1")


class Refused(Exception):  # noqa: N818 - a refusal, not an error
    """The request is invalid or would change an existing user; nothing was changed."""


def _call(  # noqa: PLR0913
    method: str,
    url: str,
    token: str | None = None,
    body: Any = None,  # noqa: ANN401 - any JSON
    form: dict[str, str] | None = None,
    *,
    location: bool = False,
) -> Any:  # noqa: ANN401 - decoded JSON (or the Location header with location=True)
    data = urllib.parse.urlencode(form).encode() if form else None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)  # noqa: S310
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        raw = resp.read()
        if location:
            return resp.headers["Location"]
    return json.loads(raw) if raw else None


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)  # noqa: T201


def _rollback(admin: str, token: str, email: str, uid: str | None) -> None:
    """Delete the half-created user; say on stderr whether that worked. Never raises."""
    try:
        if uid is None:
            raise ValueError  # noqa: TRY301 - no id (no Location header): cannot delete
        _call("DELETE", f"{admin}/users/{uid}", token)
    except Exception:  # noqa: BLE001 - the original error is re-raised by the caller
        _err(f"WARNING: user {email} may remain without role - remove it in the admin console")
    else:
        _err("Created user was rolled back.")


def create_user(args: argparse.Namespace, admin_password: str) -> str:
    """Create the user; return the temporary password. Rolls the user back if a later step fails."""
    base = args.url.rstrip("/")
    if args.role not in ROLES:
        msg = f"unknown role: {args.role} (allowed: {', '.join(ROLES)})"
        raise Refused(msg)
    try:
        uuid.UUID(args.org)
    except ValueError:
        msg = f"--org is not a UUID: {args.org}"
        raise Refused(msg) from None
    url = urllib.parse.urlsplit(base)
    if url.scheme != "https" and not (url.scheme == "http" and url.hostname in LOOPBACK):
        msg = "use https, or http only for a loopback host (127.0.0.1, localhost, ::1)"
        raise Refused(msg)
    token = _call(
        "POST",
        f"{base}/realms/master/protocol/openid-connect/token",
        form={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": args.admin_user,
            "password": admin_password,
        },
    )["access_token"]
    admin = f"{base}/admin/realms/{urllib.parse.quote(args.realm)}"
    q = urllib.parse.quote(args.email, safe="")
    try:
        role = _call("GET", f"{admin}/roles/{urllib.parse.quote(args.role)}", token)
    except urllib.error.HTTPError as err:
        if err.code == HTTP_NOT_FOUND:
            msg = f"unknown role: {args.role}"
            raise Refused(msg) from None
        raise
    if _call("GET", f"{admin}/users?email={q}&exact=true", token) or _call(
        "GET", f"{admin}/users?username={q}&exact=true", token
    ):
        msg = f"a user with e-mail {args.email} already exists; nothing changed"
        raise Refused(msg)
    password = secrets.token_urlsafe(18)
    uid = None
    try:
        loc = _call(
            "POST",
            f"{admin}/users",
            token,
            {
                "username": args.email,
                "email": args.email,
                "firstName": args.first,
                "lastName": args.last,
                "enabled": True,
                "requiredActions": ["UPDATE_PASSWORD"],
                "attributes": {"org_id": [args.org]},
            },
            location=True,
        )
        uid = loc.rsplit("/", 1)[1]
        _call(
            "PUT",
            f"{admin}/users/{uid}/reset-password",
            token,
            {"type": "password", "value": password, "temporary": True},
        )
        _call("POST", f"{admin}/users/{uid}/role-mappings/realm", token, [role])
    except Exception:
        _rollback(admin, token, args.email, uid)
        raise
    return password


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the exit code (2 = refused, nothing changed)."""
    p = argparse.ArgumentParser(
        description="Create a Keycloak pilot user with a temporary password."
    )
    p.add_argument("--url", default="http://127.0.0.1:8081")
    p.add_argument("--realm", default="nautical-deliverance")
    p.add_argument("--admin-user", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--first", required=True)
    p.add_argument("--last", required=True)
    p.add_argument("--role", required=True, help=" / ".join(ROLES))
    p.add_argument("--org", default=DEFAULT_ORG)
    args = p.parse_args(argv)
    admin_password = os.environ.get("ND_KC_ADMIN_PASSWORD") or getpass.getpass(
        "Keycloak admin password: "
    )
    try:
        password = create_user(args, admin_password)
    except Refused as err:
        _err(f"refused: {err}")
        return EXIT_REFUSED
    except urllib.error.HTTPError as err:
        _err(f"Keycloak answered HTTP {err.code} for {err.url}")
        return 1
    except urllib.error.URLError as err:
        _err(f"cannot reach Keycloak at {args.url}: {err.reason}")
        return 1
    except Exception as err:  # noqa: BLE001 - report the type only, never values
        _err(f"failed: {type(err).__name__}")
        return 1
    print(  # noqa: T201
        f"Created {args.email} ({args.role}). Temporary password (shown once): {password}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
