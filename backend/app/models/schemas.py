from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class DataStatus(str, Enum):
    real_processed = "real_processed"
    planned = "planned"
    # Retained for test-fixture and response backward compatibility only.
    demo_fixture = "demo_fixture"
    metadata_only = "metadata_only"
    unavailable = "unavailable"


class Body(str, Enum):
    earth = "earth"
    mars = "mars"
    moon = "moon"


class ProcessingStatus(str, Enum):
    not_processed = "not_processed"
    processed = "processed"
    integrity_checked = "integrity_checked"


class ScientificValidationStatus(str, Enum):
    not_reviewed = "not_reviewed"
    methodology_review_pending = "methodology_review_pending"
    research_reviewed = "research_reviewed"


class Planet(BaseModel):
    id: Body
    name: str
    description: str
    status: str
    supported_capabilities: list[str]
    default_view: dict[str, Any]


class SourceReference(BaseModel):
    id: str
    title: str
    url: str
    role: str


class Site(BaseModel):
    id: str
    name: str
    body: Body
    country_or_region: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    short_description: str
    analog_type: str
    relevant_characteristics: list[str]
    known_limitations: list[str]
    source_references: list[str]
    data_status: DataStatus
    available_metrics: list[str]
    thumbnail_url: str | None = None
    map_display: dict[str, Any]
    processing_status: ProcessingStatus = ProcessingStatus.not_processed
    scientific_validation_status: ScientificValidationStatus = ScientificValidationStatus.not_reviewed
    aoi_id: str | None = None
    source_id: str | None = None


class TerrainFeatureSummary(BaseModel):
    site_id: str
    slope_p50_deg: float | None = None
    slope_p90_deg: float | None = None
    local_relief_m: float | None = None
    roughness_index: float | None = None
    elevation_min_m: float | None = None
    elevation_max_m: float | None = None
    elevation_mean_m: float | None = None
    elevation_std_m: float | None = None
    elevation_p10_m: float | None = None
    elevation_p50_m: float | None = None
    elevation_p90_m: float | None = None
    slope_mean_deg: float | None = None
    slope_max_deg: float | None = None
    local_relief_mean_m: float | None = None
    local_relief_p50_m: float | None = None
    local_relief_p90_m: float | None = None
    roughness_mean: float | None = None
    roughness_p90: float | None = None
    valid_coverage_fraction: float = Field(ge=0, le=1)
    resolution_m: float | None = Field(default=None, gt=0)
    projection: str | None = None
    calculation_metadata: dict[str, Any]
    data_source: str
    data_status: DataStatus
    aoi_id: str | None = None
    processing_run_id: str | None = None
    analysis_width_m: float | None = None
    analysis_height_m: float | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def real_data_requires_traceability(self):
        if self.data_status == DataStatus.real_processed:
            required = {"source_checksum", "aoi_id", "processing_run_id", "methodology_version"}
            missing = required - set(self.provenance)
            if missing:
                raise ValueError(f"real_processed requires provenance fields: {', '.join(sorted(missing))}")
        return self


class SourceManifest(BaseModel):
    source_id: str
    title: str
    planetary_body: str
    provider: str
    mission: str | None
    instrument: str | None
    product_name: str
    product_version: str | None
    source_page_url: str
    download_url: str | None
    doi: str | None
    access_date: str | None
    license_or_use_constraints: str | None
    native_resolution: str | list[float] | None
    native_crs: str | None
    native_bounds: list[float] | None
    native_nodata: float | None
    file_size: int | None
    filename: str
    sha256_checksum: str | None
    citation_text: str
    processing_status: str
    notes: str | None
    extracted_filename: str | None = None
    extracted_sha256_checksum: str | None = None
    aoi_id: str | None = None
    tiles: list[dict[str, Any]] = Field(default_factory=list)
    mosaic_filename: str | None = None
    mosaic_sha256_checksum: str | None = None


class AOIRecord(BaseModel):
    aoi_id: str
    site_id: str
    version: str
    planetary_body: str
    center_latitude: float
    center_longitude: float
    width_m: float = Field(gt=0)
    height_m: float = Field(gt=0)
    selection_rationale: str
    intended_analog_characteristics: list[str]
    known_limitations: list[str]
    creation_method: str
    source_references: list[str]
    geometry: dict[str, Any]
    planetary_target: str | None = None
    analogy_dimensions_not_covered: list[str] = Field(default_factory=list)
    representativeness: str | None = None
    known_selection_bias: str | None = None


class Compatibility(BaseModel):
    compatible: bool
    aoi_scale_match: bool
    resolution_match: bool
    methodology_match: bool
    reference_resolution_m: float | None
    candidate_resolution_m: float | None
    warnings: list[str] = Field(default_factory=list)


class ProcessingRun(BaseModel):
    processing_run_id: str
    timestamp: datetime
    site_id: str
    source_id: str
    source_checksum: str
    aoi_version: str
    methodology_version: str
    software_version: str
    native_resolution: list[float]
    target_resolution: float
    source_crs: str
    processing_crs: str
    resampling_method: str
    nodata_handling: str
    requested_analysis_window_m: list[float]
    actual_analysis_window_m: list[float]
    grid_dimensions: list[int]
    metric_configuration: dict[str, Any]
    output_summary: str
    output_checksum: str
    quality_passed: bool
    warnings: list[str]


