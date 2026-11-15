from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from math import ceil, exp
from pathlib import Path
from typing import Any

import numpy as np

from app.models.schemas import DistributionSummary, FeatureCoverage, ScaleTerrainResult, TerrainV3Artifact
from app.services.geospatial_service import BACKEND_ROOT, GEO_DATA, _analysis_crs, _center_in_crs, canonical_text_sha256, load_aoi, load_manifest, sha256_file
from app.services.terrain_service import calculate_local_relief, calculate_roughness, calculate_slope, physical_window_pixels


CONFIG_PATH = Path(__file__).resolve().parents[1] / "data" / "similarity.v3.json"
CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _coverage(values: np.ndarray, total: int, edge_exclusions: int, propagation: str) -> FeatureCoverage:
    valid = int(np.isfinite(values).sum())
    fraction = valid / total if total else 0.0
    threshold = float(CONFIG["minimum_feature_coverage_fraction"])
    return FeatureCoverage(valid_sample_count=valid, total_expected_sample_count=total, coverage_fraction=fraction,
                           nodata_propagation=propagation, kernel_edge_exclusions=edge_exclusions,
                           quality_flag="pass" if fraction >= threshold else "insufficient_coverage")


def _distribution(feature: str, values: np.ndarray) -> DistributionSummary:
    valid = values[np.isfinite(values)]
    bins = np.asarray(CONFIG["distributions"][feature], dtype=float)
    clipped = np.clip(valid, bins[0], np.nextafter(bins[-1], bins[0])) if valid.size else valid
    counts, _ = np.histogram(clipped, bins=bins)
    normalized = counts / counts.sum() if counts.sum() else counts.astype(float)
    return DistributionSummary(feature=feature, bin_edges=bins.tolist(), normalized_counts=normalized.tolist(), valid_sample_count=int(valid.size))


def compute_scale(elevation_with_halo: np.ndarray, core_slice: tuple[slice, slice], resolution_m: float) -> ScaleTerrainResult:
    valid = np.isfinite(elevation_with_halo)
    slope_all = calculate_slope(elevation_with_halo, resolution_m, resolution_m, valid)
    relief_px = physical_window_pixels(CONFIG["local_relief_neighborhood_m"], resolution_m)
    roughness_px = physical_window_pixels(CONFIG["roughness_neighborhood_m"], resolution_m)
    relief_all = calculate_local_relief(elevation_with_halo, relief_px, valid)
    roughness_all = calculate_roughness(elevation_with_halo, roughness_px, valid)
    core = elevation_with_halo[core_slice]
    slope, relief, roughness = slope_all[core_slice], relief_all[core_slice], roughness_all[core_slice]
    total = core.size
    elevation_relative = core - np.nanmedian(core)
    arrays = {"elevation": core, "slope": slope, "roughness": roughness, "local_relief": relief}
    coverages = {name: _coverage(array, total, total - int(np.isfinite(array).sum()),
                                "Invalid source cells propagate through the derivative kernel and are excluded") for name, array in arrays.items()}
    def stat(array: np.ndarray, fn) -> float | None:
        values = array[np.isfinite(array)]
        return float(fn(values)) if values.size else None
    metrics = {
        "elevation_std_m": stat(core, np.std), "slope_mean_deg": stat(slope, np.mean),
        "slope_p50_deg": stat(slope, lambda x: np.percentile(x, 50)), "slope_p90_deg": stat(slope, lambda x: np.percentile(x, 90)),
        "local_relief_mean_m": stat(relief, np.mean), "local_relief_p50_m": stat(relief, lambda x: np.percentile(x, 50)),
        "local_relief_p90_m": stat(relief, lambda x: np.percentile(x, 90)), "roughness_mean": stat(roughness, np.mean),
        "roughness_p90": stat(roughness, lambda x: np.percentile(x, 90)),
    }
    distributions = {
        "elevation_relative_m": _distribution("elevation_relative_m", elevation_relative),
        "slope_deg": _distribution("slope_deg", slope),
        "roughness_m": _distribution("roughness_m", roughness),
        "local_relief_m": _distribution("local_relief_m", relief),
    }
    return ScaleTerrainResult(resolution_m=resolution_m, metrics=metrics, feature_coverage=coverages, distributions=distributions)


