// Mirrors backend/app/models/evidence.py (analog-evidence-v1). Keep the two in sync;
// e2e/fixtures/evidence-compare.json is type-checked against these definitions.

export type DimensionId = "terrain" | "temperature" | "geology" | "water_ice" | "surface_processes" | "subsurface_habitability";
export type EvidenceStatus = "measured" | "proxy" | "context_only" | "missing" | "not_comparable";
export type EvidenceQuality = "moderate" | "limited" | "none";
export type ProfileId = "balanced_science" | "rover_mobility" | "biosignature_fieldwork" | "mars_base_field_testing";

export interface SourceCitation { id: string; title: string; url: string }

export interface MetricEvidence {
  metric_id: string; label: string; value: number | null; units: string; product_id: string; source_url: string;
  native_resolution: string; analysis_resolution: string; observation_period: string; aoi_overlap: string;
  valid_coverage: number | null; processing_version: string; quality_flags: string[]; limitations: string[];
}

export interface DimensionEvidence {
  dimension: DimensionId; label: string; status: EvidenceStatus; quality: EvidenceQuality; reason: string;
  metrics: MetricEvidence[]; sources: SourceCitation[];
}

export interface OperationalContext {
  research_relevance: string; aoi_specific: boolean; source_ids: string[]; sources: SourceCitation[]; not_assessed: string[];
}

export interface SiteEvidence {
  site_id: string; site_name: string; body: "earth" | "mars" | "moon"; dimensions: DimensionEvidence[]; operational: OperationalContext | null;
}

export interface FeatureComparison {
  dimension: DimensionId; feature: string; label: string; reference_value: number | null; candidate_value: number | null;
  difference: number | null; units: string; similarity: number; weight_in_dimension: number;
}

export interface DimensionScore {
  dimension: DimensionId; label: string; profile_weight: number; status: EvidenceStatus; quality: EvidenceQuality;
  similarity: number | null; used_in_score: boolean; reason: string; features: FeatureComparison[];
}

export interface Factor { kind: "helped" | "hurt" | "gap"; dimension: DimensionId; text: string; short_label: string; weight_share: number }
export interface TerrainBaseline { method: string; index: number; rank: number | null }
export interface SensitivityResult { tested_configurations: number; index_range: [number, number]; rank_range: [number, number] | null; notice: string }

export interface CandidateEvidenceResult {
  site_id: string; site_name: string; rank: number | null; ranking_status: "ranked" | "insufficient_evidence";
  index: number | null; backed_weight_fraction: number; scoring_basis: DimensionId[]; evidence_quality: EvidenceQuality;
  dimensions: DimensionScore[]; factors: Factor[]; terrain_baseline: TerrainBaseline; sensitivity: SensitivityResult | null;
  explanation: string; not_assessed: string[];
}

export interface ProfileSummary {
  id: ProfileId; label: string; purpose: string; weights: Partial<Record<DimensionId, number>>;
  required_dimensions: DimensionId[]; min_backed_weight_fraction: number; review_status: string;
}

export interface EvidenceCompareResponse {
  model_version: string; review_status: string; reference_site_id: string; profile: ProfileSummary;
  common_basis: DimensionId[]; common_basis_weight_fraction: number; ranking_status: "ranked" | "insufficient_evidence";
  ordering_note: string; results: CandidateEvidenceResult[]; generated_at: string; mode: "prepared_artifacts"; notice: string;
}

export interface EvidenceModel {
  model_version: string; review_status: string; notice: string; default_profile: ProfileId;
  dimensions: Record<DimensionId, { label: string; question: string; scored_by: string | null }>;
  status_definitions: Record<EvidenceStatus, string>;
  quality_levels: Record<string, string>;
  thermal_comparison: { method_id: string; formula: string; rationale: string; features: Record<string, { label: string; tolerance_k: number; weight: number }> };
}

export const STATUS_LABEL: Record<EvidenceStatus, string> = {
  measured: "Measured",
  proxy: "Proxy",
  context_only: "Context only",
  missing: "Missing",
  not_comparable: "Not comparable",
};

// ---------------------------------------------------------------------------------------------
// analog-evidence-v2.0 (mirrors backend/app/models/evidence_v2.py)

