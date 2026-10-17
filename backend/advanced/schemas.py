from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models import Report


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseInput(Input):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    status: Literal["open", "review", "closed", "deleted"] = "open"
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("tags")
    @classmethod
    def tag_lengths(cls, values):
        if any(len(v) > 100 for v in values):
            raise ValueError("Tags must be at most 100 characters")
        return values


class NoteInput(Input):
    text: str = Field(min_length=1, max_length=10000)


class EvidenceInput(Input):
    kind: Literal["record", "media", "geo", "document", "analysis", "change", "entity"]
    reference_id: str = Field(pattern="^[a-f0-9-]{32,36}$")


class DocumentInput(Input):
    title: str = Field(min_length=1, max_length=500)
    organization: str = Field(default="", max_length=200)
    jurisdiction: str | None = Field(default=None, pattern="^[A-Z]{2}$")
    source_id: str = Field(min_length=1, max_length=100)
    original_url: str = Field(max_length=2048)
    published_at: datetime | None = None
    version: str = Field(default="1", max_length=100)
    text: str = Field(default="", max_length=40000)
    license_classification: Literal["public_domain", "authorized", "restricted", "metadata_only"] = (
        "metadata_only"
    )
    entity_id: str | None = Field(default=None, pattern="^[a-f0-9]{32}$")

    @field_validator("original_url")
    @classmethod
    def url(cls, value):
        return Report.safe_url(value)

    @field_validator("published_at")
    @classmethod
    def timestamp(cls, value):
        return Report.aware(value)


class GeoInput(Input):
    title: str = Field(min_length=1, max_length=200)
    geojson: dict
    precision: Literal["exact", "approximate", "region", "country", "unresolved"] = "approximate"
    basis: str = Field(min_length=10, max_length=1000)
    source_url: str = Field(max_length=2048)
    acquired_at: datetime | None = None
    license_classification: Literal["public_domain", "authorized", "restricted", "metadata_only"]

    @field_validator("source_url")
    @classmethod
    def url(cls, value):
        return Report.safe_url(value)

    @field_validator("acquired_at")
    @classmethod
    def timestamp(cls, value):
        return Report.aware(value)


class MeasureInput(Input):
    operation: Literal["distance", "area"]
    coordinates: list[tuple[float, float]] = Field(min_length=2, max_length=1000)


class WatchInput(Input):
    url: str = Field(max_length=2048)
    title: str = Field(min_length=1, max_length=200)
    interval_seconds: int = Field(default=3600, ge=900, le=604800)
    permission_basis: str = Field(min_length=30, max_length=1000)


class WatchPatch(Input):
    enabled: bool | None = None
    interval_seconds: int | None = Field(default=None, ge=900, le=604800)


class SourcePatch(Input):
    enabled: bool
    permission_basis: str = Field(min_length=30, max_length=1000)


class SourcePermissionPatch(Input):
    display_class: Literal["public", "attribution", "restricted", "review_required"]
    commercial_use: Literal["cleared", "review_required", "blocked"]
    retention_allowed: bool = True
    export_allowed: bool = False
    derivative_allowed: bool = False
    basis: str = Field(min_length=30, max_length=1000)


class ResolveInput(Input):
    name: str = Field(min_length=1, max_length=200)
    type: Literal[
        "country",
        "organization",
        "institution",
        "location",
        "event",
        "document",
        "infrastructure",
        "threat_actor",
        "campaign",
        "malware",
        "tool",
        "technique",
    ]
    entity_id: str | None = Field(default=None, pattern="^[a-f0-9]{32}$")
    alias: str | None = Field(default=None, min_length=1, max_length=200)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)


class AnalyzeInput(Input):
    question: str = Field(min_length=3, max_length=1000)
    record_ids: list[str] = Field(min_length=1, max_length=20)


class CorrelationInput(Input):
    record_ids: list[str] = Field(min_length=1, max_length=50)
    weights: dict[Literal["time", "country", "topics"], float] = Field(
        default_factory=lambda: {"time": 0.4, "country": 0.3, "topics": 0.3}
    )

    @field_validator("weights")
    @classmethod
    def bounded(cls, values):
        if (
            set(values) != {"time", "country", "topics"}
            or any(not 0 <= v <= 1 for v in values.values())
            or abs(sum(values.values()) - 1) > 0.001
        ):
            raise ValueError("Weights must sum to one")
        return values


class EnrichInput(Input):
    indicator: str = Field(min_length=1, max_length=2048)
    provider_id: str = Field(default="local", max_length=100)


class ExternalInput(Input):
    provider_id: str = Field(max_length=100)
    query: str = Field(min_length=1, max_length=200)
    confirmed: bool = False


class VerifyInput(Input):
    step: str = Field(min_length=1, max_length=200)
    result: str = Field(min_length=10, max_length=4000)


class SavedSearch(Input):
    name: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=200)


class RelationshipInput(Input):
    from_id: str = Field(pattern="^[a-f0-9]{32}$")
    to_id: str = Field(pattern="^[a-f0-9]{32}$")
    type: Literal[
        "reported_link", "co_mentioned", "institutional", "documented_ownership", "analyst_hypothesis"
    ]
    status: Literal["reported", "inferred"]
    basis: str = Field(min_length=20, max_length=1000)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    @field_validator("valid_from", "valid_to")
    @classmethod
    def aware(cls, value):
        return Report.aware(value)
