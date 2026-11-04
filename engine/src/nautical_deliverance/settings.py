"""Application settings read from ND_-prefixed environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Engine configuration."""

    model_config = SettingsConfigDict(env_prefix="ND_")

    git_sha: str = "dev"
    database_url: str
    oidc_issuer: str
    oidc_audience: str
    oidc_jwks_url: str
