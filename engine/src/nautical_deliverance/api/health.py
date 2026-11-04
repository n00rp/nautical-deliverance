"""Health endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from nautical_deliverance.settings import Settings  # noqa: TC001  (FastAPI resolves it at runtime)

router = APIRouter()


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


@router.get("/health")
def health(settings: Annotated[Settings, Depends(_settings)]) -> dict[str, str]:
    """Report liveness and the deployed git SHA."""
    return {"status": "ok", "version": settings.git_sha}
