"""Bunker procurement roles (B1-R01)."""

import re
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from nautical_deliverance.domain.identity import Role
from tests.unit.test_auth import _client, _get, _token

if TYPE_CHECKING:
    from nautical_deliverance.settings import Settings

ROOT = Path(__file__).resolve().parents[3]
OLD = "route_" + "analyst"  # built so this file does not match its own search


@pytest.mark.req("B1-R01")
def test_roles_are_bunker_roles() -> None:
    """The enum holds exactly the four bunker roles."""
    assert {r.name: r.value for r in Role} == {
        "ADMIN": "admin",
        "BUNKER_BUYER": "bunker_buyer",
        "OPERATOR": "operator",
        "VIEWER": "viewer",
    }


@pytest.mark.req("B1-R01")
def test_old_role_name_absent_from_code_and_infra() -> None:
    """The retired S0 role name appears nowhere in source, infra or tools."""
    pattern = re.compile(OLD.replace("_", "[_ -]?"), re.IGNORECASE)
    hits = [
        str(p.relative_to(ROOT))
        for top in ("engine/src", "web/src", "infra", "tools")
        for p in (ROOT / top).rglob("*")
        if p.is_file()
        and "node_modules" not in p.parts
        and p.suffix in {".py", ".ts", ".tsx", ".json", ".sh", ".yml", ".yaml", ".css", ".md"}
        and pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert hits == []


@pytest.mark.req("B1-R01")
def test_retired_role_in_token_is_ignored(settings: Settings) -> None:
    """A token carrying the retired role yields only the known roles."""
    response = _get(_client(settings), _token(settings, roles=[OLD, "operator"]))
    assert response.status_code == HTTPStatus.OK
    assert response.json()["roles"] == ["operator"]