def process_site_v3(input_path: str | Path, site_id: str, aoi_id: str, source_id: str) -> TerrainV3Artifact:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.warp import reproject

    source_path = Path(input_path)
    manifest, aoi = load_manifest(source_id), load_aoi(aoi_id)
    source_checksum = sha256_file(source_path)
    expected = manifest.mosaic_sha256_checksum or manifest.extracted_sha256_checksum or manifest.sha256_checksum
    if not expected or source_checksum != expected:
        raise ValueError("A matching registered source checksum is required for terrain-v3")
    if aoi.site_id != site_id:
        raise ValueError("AOI site_id does not match requested site")
    # LDEM_875S_20M is used through a derived GeoTIFF in metres (DN x 0.5 applied at derivation, per the PDS label).
    # USGS controlled CTX DTMs are in metres above the Mars areoid (geoid_adjusted_dem) or sphere (dtm), per the product documentation.
    vertical_units = "metre" if manifest.product_name in {"SRTMGL1", "M20_JezeroCrater_CTXDEM_20m", "LDEM_875S_20M", "MRO_CTX_controlled_USGS_DTM"} else None
    if vertical_units != "metre":
        raise ValueError("Vertical units are ambiguous; terrain derivatives cannot be validated")
    vertical_datum = "EGM96 geoid" if manifest.product_name == "SRTMGL1" else None
    scales: dict[str, ScaleTerrainResult] = {}
    core_coverage: dict[str, float] = {}; halo_coverage: dict[str, float] = {}
    warnings: list[str] = []
    with rasterio.open(source_path) as dataset:
        if not dataset.crs:
            raise ValueError("Source raster has no CRS")
        analysis_crs = _analysis_crs(dataset.crs, aoi.planetary_body, aoi.center_longitude, aoi.center_latitude)
        if not analysis_crs.is_projected or analysis_crs.linear_units.lower() not in {"metre", "meter", "metres", "meters"}:
            raise ValueError("Horizontal units must be projected metres")
        center_x, center_y = _center_in_crs(analysis_crs, aoi.planetary_body, aoi.center_longitude, aoi.center_latitude)
        for resolution in CONFIG["scales_m"]:
            core_columns, core_rows = ceil(aoi.width_m / resolution), ceil(aoi.height_m / resolution)
            halo_pixels = ceil(CONFIG["halo_width_m"] / resolution)
            width, height = core_columns + 2 * halo_pixels, core_rows + 2 * halo_pixels
            core_width, core_height = core_columns * resolution, core_rows * resolution
            transform = from_origin(center_x - core_width / 2 - halo_pixels * resolution,
                                    center_y + core_height / 2 + halo_pixels * resolution, resolution, resolution)
            destination = np.full((height, width), np.nan, dtype="float32")
            reproject(source=rasterio.band(dataset, 1), destination=destination, src_transform=dataset.transform,
                      src_crs=dataset.crs, src_nodata=dataset.nodata, dst_transform=transform, dst_crs=analysis_crs,
                      dst_nodata=np.nan, resampling=Resampling.bilinear)
            core_slice = (slice(halo_pixels, halo_pixels + core_rows), slice(halo_pixels, halo_pixels + core_columns))
            scales[str(resolution)] = compute_scale(destination, core_slice, float(resolution))
            core_coverage[str(resolution)] = float(np.isfinite(destination[core_slice]).mean())
            halo_coverage[str(resolution)] = float(np.isfinite(destination).mean())
    failed = [f"{scale}:{feature}" for scale, result in scales.items() for feature, coverage in result.feature_coverage.items() if coverage.quality_flag != "pass"]
    if failed:
        warnings.append("Insufficient feature coverage: " + ", ".join(failed))
    artifact = TerrainV3Artifact(
        site_id=site_id, core_aoi_id=aoi_id, core_width_m=aoi.width_m, core_height_m=aoi.height_m,
        halo_width_m=CONFIG["halo_width_m"], horizontal_units="metre", vertical_units=vertical_units,
        vertical_datum=vertical_datum, nodata_definition=str(manifest.native_nodata), resampling_method="bilinear elevation resampling before derivatives",
        scales=scales, core_valid_coverage=core_coverage, halo_valid_coverage=halo_coverage,
        quality_status="quality_checked" if not failed else "failed_validation",
        cross_validation_status="review_pending", warnings=warnings + (["Vertical datum is not recorded in the local Mars source manifest; relative terrain derivatives remain usable."] if vertical_datum is None else []),
        provenance={"source_id": source_id, "source_checksum": source_checksum, "source_manifest": f"data/manifests/{source_id}.json",
                    "aoi_id": aoi_id, "configuration": "app/data/similarity.v3.json", "generated_at": datetime.now(timezone.utc).isoformat()},
    )
    output = GEO_DATA / "processed" / f"{site_id}.terrain-v3.json"
    payload = artifact.model_dump(mode="json")
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")
    output.with_suffix(".sha256").write_text(canonical_text_sha256(output), encoding="ascii", newline="\n")
    return TerrainV3Artifact.model_validate(payload)


def load_v3_artifact(site_id: str) -> TerrainV3Artifact | None:
    path = GEO_DATA / "processed" / f"{site_id}.terrain-v3.json"
    return TerrainV3Artifact.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None


