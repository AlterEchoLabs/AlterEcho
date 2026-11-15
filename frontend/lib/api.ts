import type { CompareResponseV2, EvidenceCompareResponse, EvidenceModel, ProfileId, ProfileIdV2, ProfileSummary, ProfileV2, SiteEvidence } from "./evidence";
import type { CompareV3, DataRole, ExplorerWindow, ProfileIdV3, ProfileV3, ReferenceV3, ResultDetail, ContextV3 } from "./analogue";

export type DataStatus = "real_processed" | "planned" | "metadata_only" | "unavailable";
export type Body = "earth" | "mars" | "moon";

export interface Site {
  id: string; name: string; body: Body; country_or_region: string; latitude: number; longitude: number;
  short_description: string; analog_type: string; relevant_characteristics: string[]; known_limitations: string[];
  source_references: string[]; data_status: DataStatus; available_metrics: string[];
  processing_status: string; scientific_validation_status: string; aoi_id: string | null; source_id: string | null;
}

export interface HealthResponse {
  status: string; product_name: string; application_version: string; build_identifier: string; methodology_version: string;
  data_mode: string; data_counts: { real_processed_sites: number; planned_sites: number; metadata_only_sites: number; unavailable_sites: number; rankable_real_earth_candidates: number };
}

export interface AoiFeature {
  type: "Feature"; id?: string;
  properties: { aoi_id: string; site_id: string; planetary_body: string; width_m: number; height_m: number; center_latitude: number; center_longitude: number; selection_rationale: string; representativeness?: string; known_selection_bias?: string; [key: string]: unknown };
  geometry: { type: "Polygon"; coordinates: number[][][] };
}

export interface ImageryRecord {
  imagery_id: string; site_id: string; body: Body; mode: "reference" | "latest_observation" | "terrain"; provider: string;
  collection: string | null; product_id: string | null; acquisition_datetime: string | null; resolution_m: number | null;
  cloud_cover_pct: number | null; processing_level: string | null; bbox: number[]; aoi_id: string | null;
  preview_url: string | null; tile_url: string | null; attribution: string; official_source_url: string;
  cache_status: string; data_status: string; limitations: string[]; display_resolution_m: number | null;
  aoi_coverage_fraction: number | null; preview_checksum: string | null; source_crs: string | null;
  aoi_cloud_fraction?: number | null; aoi_snow_fraction?: number | null; aoi_valid_pixel_fraction?: number | null;
  aoi_statistics_method?: string | null; aoi_coverage_meaning?: string | null; registration?: Record<string, unknown> | null; publication_datetime?: string | null;
}

export interface LayerMeta { site_id: string; resolution_m: number; pixels: number; slope_ramp: string; slope_p50_deg: number; source_sha256: string }

export interface Preflight {
  center: { lat: number; lon: number }; geometry: AoiFeature["geometry"]; width_m: number; supported: boolean; reason: string | null;
  processing: { available: boolean; reason: string | null };
  dem: { product: string; native_resolution: string; analysis_scales_m: number[]; tiles: string[]; tiles_cached: string[]; credentials_available: boolean; requires_credentials: boolean };
  imagery: { product: string; authentication: string; note: string }; references: string[]; queue: { pending: number; max: number };
  limits: { per_client_per_hour: number; global_per_day: number }; status_label: string;
}

export interface ScreeningResult {
  label: string; inputs: { tile_id: string; file: string; sha256: string; product: string }[]; coverage: Record<string, Record<string, number>>;
  metrics_60m: Record<string, number | null>; method_version?: string;
  /** analogue-method-v1.0, one entry per reference window: the same calculation as the atlas. */
  comparisons: Record<string, {
    reference_name: string; method: string; scored: boolean; terrain_index: number | null; terrain_class: "same" | "partial" | "different" | null;
    standing: { closer_than: number; as_close_or_closer: number; of: number; statement: string } | null; reason: string | null;
    features: Record<string, { label: string; units: string; distance: number | null; tau: number | null; similarity: number | null; role: string }>;
  }>;
  imagery: null | { status: string; reason?: string; product_id?: string; acquisition_datetime?: string; preview_url?: string; aoi_cloud_fraction?: number; attribution?: string };
  limitations: string[]; result_sha256: string | null;
}

export interface ScreeningJob {
  job_id: string; label: string; state: "queued" | "acquiring" | "processing" | "quality_check" | "ready" | "failed" | "unsupported" | "requires_credentials";
  center: { lat: number; lon: number }; geometry: AoiFeature["geometry"]; created_at: string; updated_at: string;
  log: { at: string; state: string; message: string }[]; preflight: Preflight; screening: boolean; result: ScreeningResult | null;
}

