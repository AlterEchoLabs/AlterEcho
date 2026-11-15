import json
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from app.models.ids import ImageryIdPath, RunIdPath, SiteIdPath, SourceIdPath
from app.models.schemas import DatasetRecord, ImageryRecord, ProcessingRun, SourceManifest, TerrainFeatureSummary
from app.services.catalog_service import get_site, get_validated_processed_summary
from app.services.geospatial_service import GEO_DATA, load_manifest
from app.services.imagery_service import get_imagery, list_site_imagery, load_dataset_registry
from app.services.terrain_v3_service import load_v3_artifact, sensitivity_v3

router = APIRouter()
IMAGERY_DIR = GEO_DATA / "processed" / "imagery"


def _known_ids(folder: str, suffix: str) -> set[str]:
    return {path.name[: -len(suffix)] for path in (GEO_DATA / folder).glob(f"*{suffix}")}


def _require_site(site_id: str):
    site = get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail={"code": "site_not_found", "message": "Unknown site ID"})
    return site


def _v3_or_404(site_id: str):
    _require_site(site_id)
    artifact = load_v3_artifact(site_id)
    if not artifact:
        raise HTTPException(status_code=404, detail={"code": "terrain_v3_unavailable", "message": "No terrain-v3 artifact is available"})
    return artifact


@router.get("/sites/{site_id}/aoi")
def site_aoi(site_id: SiteIdPath):
    site = _require_site(site_id)
    if not site.aoi_id:
        raise HTTPException(status_code=404, detail={"code": "aoi_not_found", "message": "No AOI is registered for this site"})
    path = GEO_DATA / "aoi" / f"{site.aoi_id}.geojson"
    if not path.exists():
        raise HTTPException(status_code=404, detail={"code": "aoi_not_found", "message": "No AOI is registered for this site"})
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/sites/{site_id}/terrain", response_model=TerrainFeatureSummary)
def site_terrain(site_id: SiteIdPath):
    _require_site(site_id)
    summary = get_validated_processed_summary(site_id)
    if not summary:
        raise HTTPException(status_code=404, detail={"code": "terrain_unavailable", "message": "No terrain summary is available for this site"})
    return summary


@router.get("/sources", response_model=list[SourceManifest])
def sources():
    return [load_manifest(source_id) for source_id in sorted(_known_ids("manifests", ".json"))]


@router.get("/sources/{source_id}", response_model=SourceManifest)
def source(source_id: SourceIdPath):
    if source_id not in _known_ids("manifests", ".json"):
        raise HTTPException(status_code=404, detail={"code": "source_not_found", "message": "Unknown source ID"})
    return load_manifest(source_id)


@router.get("/processing-runs/{run_id}", response_model=ProcessingRun)
def processing_run(run_id: RunIdPath):
    if run_id not in _known_ids("processed", ".processing.json"):
        raise HTTPException(status_code=404, detail={"code": "processing_run_not_found", "message": "Unknown processing run"})
    return ProcessingRun.model_validate_json((GEO_DATA / "processed" / f"{run_id}.processing.json").read_text(encoding="utf-8"))


def _allowed_imagery_assets() -> set[str]:
    """Only PNG previews that have a committed metadata record are served."""
    allowed = set()
    for metadata in IMAGERY_DIR.glob("*-reference.json"):
        try:
            preview = json.loads(metadata.read_text(encoding="utf-8")).get("preview_url") or ""
        except json.JSONDecodeError:
            continue
        name = preview.rsplit("/", 1)[-1]
        if preview.startswith("/api/imagery-assets/") and name.endswith(".png") and (IMAGERY_DIR / name).exists():
            allowed.add(name)
    return allowed


