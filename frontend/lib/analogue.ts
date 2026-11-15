/** analogue-method-v1.0 (/api/v3) response types. Mirrors backend/app/models/analogue_v1.py. */

export type ProfileIdV3 = "terrain_analogy" | "balanced_science" | "rover_mobility" | "biosignature_fieldwork" | "mars_base_field_testing";
export type FamilyId = "terrain" | "geology" | "temperature" | "water_ice" | "surface_processes" | "subsurface_habitability" | "field_test_suitability";
export type FamilyStatus = "measured_comparable" | "measured_context_only" | "source_available_unprocessed" | "missing_earth" | "missing_planetary" | "incompatible" | "review_pending" | "excluded";
export type CandidateState = "ranked" | "partial" | "not_assessed" | "excluded" | "not_measured";
export type ProfileStateV3 = "ranked" | "partial" | "not_assessed";
export type ViewMode = "simple" | "full";

export interface WindowStats { median: number | null; p90: number | null; coverage: number; valid_cells: number }

export interface FeatureRecord {
  feature: string; label: string; units: string; role: "scored" | "diagnostic"; redundant_with: string | null; measures: string;
  eligible: boolean; reason: string; distance: number | null; tau: number | null; delta: number | null; d_over_tau: number | null;
  similarity: number | null; weight: number; contribution: number | null; resolvable: boolean | null; earth: WindowStats | null; planet: WindowStats | null;
}

export interface FamilyRecord {
  scientific_status?: "real_processed" | "real_context_only" | "planned" | "not_assessed" | "unavailable" | "failed_quality_gate";
  family: FamilyId; label: string; weight: number; eligible: boolean; status: FamilyStatus; reason: string; score: number | null;
  task_critical: boolean; features: FeatureRecord[]; context: Record<string, unknown> | null;
}

export interface Scenario { id: string; kind: "nominal" | "placement" | "reference_placement" | "dem" | "scale" | "tolerance" | "weights"; label: string; index: number | null; rank: number | null }
export interface SensitivityV3 { scenarios: Scenario[]; index_range: [number, number] | null; rank_range: [number, number] | null; tie_group: number | null; notice: string }

export interface SimpleResult {
  conclusion: string; measured: string[]; coverage_text: string; validation_status: string; strength: string | null; mismatch: string | null;
  limitation: string; show_index: boolean; index_label: string | null; background_text?: string | null;
}

export interface Citation { id: string; title: string; url: string }

export interface CandidateV3 {
  scientific_status?: "real_processed" | "real_context_only" | "planned" | "not_assessed" | "unavailable" | "failed_quality_gate";
  site_id: string; site_name: string; state: CandidateState; rank: number | null; observed_index: number | null; evidence_coverage: number;
  resolution: "unresolved_from_reference" | "resolved" | "not_applicable"; critical_gates: Record<string, boolean>; families: FamilyRecord[];
  sensitivity: SensitivityV3 | null; eligibility_key: string | null; simple: SimpleResult;
  exclusion: { reason: string; replacement: string; replacement_name: string | null } | null;
  literature_context: { summary?: string; scope: string; sources: Citation[]; [key: string]: unknown } | null; data_roles: string[];
  background_share?: number | null;
}

export interface ToleranceRecord {
  feature: string; units: string; role: "scored" | "diagnostic"; tau: number; tau_by_scale: Record<string, number>; leave_one_tile_out: [number, number];
  delta: number; delta_placement: number; delta_dem: number | null; noise_condition_passed: boolean; redundant_with: string | null;
}

export interface ProfileV3 {
  id: ProfileIdV3; label: string; question: string; rankable: boolean; weights: Record<string, number>; task_critical: string[];
  permitted_conclusion: string; scope_line: string; not_assessed: string[];
}

export interface BaseRate { count: number; median_index: number; p10?: number; p90?: number; share_at_or_above: Record<string, number> }
export interface FloorRecord { placement: number; dem_product: number; combined: number; placement_source?: string; noise_condition_passed: boolean }
export interface Discrimination {
  background: BaseRate | null; single_feature: Record<string, Record<string, number>>; alternative_tolerances: Record<string, Record<string, number>>;
  leave_one_region_out_tau: Record<string, [number, number]>; top_five_order_stable_across_regions: boolean | null;
  population: { windows: number; regions: Record<string, number>; caveat: string } | null; notice: string; interpretation: string;
}
export interface ReferenceV3 {
  id: string; name: string; body: "mars" | "moon"; region: string; center: [number, number]; width_m: number; description: string; characteristics: string[];
  limitations: string[]; selection_rationale: string; context: string | null;
  dem: { product: string; item: string | null; doi: string | null; provider: string; source_page: string; native_resolution: number[] | string | null; sha256: string | null; licence: string | null; intersection_error: { median_m: number; p95_m: number } | null };
  imagery: { url: string; product_id: string | null; resolution_m: number | null; attribution: string; source_url: string | null; published: string | null } | null;
  hillshade_url: string; slope_url: string; slope_median_60m: number; relative_elevation_p10_p90_60m: [number, number];
  resolution_floor: Record<string, FloorRecord>; scorable: boolean; scorable_reason: string | null;
}

