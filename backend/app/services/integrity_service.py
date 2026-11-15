import json
from hashlib import sha256
from math import ceil
from pathlib import Path

from app.models.schemas import DataStatus, Site, TerrainFeatureSummary, TerrainV3Artifact
from app.services.geospatial_service import BACKEND_ROOT, GEO_DATA, canonical_text_sha256, load_aoi, load_manifest, validate_processing_report
from app.services.similarity_service import CONFIG_V2
from app.services.terrain_v3_service import CONFIG as CONFIG_V3


CATALOG_PATH = BACKEND_ROOT / "app" / "data" / "sites.json"


def _catalog_sites() -> list[Site]:
    return [Site.model_validate(item) for item in json.loads(CATALOG_PATH.read_text(encoding="utf-8"))]


def validate_site_integrity(site: Site) -> list[str]:
    errors: list[str] = []
    summary_path = GEO_DATA / "processed" / f"{site.id}.terrain.json"
    if site.data_status != DataStatus.real_processed:
        if summary_path.exists():
            errors.append("non-real catalog site has a processed terrain summary")
        return errors
    if not summary_path.exists():
        return ["processed terrain summary is missing"]
    try:
        summary = TerrainFeatureSummary.model_validate_json(summary_path.read_text(encoding="utf-8"))
    except Exception as error:
        return [f"terrain summary is invalid: {error}"]
    if summary.data_status != DataStatus.real_processed:
        errors.append("terrain summary is not real_processed")
    if not site.source_id:
        errors.append("catalog source_id is missing")
    if not site.aoi_id:
        errors.append("catalog aoi_id is missing")
    if summary.aoi_id != site.aoi_id:
        errors.append("catalog and terrain-summary AOI IDs differ")
    if not summary.processing_run_id:
        errors.append("processing_run_id is missing")
    if summary.resolution_m != CONFIG_V2["target_resolution_m"]:
        errors.append(f"target resolution must be {CONFIG_V2['target_resolution_m']} m")
    if summary.valid_coverage_fraction < CONFIG_V2["minimum_valid_coverage_fraction"]:
        errors.append("valid coverage is below the configured threshold")
    if summary.calculation_metadata.get("methodology_version") != CONFIG_V2["methodology_version"]:
        errors.append("methodology version does not match terrain-v2.0 configuration")
    serialized = json.dumps({"data_source": summary.data_source, "provenance": summary.provenance}).lower()
    if "fixture" in serialized or "synthetic" in serialized or "demo_only" in serialized:
        errors.append("real artifact references a test fixture")
    try:
        manifest = load_manifest(site.source_id) if site.source_id else None
    except Exception as error:
        manifest = None
        errors.append(f"source manifest is missing or invalid: {error}")
    try:
        aoi = load_aoi(site.aoi_id) if site.aoi_id else None
    except Exception as error:
        aoi = None
        errors.append(f"AOI is missing or invalid: {error}")
    report = None
    if summary.processing_run_id:
        report_path = GEO_DATA / "processed" / f"{summary.processing_run_id}.processing.json"
        if not report_path.exists():
            errors.append("processing-run report is missing")
        else:
            try:
                report = validate_processing_report(report_path)
            except Exception as error:
                errors.append(f"processing-run output checksum failed: {error}")
    if manifest and report:
        checksums = {
            value for value in (
                manifest.sha256_checksum,
                manifest.extracted_sha256_checksum,
                manifest.mosaic_sha256_checksum,
                *(tile.get("extracted_sha256_checksum") for tile in manifest.tiles),
            ) if value
        }
        if not checksums:
            errors.append("source manifest has no checksum")
        elif report.get("source_checksum") not in checksums:
            errors.append("processing-run source checksum is not recorded by the manifest")
        if report.get("methodology_version") != CONFIG_V2["methodology_version"]:
            errors.append("processing-run methodology version differs")
        if report.get("target_resolution") != CONFIG_V2["target_resolution_m"]:
            errors.append("processing-run target resolution differs")
        if not report.get("quality_passed"):
            errors.append("processing-run quality gate did not pass")
    if aoi and report:
        expected_grid = [ceil(aoi.width_m / summary.resolution_m), ceil(aoi.height_m / summary.resolution_m)]
        if report.get("grid_dimensions") != expected_grid:
            errors.append("grid dimensions do not match AOI and resolution")
        expected_extent = [expected_grid[0] * summary.resolution_m, expected_grid[1] * summary.resolution_m]
        if report.get("actual_analysis_window_m") != expected_extent:
            errors.append("recorded processed dimensions are inconsistent")
        if [summary.analysis_width_m, summary.analysis_height_m] != expected_extent:
            errors.append("terrain-summary processed dimensions are inconsistent")
    v3_path = GEO_DATA / "processed" / f"{site.id}.terrain-v3.json"
    if not v3_path.exists():
        errors.append("terrain-v3 artifact is missing")
    else:
        try:
            checksum_path = v3_path.with_suffix(".sha256")
            if not checksum_path.exists() or checksum_path.read_text(encoding="ascii").strip() != canonical_text_sha256(v3_path):
                errors.append("terrain-v3 artifact checksum is missing or stale")
            v3_payload = json.loads(v3_path.read_text(encoding="utf-8"))
            v3 = TerrainV3Artifact.model_validate(v3_payload)
            if v3.core_aoi_id != site.aoi_id:
                errors.append("terrain-v3 AOI differs from the catalog")
            if v3.methodology_version != CONFIG_V3["methodology_version"] or set(v3.scales) != {str(item) for item in CONFIG_V3["scales_m"]}:
                errors.append("terrain-v3 version or scales differ from configuration")
            if v3.quality_status != "quality_checked":
                errors.append("terrain-v3 quality gate did not pass")
            if any(coverage.coverage_fraction < CONFIG_V3["minimum_feature_coverage_fraction"] for scale in v3.scales.values() for coverage in scale.feature_coverage.values()):
                errors.append("terrain-v3 feature coverage is below threshold")
            if manifest and v3.provenance.get("source_checksum") not in {manifest.sha256_checksum, manifest.extracted_sha256_checksum, manifest.mosaic_sha256_checksum}:
                errors.append("terrain-v3 source checksum is not registered by the manifest")
        except Exception as error:
            errors.append(f"terrain-v3 artifact is invalid: {error}")
    return errors


def validate_catalog_integrity() -> dict[str, list[str]]:
    return {site.id: errors for site in _catalog_sites() if (errors := validate_site_integrity(site))}