export interface Heightmap {
  site_id: string; body: Body; resolution_m: number; columns: number; rows: number; nodata: number;
  relative_min_m: number; relative_max_m: number; heights: number[]; source_id: string; source_sha256: string;
}

export interface Distribution { feature: string; bin_edges: number[]; normalized_counts: number[]; valid_sample_count: number }
export interface DistributionsResponse { site_id: string; methodology_version: string; scales: Record<string, Record<string, Distribution>> }

export interface SourceManifest {
  source_id: string; title: string; provider: string; mission: string | null; instrument: string | null; product_name: string;
  product_version: string | null; native_resolution: string | number[] | null; source_page_url: string; doi: string | null;
  access_date: string | null; license_or_use_constraints: string | null; citation_text: string; sha256_checksum: string | null;
}

export interface DatasetRecord {
  dataset_id: string; provider: string; product_name: string; product_id: string | null; celestial_body: string;
  scientific_dimension: string; spatial_resolution: string | null; local_status: string; intended_project_use: string;
  known_limitations: string[]; official_landing_page: string; doi: string | null;
}

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

/** Resolve an API-relative path. Absolute URLs are only accepted over https (or the configured API origin). */
export function resolveApiUrl(path: string): string | null {
  if (path.startsWith("/api/")) return `${API_BASE_URL}${path}`;
  try {
    const url = new URL(path);
    if (url.protocol === "https:" || url.origin === new URL(API_BASE_URL).origin) return url.toString();
  } catch { /* not a URL */ }
  return null;
}

/** External links from API metadata: https only, so a record can never inject javascript: or data: URLs. */
export function safeExternalUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  if (url.startsWith("/api/")) return `${API_BASE_URL}${url}`;
  try { return new URL(url).protocol === "https:" ? url : null; } catch { return null; }
}

export class ApiError extends Error {
  constructor(message: string, public readonly status?: number) { super(message); }
}

async function request<T>(path: string, init?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(new DOMException("timeout", "TimeoutError")), init?.timeoutMs ?? 12000);
  const onAbort = () => controller.abort(init?.signal?.reason);
  init?.signal?.addEventListener("abort", onAbort, { once: true });
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers: { "Content-Type": "application/json", ...init?.headers }, signal: controller.signal });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new ApiError(payload?.error?.message ?? `Request failed (${response.status})`, response.status);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (init?.signal?.aborted) throw error;
    if (controller.signal.aborted) throw new ApiError("The API did not respond in time");
    throw new ApiError("The API is not reachable");
  } finally {
    clearTimeout(timeout);
    init?.signal?.removeEventListener("abort", onAbort);
  }
}

const cache = new Map<string, Promise<unknown>>();
function cached<T>(path: string): Promise<T> {
  const hit = cache.get(path) as Promise<T> | undefined;
  if (hit) return hit;
  const pending = request<T>(path).catch((error) => { cache.delete(path); throw error; });
  cache.set(path, pending);
  return pending;
}

export const api = {
  health: () => cached<HealthResponse>("/api/health"),
  sites: () => cached<Site[]>("/api/sites"),
  aoi: (siteId: string) => cached<AoiFeature>(`/api/sites/${encodeURIComponent(siteId)}/aoi`),
  imagery: (siteId: string) => cached<ImageryRecord[]>(`/api/sites/${encodeURIComponent(siteId)}/imagery`),
  heightmap: (siteId: string) => cached<Heightmap>(`/api/sites/${encodeURIComponent(siteId)}/terrain/heightmap`),
  distributions: (siteId: string) => cached<DistributionsResponse>(`/api/sites/${encodeURIComponent(siteId)}/terrain/distributions`),
  siteEvidence: (siteId: string) => cached<SiteEvidence>(`/api/sites/${encodeURIComponent(siteId)}/evidence`),
  sources: () => cached<SourceManifest[]>("/api/sources"),
  datasets: () => cached<DatasetRecord[]>("/api/datasets"),
  profiles: () => cached<ProfileSummary[]>("/api/evidence/profiles"),
  evidenceModel: () => cached<EvidenceModel>("/api/evidence/model"),
  /** Prepared-artifact comparison. Results are deterministic for a given profile, so they are memoised per profile. */
  compare: (candidateIds: string[], profileId: ProfileId): Promise<EvidenceCompareResponse> => {
    const key = `${profileId}|${candidateIds.join(",")}`;
    const hit = compareCache.get(key);
    if (hit) return hit;
    const pending = request<EvidenceCompareResponse>("/api/evidence/compare", {
      method: "POST",
      body: JSON.stringify({ reference_site_id: "mars-jezero", candidate_site_ids: candidateIds, profile_id: profileId }),
    }).catch((error) => { compareCache.delete(key); throw error; });
    compareCache.set(key, pending);
    return pending;
  },
};