export interface CompareV3 {
  method_version: string; terrain_method: string; status: string; review_status: string; comparison_definition: string;
  reference_site_id: string; reference_name: string; reference_aoi_id: string; reference_body: "mars" | "moon";
  profile: ProfileV3; profile_state: ProfileStateV3; profile_state_reason: string; headline: string; evidence_coverage: number; primary_scale_m: number;
  tolerances: ToleranceRecord[]; base_rate: BaseRate | null; tie_groups: string[][]; ordering_note: string; results: CandidateV3[];
  physical_limits: string[]; formulas: Record<string, string>; parameters: Record<string, string>; validation_status: string; notice: string; generated_at: string;
  discrimination?: Discrimination | null; resolution_floor?: Record<string, FloorRecord> | null;
}

export interface DistributionPair { feature: string; units: string; u: number[]; earth: number[]; planet: number[] }

export interface WindowRecord {
  site_id: string; name: string; body: string; aoi_id: string; center: [number, number]; width_m: number; height_m: number; selection_rationale?: string;
  source_id?: string; source_file?: string; source_sha256?: string; exclusion?: Record<string, unknown> | null;
  coverage_60m?: Record<string, number>; excluded_fraction_60m?: number;
  dem?: { product: string; version: string; doi: string | null; provider: string; native_resolution: number[] | null; native_crs: string; access_date: string | null; citation: string } | null;
}

export interface ResultDetail {
  comparison: Omit<CompareV3, "results">; candidate: CandidateV3; distributions: DistributionPair[]; earth_window: WindowRecord; reference_window: WindowRecord;
  sources: { role: string; label: string; product: string; url: string | null }[]; calibration: Record<string, unknown>; reproducibility: Record<string, unknown>;
}

export interface DataRole {
  id: string; label: string; role: "scored_input" | "uncertainty_input" | "quality_input" | "display_context" | "context_measurement" | "literature_context";
  body: string; product: string; registry_id: string | null; measures: string; why: Record<string, string>; native_resolution: string; analysis_resolution: string;
  dates: string; footprint: string; used_in: string[]; cannot_establish: string[]; source_url: string | null; doi?: string | null;
}

export interface ExplorerOverlay { url: string; corners: [number, number][]; resolution_m: number; [key: string]: unknown }
export interface ExplorerWindow {
  site_id: string; name: string; center: [number, number]; aoi_corners: [number, number][];
  imagery: (ExplorerOverlay & { product_id: string; acquired: string | null; attribution: string; source_url: string | null }) | null;
  hillshade: (ExplorerOverlay & { source: string; light: string }) | null; slope: (ExplorerOverlay & { ramp: string }) | null;
  recent: { tile_url: string; resolution_m: number; observed: string | null; attribution: string; product_id: string } | null;
  max_native_zoom: number; notes: string[];
}

export const PROFILE_IDS_V3: ProfileIdV3[] = ["terrain_analogy", "balanced_science", "rover_mobility", "biosignature_fieldwork", "mars_base_field_testing"];

export const STATE_TEXT: Record<CandidateState, string> = {
  ranked: "Ranked", partial: "Partial evidence", not_assessed: "Not assessed", excluded: "Excluded", not_measured: "Not measured",
};

export const PROFILE_STATE_TEXT: Record<ProfileStateV3, string> = {
  ranked: "Ranked on terrain", partial: "Partial evidence · not ranked", not_assessed: "Not assessed",
};

export const ROLE_TEXT: Record<DataRole["role"], string> = {
  scored_input: "Scored input", uncertainty_input: "Uncertainty check", quality_input: "Quality mask", display_context: "Display only",
  context_measurement: "Measured · context only", literature_context: "Literature context",
};

export const STATUS_TEXT: Record<FamilyStatus, string> = {
  measured_comparable: "Measured · comparable", measured_context_only: "Measured · context only", source_available_unprocessed: "Source exists · not processed",
  missing_earth: "Missing on Earth", missing_planetary: "Missing on the reference", incompatible: "Incompatible", review_pending: "Review pending", excluded: "Excluded",
};
