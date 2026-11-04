"""Health endpoint tests."""

from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from nautical_deliverance.main import create_app

if TYPE_CHECKING:
    from nautical_deliverance.settings import Settings


@pytest.mark.req("S0-R02")
def test_health_returns_ok_and_version(settings: Settings) -> None:
    """Health is public and reports the git SHA."""
    response = TestClient(create_app(settings)).get("/api/v1/health")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok", "version": "abc123"}
    assert "authorization" not in response.request.headers
