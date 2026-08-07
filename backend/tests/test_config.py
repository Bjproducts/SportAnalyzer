"""Configuration and secret-handling tests."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.logging import _redact_secrets


def test_cors_origins_accepts_comma_separated_string():
    settings = Settings(cors_origins="http://a.test, http://b.test")  # type: ignore[arg-type]
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_cors_origins_parses_from_the_environment(monkeypatch):
    """Regression: the env path differs from the kwargs path.

    pydantic-settings JSON-decodes complex-typed fields read from the
    environment before validators run, so a comma-separated CORS_ORIGINS used
    to raise SettingsError at import time even though the kwargs form worked.
    """
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test,http://b.test")
    settings = Settings()
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_cors_origins_falls_back_to_default_when_unset(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert Settings(_env_file=None).cors_origins == ["http://localhost:3000"]


def test_empty_cors_origin_regex_is_disabled():
    assert Settings(_env_file=None, cors_origin_regex="  ").cors_origin_regex is None


def test_netlify_preview_cors_regex_is_preserved():
    pattern = r"^https://deploy-preview-[0-9]+--sot-lab\.netlify\.app$"
    assert Settings(_env_file=None, cors_origin_regex=pattern).cors_origin_regex == pattern


def test_database_uri_uses_async_driver():
    settings = Settings(
        _env_file=None,
        database_url=None,
        postgres_user="u",
        postgres_password="p",
        postgres_host="h",
        postgres_db="d",
    )
    assert settings.sqlalchemy_database_uri.startswith("postgresql+psycopg://")


@pytest.mark.parametrize(
    "given",
    ["postgres://u:p@h:5432/d", "postgresql://u:p@h:5432/d"],
)
def test_database_url_override_is_normalised_to_the_async_driver(given):
    """A provider-injected sync DSN must not reach the async engine unchanged."""
    settings = Settings(database_url=given)
    assert settings.sqlalchemy_database_uri.startswith("postgresql+psycopg://")


def test_safe_summary_contains_no_secret_values():
    settings = Settings(
        postgres_password="super-secret-pw",
        admin_api_token="super-secret-token",
        football_api_key="super-secret-key",
    )
    rendered = repr(settings.safe_summary())
    assert "super-secret" not in rendered
    # It still reports *whether* they are configured.
    assert settings.safe_summary()["admin_auth_configured"] is True
    assert settings.safe_summary()["provider_auth_configured"] is True


def test_safe_summary_survives_log_redaction():
    """The summary must stay informative after passing through the redactor.

    Naming a field `admin_token_set` would trip the substring match and blank
    the boolean, making the startup log useless.
    """
    summary = Settings(admin_api_token="x", football_api_key="y").safe_summary()
    redacted = _redact_secrets(None, "info", dict(summary))
    assert redacted["admin_auth_configured"] is True
    assert redacted["provider_auth_configured"] is True


def test_secrets_never_render_in_str():
    settings = Settings(postgres_password="hunter2")
    assert "hunter2" not in str(settings.postgres_password)


@pytest.mark.parametrize(
    "key",
    ["password", "api_key", "X-Admin-Token", "Authorization", "DATABASE_URL", "client_secret"],
)
def test_log_redaction_scrubs_sensitive_keys(key):
    event = {"event": "test", key: "leaked-value"}
    result = _redact_secrets(None, "info", event)
    assert result[key] == "***redacted***"


def test_log_redaction_recurses_into_nested_dicts():
    event = {"event": "provider_call", "headers": {"x-rapidapi-key": "leaked", "accept": "json"}}
    result = _redact_secrets(None, "info", event)
    assert result["headers"]["x-rapidapi-key"] == "***redacted***"
    assert result["headers"]["accept"] == "json"


def test_log_redaction_leaves_ordinary_fields_intact():
    event = {"event": "x", "player_id": 42, "shots_on_target": None}
    result = _redact_secrets(None, "info", event)
    assert result["player_id"] == 42
    assert result["shots_on_target"] is None
