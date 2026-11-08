from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OSINT_", env_file=ROOT / ".env", extra="ignore")

    database: Path = ROOT / "data/osint.sqlite3"
    advanced_public_read: bool = False
    # Declares that this deployment displays or redistributes source output for
    # payment or advertising. When set, every source whose source_permissions row
    # is not `cleared` is refused rather than silently collected (SRS FR-DATA-01).
    commercial_use: bool = False
    media_max_bytes: int = Field(20_971_520, ge=1024, le=41_943_040)
    evidence_directory: Path = ROOT / "data/evidence"
    evidence_retention_days: int = Field(180, ge=1, le=3650)
    watch_allowed_hosts: list[str] = []
    searxng_url: str = ""
    advanced_ai_daily_budget: int = Field(20, ge=0, le=1000)
    advanced_lookup_daily_budget: int = Field(100, ge=0, le=1000)
    threat_catalogs_enabled: bool = True
    sans_contact: str = ""
    dshield_enabled: bool = True
    dshield_limit: int = Field(50, ge=1, le=100)
    isc_honeypots_enabled: bool = False
    isc_honeypots_user_agent: str = Field("jndi:ldap", min_length=1, max_length=120)
    cyber_observation_retention_days: int = Field(30, ge=1, le=180)
    threatfox_auth_key: str = ""
    greynoise_api_key: str = ""
    cloudflare_radar_token: str = ""
    infrastructure_geo_enabled: bool = True
    infrastructure_geo_daily_budget: int = Field(250, ge=0, le=750)
    admin_token: str = ""
    monitoring_retention_days: int = Field(7, ge=1, le=90)
    monitoring_max_rows: int = Field(250_000, ge=1000, le=2_000_000)
    tfl_cameras_enabled: bool = True
    satnogs_stations_enabled: bool = True
    public_radio_receivers: list[dict] = []
    monitoring_adsb_url: str = ""
    shodan_api_key: str = ""
    shodan_daily_budget: int = Field(20, ge=0, le=200)
    expansion_enabled: list[str] = [
        "feodo",
        "nws_alerts",
        "swpc",
        "caltrans_cameras",
        "nyc_cameras",
        "singapore_cameras",
        "kiwisdr",
        "amtraker",
        "digitraffic",
        "volcanoes",
        "ripe_atlas",
    ]
    urlhaus_auth_key: str = ""
    caltrans_districts: list[int] = [3, 4, 7, 11, 12]
    openaq_api_key: str = ""
    openaq_location_ids: list[int] = []
    psk_callsign: str = ""
    tinygs_token: str = ""
    tinygs_url: str = "https://api.tinygs.com/v1/satellitesWorldmap"
    gfw_event_types: list[str] = ["fishing", "encounter", "loitering", "port_visit", "gap"]
    reference_feeds: list[dict] = []
    wastewater_url: str = ""
    wastewater_license: str = ""
    published_assessments_url: str = ""
    published_assessments_license: str = ""
    expansion_lookup_daily_budget: int = Field(40, ge=0, le=500)
    earthdata_token: str = ""
    imagery_search_url: str = "https://earth-search.aws.element84.com/v1/search"
    imagery_asset_hosts: list[str] = [
        "earth-search.aws.element84.com",
        "sentinel-cogs.s3.us-west-2.amazonaws.com",
    ]
    raster_max_pixels: int = Field(4_000_000, ge=1000, le=16_000_000)
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
    opensky_poll_seconds: int = Field(30, ge=10, le=1800)
    maritime_url: str = ""
    maritime_token: str = ""
    # AIS Stream account key. Server-side only: the service forbids direct
    # browser connections, and the key is never sent to a client or written to
    # a stored observation. Empty disables the keyed primary and leaves the
    # anonymous OpenSeaFeed/Open Waters streams in place.
    aisstream_api_key: str = ""
    # BarentsWatch live AIS (Norwegian Coastal Administration open data).
    # Free OAuth2 client credentials from barentswatch.no; the secret stays in
    # the worker process and is never logged or exposed to a client.
    barentswatch_client_id: str = ""
    barentswatch_client_secret: str = ""
    # Global Fishing Watch research token for vessel-registry identity. Free
    # non-commercial registration; presented as a Bearer token from the worker.
    gfw_api_token: str = ""
    # NOAA/BOEM Marine Cadastre AIS bulk lane (manual collector). Points at one
    # CSV.zst day file from noaaocm.blob.core.windows.net; scheduled cycles
    # never touch it, so a run is operator-initiated and size-bounded.
    noaa_ais_url: str = ""
    noaa_ais_max_bytes: int = Field(603_979_776, ge=1_048_576, le=1_073_741_824)
    extra_allowed_hosts: list[str] = []
    extra_rss: list[dict] = []
    reddit_subreddits: list[str] = ["worldnews", "geopolitics", "climate"]
    social_feeds: list[dict] = []
    telegram_channels: list[str] = ["geopoliticsandempire"]
    youtube_channels: list[dict] = [
        {"id": "UC16niRr50-MSBwiO3YDb3RA", "name": "BBC News", "country": "GB"},
        {"id": "UCknLrEdhRCp1aegoMqRaCZg", "name": "DW News", "country": "DE"},
        {"id": "UCNye-wNBqNL5ZzHSJj3l8Bg", "name": "Al Jazeera English", "country": "QA"},
        # Official defence and security channels. NATO has no usable public RSS
        # feed, so its uploads are the only reachable first-party NATO reporting;
        # the combatant commands block automated website access but not uploads.
        {
            "id": "UC3z9S2WXr6BRZm5bAU3DS6Q",
            "name": "NATO",
            "country": None,
            "category": "military",
        },
        {
            "id": "UCNEEHeS9Y2yFVLbWGeHhbYA",
            "name": "US Central Command",
            "country": "US",
            "category": "military",
        },
        {
            "id": "UCJjsCRh3ym2AVZY4_Yqd2PQ",
            "name": "US European Command",
            "country": "US",
            "category": "military",
        },
        {
            "id": "UCch5n8gbHHXrgDjfU8BcfFA",
            "name": "US Indo-Pacific Command",
            "country": "US",
            "category": "military",
        },
        {
            "id": "UCjdWZTMt_7O6Jue7gFbxj7w",
            "name": "US Navy",
            "country": "US",
            "category": "military",
        },
        {
            "id": "UCv6J1XT-BsmAAw8QWjOpyOA",
            "name": "US Army",
            "country": "US",
            "category": "military",
        },
        {
            "id": "UCPuDWLu1965eOYZaZHCjr8Q",
            "name": "US Air Force",
            "country": "US",
            "category": "military",
        },
        {
            "id": "UCwvbiJEOraaER7z1DYWy1VA",
            "name": "Israel Defense Forces",
            "country": "IL",
            "category": "military",
        },
        # Defence trade press and research institutes publishing as video.
        {
            "id": "UCIUg-gNzeWPEvt-GXQwPBdg",
            "name": "The War Zone",
            "country": "US",
            "category": "military",
        },
        {
            "id": "UCQlkl2_FLVkaS4e_R6IVIOw",
            "name": "Naval News",
            "country": "GB",
            "category": "military",
        },
        {
            "id": "UCw0y9zO1RXI6uEzoKbbnxTQ",
            "name": "Atlantic Council",
            "country": "US",
            "category": "military",
        },
    ]
