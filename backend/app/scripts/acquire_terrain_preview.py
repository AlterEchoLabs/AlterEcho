"""Build small relative-height grids for the 3D terrain view from the SAME source rasters used for scoring.

For each processed site the registered source raster is downloaded (if absent), its SHA-256 is
checked against the value already recorded in the committed manifest (manifests are never
rewritten here), and it is reprojected onto the exact metric grid construction used by
terrain-v3 at 120 m (84 x 84 cells for the 10 km core AOI). Heights are stored relative to the
AOI median, in decimetres, so the browser can draw the shape without receiving raw elevations.

This is a visualisation artifact. Numeric analysis continues to use terrain-v3 artifacts.

Usage (from ``backend/``; Earth sources need EARTHDATA_TOKEN in the process environment)::

    python -m app.scripts.acquire_terrain_preview
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from math import ceil
import os

import numpy as np

from app.config import settings
from app.scripts.acquire_dataset import AcquisitionError, download, earthdata_headers, extract_dem
from app.services.catalog_service import get_site
from app.services.geospatial_service import GEO_DATA, _analysis_crs, _center_in_crs, load_aoi, load_manifest, sha256_file
from app.services.georeferencing import build_grid_georeferencing

def _sites() -> list[str]:
    from app.services.catalog_service import SITES as CATALOG
    return [site.id for site in CATALOG if site.aoi_id and site.data_status.value == "real_processed" and site.body.value in {"earth", "mars", "moon"}]


SITES = _sites()
LAYER_RESOLUTION_M = 30.0
RESOLUTION_M = 120.0
OUTPUT_DIR = GEO_DATA / "processed" / "terrain-preview"


def _source_path(manifest) -> "os.PathLike":
    raw = GEO_DATA / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    if manifest.planetary_body == "earth" and manifest.mosaic_filename:
        extracted = GEO_DATA / "interim" / manifest.mosaic_filename
        if not extracted.exists():
            raise AcquisitionError(f"{manifest.mosaic_filename}: mosaic missing; run acquire_dataset first")
        if sha256_file(extracted) != manifest.mosaic_sha256_checksum:
            raise AcquisitionError(f"{extracted.name}: mosaic checksum differs from the committed manifest")
        return extracted
    if manifest.planetary_body == "earth":
        tile = manifest.tiles[0]
        archive = raw / tile["filename"]
        if not archive.exists():
            download(tile["download_url"], archive, earthdata_headers(dict(os.environ)))
        if sha256_file(archive) != tile.get("sha256_checksum", manifest.sha256_checksum):
            raise AcquisitionError(f"{archive.name}: archive checksum differs from the committed manifest")
        extracted = extract_dem(archive, raw)
        expected = manifest.extracted_sha256_checksum
    elif manifest.extracted_filename:
        extracted = raw / manifest.extracted_filename  # derived product (e.g. LOLA clip in metres); see its manifest notes
        expected = manifest.extracted_sha256_checksum
    else:
        extracted = raw / manifest.filename
        if not extracted.exists():
            download(manifest.download_url, extracted, {"User-Agent": f"{settings.application_id}/{settings.app_version}"})
        expected = manifest.sha256_checksum
    if sha256_file(extracted) != expected:
        raise AcquisitionError(f"{extracted.name}: checksum differs from the committed manifest")
    return extracted


def build(site_id: str) -> dict:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.warp import reproject

    site = get_site(site_id)
    manifest, aoi = load_manifest(site.source_id), load_aoi(site.aoi_id)
    source = _source_path(manifest)
    columns, rows = ceil(aoi.width_m / RESOLUTION_M), ceil(aoi.height_m / RESOLUTION_M)
    with rasterio.open(source) as dataset:
        crs = _analysis_crs(dataset.crs, aoi.planetary_body, aoi.center_longitude, aoi.center_latitude)
        cx, cy = _center_in_crs(crs, aoi.planetary_body, aoi.center_longitude, aoi.center_latitude)
        transform = from_origin(cx - columns * RESOLUTION_M / 2, cy + rows * RESOLUTION_M / 2, RESOLUTION_M, RESOLUTION_M)
        grid = np.full((rows, columns), np.nan, dtype="float32")
        reproject(source=rasterio.band(dataset, 1), destination=grid, src_transform=dataset.transform, src_crs=dataset.crs,
                  src_nodata=dataset.nodata, dst_transform=transform, dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.average)
    valid = np.isfinite(grid)
    if valid.mean() < 0.9:
        raise AcquisitionError(f"{site_id}: preview grid coverage {valid.mean():.1%} is below 90%")
    relative = grid - np.nanmedian(grid)
    decimetres = np.where(valid, np.round(relative * 10), -32768).astype(int)
    artifact = {
        "site_id": site_id, "body": aoi.planetary_body, "aoi_id": aoi.aoi_id, "purpose": "visualisation only; numeric analysis uses terrain-v3",
        "resolution_m": RESOLUTION_M, "columns": columns, "rows": rows, "crs": str(crs), "row_order": "north to south",
        "height_units": "decimetres relative to the AOI median elevation", "nodata": -32768,
        "relative_min_m": round(float(np.nanmin(relative)), 1), "relative_max_m": round(float(np.nanmax(relative)), 1),
        "valid_fraction": round(float(valid.mean()), 4), "resampling": "average (aggregation from finer source)",
        "source_id": manifest.source_id, "source_sha256": expected_checksum(manifest),
        "heights": decimetres.flatten().tolist(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"{site_id}.heightmap.json").write_text(json.dumps(artifact, separators=(",", ":")), encoding="utf-8", newline="\n")
    return artifact


def build_layers(site_id: str) -> dict:
    """Hillshade and slope PNGs at 30 m over the exact core AOI (visualisation; same DEM as the score)."""
    import rasterio
    from PIL import Image
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.warp import reproject

    site = get_site(site_id)
    manifest, aoi = load_manifest(site.source_id), load_aoi(site.aoi_id)
    source = _source_path(manifest)
    n = ceil(aoi.width_m / LAYER_RESOLUTION_M)
    pad = 1
    with rasterio.open(source) as dataset:
        crs = _analysis_crs(dataset.crs, aoi.planetary_body, aoi.center_longitude, aoi.center_latitude)
        cx, cy = _center_in_crs(crs, aoi.planetary_body, aoi.center_longitude, aoi.center_latitude)
        size = n + 2 * pad
        transform = from_origin(cx - size * LAYER_RESOLUTION_M / 2, cy + size * LAYER_RESOLUTION_M / 2, LAYER_RESOLUTION_M, LAYER_RESOLUTION_M)
        image_transform = from_origin(cx - n * LAYER_RESOLUTION_M / 2, cy + n * LAYER_RESOLUTION_M / 2, LAYER_RESOLUTION_M, LAYER_RESOLUTION_M)
        study_columns = ceil(aoi.width_m / LAYER_RESOLUTION_M)
        study_rows = ceil(aoi.height_m / LAYER_RESOLUTION_M)
        study_transform = from_origin(cx - aoi.width_m / 2, cy + aoi.height_m / 2, aoi.width_m / study_columns, aoi.height_m / study_rows)
        z = np.full((size, size), np.nan, dtype="float64")
        reproject(source=rasterio.band(dataset, 1), destination=z, src_transform=dataset.transform, src_crs=dataset.crs,
                  src_nodata=dataset.nodata, dst_transform=transform, dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.bilinear)
    dzdy, dzdx = np.gradient(z, LAYER_RESOLUTION_M)
    dzdy = -dzdy  # rows run north to south
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    aspect = np.arctan2(-dzdx, dzdy)
    azimuth, altitude = np.radians(315.0), np.radians(45.0)
    shade = np.sin(altitude) * np.cos(np.radians(slope)) + np.cos(altitude) * np.sin(np.radians(slope)) * np.cos(azimuth - aspect)
    core = (slice(pad, pad + n), slice(pad, pad + n))
    shade, slope = shade[core], slope[core]
    hill = np.nan_to_num(np.clip(shade, 0, 1) * 255).astype("uint8")
    # slope ramp: dark (flat) -> sand -> white (>= 35 degrees), fixed so sites are visually comparable
    t = np.clip(np.nan_to_num(slope) / 35.0, 0, 1)
    ramp = np.stack([25 + t * 215, 30 + t * 190, 38 + t * 120], axis=-1).astype("uint8")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    Image.fromarray(hill, "L").save(OUTPUT_DIR / f"{site_id}.hillshade.png", optimize=True)
    Image.fromarray(ramp, "RGB").save(OUTPUT_DIR / f"{site_id}.slope.png", optimize=True)
    meta = {"site_id": site_id, "resolution_m": LAYER_RESOLUTION_M, "pixels": n, "hillshade": {"azimuth_deg": 315, "altitude_deg": 45},
            "slope_ramp": "linear 0-35 degrees, fixed across sites", "slope_p50_deg": round(float(np.nanmedian(slope)), 2),
            "source_sha256": expected_checksum(manifest), "purpose": "visualisation only; numeric analysis uses terrain-v3/v4",
            "georeferencing": build_grid_georeferencing(
                crs, image_transform, n, n, body=aoi.planetary_body,
                study_window_affine=study_transform,
                study_window_width_pixels=study_columns,
                study_window_height_pixels=study_rows,
            )}
    (OUTPUT_DIR / f"{site_id}.layers.json").write_text(json.dumps(meta, indent=2), encoding="utf-8", newline="\n")
    return meta


def expected_checksum(manifest) -> str:
    return manifest.mosaic_sha256_checksum or manifest.extracted_sha256_checksum or manifest.sha256_checksum


def main() -> None:
    for site_id in SITES:
        try:
            artifact = build(site_id)
            layers = build_layers(site_id)
            print(site_id, artifact["columns"], "x", artifact["rows"], "relief", artifact["relative_min_m"], "to", artifact["relative_max_m"], "m; layers", layers["pixels"], "px")
        except AcquisitionError as error:
            print(site_id, "BLOCKED:", error)


if __name__ == "__main__":
    main()
