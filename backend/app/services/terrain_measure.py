"""Measure terrain-v3 distributions for an arbitrary square window using the exact v3 kernels.

Used by the terrain-v4 evaluation (AOI shifts, halo effects, DEM choice, base-rate windows) and by
user-defined screening AOIs. Registered production artifacts are still written only by
terrain_v3_service.process_site_v3.
"""

from __future__ import annotations

from math import ceil
from typing import Any

import numpy as np

from app.models.schemas import ScaleTerrainResult, TerrainV3Artifact
from app.services.geospatial_service import _analysis_crs, _center_in_crs
from app.services.terrain_v3_service import CONFIG as V3, compute_scale


class MeasurementError(ValueError):
    pass


def measure_window(source: Any, body: str, longitude: float, latitude: float, width_m: float = 10_000.0,
                   halo_m: float | None = None, scales: tuple[int, ...] | None = None) -> dict[str, Any]:
    """Return {scale: ScaleTerrainResult} plus core/halo coverage for a square window centred on lon/lat.

    ``source`` is a path, URL or an open rasterio dataset. Units must be metres (checked by the caller
    for registered sources; DEMs used here are SRTM/NASADEM/Copernicus/CTX/LOLA, all in metres).
    """
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.warp import reproject

    halo_m = V3["halo_width_m"] if halo_m is None else halo_m
    scales = scales or tuple(V3["scales_m"])
    dataset = rasterio.open(source) if not hasattr(source, "read") else source
    try:
        if not dataset.crs:
            raise MeasurementError("Source raster has no CRS")
        crs = _analysis_crs(dataset.crs, body, longitude, latitude)
        cx, cy = _center_in_crs(crs, body, longitude, latitude)
        results: dict[str, ScaleTerrainResult] = {}
        core_cov: dict[str, float] = {}
        halo_cov: dict[str, float] = {}
        for resolution in scales:
            n = ceil(width_m / resolution)
            halo_px = ceil(halo_m / resolution) if halo_m > 0 else 0
            size = n + 2 * halo_px
            transform = from_origin(cx - n * resolution / 2 - halo_px * resolution, cy + n * resolution / 2 + halo_px * resolution, resolution, resolution)
            grid = np.full((size, size), np.nan, dtype="float32")
            reproject(source=rasterio.band(dataset, 1), destination=grid, src_transform=dataset.transform, src_crs=dataset.crs,
                      src_nodata=dataset.nodata, dst_transform=transform, dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.bilinear)
            core = (slice(halo_px, halo_px + n), slice(halo_px, halo_px + n))
            results[str(resolution)] = compute_scale(grid, core, float(resolution))
            core_cov[str(resolution)] = float(np.isfinite(grid[core]).mean())
            halo_cov[str(resolution)] = float(np.isfinite(grid).mean())
    finally:
        if not hasattr(source, "read"):
            dataset.close()
    return {"scales": results, "core_valid_coverage": core_cov, "halo_valid_coverage": halo_cov}


def as_artifact(site_id: str, measured: dict[str, Any], width_m: float = 10_000.0, halo_m: float | None = None,
                provenance: dict | None = None) -> TerrainV3Artifact:
    """Wrap a measurement so terrain-v4 can compare it; quality follows the v3 coverage gate."""
    threshold = V3["minimum_feature_coverage_fraction"]
    passed = all(c.coverage_fraction >= threshold for s in measured["scales"].values() for c in s.feature_coverage.values())
    return TerrainV3Artifact(
        site_id=site_id, core_aoi_id=f"{site_id}-window", core_width_m=width_m, core_height_m=width_m,
        halo_width_m=V3["halo_width_m"] if halo_m is None else halo_m, horizontal_units="metre", vertical_units="metre",
        vertical_datum=None, nodata_definition="source nodata -> NaN", resampling_method="bilinear elevation resampling before derivatives",
        scales=measured["scales"], core_valid_coverage=measured["core_valid_coverage"], halo_valid_coverage=measured["halo_valid_coverage"],
        quality_status="quality_checked" if passed else "failed_validation", cross_validation_status="not_applicable",
        provenance=provenance or {},
    )
