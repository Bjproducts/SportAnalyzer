"""Application configuration.

All settings are read from the environment (or a local `.env` file) exactly
once and cached.  Nothing in the application reads `os.environ` directly - it
goes through :func:`get_settings` so that tests can override cleanly and so
that secrets have a single, auditable entry point.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TEST = "test"


class Settings(BaseSettings):
    """Runtime configuration, populated from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Runtime -----------------------------------------------------------
    environment: Environment = Environment.DEVELOPMENT
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_json: bool = False

    # --- API ---------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_v1_prefix: str = "/api"
    project_name: str = "SOT Analyzer"

    # `NoDecode` is required: without it pydantic-settings tries to JSON-decode
    # any complex-typed field read from the environment *before* validators run,
    # so a plain `CORS_ORIGINS=a,b` raises a SettingsError at startup.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    cors_origin_regex: str | None = None

    # --- Database ----------------------------------------------------------
    postgres_user: str = "sot"
    postgres_password: SecretStr = SecretStr("sot")
    postgres_db: str = "sot_analyzer"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Full DSN override. Wins over the individual POSTGRES_* parts when set.
    database_url: str | None = None

    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # --- Admin -------------------------------------------------------------
    admin_api_token: SecretStr = SecretStr("")

    # --- Provider ----------------------------------------------------------
    football_provider: str = "fake"
    football_api_key: SecretStr = SecretStr("")
    football_api_base_url: str = "https://v3.football.api-sports.io"
    sports_api_pro_key: SecretStr = SecretStr("")
    sports_api_pro_base_url: str = "https://v2.football.sportsapipro.com"
    sports_api_pro_history_pages: Annotated[int, Field(ge=1, le=100)] = 1
    football_open_data_base_url: str = (
        "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
    )
    football_api_rate_limit_per_minute: Annotated[int, Field(ge=1, le=10_000)] = 10
    football_api_timeout_seconds: Annotated[float, Field(gt=0)] = 20.0
    football_api_max_retries: Annotated[int, Field(ge=0, le=10)] = 4

    # --- Analytics defaults ------------------------------------------------
    default_min_starts_for_ranking: Annotated[int, Field(ge=1)] = 5
    early_exit_minutes_threshold: Annotated[int, Field(ge=1, le=120)] = 45

    # --- Validators --------------------------------------------------------

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept either a comma-separated string or a real list.

        `.env` files can only carry strings, so `CORS_ORIGINS=a,b` must be
        split here rather than relying on pydantic's JSON list parsing.
        """
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_origin_regex", mode="before")
    @classmethod
    def _empty_cors_regex_is_none(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    # --- Derived -----------------------------------------------------------

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_database_uri(self) -> str:
        """Async SQLAlchemy URL.

        Always uses the `psycopg` (v3) async driver.  A `DATABASE_URL` override
        is normalised so that a plain `postgresql://` value - which is what most
        hosting providers inject - does not silently select the sync driver and
        blow up inside the async engine.
        """
        if self.database_url:
            url = self.database_url
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+psycopg://", 1)
            return url

        return str(
            PostgresDsn.build(
                scheme="postgresql+psycopg",
                username=self.postgres_user,
                password=self.postgres_password.get_secret_value(),
                host=self.postgres_host,
                port=self.postgres_port,
                path=self.postgres_db,
            )
        )

    def safe_summary(self) -> dict[str, object]:
        """Configuration snapshot with every secret removed - safe to log."""
        return {
            "environment": str(self.environment),
            "log_level": self.log_level,
            "api_prefix": self.api_v1_prefix,
            "cors_origins": self.cors_origins,
            "postgres_host": self.postgres_host,
            "postgres_port": self.postgres_port,
            "postgres_db": self.postgres_db,
            "football_provider": self.football_provider,
            # These names deliberately avoid every substring in
            # `logging._SENSITIVE_KEY_PARTS` (token / secret / api_key /
            # credential / ...). The redactor blanks values by key name, and
            # blanking these booleans would gut the startup log.
            # `test_safe_summary_survives_log_redaction` locks this in.
            "provider_auth_configured": bool(
                self.football_api_key.get_secret_value()
                or self.sports_api_pro_key.get_secret_value()
            ),
            "admin_auth_configured": bool(self.admin_api_token.get_secret_value()),
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings singleton."""
    return Settings()
