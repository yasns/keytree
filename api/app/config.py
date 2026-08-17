from importlib.metadata import version

from pydantic_settings import BaseSettings, SettingsConfigDict

# pyproject.toml [project].version
APP_VERSION = version("keytree-api")


class Settings(BaseSettings):
    """Everything comes from the environment (or .env locally)."""

    # extra="ignore": .env also carries tsgauth's own OIDC_* vars, which aren't fields here
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str  # set per environment
    git_sha: str = "unknown"  # added to the image at build time
    log_level: str = "INFO"
    secret_key: str  # signs tsgauth session state, set per environment via Secret


settings = Settings()  # pyright: ignore[reportCallIssue] # fields come from the environment
