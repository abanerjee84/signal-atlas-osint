import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def stamp(value: datetime | None = None) -> str:
    return (value or utcnow()).astimezone(timezone.utc).isoformat(timespec="seconds")


class Category(StrEnum):
    geopolitical = "geopolitical"
    military = "military"
    aviation = "aviation"
    maritime = "maritime"
    sentiment = "sentiment"
    cyber = "cyber"
    threat = "threat"
    economic = "economic"
    environment = "environment"
    analysis = "analysis"


class Confidence(StrEnum):
    verified = "Verified"
    corroborated = "Corroborated"
    single = "Single-source"
    disputed = "Disputed"
    unverified = "Unverified"


class SocialRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["reply", "quote", "repost", "comment_on", "crosspost"]
    target_id: str = Field(min_length=1, max_length=512)
    target_url: str = Field(max_length=2048)


class SocialMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: Literal["x", "reddit", "youtube", "mastodon", "lemmy", "telegram"]
    post_id: str = Field(min_length=1, max_length=512)
    author: str = Field(default="", max_length=200)
    community: str = Field(default="", max_length=200)
    content_type: Literal["post", "comment", "video"] = "post"
    origin_country: str | None = Field(default=None, pattern="^[A-Z]{2}$")
    origin_basis: str = Field(default="Platform does not supply a supported post origin", max_length=500)
    mentioned_countries: list[str] = Field(default_factory=list, max_length=20)
    context_countries: list[str] = Field(default_factory=list, max_length=20)
    relations: list[SocialRelation] = Field(default_factory=list, max_length=20)

    @field_validator("mentioned_countries", "context_countries")
    @classmethod
    def country_codes(cls, values):
        if any(not re.fullmatch(r"[A-Z]{2}", value) for value in values):
            raise ValueError("Invalid mentioned country")
        return sorted(set(values))


class NewsMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    publisher_country: str | None = Field(default=None, pattern="^[A-Z]{2}$")
    publisher_basis: str = "Configured publisher base country; not a report's place of origin"
    mentioned_countries: list[str] = Field(default_factory=list, max_length=20)
    upstream_sources: list[str] = Field(default_factory=list, max_length=5)
    reporting_location: str = Field(default="", max_length=250)
    event_type: str = Field(default="", max_length=50)

    @field_validator("upstream_sources")
    @classmethod
    def references(cls, values):
        if any(len(value) > 2048 for value in values):
            raise ValueError("Upstream reference too long")
        return list(dict.fromkeys(Report.safe_url(value) for value in values))

    @field_validator("mentioned_countries")
    @classmethod
    def country_codes(cls, values):
        return SocialMetadata.country_codes(values)


class AircraftMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    icao24: str = Field(max_length=20)
    registration_country: str = Field(max_length=100)
    barometric_altitude_m: float | None = Field(default=None, allow_inf_nan=False)
    geometric_altitude_m: float | None = Field(default=None, allow_inf_nan=False)
    speed_mps: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    vertical_rate_mps: float | None = Field(default=None, allow_inf_nan=False)
    on_ground: bool | None = None
    last_contact: datetime | None = None


class ThreatMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = Field(default="Unknown actor", max_length=200)
    attacker_country: str | None = Field(default=None, pattern="^[A-Z]{2}$")
    victim_countries: list[str] = Field(default_factory=list, max_length=20)
    attack_kind: str = Field(max_length=80)
    attack_vectors: list[str] = Field(default_factory=list, max_length=12)
    vector_evidence: str = Field(default="", max_length=1000)
    cves: list[str] = Field(default_factory=list, max_length=20)
    attribution_basis: str = Field(max_length=1000)
    victim_basis: str = Field(max_length=1000)
    classification: Literal["reported_attack", "observed_traffic", "detection"] = "reported_attack"
    traffic_origin_country: str | None = Field(default=None, pattern="^[A-Z]{2}$")
    traffic_target_country: str | None = Field(default=None, pattern="^[A-Z]{2}$")
    detection_country: str | None = Field(default=None, pattern="^[A-Z]{2}$")
    provider_time: str = Field(default="", max_length=100)
    received_at: datetime | None = None

    @model_validator(mode="after")
    def separate_traffic_attribution(self):
        if self.classification != "reported_attack" and (
            self.attacker_country or self.victim_countries or self.actor != "Unknown actor"
        ):
            raise ValueError("Traffic geography cannot establish actor or victim attribution")
        if self.classification == "reported_attack" and (
            self.traffic_origin_country or self.traffic_target_country or self.detection_country
        ):
            raise ValueError("Reported attribution cannot contain telemetry geography")
        if self.received_at and self.received_at.tzinfo is None:
            raise ValueError("Receipt timestamp requires a timezone")
        return self

    @field_validator("victim_countries")
    @classmethod
    def country_codes(cls, values):
        return SocialMetadata.country_codes(values)


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_id: str = Field(min_length=1, max_length=512)
    source_id: str = Field(min_length=1, max_length=100)
    source_url: str = Field(max_length=2048)
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=10000)
    category: Category
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    location_precision: str = Field(default="unknown", pattern="^(exact|approximate|regional|unknown)$")
    location_basis: str = "No supported location"
    country_code: str | None = Field(default=None, pattern="^[A-Z]{2}$")
    occurred_at: datetime | None = None
    published_at: datetime
    confidence: Confidence = Confidence.single
    evidence_basis: str = "One source report; not independently verified"
    severity: str = Field(default="unknown", pattern="^(low|moderate|high|critical|unknown)$")
    severity_basis: str = "No severity assigned"
    tags: list[str] = Field(default_factory=list, max_length=30)
    language: str = Field(default="unknown", max_length=80)
    sentiment_kind: str | None = Field(default=None, pattern="^(news|public|official)$")
    social: SocialMetadata | None = None
    news: NewsMetadata | None = None
    aircraft_track_deg: float | None = Field(default=None, ge=0, lt=360, allow_inf_nan=False)
    aircraft_callsign: str = Field(default="", max_length=20)
    aircraft_category: int | None = Field(default=None, ge=0, le=17)
    aircraft: AircraftMetadata | None = None
    threat: ThreatMetadata | None = None
    raw: dict = Field(default_factory=dict)

    @field_validator("source_url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        from urllib.parse import urlsplit

        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Source URL must be an HTTP(S) reference without credentials")
        return value

    @field_validator("published_at", "occurred_at")
    @classmethod
    def aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Timestamp requires a timezone")
        return value.astimezone(timezone.utc) if value else None

    @model_validator(mode="after")
    def coordinates(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Coordinates must be a pair")
        if self.latitude is None:
            self.location_precision = "unknown"
        if any(len(tag) > 100 for tag in self.tags):
            raise ValueError("Tag exceeds 100 characters")
        if self.social:
            if self.social.content_type == "video":
                if self.sentiment_kind != "news":
                    raise ValueError("Channel upload wording belongs in the news dataset")
            elif self.category != Category.sentiment or self.sentiment_kind != "public":
                raise ValueError("Social discussions require their own public sentiment category")
            for relation in self.social.relations:
                self.safe_url(relation.target_url)
        return self


class Filters(BaseModel):
    categories: list[Category] = Field(default_factory=list)
    aircraft_categories: list[Literal[4, 5]] = Field(default_factory=list, max_length=2)
    q: str = Field(default="", max_length=200)
    country: str | None = Field(default=None, pattern="^[A-Z]{2}$")
    start: datetime | None = None
    end: datetime | None = None
    bbox: tuple[float, float, float, float] | None = None
    time_basis: str = Field(default="event", pattern="^(event|published|ingested)$")

    @model_validator(mode="after")
    def valid_range(self):
        for field in ("start", "end"):
            value = getattr(self, field)
            if value:
                if not value.tzinfo:
                    raise ValueError("Filter dates require timezone")
                setattr(self, field, value.astimezone(timezone.utc))
        if self.start and self.end and self.start > self.end:
            raise ValueError("Start must precede end")
        if self.bbox:
            west, south, east, north = self.bbox
            if not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south <= north <= 90):
                raise ValueError("Invalid bounding box")
        return self


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=1000)
    event_ids: list[str] = Field(default_factory=list, max_length=30)
    filters: Filters = Field(default_factory=Filters)

    @field_validator("event_ids")
    @classmethod
    def ids(cls, values: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[a-f0-9]{32}", value) for value in values):
            raise ValueError("Invalid event ID")
        return sorted(set(values))


class EvidenceReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confidence: Confidence
    basis: str = Field(min_length=30, max_length=2000)
    report_ids: list[str] = Field(min_length=1, max_length=20)
    independent_sources_confirmed: bool = False
    contradiction_confirmed: bool = False

    @field_validator("report_ids")
    @classmethod
    def valid_report_ids(cls, values):
        if any(not re.fullmatch(r"[a-f0-9]{32}", value) for value in values):
            raise ValueError("Invalid report ID")
        return sorted(set(values))


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    report_id: str


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=1500)
    kind: str = Field(pattern="^(sourced_fact|interpretation|contradiction)$")
    citations: list[Citation] = Field(min_length=1, max_length=10)


class AnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claims: list[Claim] = Field(min_length=1, max_length=20)
    limitations: list[str] = Field(min_length=1, max_length=10)

    @field_validator("limitations")
    @classmethod
    def limit_strings(cls, values):
        if any(len(value) > 1000 for value in values):
            raise ValueError("Limitation exceeds bound")
        return values
