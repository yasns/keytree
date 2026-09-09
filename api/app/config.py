from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """Populated from the environment (or .env locally)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")  # ignore OIDC_ vars

    environment: str
    git_sha: str = "unknown"  # added to the image at build time
    log_level: str = "INFO"
    secret_key: str

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "keytree"
    postgres_user: str = "keytree"
    postgres_password: str = ""
    postgres_sslmode: str = "prefer"

    @property
    def database_url(self) -> URL:
        """The API connects as the least-privileged app user, migrations as the owner."""
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
            query={"sslmode": self.postgres_sslmode},
        )


settings = Settings()  # pyright: ignore[reportCallIssue] # fields come from the environment
