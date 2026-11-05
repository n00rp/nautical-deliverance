"""Application factory."""

import jwt
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from nautical_deliverance.api import common, health, master, me
from nautical_deliverance.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app; settings default to the environment."""
    app = FastAPI()
    app.state.settings = settings or Settings()  # type: ignore[call-arg]
    # One JWKS client per app: it caches signing keys across requests.
    app.state.jwks_client = jwt.PyJWKClient(
        app.state.settings.oidc_jwks_url, cache_keys=True, timeout=5
    )
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(me.router, prefix="/api/v1")
    app.include_router(master.router, prefix="/api/v1")
    app.add_exception_handler(RequestValidationError, common.validation_handler)
    return app