const compareCache = new Map<string, Promise<EvidenceCompareResponse>>();
const compareV2Cache = new Map<string, Promise<CompareResponseV2>>();

export const apiV2 = {
  profiles: () => cached<ProfileV2[]>("/api/v2/profiles"),
  model: () => cached<Record<string, unknown>>("/api/v2/model"),
  evaluation: () => cached<Record<string, unknown>>("/api/v2/evaluation"),
  workedExample: (siteId: string, family: string) => cached<Record<string, unknown>>(`/api/v2/method/worked-example?site_id=${encodeURIComponent(siteId)}&family=${encodeURIComponent(family)}`),
  report: (siteId: string, profileId: ProfileIdV2, referenceId: string) => request<Record<string, unknown>>(`/api/v2/reports/${encodeURIComponent(siteId)}?profile_id=${profileId}&reference_site_id=${encodeURIComponent(referenceId)}`, { timeoutMs: 30000 }),
  layers: (siteId: string) => cached<LayerMeta>(`/api/sites/${encodeURIComponent(siteId)}/terrain/layers`),
  compare: (referenceId: string, profileId: ProfileIdV2): Promise<CompareResponseV2> => {
    const key = `${referenceId}|${profileId}`;
    const hit = compareV2Cache.get(key);
    if (hit) return hit;
    const pending = request<CompareResponseV2>("/api/v2/compare", { method: "POST", timeoutMs: 30000, body: JSON.stringify({ reference_site_id: referenceId, profile_id: profileId }) })
      .catch((error) => { compareV2Cache.delete(key); throw error; });
    compareV2Cache.set(key, pending);
    return pending;
  },
  preflight: (lat: number, lon: number) => request<Preflight>("/api/explore/preflight", { method: "POST", body: JSON.stringify({ lat, lon }) }),
  submit: (lat: number, lon: number, label?: string) => request<ScreeningJob>("/api/explore/jobs", { method: "POST", body: JSON.stringify({ lat, lon, label }) }),
  job: (jobId: string, signal?: AbortSignal) => request<ScreeningJob>(`/api/explore/jobs/${encodeURIComponent(jobId)}`, { signal }),
  recentJobs: () => request<Pick<ScreeningJob, "job_id" | "label" | "state" | "center" | "created_at" | "updated_at">[]>("/api/explore/jobs"),
};

const compareV3Cache = new Map<string, Promise<CompareV3>>();

/** analogue-method-v1.0. Comparisons are deterministic for a reference/profile pair, so they are memoised. */
export const apiV3 = {
  method: () => cached<Record<string, unknown>>("/api/v3/method"),
  profiles: () => cached<ProfileV3[]>("/api/v3/profiles"),
  references: () => cached<ReferenceV3[]>("/api/v3/references"),
  dataRoles: () => cached<DataRole[]>("/api/v3/data-roles"),
  context: (referenceId: string) => cached<ContextV3>(`/api/v3/context?reference=${encodeURIComponent(referenceId)}`),
  explorer: (siteId: string) => cached<ExplorerWindow>(`/api/v3/sites/${encodeURIComponent(siteId)}/explorer`),
  result: (siteId: string, profileId: ProfileIdV3, referenceId: string) =>
    cached<ResultDetail>(`/api/v3/result?site=${encodeURIComponent(siteId)}&profile=${profileId}&reference=${encodeURIComponent(referenceId)}`),
  resultUrl: (siteId: string, profileId: ProfileIdV3, referenceId: string) =>
    `${API_BASE_URL}/api/v3/result?site=${encodeURIComponent(siteId)}&profile=${profileId}&reference=${encodeURIComponent(referenceId)}`,
  compare: (referenceId: string, profileId: ProfileIdV3): Promise<CompareV3> => {
    const key = `${referenceId}|${profileId}`;
    const hit = compareV3Cache.get(key);
    if (hit) return hit;
    const pending = request<CompareV3>(`/api/v3/compare?reference=${encodeURIComponent(referenceId)}&profile=${profileId}`, { timeoutMs: 30000 })
      .catch((error) => { compareV3Cache.delete(key); throw error; });
    compareV3Cache.set(key, pending);
    return pending;
  },
};
