"""terrain-v5.0 measurement: per-cell quantile functions of four terrain constructs.

Replaces the coarse fixed-bin histograms of terrain-v3 (whose W1 placed each bin's mass at its lower
edge, so differences inside a 1 degree or 10 m bin vanished) with the empirical inverse CDF of the
valid cells, sampled at u = (i + 0.5) / N. W1 between two windows is then

    W1 = integral_0^1 |F_E^-1(u) - F_P^-1(u)| du  ~=  mean_i |Q_E(u_i) - Q_P(u_i)|

Kernels are exactly those of terrain-v3 (metric gradients, 1,000 m local relief, 300 m roughness,
z - median(z) relative elevation, bilinear resampling, 1.2 km halo). Cells of a projected local grid
carry equal area: UTM (Earth), equirectangular with standard parallel 18.4663 deg (Jezero) and polar
stereographic true at the pole (Moon) all vary in area by far less than 0.1 % over a 10 km window,
so every valid cell has the same weight.

An optional exclusion mask (for example built-up land from ESA WorldCover) is applied to elevation
before derivatives, so excluded cells and every stencil that touches them drop out. No cell is filled.
"""

from __future__ import annotations

from math import ceil
from pathlib import Path
from typing import Any, Callable

import numpy as np

from app.services.geospatial_service import _analysis_crs, _center_in_crs
from app.services.terrain_service import calculate_local_relief, calculate_roughness, calculate_slope, physical_window_pixels
from app.services.terrain_v3_service import CONFIG as V3

N_QUANTILES = 500
U = (np.arange(N_QUANTILES) + 0.5) / N_QUANTILES
FEATURES: dict[str, str] = {"slope": "degrees", "local_relief": "metres", "roughness": "metres", "relative_elevation": "metres"}
PRIMARY_SCALE = "60"
SCALES = (60, 120, 240)

Exclusion = Callable[[Any, Any, tuple[int, int]], np.ndarray | None]


class QuantileMeasurementError(ValueError):
    pass


def quantile_function(values: np.ndarray) -> list[float]:
    """Empirical inverse CDF at the fixed u grid (inverted-CDF definition, no interpolation)."""
    valid = values[np.isfinite(values)]
    if valid.size == 0:
        return []
    return [round(float(v), 4) for v in np.quantile(valid, U, method="inverted_cdf")]


def w1_quantiles(a: list[float], b: list[float]) -> float:
    """Wasserstein-1 from two quantile functions on the same u grid, in the feature's units."""
    if len(a) != len(b) or not a:
        raise QuantileMeasurementError("Quantile functions must be non-empty and share the same u grid")
    return float(np.mean(np.abs(np.asarray(a, dtype=float) - np.asarray(b, dtype=float))))


def dilate(mask: np.ndarray, cells: int = 1) -> np.ndarray:
    out = mask.copy()
    for _ in range(cells):
        padded = np.pad(out, 1, constant_values=False)
        out = np.zeros_like(out)
        for dy in (0, 1, 2):
            for dx in (0, 1, 2):
                out |= padded[dy:dy + mask.shape[0], dx:dx + mask.shape[1]]
    return out


def feature_arrays(grid: np.ndarray, core: tuple[slice, slice], resolution_m: float) -> dict[str, np.ndarray]:
    valid = np.isfinite(grid)
    slope = calculate_slope(grid, resolution_m, resolution_m, valid)[core]
    relief = calculate_local_relief(grid, physical_window_pixels(V3["local_relief_neighborhood_m"], resolution_m), valid)[core]
    rough = calculate_roughness(grid, physical_window_pixels(V3["roughness_neighborhood_m"], resolution_m), valid)[core]
    z = grid[core]
    rel = z - np.nanmedian(z) if np.isfinite(z).any() else z
    return {"slope": slope, "local_relief": relief, "roughness": rough, "relative_elevation": rel}