def normalized_wasserstein(reference: DistributionSummary, candidate: DistributionSummary) -> float:
    if reference.bin_edges != candidate.bin_edges:
        raise ValueError("Distribution bins differ")
    edges = np.asarray(reference.bin_edges)
    ref, cand = np.asarray(reference.normalized_counts), np.asarray(candidate.normalized_counts)
    return float(np.sum(np.abs(np.cumsum(ref) - np.cumsum(cand)) * np.diff(edges)))


def compare_v3(reference: TerrainV3Artifact, candidate: TerrainV3Artifact, feature_weights: dict[str, float] | None = None,
               distance_scales: dict[str, float] | None = None) -> dict[str, Any]:
    weights = feature_weights or CONFIG["feature_weights"]
    distance_scales = distance_scales or CONFIG["distribution_distance_scales"]
    by_scale: dict[str, Any] = {}
    for scale in ("60", "120", "240"):
        ref_scale, cand_scale = reference.scales[scale], candidate.scales[scale]
        components = {}
        for feature, weight in weights.items():
            distance = normalized_wasserstein(ref_scale.distributions[feature], cand_scale.distributions[feature])
            similarity = exp(-distance / distance_scales[feature])
            components[feature] = {"distance": distance, "similarity": similarity, "weight": weight}
        total = sum(item["weight"] for item in components.values())
        score = sum(item["similarity"] * item["weight"] for item in components.values()) / total
        by_scale[scale] = {"score": score, "components": components}
    overall = sum(by_scale[s]["score"] * CONFIG["scale_weights"][s] for s in by_scale)
    return {"overall_similarity": overall, "display_index": round(overall * 100, 1), "by_scale": by_scale,
            "methodology_version": "terrain-v3.0", "scale_stability_range": [min(x["score"] for x in by_scale.values()), max(x["score"] for x in by_scale.values())]}


def sensitivity_v3(reference: TerrainV3Artifact, candidate: TerrainV3Artifact) -> dict[str, Any]:
    nominal = compare_v3(reference, candidate)
    scores = [nominal["overall_similarity"]]
    influence = {}
    for feature in CONFIG["feature_weights"]:
        leave_one_out = {name: weight for name, weight in CONFIG["feature_weights"].items() if name != feature}
        result = compare_v3(reference, candidate, leave_one_out)
        scores.append(result["overall_similarity"]); influence[feature] = abs(result["overall_similarity"] - nominal["overall_similarity"])
    for direction in (-1, 1):
        factor = 1 + direction * CONFIG["sensitivity"]["distance_scale_perturbation_fraction"]
        scales = {name: value * factor for name, value in CONFIG["distribution_distance_scales"].items()}
        scores.append(compare_v3(reference, candidate, distance_scales=scales)["overall_similarity"])
    return {"nominal_index": nominal["display_index"], "tested_index_range": [round(min(scores) * 100, 1), round(max(scores) * 100, 1)],
            "most_influential_metrics": [name for name, _ in sorted(influence.items(), key=lambda item: item[1], reverse=True)],
            "rank_stability": "single-candidate only; use /api/discover across candidates for rank stability", "notice": "Tested configuration range, not a statistical confidence interval."}


def rank_stability_v3(reference: TerrainV3Artifact, candidates: dict[str, TerrainV3Artifact]) -> dict[str, Any]:
    configurations: list[tuple[str, dict[str, float] | None, dict[str, float] | None]] = [("nominal", None, None)]
    for feature in CONFIG["feature_weights"]:
        configurations.append((f"leave_out_{feature}", {name: value for name, value in CONFIG["feature_weights"].items() if name != feature}, None))
    delta = CONFIG["sensitivity"]["distance_scale_perturbation_fraction"]
    for direction, label in ((1 - delta, "distance_scales_minus_20pct"), (1 + delta, "distance_scales_plus_20pct")):
        configurations.append((label, None, {name: value * direction for name, value in CONFIG["distribution_distance_scales"].items()}))
    rankings = {}
    positions = {site_id: [] for site_id in candidates}
    for label, weights, scales in configurations:
        scores = {site_id: compare_v3(reference, artifact, weights, scales)["overall_similarity"] for site_id, artifact in candidates.items()}
        ranking = sorted(scores, key=lambda site_id: (-scores[site_id], site_id))
        rankings[label] = ranking
        for position, site_id in enumerate(ranking, start=1):
            positions[site_id].append(position)
    return {"tested_rankings": rankings, "candidate_rank_ranges": {site_id: [min(values), max(values)] for site_id, values in positions.items()},
            "fully_stable": all(min(values) == max(values) for values in positions.values()),
            "notice": "Deterministic configuration perturbation result, not a statistical confidence statement."}
