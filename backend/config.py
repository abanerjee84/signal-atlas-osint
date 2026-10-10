from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OSINT_", env_file=ROOT / ".env", extra="ignore")

    database: Path = ROOT / "data/osint.sqlite3"
    advanced_public_read: bool = False
    media_max_bytes: int = Field(20_971_520, ge=1024, le=41_943_040)
    evidence_directory: Path = ROOT / "data/evidence"
    evidence_retention_days: int = Field(180, ge=1, le=3650)
    watch_allowed_hosts: list[str] = []
    searxng_url: str = ""
    advanced_ai_daily_budget: int = Field(20, ge=0, le=1000)
    advanced_lookup_daily_budget: int = Field(100, ge=0, le=1000)
    threat_catalogs_enabled: bool = True
    sans_contact: str = ""
    admin_token: str = ""
    http_timeout: float = Field(25, ge=1, le=120)
    connector_concurrency: int = Field(2, ge=1, le=4)
    max_feed_bytes: int = Field(8_388_608, ge=1024, le=33_554_432)
    max_records: int = Field(1000, ge=1, le=5000)
    raw_retention_days: int = Field(30, ge=1, le=365)
    event_retention_days: int = Field(180, ge=1, le=3650)
    stats_retention_days: int = Field(365, ge=1, le=3650)
    ai_cache_days: int = Field(7, ge=1, le=30)
    ai_daily_budget: int = Field(40, ge=0, le=10000)
    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"
    openrouter_fallback: str = ""
    ai_free_only: bool = True
    ai_timeout: float = Field(45, ge=1, le=120)
    firms_map_key: str = ""
    firms_area: str = "world"
    reliefweb_appname: str = ""
    acled_email: str = ""
    acled_password: str = ""
    opensky_client_id: str = ""
    opensky_client_secret: str = ""
    opensky_bbox: str = "world"
    opensky_poll_seconds: int = Field(120, ge=120, le=1800)
    maritime_url: str = ""
    maritime_token: str = ""
    extra_allowed_hosts: list[str] = []
    extra_rss: list[dict] = []
    reddit_subreddits: list[str] = ["worldnews", "geopolitics", "climate"]
    social_feeds: list[dict] = []
    youtube_channels: list[dict] = [
        {"id": "UC16niRr50-MSBwiO3YDb3RA", "name": "BBC News", "country": "GB"},
        {"id": "UCknLrEdhRCp1aegoMqRaCZg", "name": "DW News", "country": "DE"},
        {"id": "UCNye-wNBqNL5ZzHSJj3l8Bg", "name": "Al Jazeera English", "country": "QA"},
    ]
