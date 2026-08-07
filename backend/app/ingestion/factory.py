"""Provider selection from server-side settings."""

from app.core.config import Settings
from app.core.exceptions import ValidationError
from app.ingestion.api_football import ApiFootballProvider
from app.ingestion.fake import FakeFootballProvider
from app.ingestion.provider import FootballDataProvider
from app.ingestion.sports_api_pro import SportsApiProProvider
from app.ingestion.statsbomb import StatsBombOpenDataProvider


def create_provider(settings: Settings) -> FootballDataProvider:
    name = settings.football_provider.strip().casefold()
    if name == "fake":
        return FakeFootballProvider()
    if name == "statsbomb":
        return StatsBombOpenDataProvider(
            base_url=settings.football_open_data_base_url,
            timeout_seconds=settings.football_api_timeout_seconds,
            max_retries=settings.football_api_max_retries,
        )
    if name == "sportsapipro":
        key = settings.sports_api_pro_key.get_secret_value()
        if not key:
            raise ValidationError(
                "SPORTS_API_PRO_KEY is required when FOOTBALL_PROVIDER=sportsapipro."
            )
        return SportsApiProProvider(
            api_key=key,
            base_url=settings.sports_api_pro_base_url,
            calls_per_minute=settings.football_api_rate_limit_per_minute,
            timeout_seconds=settings.football_api_timeout_seconds,
            max_retries=settings.football_api_max_retries,
            history_pages=settings.sports_api_pro_history_pages,
        )
    if name == "apifootball":
        key = settings.football_api_key.get_secret_value()
        if not key:
            raise ValidationError(
                "FOOTBALL_API_KEY is required when FOOTBALL_PROVIDER=apifootball."
            )
        return ApiFootballProvider(
            api_key=key,
            base_url=settings.football_api_base_url,
            calls_per_minute=settings.football_api_rate_limit_per_minute,
            timeout_seconds=settings.football_api_timeout_seconds,
            max_retries=settings.football_api_max_retries,
        )
    raise ValidationError(f"Unsupported football provider: {settings.football_provider!r}.")
