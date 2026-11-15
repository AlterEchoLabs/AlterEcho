"""Typed evidence contract for the analog-evidence-v1 model (mirrored in frontend/lib/evidence.ts)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.ids import SITE_ID_PATTERN

DimensionId = Literal["terrain", "temperature", "geology", "water_ice", "surface_processes", "subsurface_habitability"]
EvidenceStatus = Literal["measured", "proxy", "context_only", "missing", "not_comparable"]
EvidenceQuality = Literal["moderate", "limited", "none"]
ProfileId = Literal["balanced_science", "rover_mobility", "biosignature_fieldwork", "mars_base_field_testing"]


class SourceCitation(BaseModel):
    id: str
    title: str
    url: str


class MetricEvidence(BaseModel):
    """One measured quantity, with everything needed to judge whether it is comparable."""

    metric_id: str
    label: str
    value: float | None
    units: str
    product_id: str
    source_url: str
    native_resolution: str
    analysis_resolution: str
    observation_period: str
    aoi_overlap: str
    valid_coverage: float | None = Field(default=None, ge=0, le=1)
    processing_version: str
    quality_flags: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class DimensionEvidence(BaseModel):
    dimension: DimensionId
    label: str
    status: EvidenceStatus
    quality: EvidenceQuality
    reason: str
    metrics: list[MetricEvidence] = Field(default_factory=list)
    sources: list[SourceCitation] = Field(default_factory=list)


class SiteEvidence(BaseModel):
    site_id: str
    site_name: str
    body: Literal["earth", "mars", "moon"]
    dimensions: list[DimensionEvidence]
    operational: dict | None = None


class FeatureComparison(BaseModel):
    dimension: DimensionId
    feature: str
    label: str
    reference_value: float | None
    candidate_value: float | None
    difference: float | None
    units: str
    similarity: float = Field(ge=0, le=1)
    weight_in_dimension: float


class DimensionScore(BaseModel):
    dimension: DimensionId
    label: str
    profile_weight: float
    status: EvidenceStatus
    quality: EvidenceQuality
    similarity: float | None = Field(default=None, ge=0, le=1)
    used_in_score: bool
    reason: str
    features: list[FeatureComparison] = Field(default_factory=list)


class Factor(BaseModel):
    kind: Literal["helped", "hurt", "gap"]
    dimension: DimensionId
    text: str
    short_label: str = Field(description="Few-word name of the feature or dimension, for compact lists")
    weight_share: float


class TerrainBaseline(BaseModel):
    method: str
    index: float
    rank: int | None


class SensitivityResult(BaseModel):
    tested_configurations: int
    index_range: list[float]
    rank_range: list[int] | None
    notice: str


class CandidateEvidenceResult(BaseModel):
    site_id: str
    site_name: str
    rank: int | None
    ranking_status: Literal["ranked", "insufficient_evidence"]
    index: float | None = Field(description="Analog evidence index out of 100 on the common basis. Not a probability or percentage of identity.")
    backed_weight_fraction: float = Field(ge=0, le=1, description="Share of the profile weight backed by comparable measured evidence")
    scoring_basis: list[DimensionId]
    evidence_quality: EvidenceQuality
    dimensions: list[DimensionScore]
    factors: list[Factor]
    terrain_baseline: TerrainBaseline
    sensitivity: SensitivityResult | None
    explanation: str
    not_assessed: list[str]


class ProfileSummary(BaseModel):
    id: ProfileId
    label: str
    purpose: str
    weights: dict[str, float]
    required_dimensions: list[DimensionId]
    min_backed_weight_fraction: float
    review_status: str


class EvidenceCompareRequest(BaseModel):
    reference_site_id: str = Field(default="mars-jezero", pattern=SITE_ID_PATTERN, max_length=64)
    candidate_site_ids: list[str] = Field(min_length=1, max_length=20)
    profile_id: ProfileId = "balanced_science"

    @field_validator("candidate_site_ids")
    @classmethod
    def valid_candidates(cls, value: list[str]) -> list[str]:
        import re

        if len(value) != len(set(value)):
            raise ValueError("candidate_site_ids must not contain duplicates")
        if any(not isinstance(item, str) or len(item) > 64 or not re.fullmatch(SITE_ID_PATTERN, item) for item in value):
            raise ValueError("candidate_site_ids must be catalog identifiers")
        return value


class EvidenceCompareResponse(BaseModel):
    model_version: str
    review_status: str
    reference_site_id: str
    profile: ProfileSummary
    common_basis: list[DimensionId]
    common_basis_weight_fraction: float
    ranking_status: Literal["ranked", "insufficient_evidence"]
    ordering_note: str
    results: list[CandidateEvidenceResult]
    generated_at: datetime
    mode: Literal["prepared_artifacts"] = "prepared_artifacts"
    notice: str
