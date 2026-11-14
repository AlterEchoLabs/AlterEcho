import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from app.models.schemas import DatasetRecord, ImageryRecord, ProcessingRun, SourceManifest, TerrainFeatureSummary
from app.services.catalog_service import get_validated_processed_summary, get_site
from app.services.geospatial_service import GEO_DATA, load_aoi, load_manifest
from app.services.imagery_service import get_imagery, list_site_imagery, load_dataset_registry
from app.services.terrain_v3_service import load_v3_artifact, sensitivity_v3

router = APIRouter()


@router.get("/sites/{site_id}/aoi")
def site_aoi(site_id: str):
    site = get_site(site_id)
    if not site: raise HTTPException(status_code=404, detail={"code": "site_not_found", "message": f"Unknown site ID: {site_id}"})
    matches = list((GEO_DATA / "aoi").glob(f"{site_id}-aoi-*.geojson"))
    if not matches: raise HTTPException(status_code=404, detail={"code": "aoi_not_found", "message": f"No AOI is registered for {site_id}"})
    return json.loads(matches[-1].read_text(encoding="utf-8"))


@router.get("/sites/{site_id}/terrain", response_model=TerrainFeatureSummary)
def site_terrain(site_id: str):
    if not get_site(site_id): raise HTTPException(status_code=404, detail={"code": "site_not_found", "message": f"Unknown site ID: {site_id}"})
    summary = get_validated_processed_summary(site_id)
    if not summary: raise HTTPException(status_code=404, detail={"code": "terrain_unavailable", "message": f"No terrain summary is available for {site_id}"})
    return summary


@router.get("/sources", response_model=list[SourceManifest])
def sources():
    return [load_manifest(path.stem) for path in sorted((GEO_DATA / "manifests").glob("*.json"))]


@router.get("/sources/{source_id}", response_model=SourceManifest)
def source(source_id: str):
    path = GEO_DATA / "manifests" / f"{source_id}.json"
    if not path.exists(): raise HTTPException(status_code=404, detail={"code": "source_not_found", "message": f"Unknown source ID: {source_id}"})
    return load_manifest(source_id)


@router.get("/processing-runs/{run_id}", response_model=ProcessingRun)
def processing_run(run_id: str):
    path = GEO_DATA / "processed" / f"{run_id}.processing.json"
    if not path.exists(): raise HTTPException(status_code=404, detail={"code": "processing_run_not_found", "message": f"Unknown processing run: {run_id}"})
    return ProcessingRun.model_validate_json(path.read_text(encoding="utf-8"))


@router.get("/imagery-assets/{asset_name}", include_in_schema=False)
def imagery_asset(asset_name: str):
    allowed = {"mars-jezero-ctx-reference.png", "earth-atacama-sentinel-reference.png"}
    if asset_name not in allowed:
        raise HTTPException(status_code=404, detail={"code": "imagery_asset_not_found", "message": "Unknown imagery asset"})
    path = GEO_DATA / "processed" / "imagery" / asset_name
    if not path.exists():
        raise HTTPException(status_code=404, detail={"code": "imagery_asset_not_found", "message": "Imagery asset has not been generated"})
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/datasets", response_model=list[DatasetRecord])
def datasets():
    return load_dataset_registry()


@router.get("/sites/{site_id}/imagery", response_model=list[ImageryRecord])
def site_imagery(site_id: str):
    if not get_site(site_id):
        raise HTTPException(status_code=404, detail={"code": "site_not_found", "message": f"Unknown site ID: {site_id}"})
    return list_site_imagery(site_id)


@router.get("/sites/{site_id}/imagery/latest", response_model=ImageryRecord)
def latest_site_imagery(site_id: str):
    try:
        records = list_site_imagery(site_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={"code": "site_not_found", "message": f"Unknown site ID: {site_id}"})
    latest = next((item for item in records if item.mode == "latest_observation"), None)
    if not latest:
        raise HTTPException(status_code=404, detail={"code": "imagery_unavailable", "message": "No latest-observation provider is registered for this site"})
    return latest