def measure(source: Any, body: str, longitude: float, latitude: float, width_m: float = 10_000.0, halo_m: float | None = None,
            scales: tuple[int, ...] = SCALES, exclusion: Exclusion | None = None, keep_arrays: bool = False) -> dict[str, Any]:
    """Quantile functions and coverage for a square window centred on lon/lat at each scale."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.warp import reproject

    halo_m = V3["halo_width_m"] if halo_m is None else halo_m
    dataset = rasterio.open(source) if not hasattr(source, "read") else source
    out: dict[str, Any] = {}
    try:
        if not dataset.crs:
            raise QuantileMeasurementError("Source raster has no CRS")
        crs = _analysis_crs(dataset.crs, body, longitude, latitude)
        cx, cy = _center_in_crs(crs, body, longitude, latitude)
        for resolution in scales:
            n = ceil(width_m / resolution)
            halo_px = ceil(halo_m / resolution) if halo_m > 0 else 0
            size = n + 2 * halo_px
            transform = from_origin(cx - n * resolution / 2 - halo_px * resolution, cy + n * resolution / 2 + halo_px * resolution, resolution, resolution)
            grid = np.full((size, size), np.nan, dtype="float64")
            reproject(source=rasterio.band(dataset, 1), destination=grid, src_transform=dataset.transform, src_crs=dataset.crs,
                      src_nodata=dataset.nodata, dst_transform=transform, dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.bilinear)
            core = (slice(halo_px, halo_px + n), slice(halo_px, halo_px + n))
            source_valid = float(np.isfinite(grid[core]).mean())
            excluded_fraction = 0.0
            if exclusion is not None:
                mask = exclusion(transform, crs, grid.shape)
                if mask is not None:
                    excluded_fraction = float((mask[core] & np.isfinite(grid[core])).mean())
                    grid[mask] = np.nan
            arrays = feature_arrays(grid, core, float(resolution))
            total = n * n
            if keep_arrays:
                out.setdefault("_arrays", {})[str(resolution)] = arrays
            out[str(resolution)] = {
                "resolution_m": float(resolution),
                "source_valid_fraction": round(source_valid, 6),
                "excluded_fraction": round(excluded_fraction, 6),
                "features": {name: {"units": FEATURES[name], "valid_cells": int(np.isfinite(a).sum()), "total_cells": total,
                                    "coverage": round(float(np.isfinite(a).sum()) / total, 6),
                                    "median": round(float(np.nanmedian(a)), 4) if np.isfinite(a).any() else None,
                                    "p90": round(float(np.nanpercentile(a, 90)), 4) if np.isfinite(a).any() else None,
                                    "quantiles": quantile_function(a)} for name, a in arrays.items()},
            }
    finally:
        if not hasattr(source, "read"):
            dataset.close()
    return out


EXCLUSION_RULE = "Analysis cell excluded when at least half of its area is WorldCover built-up (class 50); no buffer"


def landcover_exclusion(clip_path: Path, classes: tuple[int, ...] = (50,), min_fraction: float = 0.5, buffer_cells: int = 0) -> Exclusion:
    """Exclude analysis cells whose area is at least ``min_fraction`` the given WorldCover classes.

    A majority rule (not "any pixel") avoids removing whole valley floors around scattered villages,
    which would bias a window towards steeper terrain. Derivative stencils touching an excluded cell
    still drop out because excluded elevation becomes NaN before derivatives.
    """
    def build(transform, crs, shape):
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.warp import reproject
        with rasterio.open(clip_path) as src:
            indicator = np.isin(src.read(1), classes).astype("float32")
            share = np.zeros(shape, dtype="float32")
            reproject(source=indicator, destination=share, src_transform=src.transform, src_crs=src.crs, dst_transform=transform,
                      dst_crs=crs, resampling=Resampling.average, src_nodata=None)
        mask = share >= min_fraction
        return dilate(mask, buffer_cells) if buffer_cells else mask
    return build
