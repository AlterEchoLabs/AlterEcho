"""Typed contract for analog-evidence-v2.0 (mirrored in frontend/lib/evidence.ts)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.ids import SITE_ID_PATTERN

DimensionV2 = Literal["terrain", "geology", "temperature", "water_ice", "surface_processes", "subsurface_habitability", "field_test_suitability"]
StatusV2 = Literal["measured_comparable", "measured_context_only", "source_available_unprocessed", "missing_earth", "missing_planetary", "incompatible", "review_pending"]
ProfileState = Literal["ranked", "experimental_partial", "not_assessed"]
ProfileIdV2 = Literal["terrain_analogy", "balanced_science", "rover_mobility", "biosignature_fieldwork", "mars_base_field_testing"]


class Citation(BaseModel):
    id: str
    title: str
    url: str


class FamilyScore(BaseModel):
    family: str
    label: str
    units: str
    tau: float = Field(gt=0)
    weight: float
    w1_by_scale: dict[str, float]
    index_by_scale: dict[str, float]
    index: float = Field(ge=0, le=100)
    reference_stat: float | None
    candidate_stat: float | None
    stat_label: str


class AuditCheck(BaseModel):
    check: str
    required: bool
    passed: bool
    detail: str


class ThermalAudit(BaseModel):
    decision: Literal["measured_comparable", "measured_context_only", "missing"]
    checks: list[AuditCheck]
    summary: str
    context_values: dict[str, Any] = Field(default_factory=dict)


class DimensionRecord(BaseModel):
    dimension: DimensionV2
    label: str
    scorable: bool
    status: StatusV2
    profile_weight: float
    included: bool
    index: float | None = Field(default=None, ge=0, le=100)
    reason: str
    earth_note: str | None = None
    planetary_note: str | None = None
    families: list[FamilyScore] = Field(default_factory=list)
    thermal_audit: ThermalAudit | None = None
    sources: list[Citation] = Field(default_factory=list)


class Eligibility(BaseModel):
    reference_aoi_id: str
    method_version: str
    included_dimensions: list[DimensionV2]
    feature_definitions_sha256: str
    resolution_policy: str
    weights_sha256: str
    dem_product: str
    key: str


class Sensitivity(BaseModel):
    method_index_range: list[float] | None = None
    method_rank_range: list[int] | None = None
    placement_index_range: list[float] | None = None
    dem_index: dict[str, float | None] = Field(default_factory=dict)
    halo_effect_index: float | None = None
    tie_group: int | None = None
    notice: str = "Deterministic configuration, placement and DEM checks. Not a statistical confidence interval."


class CandidateResult(BaseModel):
    site_id: str
    site_name: str
    rank: int | None
    state: Literal["ranked", "experimental_partial", "not_assessed", "not_rankable"]
    partial_index: float | None = Field(default=None, ge=0, le=100, description="Partial index on the included dimensions only")
    evidence_coverage: float = Field(ge=0, le=1, description="Sum of the profile weights of the included dimensions")
    included_dimensions: list[DimensionV2]
    missing_task_critical: list[DimensionV2]
    dimensions: list[DimensionRecord]
    closest: list[str]
    furthest: list[str]
    historical_terrain_v3_index: float | None
    sensitivity: Sensitivity
    eligibility: Eligibility | None
    field_test: dict[str, Any]
    research_context: dict[str, Any] | None
    explanation: str
    permitted_conclusion: str
    unassessed: list[str]


class ProfileV2(BaseModel):
    id: ProfileIdV2
    label: str
    question: str
    required_measurements: list[str]
    weights: dict[str, float]
    task_critical: list[DimensionV2]
    allowed_missing: list[DimensionV2]
    ranking_conditions: str
    permitted_conclusion: str
    unassessed: list[str]
    review_status: str


class CompareRequestV2(BaseModel):
    reference_site_id: str = Field(default="mars-jezero", pattern=SITE_ID_PATTERN, max_length=64)
    candidate_site_ids: list[str] | None = Field(default=None, max_length=30)
    profile_id: ProfileIdV2 = "terrain_analogy"

    @field_validator("candidate_site_ids")
    @classmethod
    def valid_ids(cls, value: list[str] | None) -> list[str] | None:
        import re
        if value is None:
            return value
        if len(value) != len(set(value)) or any(not re.fullmatch(SITE_ID_PATTERN, item) for item in value):
            raise ValueError("candidate_site_ids must be unique catalog identifiers")
        return value


class CompareResponseV2(BaseModel):
    model_version: str
    terrain_method: str
    review_status: str
    reference_site_id: str
    reference_aoi_id: str
    reference_body: Literal["mars", "moon"]
    profile: ProfileV2
    profile_state: ProfileState
    profile_state_reason: str
    included_dimensions: list[DimensionV2]
    evidence_coverage: float
    ordering_note: str
    tie_groups: list[list[str]]
    ranking_sensitive: bool
    results: list[CandidateResult]
    physical_limits: list[str]
    evaluation: dict[str, Any]
    generated_at: datetime
    mode: Literal["prepared_artifacts"] = "prepared_artifacts"
    notice: str