@router.get("/sites/{site_id}/imagery/{imagery_id}", response_model=ImageryRecord)
def site_imagery_record(site_id: str, imagery_id: str):
    try:
        record = get_imagery(site_id, imagery_id)
    except KeyError:
        record = None
    if not record:
        raise HTTPException(status_code=404, detail={"code": "imagery_not_found", "message": "Unknown imagery record"})
    return record


@router.get("/sites/{site_id}/terrain/preview.svg", include_in_schema=False)
def terrain_preview(site_id: str):
    artifact = load_v3_artifact(site_id)
    site = get_site(site_id)
    if not site or not artifact:
        raise HTTPException(status_code=404, detail={"code": "terrain_preview_unavailable", "message": "No terrain-v3 artifact is available"})
    metrics = artifact.scales["60"].metrics
    values = [metrics.get("slope_p50_deg") or 0, metrics.get("slope_p90_deg") or 0, metrics.get("local_relief_p50_m") or 0, metrics.get("roughness_mean") or 0]
    bars = "".join(f'<rect x="{60+i*125}" y="{340-min(value*3,240):.1f}" width="70" height="{min(value*3,240):.1f}" rx="5" fill="#38bdf8" opacity="{0.55+i*0.1}"/>' for i, value in enumerate(values))
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 420"><defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="#071426"/><stop offset="1" stop-color="#19263c"/></linearGradient></defs><rect width="600" height="420" fill="url(#g)"/><path d="M0 300 Q90 170 180 260 T360 190 T600 250 V420 H0Z" fill="#24465b"/><path d="M0 330 Q130 250 220 315 T420 260 T600 300" fill="none" stroke="#7dd9ff" stroke-width="3" opacity=".7"/>{bars}<rect x="12" y="12" width="576" height="396" fill="none" stroke="#f59e0b" stroke-width="3" stroke-dasharray="9 7"/><text x="30" y="46" fill="white" font-family="system-ui" font-size="22">{site.name} · terrain-v3 derived view</text><text x="30" y="76" fill="#a8c2db" font-family="system-ui" font-size="14">AOI boundary · 60 m scale · visualization, not optical imagery</text></svg>'''
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/sites/{site_id}/terrain/quality")
def terrain_quality(site_id: str):
    artifact = load_v3_artifact(site_id)
    if not artifact:
        raise HTTPException(status_code=404, detail={"code": "terrain_v3_unavailable", "message": "No terrain-v3 artifact is available"})
    return {"site_id": site_id, "methodology_version": artifact.methodology_version, "quality_status": artifact.quality_status,
            "cross_validation_status": artifact.cross_validation_status, "feature_coverage": {scale: item.feature_coverage for scale, item in artifact.scales.items()},
            "core_valid_coverage": artifact.core_valid_coverage, "halo_valid_coverage": artifact.halo_valid_coverage,
            "units": {"horizontal": artifact.horizontal_units, "vertical": artifact.vertical_units, "vertical_datum": artifact.vertical_datum}, "warnings": artifact.warnings}


@router.get("/sites/{site_id}/terrain/distributions")
def terrain_distributions(site_id: str):
    artifact = load_v3_artifact(site_id)
    if not artifact:
        raise HTTPException(status_code=404, detail={"code": "terrain_v3_unavailable", "message": "No terrain-v3 artifact is available"})
    return {"site_id": site_id, "methodology_version": artifact.methodology_version,
            "scales": {scale: item.distributions for scale, item in artifact.scales.items()}}


@router.get("/sites/{site_id}/terrain/sensitivity")
def terrain_sensitivity(site_id: str):
    reference, candidate = load_v3_artifact("mars-jezero"), load_v3_artifact(site_id)
    if not reference or not candidate:
        raise HTTPException(status_code=404, detail={"code": "terrain_v3_unavailable", "message": "Reference or candidate terrain-v3 artifact is unavailable"})
    return {"site_id": site_id, "reference_site_id": "mars-jezero", **sensitivity_v3(reference, candidate)}
