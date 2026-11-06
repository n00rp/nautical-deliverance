"""The production overlay (B6-R01) and the pilot realm (B6-R03), from the rendered config."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

MIN_PASSWORD_LENGTH = 12
ROOT = Path(__file__).resolve().parent.parent
INFRA = ROOT / "infra"
CADDYFILE = INFRA / "caddy" / "Caddyfile"
REALM = INFRA / "keycloak" / "realm-pilot.json"
ENV_EXAMPLE = INFRA / ".env.prod.example"
# Dummy values only: `config` needs every `:?` variable to be set.
DUMMY_ENV = {
    "ND_PUBLIC_HOST": "pilot.example.test",
    "ND_DB_SUPERUSER_PASSWORD": "x",
    "ND_DB_OWNER_PASSWORD": "x",
    "ND_DB_APP_PASSWORD": "x",
    "ND_DB_KEYCLOAK_PASSWORD": "x",
    "ND_KEYCLOAK_ADMIN_PASSWORD": "x",
}


def _compose(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Render the merged config; devnull as env file keeps a developer's infra/.env out."""
    cmd = ["docker", "compose", "--env-file", os.devnull, "--project-directory", str(INFRA)]
    for name in ("docker-compose.yml", "docker-compose.prod.yml"):
        cmd += ["-f", str(INFRA / name)]
    return subprocess.run(  # noqa: S603
        [*cmd, "config", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env={k: v for k, v in os.environ.items() if not k.startswith("ND_")} | env,
    )


def _config() -> dict[str, Any]:
    result = _compose(DUMMY_ENV)
    assert result.returncode == 0, result.stderr
    config: dict[str, Any] = json.loads(result.stdout)
    return config


needs_docker = pytest.mark.skipif(shutil.which("docker") is None, reason="needs docker compose")


@needs_docker
@pytest.mark.req("B6-R01")
def test_only_caddy_publishes_ports() -> None:
    services = _config()["services"]
    published = {n for n, s in services.items() if s.get("ports")}
    assert published == {"caddy"}
    ports = {(p["target"], p["published"]) for p in services["caddy"]["ports"]}
    assert ports == {(80, "80"), (443, "443")}


@needs_docker
@pytest.mark.req("B6-R01")
def test_keycloak_runs_production_mode_behind_the_proxy() -> None:
    kc = _config()["services"]["keycloak"]
    assert kc["command"][0] == "start"
    assert "start-dev" not in kc["command"]
    assert "--import-realm" in kc["command"]
    env = kc["environment"]
    assert env["KC_HOSTNAME"] == "https://pilot.example.test"
    assert env["KC_PROXY_HEADERS"] == "xforwarded"
    assert env["KC_HTTP_ENABLED"] == "true"
    assert env["KC_DB"] == "postgres"
    volumes = [v["source"] for v in kc["volumes"]]
    assert [Path(v).name for v in volumes] == ["realm-pilot.json"]


@needs_docker
@pytest.mark.req("B6-R01")
def test_every_service_restarts_and_every_image_is_pinned_or_built() -> None:
    services = _config()["services"]
    assert set(services) == {"caddy", "db", "keycloak", "engine", "web"}
    for name, service in services.items():
        assert service.get("restart") == "unless-stopped", name
    assert re.search(r"@sha256:[0-9a-f]{64}$", services["caddy"]["image"])


@needs_docker
@pytest.mark.req("B6-R01")
def test_app_wiring_uses_the_public_host_and_pilot_seed() -> None:
    services = _config()["services"]
    issuer = "https://pilot.example.test/realms/nautical-deliverance"
    engine = services["engine"]["environment"]
    assert engine["ND_SEED"] == "pilot"
    assert engine["ND_OIDC_ISSUER"] == issuer
    assert engine["ND_OIDC_JWKS_URL"].startswith("http://keycloak:8080/")
    assert services["web"]["build"]["args"]["VITE_OIDC_AUTHORITY"] == issuer
    assert services["caddy"]["environment"]["ND_PUBLIC_HOST"] == "pilot.example.test"


@needs_docker
@pytest.mark.req("B6-R01")
@pytest.mark.parametrize("missing", sorted(DUMMY_ENV))
def test_missing_secret_is_refused_instead_of_defaulting_to_dev(missing: str) -> None:
    result = _compose({k: v for k, v in DUMMY_ENV.items() if k != missing})
    assert result.returncode != 0
    assert missing in result.stderr


@pytest.mark.req("B6-R01")
def test_caddyfile_headers_admin_block_and_routes() -> None:
    text = CADDYFILE.read_text(encoding="utf-8")
    assert "{$ND_PUBLIC_HOST}" in text
    for fragment in (
        "Strict-Transport-Security",
        "max-age=31536000",
        "Content-Security-Policy",
        "X-Content-Type-Options",
        "nosniff",
        "Referrer-Policy",
        "strict-origin-when-cross-origin",
        "X-Frame-Options",
        "DENY",
        "respond 404",
        "/admin",
        "reverse_proxy engine:8000",
        "reverse_proxy keycloak:8080",
        "reverse_proxy web:8080",
    ):
        assert fragment in text, fragment


@pytest.mark.req("B6-R03")
def test_pilot_realm_has_roles_client_and_no_users() -> None:
    realm = json.loads(REALM.read_text(encoding="utf-8"))
    assert {r["name"] for r in realm["roles"]["realm"]} == {
        "admin",
        "bunker_buyer",
        "operator",
        "viewer",
    }
    assert not realm.get("users")
    assert [c["clientId"] for c in realm["clients"]] == ["nd-web"]
    mappers = {m["name"] for m in realm["clients"][0]["protocolMappers"]}
    assert {"org_id", "roles", "audience-nd-api"} <= mappers
    assert realm["bruteForceProtected"] is True
    match = re.search(r"length\((\d+)\)", realm["passwordPolicy"])
    assert match
    assert int(match.group(1)) >= MIN_PASSWORD_LENGTH
    assert "DEV" not in json.dumps(realm)


@pytest.mark.req("B6-R03")
def test_pilot_realm_redirects_only_to_the_pilot_url() -> None:
    client = json.loads(REALM.read_text(encoding="utf-8"))["clients"][0]
    host = "${ND_PUBLIC_HOST}"
    assert client["redirectUris"] == [f"https://{host}/*"]
    assert client["webOrigins"] == [f"https://{host}"]
    assert client["attributes"]["post.logout.redirect.uris"] == f"https://{host}/*"
    assert client["publicClient"] is True
    assert client["directAccessGrantsEnabled"] is False


def _git_ignored(path: str) -> bool:
    result = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False)  # noqa: S603, S607
    return result.returncode == 0


@pytest.mark.req("B6-R03")
def test_env_prod_is_gitignored_and_example_holds_placeholders_only() -> None:
    assert _git_ignored("infra/.env.prod")
    assert not _git_ignored("infra/.env.prod.example")
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            assert value == "CHANGE_ME" or key == "ND_PUBLIC_HOST", line