export type DimensionV2 = "terrain" | "geology" | "temperature" | "water_ice" | "surface_processes" | "subsurface_habitability" | "field_test_suitability";
export type StatusV2 = "measured_comparable" | "measured_context_only" | "source_available_unprocessed" | "missing_earth" | "missing_planetary" | "incompatible" | "review_pending";
export type ProfileState = "ranked" | "experimental_partial" | "not_assessed";
export type ProfileIdV2 = "terrain_analogy" | "balanced_science" | "rover_mobility" | "biosignature_fieldwork" | "mars_base_field_testing";

export interface FamilyScore {
  family: string; label: string; units: string; tau: number; weight: number;
  w1_by_scale: Record<string, number>; index_by_scale: Record<string, number>; index: number;
  reference_stat: number | null; candidate_stat: number | null; stat_label: string;
}
export interface AuditCheck { check: string; required: boolean; passed: boolean; detail: string }
export interface ThermalAudit {
  decision: "measured_comparable" | "measured_context_only" | "missing"; checks: AuditCheck[]; summary: string;
  context_values: Record<string, { earth: number | null; planetary: number | null }>;
}
export interface DimensionRecord {
  dimension: DimensionV2; label: string; scorable: boolean; status: StatusV2; profile_weight: number; included: boolean;
  index: number | null; reason: string; earth_note: string | null; planetary_note: string | null;
  families: FamilyScore[]; thermal_audit: ThermalAudit | null; sources: SourceCitation[];
}
export interface Eligibility {
  reference_aoi_id: string; method_version: string; included_dimensions: DimensionV2[]; feature_definitions_sha256: string;
  resolution_policy: string; weights_sha256: string; dem_product: string; key: string;
}
export interface SensitivityV2 {
  method_index_range: [number, number] | null; method_rank_range: [number, number] | null; placement_index_range: [number, number] | null;
  dem_index: Record<string, number | null>; halo_effect_index: number | null; tie_group: number | null; notice: string;
}
export interface FieldEntry { value: string; note: string; sources?: SourceCitation[] }
export interface CandidateResultV2 {
  site_id: string; site_name: string; rank: number | null; state: ProfileState | "not_rankable"; partial_index: number | null;
  evidence_coverage: number; included_dimensions: DimensionV2[]; missing_task_critical: DimensionV2[]; dimensions: DimensionRecord[];
  closest: string[]; furthest: string[]; historical_terrain_v3_index: number | null; sensitivity: SensitivityV2; eligibility: Eligibility | null;
  field_test: Record<string, FieldEntry>; research_context: { text: string; aoi_specific: boolean; sources: SourceCitation[] } | null;
  explanation: string; permitted_conclusion: string; unassessed: string[];
}
export interface ProfileV2 {
  id: ProfileIdV2; label: string; question: string; required_measurements: string[]; weights: Partial<Record<DimensionV2, number>>;
  task_critical: DimensionV2[]; allowed_missing: DimensionV2[]; ranking_conditions: string; permitted_conclusion: string; unassessed: string[]; review_status: string;
}
export interface CompareResponseV2 {
  model_version: string; terrain_method: string; review_status: string; reference_site_id: string; reference_aoi_id: string; reference_body: "mars" | "moon";
  profile: ProfileV2; profile_state: ProfileState; profile_state_reason: string; included_dimensions: DimensionV2[]; evidence_coverage: number;
  ordering_note: string; tie_groups: string[][]; ranking_sensitive: boolean; results: CandidateResultV2[]; physical_limits: string[];
  evaluation: {
    base_rate_share_at_or_above: Record<string, number> | null; base_rate_windows: number | null; base_rate_median: number | null;
    reference_stability: Record<string, number | null> | null;
    redundancy: { families: string[]; spearman_w1_60m: number[][]; n_windows: number; interpretation: string } | null;
    mola_vs_ctx: Record<string, unknown> | null;
  };
  generated_at: string; mode: "prepared_artifacts"; notice: string;
}

export const STATUS_V2_LABEL: Record<StatusV2, string> = {
  measured_comparable: "Measured · comparable",
  measured_context_only: "Measured · context only",
  source_available_unprocessed: "Source available · unprocessed",
  missing_earth: "Missing (Earth)",
  missing_planetary: "Missing (reference)",
  incompatible: "Incompatible",
  review_pending: "Review pending",
};

export const STATE_LABEL: Record<ProfileState | "not_rankable", string> = {
  ranked: "Ranked",
  experimental_partial: "Experimental partial comparison",
  not_assessed: "Not assessed",
  not_rankable: "Not measured",
};
