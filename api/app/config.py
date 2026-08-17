from importlib.metadata import version

from pydantic_settings import BaseSettings

# pyproject.toml [project].version
APP_VERSION = version("keytree-api")


class Settings(BaseSettings):
    """Everything comes from the environment."""

    environment: str  # set per environment via ConfigMap
    git_sha: str = "unknown"  # added to the image at build time
    log_level: str = "INFO"


settings = Settings()  # pyright: ignore[reportCallIssue] # fields come from the environment
