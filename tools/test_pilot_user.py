"""pilot_user.py against a real Keycloak with the pilot realm (B6-R05).

Needs Docker and downloads the Keycloak image, so it runs only when ND_KC_TESTS=1 (the CI job
`pilot-user` sets it).
"""

import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pilot_user
import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

needs_kc = pytest.mark.skipif(os.environ.get("ND_KC_TESTS") != "1", reason="set ND_KC_TESTS=1")
ROOT = Path(__file__).resolve().parent.parent
REALM = ROOT / "infra" / "keycloak" / "realm-pilot.json"
IMAGE = next(
    ln.split("image:")[1].strip()
    for ln in (ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf-8").splitlines()
    if "quay.io/keycloak/keycloak" in ln
)
MIN_PASSWORD_LEN = 16
HTTP_BAD_REQUEST = 400
EXIT_REFUSED = pilot_user.EXIT_REFUSED
ADMIN_PW = secrets.token_hex(12)
NAME = f"nd-pilot-user-test-{os.getpid()}"
ARGS = ["--admin-user", "admin", "--first", "Ada", "--last", "Buyer", "--role", "bunker_buyer"]
TOKEN_PATH = "/protocol/openid-connect/token"  # noqa: S105 - an URL path


def _docker(*a: str) -> str:
    return subprocess.run(["docker", *a], capture_output=True, text=True, check=True).stdout  # noqa: S603, S607


def _json(url: str, token: str | None = None, form: dict[str, str] | None = None) -> Any:  # noqa: ANN401
    req = urllib.request.Request(  # noqa: S310
        url,
        data=urllib.parse.urlencode(form).encode() if form else None,
        headers={"Authorization": f"Bearer {token}"} if token else {},
    )
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        return json.load(r)


@pytest.fixture(scope="module")
def kc(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Keycloak with the pilot realm plus a test-only direct-grant client (pilot file untouched)."""
    realm = json.loads(REALM.read_text(encoding="utf-8"))
    realm["clients"].append(
        {"clientId": "nd-test", "publicClient": True, "directAccessGrantsEnabled": True}
    )
    f = tmp_path_factory.mktemp("realm") / "realm-pilot.json"
    f.write_text(json.dumps(realm), encoding="utf-8")
    _docker(
        *("run", "-d", "--name", NAME, "-p", "127.0.0.1::8080"),
        *("-e", "KC_BOOTSTRAP_ADMIN_USERNAME=admin", "-e", "ND_PUBLIC_HOST=pilot.example.test"),
        *("-e", f"KC_BOOTSTRAP_ADMIN_PASSWORD={ADMIN_PW}"),
        *("-v", f"{f}:/opt/keycloak/data/import/realm-pilot.json:ro"),
        *(IMAGE, "start-dev", "--import-realm"),
    )
    try:
        port = _docker("port", NAME, "8080/tcp").split(":")[-1].strip()
        url = f"http://127.0.0.1:{port}"
        for _ in range(120):
            try:
                _json(f"{url}/realms/nautical-deliverance/.well-known/openid-configuration")
                break
            except OSError:  # URLError, ConnectionError and resets are all OSError
                time.sleep(2)
        else:
            pytest.fail(_docker("logs", NAME))
        yield url
    finally:
        subprocess.run(["docker", "rm", "-f", NAME], capture_output=True, check=False)  # noqa: S603, S607


def _admin(kc: str) -> tuple[str, str]:
    form = {"grant_type": "password", "client_id": "admin-cli", "username": "admin"}
    tok = _json(f"{kc}/realms/master{TOKEN_PATH}", form=form | {"password": ADMIN_PW})
    return tok["access_token"], f"{kc}/admin/realms/nautical-deliverance"


def _run(
    kc: str,
    email: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    *extra: str,
) -> tuple[int, str, str]:
    monkeypatch.setenv("ND_KC_ADMIN_PASSWORD", ADMIN_PW)
    code = pilot_user.main(["--url", kc, "--email", email, *ARGS, *extra])
    out = capsys.readouterr()
    return code, out.out, out.err


def test_default_org_is_the_seeded_pilot_org() -> None:
    from nautical_deliverance.persistence.seed import PILOT_ORGS  # type: ignore[import-untyped]  # noqa: PLC0415

    assert [str(u) for u in PILOT_ORGS] == [pilot_user.DEFAULT_ORG]


@needs_kc
@pytest.mark.req("B6-R05")
def test_create_sets_role_org_and_forces_password_change(
    kc: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out, err = _run(kc, "ada@pilot.example", capsys, monkeypatch)
    assert code == 0
    assert err == ""
    password = out.strip().rsplit(" ", 1)[1]
    assert len(password) >= MIN_PASSWORD_LEN
    assert out.count(password) == 1

    tok, admin = _admin(kc)
    (user,) = _json(f"{admin}/users?email=ada@pilot.example&exact=true", tok)
    assert user["attributes"]["org_id"] == [pilot_user.DEFAULT_ORG]
    assert "UPDATE_PASSWORD" in user["requiredActions"]
    roles = _json(f"{admin}/users/{user['id']}/role-mappings/realm", tok)
    assert {r["name"] for r in roles} - {"default-roles-nautical-deliverance"} == {"bunker_buyer"}
    (cred,) = _json(f"{admin}/users/{user['id']}/credentials", tok)
    assert cred["type"] == "password"

    # Signing in with the temporary password is refused until the password is changed.
    form = {"grant_type": "password", "client_id": "nd-test", "username": "ada@pilot.example"}
    with pytest.raises(urllib.error.HTTPError) as exc:
        _json(f"{kc}/realms/nautical-deliverance{TOKEN_PATH}", form=form | {"password": password})
    body = json.loads(exc.value.read())
    assert exc.value.code == HTTP_BAD_REQUEST
    assert body["error"] == "invalid_grant"
    assert "not fully set up" in body["error_description"]


@needs_kc
@pytest.mark.req("B6-R05")
def test_duplicate_email_exits_2_and_changes_nothing(
    kc: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _run(kc, "dup@pilot.example", capsys, monkeypatch)[0] == 0
    tok, admin = _admin(kc)
    (before,) = _json(f"{admin}/users?email=dup@pilot.example&exact=true", tok)
    creds = _json(f"{admin}/users/{before['id']}/credentials", tok)

    other_org = "44444444-4444-4444-8444-444444444444"
    code, out, err = _run(kc, "DUP@pilot.example", capsys, monkeypatch, "--org", other_org)
    assert code == EXIT_REFUSED
    assert out == ""
    assert "already exists" in err
    users = _json(f"{admin}/users?search=dup@pilot.example", tok)
    assert [u["id"] for u in users] == [before["id"]]
    assert _json(f"{admin}/users/{before['id']}", tok)["attributes"] == before["attributes"]
    assert _json(f"{admin}/users/{before['id']}/credentials", tok) == creds


@needs_kc
@pytest.mark.req("B6-R05")
def test_unknown_role_is_refused(
    kc: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    args = ["--url", kc, "--email", "x@pilot.example", *ARGS[:-1], "superuser"]
    monkeypatch.setenv("ND_KC_ADMIN_PASSWORD", ADMIN_PW)
    assert pilot_user.main(args) == EXIT_REFUSED
    cap = capsys.readouterr()
    assert "unknown role" in cap.err
    assert cap.out == ""
    tok, admin = _admin(kc)
    assert _json(f"{admin}/users?email=x@pilot.example&exact=true", tok) == []


@needs_kc
@pytest.mark.req("B6-R05")
def test_password_appears_once_and_in_no_log(
    kc: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("DEBUG")
    code, out, err = _run(kc, "log@pilot.example", capsys, monkeypatch)
    password = out.strip().rsplit(" ", 1)[1]
    assert code == 0
    assert out.count(password) == 1
    assert password not in err
    assert password not in caplog.text


def _realm_roles(admin: str, tok: str, uid: str) -> set[str]:
    roles = _json(f"{admin}/users/{uid}/role-mappings/realm", tok)
    return {r["name"] for r in roles} - {"default-roles-nautical-deliverance"}


def _users(admin: str, tok: str) -> list[Any]:
    return _json(f"{admin}/users?max=1000", tok)  # type: ignore[no-any-return]


@needs_kc
@pytest.mark.req("B7a-R05")
def test_create_with_two_roles(
    kc: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    code, _, _ = _run(kc, "two@pilot.example", capsys, monkeypatch, "--role", "admin")
    assert code == 0
    tok, admin = _admin(kc)
    (user,) = _json(f"{admin}/users?email=two@pilot.example&exact=true", tok)
    assert _realm_roles(admin, tok, user["id"]) == {"bunker_buyer", "admin"}


@needs_kc
@pytest.mark.req("B7a-R05")
def test_add_role_to_existing_user(
    kc: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _run(kc, "addrole@pilot.example", capsys, monkeypatch)[0] == 0
    tok, admin = _admin(kc)
    (before,) = _json(f"{admin}/users?email=addrole@pilot.example&exact=true", tok)
    creds = _json(f"{admin}/users/{before['id']}/credentials", tok)

    code, out, err = _run(
        kc, "ADDROLE@pilot.example", capsys, monkeypatch, "--add-role", "--role", "admin"
    )
    assert code == 0
    assert err == ""
    assert "password" not in out.lower()
    (after,) = _json(f"{admin}/users?email=addrole@pilot.example&exact=true", tok)
    assert _realm_roles(admin, tok, after["id"]) == {"bunker_buyer", "admin"}
    assert after["requiredActions"] == before["requiredActions"]
    after_creds = _json(f"{admin}/users/{before['id']}/credentials", tok)
    assert len(after_creds) == len(creds) == 1
    assert [c["id"] for c in after_creds] == [c["id"] for c in creds]


@needs_kc
@pytest.mark.req("B7a-R05")
def test_add_role_unknown_email_exits_2(
    kc: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    tok, admin = _admin(kc)
    before = len(_users(admin, tok))
    code, out, err = _run(
        kc, "nobody@pilot.example", capsys, monkeypatch, "--add-role", "--role", "admin"
    )
    assert code == EXIT_REFUSED
    assert out == ""
    assert "no user with e-mail nobody@pilot.example" in err
    assert len(_users(admin, tok)) == before


@needs_kc
@pytest.mark.req("B7a-R05")
def test_unknown_role_in_list_is_refused(
    kc: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out, err = _run(
        kc, "badlist@pilot.example", capsys, monkeypatch, "--role", "admin", "--role", "nope"
    )
    assert code != 0
    assert out == ""
    assert "unknown role" in err
    tok, admin = _admin(kc)
    assert _json(f"{admin}/users?email=badlist@pilot.example&exact=true", tok) == []


# --- rollback, no Docker: _call is stubbed -------------------------------------------------

TOKEN = "tok-secret-value"  # noqa: S105
LOC = "http://kc/admin/realms/r/users/uid-1"


def _stub(
    monkeypatch: pytest.MonkeyPatch,
    fail_on: str,
    *,
    delete_fails: bool = False,
    loc: str | None = LOC,
) -> list[str]:
    calls: list[str] = []

    def fake(method: str, url: str, *_a: object, **kw: object) -> object:
        calls.append(f"{method} {url.rsplit('/admin/realms/r', maxsplit=1)[-1]}")
        if "openid-connect/token" in url:
            return {"access_token": TOKEN}
        if method == "DELETE" and delete_fails:
            msg = "down"
            raise urllib.error.URLError(msg)
        if fail_on in (method, url.rpartition("/")[2]):
            raise urllib.error.HTTPError(url, 500, "boom", None, None)  # type: ignore[arg-type]
        if kw.get("location"):
            return loc
        if method == "GET":
            return {"name": "bunker_buyer"} if "/roles/" in url else []
        return None

    monkeypatch.setattr(pilot_user, "_call", fake)
    monkeypatch.setenv("ND_KC_ADMIN_PASSWORD", "admin-secret-value")
    return calls


def _main() -> int:
    return pilot_user.main(
        ["--url", "http://127.0.0.1:1", "--realm", "r", "--email", "a@b.example", *ARGS]
    )


def test_failure_after_create_rolls_back(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _stub(monkeypatch, "realm")
    assert _main() == 1
    cap = capsys.readouterr()
    assert "DELETE /users/uid-1" in calls
    assert "rolled back" in cap.err
    assert "WARNING" not in cap.err
    assert cap.out == ""
    for secret in (TOKEN, "admin-secret-value"):
        assert secret not in cap.err


def test_failed_rollback_warns(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub(monkeypatch, "reset-password", delete_fails=True)
    assert _main() == 1
    cap = capsys.readouterr()
    assert "WARNING: user a@b.example may remain without role" in cap.err
    assert "HTTP 500" in cap.err  # the original error is not masked
    assert cap.out == ""
    for secret in (TOKEN, "admin-secret-value"):
        assert secret not in cap.err + cap.out


def test_missing_location_still_warns(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub(monkeypatch, "none", loc="no-slash")  # id parse fails after create
    assert _main() == 1
    assert "WARNING" in capsys.readouterr().err


@pytest.mark.parametrize(
    "extra",
    [
        ["--role", "offline_access"],
        ["--org", "not-a-uuid"],
        ["--url", "http://kc.example.com"],
    ],
)
def test_bad_inputs_refused(
    extra: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = _stub(monkeypatch, "none")
    base = ["--url", "http://127.0.0.1:1", "--email", "a@b.example", *ARGS]
    # later options win in argparse
    assert pilot_user.main([*base, *extra]) == EXIT_REFUSED
    assert calls == []
    assert capsys.readouterr().out == ""