@router.get("/imagery-assets/{asset_name}", include_in_schema=False)
def imagery_asset(asset_name: str):
    if len(asset_name) > 96 or asset_name not in _allowed_imagery_assets():
        raise HTTPException(status_code=404, detail={"code": "imagery_asset_not_found", "message": "Unknown imagery asset"})
    return FileResponse(IMAGERY_DIR / asset_name, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/datasets", response_model=list[DatasetRecord])
def datasets():
    return load_dataset_registry()


@router.get("/sites/{site_id}/imagery", response_model=list[ImageryRecord])
def site_imagery(site_id: SiteIdPath):
    _require_site(site_id)
    return list_site_imagery(site_id)


@router.get("/sites/{site_id}/imagery/latest", response_model=ImageryRecord)
def latest_site_imagery(site_id: SiteIdPath):
    _require_site(site_id)
    latest = next((item for item in list_site_imagery(site_id) if item.mode == "latest_observation"), None)
    if not latest:
        raise HTTPException(status_code=404, detail={"code": "imagery_unavailable", "message": "No latest-observation provider is registered for this site"})
    return latest


@router.get("/sites/{site_id}/imagery/{imagery_id}", response_model=ImageryRecord)
def site_imagery_record(site_id: SiteIdPath, imagery_id: ImageryIdPath):
    _require_site(site_id)
    record = get_imagery(site_id, imagery_id)
    if not record:
        raise HTTPException(status_code=404, detail={"code": "imagery_not_found", "message": "Unknown imagery record"})
    return record


@router.get("/sites/{site_id}/terrain/preview.svg", include_in_schema=False)
def terrain_preview(site_id: SiteIdPath):
    artifact = _v3_or_404(site_id)
    site = get_site(site_id)
    distributions = artifact.scales["60"].distributions["slope_deg"]
    counts, edges = distributions.normalized_counts, distributions.bin_edges
    peak = max(counts) or 1
    bars = "".join(
        f'<rect x="{40 + i * 44}" y="{300 - 220 * value / peak:.1f}" width="36" height="{220 * value / peak:.1f}" fill="#c9a96e"/>'
        f'<text x="{58 + i * 44}" y="322" fill="#8a94a6" font-size="11" text-anchor="middle">{edges[i]:g}</text>'
        for i, value in enumerate(counts))
    title = escape(f"{site.name} · slope distribution at 60 m (terrain-v3)")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 360" font-family="system-ui"><rect width="600" height="360" fill="#0f141b"/>'
           f'{bars}<text x="40" y="40" fill="#e8e3d8" font-size="16">{title}</text>'
           f'<text x="40" y="346" fill="#8a94a6" font-size="11">Slope bin lower edge (°). Derived from the DEM; not optical imagery.</text></svg>')
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=3600", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})


@router.get("/sites/{site_id}/terrain/heightmap")
def terrain_heightmap(site_id: SiteIdPath):
    """Relative-height grid (decimetres from the AOI median) for the 3D terrain view. Visualisation only."""
    _require_site(site_id)
    path = GEO_DATA / "processed" / "terrain-preview" / f"{site_id}.heightmap.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail={"code": "heightmap_unavailable", "message": "No terrain preview grid has been generated for this site"})
    return Response(path.read_text(encoding="utf-8"), media_type="application/json", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/sites/{site_id}/terrain/layers/{kind}.png", include_in_schema=False)
def terrain_layer(site_id: SiteIdPath, kind: str):
    """30 m hillshade or fixed-ramp slope image over the exact AOI (visualisation; same DEM as the score)."""
    _require_site(site_id)
    if kind not in {"hillshade", "slope"}:
        raise HTTPException(status_code=404, detail={"code": "layer_not_found", "message": "Unknown layer"})
    path = GEO_DATA / "processed" / "terrain-preview" / f"{site_id}.{kind}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail={"code": "layer_not_found", "message": "Layer has not been generated"})
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/sites/{site_id}/terrain/layers")
def terrain_layers_meta(site_id: SiteIdPath):
    _require_site(site_id)
    path = GEO_DATA / "processed" / "terrain-preview" / f"{site_id}.layers.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail={"code": "layer_not_found", "message": "Layers have not been generated"})
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/sites/{site_id}/terrain/quality")
def terrain_quality(site_id: SiteIdPath):
    artifact = _v3_or_404(site_id)
    return {"site_id": site_id, "methodology_version": artifact.methodology_version, "quality_status": artifact.quality_status,
            "cross_validation_status": artifact.cross_validation_status, "feature_coverage": {scale: item.feature_coverage for scale, item in artifact.scales.items()},
            "core_valid_coverage": artifact.core_valid_coverage, "halo_valid_coverage": artifact.halo_valid_coverage,
            "units": {"horizontal": artifact.horizontal_units, "vertical": artifact.vertical_units, "vertical_datum": artifact.vertical_datum}, "warnings": artifact.warnings}


@router.get("/sites/{site_id}/terrain/distributions")
def terrain_distributions(site_id: SiteIdPath):
    artifact = _v3_or_404(site_id)
    return {"site_id": site_id, "methodology_version": artifact.methodology_version,
            "scales": {scale: item.distributions for scale, item in artifact.scales.items()}}


@router.get("/sites/{site_id}/terrain/sensitivity")
def terrain_sensitivity(site_id: SiteIdPath):
    candidate = _v3_or_404(site_id)
    reference = load_v3_artifact("mars-jezero")
    if not reference:
        raise HTTPException(status_code=404, detail={"code": "terrain_v3_unavailable", "message": "Reference terrain-v3 artifact is unavailable"})
    return {"site_id": site_id, "reference_site_id": "mars-jezero", **sensitivity_v3(reference, candidate)}
