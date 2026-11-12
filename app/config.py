from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

INTERVAL_SECONDS: dict[str, int] = {
    "1h": 3600,
    "6h": 6 * 3600,
    "12h": 12 * 3600,
    "24h": 24 * 3600,
    "7d": 7 * 24 * 3600,
}

RANGE_DAYS: dict[str, int | None] = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "all": None,
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./data/app.db"

    scrape_poll_seconds: int = 30
    scrape_batch_size: int = 10
    scrape_min_gap_per_domain: float = 15.0
    http_timeout: float = 20.0
    max_failure_backoff_seconds: int = 6 * 3600
    default_interval: str = "24h"
    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    rss_url: str = "https://www.pepper.pl/rss/wszystkie"
    rss_poll_seconds: int = 900
    rss_max_items: int = 300
    rss_keep_hours: int = 72

    playwright_enabled: bool = True
    playwright_timeout_ms: int = 25_000
    playwright_navigation_wait: str = "domcontentloaded"
    playwright_settle_ms: int = 1_500
    playwright_browsers_path: str = ""

    discord_webhook_url: str = ""
    discord_min_drop_pct: float = 0.0
    discord_highlight_all_time_low: bool = True

    adapters_dir: str = "./data/adapters"

    image_proxy_enabled: bool = True
    image_cache_dir: str = "./data/image_cache"
    image_cache_ttl_days: int = 7
    image_cache_max_mb: int = 256
    image_max_bytes: int = 5 * 1024 * 1024

    admin_password: str = ""
    secret_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