class DiscoverRequest(BaseModel):
    reference_site_id: str = "mars-jezero"
    candidate_site_ids: list[str] = Field(min_length=1, max_length=20)
    weights: dict[str, float] | None = None
    methodology_version: str = "terrain-v3.0"

    @field_validator("candidate_site_ids")
    @classmethod
    def unique_candidates(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("candidate_site_ids must not contain duplicates")
        return value

    @field_validator("weights")
    @classmethod
    def valid_weights(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        if value is None:
            return value
        if any(weight < 0 for weight in value.values()):
            raise ValueError("weights cannot be negative")
        if not any(weight > 0 for weight in value.values()):
            raise ValueError("weights must contain a positive value")
        return value


class MetricComparison(BaseModel):
    metric: str
    reference_value: float
    candidate_value: float
    tolerance: float
    normalized_weight: float
    similarity: float = Field(ge=0, le=1)


class ComparisonResult(BaseModel):
    request_id: str
    reference_site: Site
    candidate_site: Site
    overall_similarity: float | None
    display_percentage: float | None
    rankability: str
    metric_similarities: list[MetricComparison]
    available_metrics: list[str]
    missing_metrics: list[str]
    explanation: str
    limitations: list[str]
    provenance: dict[str, Any]
    data_status: DataStatus
    methodology_version: str
    generated_at: datetime
    compatibility: Compatibility | None = None
    quality: dict[str, Any] = Field(default_factory=dict)
    ranking_scope: str = "preview_only"
    reference_data_status: DataStatus | None = None
    candidate_data_status: DataStatus | None = None
    comparison_classification: str = "preview"
    processing_run_ids: dict[str, str | None] = Field(default_factory=dict)


class DiscoverResponse(BaseModel):
    request_id: str
    reference_site_id: str
    results: list[ComparisonResult]
    methodology_version: str
    data_mode: str
    generated_at: datetime
    ranking_scope: str = "preview_only"
    real_results: list[ComparisonResult] = Field(default_factory=list)
    preview_results: list[ComparisonResult] = Field(default_factory=list)
    unrankable_results: list[ComparisonResult] = Field(default_factory=list)


class FeatureCoverage(BaseModel):
    valid_sample_count: int = Field(ge=0)
    total_expected_sample_count: int = Field(gt=0)
    coverage_fraction: float = Field(ge=0, le=1)
    nodata_propagation: str
    kernel_edge_exclusions: int = Field(ge=0)
    quality_flag: str


class DistributionSummary(BaseModel):
    feature: str
    bin_edges: list[float]
    normalized_counts: list[float]
    valid_sample_count: int = Field(ge=0)
    @model_validator(mode="after")
    def bins_match_counts(self):
        if len(self.bin_edges) != len(self.normalized_counts) + 1:
            raise ValueError("distribution bin_edges must contain one more value than normalized_counts")
        return self


class ScaleTerrainResult(BaseModel):
    resolution_m: float = Field(gt=0)
    metrics: dict[str, float | None]
    feature_coverage: dict[str, FeatureCoverage]
    distributions: dict[str, DistributionSummary]


class TerrainV3Artifact(BaseModel):
    site_id: str
    methodology_version: str = "terrain-v3.0"
    source_summary_methodology: str = "terrain-v2.0"
    core_aoi_id: str
    core_width_m: float
    core_height_m: float
    halo_width_m: float
    horizontal_units: str
    vertical_units: str
    vertical_datum: str | None
    nodata_definition: str
    resampling_method: str
    scales: dict[str, ScaleTerrainResult]
    core_valid_coverage: dict[str, float]
    halo_valid_coverage: dict[str, float]
    quality_status: str
    cross_validation_status: str
    provenance: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


class DatasetRecord(BaseModel):
    dataset_id: str
    provider: str
    product_name: str
    product_id: str | None
    collection: str | None
    version: str | None
    celestial_body: str
    scientific_dimension: str
    spatial_resolution: str | None
    temporal_coverage: str | None
    spatial_coverage: str | None
    authentication_requirement: str | None
    license_or_usage_notes: str | None
    doi: str | None
    official_landing_page: str
    api_endpoint: str | None
    local_status: str
    intended_project_use: str
    known_limitations: list[str]
    checksum: str | None = None
    last_checked_date: str | None = None


class ImageryRecord(BaseModel):
    imagery_id: str
    site_id: str
    body: Body
    mode: str
    provider: str
    collection: str | None
    product_id: str | None
    acquisition_datetime: datetime | None
    publication_datetime: datetime | None = None
    resolution_m: float | None
    cloud_cover_pct: float | None = Field(default=None, ge=0, le=100)
    processing_level: str | None
    bbox: list[float]
    aoi_id: str | None
    preview_url: str | None
    tile_url: str | None = None
    attribution: str
    official_source_url: str
    cache_status: str
    cache_date: datetime | None = None
    data_status: str
    limitations: list[str] = Field(default_factory=list)
    display_resolution_m: float | None = None
    aoi_coverage_fraction: float | None = Field(default=None, ge=0, le=1)
    source_checksum: str | None = None
    preview_checksum: str | None = None
    source_crs: str | None = None
    native_resolution: list[float] | None = None
    source_download_url: str | None = None

