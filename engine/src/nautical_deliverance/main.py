"""Application factory."""

from fastapi import FastAPI

from nautical_deliverance.api import health
from nautical_deliverance.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app; settings default to the environment."""
    app = FastAPI()
    app.state.settings = settings or Settings()  # type: ignore[call-arg]
    app.include_router(health.router, prefix="/api/v1")
    return app
