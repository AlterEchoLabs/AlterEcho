"""Response models for analogue-method-v1.0 (/api/v3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field

ScientificStatus = Literal["real_processed", "real_context_only", "planned", "not_assessed", "unavailable", "failed_quality_gate"]

FamilyId = Literal["terrain", "geology", "temperature", "water_ice", "surface_processes", "subsurface_habitability", "field_test_suitability"]
ProfileIdV3 = Literal["terrain_analogy", "balanced_science", "rover_mobility", "biosignature_fieldwork", "mars_base_field_testing"]
Status = Literal["measured_comparable", "measured_context_only", "source_available_unprocessed", "missing_earth", "missing_planetary",
                 "incompatible", "review_pending", "excluded"]


class WindowStats(BaseModel):
    median: float | None
    p90: float | None
    coverage: float
    valid_cells: int


class FeatureRecord(BaseModel):
    feature: str
    label: str
    units: str
    role: Literal["scored", "diagnostic"]
    redundant_with: str | None = None
    measures: str
    eligible: bool
    reason: str
    distance: float | None = Field(None, description="d_k: W1 in the feature's units")
    tau: float | None = None
    delta: float | None = Field(None, description="resolution floor in the feature's units")
    d_over_tau: float | None = None
    similarity: float | None = Field(None, description="s_k in [0, 1]")
    weight: float = Field(0.0, description="a_k|g inside the family")
    contribution: float | None = Field(None, description="index points contributed: 100 * share * a_k * s_k")
    resolvable: bool | None = Field(None, description="True when d_k exceeds the resolution floor")
    earth: WindowStats | None = None
    planet: WindowStats | None = None


class FamilyRecord(BaseModel):
    family: FamilyId
    label: str
    weight: float = Field(description="w_g: planned profile weight")
    eligible: bool = Field(description="I_g")
    status: Status
    reason: str
    score: float | None = Field(None, description="S_g in [0, 1]")
    task_critical: bool
    features: list[FeatureRecord] = []
    context: dict[str, Any] | None = None

    @computed_field
    @property
    def scientific_status(self) -> ScientificStatus:
        if self.eligible:
            return "real_processed"
        if self.status == "measured_context_only":
            return "real_context_only"
        if self.status in {"incompatible", "excluded"}:
            return "failed_quality_gate"
        if self.status == "source_available_unprocessed":
            return "planned"
        if self.status in {"missing_earth", "missing_planetary"}:
            return "unavailable"
        return "not_assessed"


class Scenario(BaseModel):
    id: str
    kind: Literal["nominal", "placement", "reference_placement", "dem", "scale", "tolerance", "weights"]
    label: str
    index: float | None
    rank: int | None = None


class SensitivityV3(BaseModel):
    scenarios: list[Scenario]
    index_range: list[float] | None = None
    rank_range: list[int] | None = None
    tie_group: int | None = None
    notice: str


class SimpleResult(BaseModel):
    conclusion: str
    measured: list[str]
    coverage_text: str
    validation_status: str
    strength: str | None
    mismatch: str | None
    limitation: str
    show_index: bool
    index_label: str | None
    background_text: str | None = None
    standing_text: str | None = None
    class_label: str | None = None
    verdict: str | None = None


class Standing(BaseModel):
    """Where a candidate sits among the unselected ("ordinary") Earth land windows scored against the same reference."""
    closer_than: int = Field(..., description="Ordinary windows whose terrain index is strictly lower than this candidate's")
    as_close_or_closer: int = Field(..., description="Ordinary windows whose terrain index is at least this candidate's")
    of: int = Field(..., description="Ordinary windows scored against this reference")
    statement: str


class ClassGroup(BaseModel):
    """Candidates that share a terrain class against the reference, listed together."""
    terrain_class: Literal["same", "partial", "different"]
    label: str
    site_ids: list[str]
    order_resolved: bool
    note: str


class CandidateV3(BaseModel):
    site_id: str
    site_name: str
    state: Literal["ranked", "partial", "not_assessed", "excluded", "not_measured"]
    rank: int | None = None
    observed_index: float | None = None
    evidence_coverage: float
    resolution: Literal["unresolved_from_reference", "resolved", "not_applicable"]
    critical_gates: dict[str, bool]
    families: list[FamilyRecord]
    sensitivity: SensitivityV3 | None = None
    eligibility_key: str | None = None
    simple: SimpleResult
    exclusion: dict[str, Any] | None = None
    literature_context: dict[str, Any] | None = None
    data_roles: list[str]
    background_share: float | None = Field(None, description="Share of unselected Earth windows whose terrain index is at least this candidate's")
    standing: Standing | None = None
    terrain_class: Literal["same", "partial", "different"] | None = Field(
        None, description="same: every scored feature differs from the reference by less than its tolerance; different: every one by more; partial: mixed")

    @computed_field
    @property
    def scientific_status(self) -> ScientificStatus:
        if self.state == "excluded":
            return "failed_quality_gate"
        if self.observed_index is not None:
            return "real_processed"
        if self.state == "not_measured":
            return "unavailable"
        if any(f.eligible or f.status == "measured_context_only" for f in self.families):
            return "real_context_only"
        return "not_assessed"


class ToleranceRecord(BaseModel):
    feature: str
    units: str
    role: Literal["scored", "diagnostic"]
    tau: float
    tau_by_scale: dict[str, float]
    leave_one_tile_out: list[float]
    delta: float
    delta_placement: float
    delta_dem: float | None
    noise_condition_passed: bool
    redundant_with: str | None = None


class ProfileV3(BaseModel):
    id: ProfileIdV3
    label: str
    question: str
    rankable: bool
    weights: dict[str, float]
    task_critical: list[str]
    permitted_conclusion: str
    scope_line: str
    not_assessed: list[str]


class CompareV3(BaseModel):
    method_version: str
    terrain_method: str
    status: str
    review_status: str
    comparison_definition: str
    reference_site_id: str
    reference_name: str
    reference_aoi_id: str
    reference_body: Literal["mars", "moon"]
    profile: ProfileV3
    profile_state: Literal["ranked", "partial", "not_assessed"]
    profile_state_reason: str
    headline: str
    evidence_coverage: float
    primary_scale_m: int
    tolerances: list[ToleranceRecord]
    base_rate: dict[str, Any] | None
    tie_groups: list[list[str]]
    class_groups: list[ClassGroup] = Field(default_factory=list)
    background_scores: list[float] = Field(default_factory=list, description="Terrain index of every ordinary Earth window against this reference, ascending")
    ordering_note: str
    results: list[CandidateV3]
    physical_limits: list[str]
    formulas: dict[str, str]
    formulas_tex: dict[str, str] = Field(default_factory=dict)
    parameters: dict[str, str]
    validation_status: str
    notice: str
    generated_at: datetime
    discrimination: dict[str, Any] | None = None
    resolution_floor: dict[str, Any] | None = None


class DistributionPair(BaseModel):
    feature: str
    units: str
    u: list[float]
    earth: list[float]
    planet: list[float]


class ResultDetail(BaseModel):
    comparison: dict[str, Any]
    candidate: CandidateV3
    distributions: list[DistributionPair]
    earth_window: dict[str, Any]
    reference_window: dict[str, Any]
    sources: list[dict[str, Any]]
    calibration: dict[str, Any]
    reproducibility: dict[str, Any]


class DataRole(BaseModel):
    id: str
    label: str
    role: Literal["scored_input", "uncertainty_input", "quality_input", "display_context", "context_measurement", "literature_context"]
    body: str
    product: str
    registry_id: str | None
    measures: str
    why: dict[str, str]
    native_resolution: str
    analysis_resolution: str
    dates: str
    footprint: str
    used_in: list[str]
    cannot_establish: list[str]
    source_url: str | None
    doi: str | None = None


class ExplorerWindow(BaseModel):
    site_id: str
    name: str
    center: list[float]
    aoi_corners: list[list[float]] = Field(description="Exact analysis-grid corners [lon, lat]: top-left, top-right, bottom-right, bottom-left")
    imagery: dict[str, Any] | None
    hillshade: dict[str, Any] | None
    slope: dict[str, Any] | None
    recent: dict[str, Any] | None
    max_native_zoom: float
    notes: list[str]
