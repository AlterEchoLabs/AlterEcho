"""Versioned portable source registry contract. Unknown metadata must be null."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str
    provider: str
    mission_instrument: str | None
    product_collection: str | None
    collection_version: str | None
    official_landing_page: str | None
    doi_or_pds_identifier: str | None
    discovery_endpoint: str | None
    body: str
    measured_variable: str | None
    native_resolution: str | list[float] | None
    analysis_resolution: str | None
    spatial_support: str | list[str] | None
    crs: str | None
    vertical_datum: str | None
    units: str | None
    observation_interval: str | None
    processing_level: str | None
    retrieval_date: str | None
    license: str | None
    authentication: str | None
    raw_filename: str | None
    byte_size: int | None = Field(ge=0)
    sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    processing_software: dict[str, Any] | None
    role: Literal["scored", "diagnostic", "quality-mask", "display-only", "context-only"]
    known_limitations: list[str]
    status: Literal["verified", "processing", "blocked", "planned", "rejected"]
    status_reason: str
    artifact: dict[str, Any] | None = None
    quality: dict[str, Any] | None = None
    files: list[dict[str, Any]] = []


class SourceRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["source-registry-v1"]
    audited_at: str
    verification_scope: str
    records: list[SourceRecord]
    sites: list[dict[str, Any]]
    imagery: list[dict[str, Any]]
    unknown_metadata_policy: str
    new_products_acquired: list[str]
    blocked_acquisitions: list[str]
    scientific_limitations: list[str]
