"""Versioned georeferencing metadata for preprocessed raster images.

Rasterio belongs in preprocessing only.  Request handlers may validate and read the
resulting JSON with :func:`corners_from_georeferencing`, which deliberately has no
native-library imports.
"""

from __future__ import annotations

from math import isfinite
from typing import Any


GEOREFERENCING_VERSION = "georeferenced-grid-v1.0"
CORNER_ORDER = ["northwest", "northeast", "southeast", "southwest"]


def build_grid_georeferencing(
    crs: Any,
    affine: Any,
    width_pixels: int,
    height_pixels: int,
    *,
    body: str = "earth",
    study_window_affine: Any | None = None,
    study_window_width_pixels: int | None = None,
    study_window_height_pixels: int | None = None,
) -> dict[str, Any]:
    """Project exact outer pixel edges to body-fixed longitude/latitude.

    This function is called while producing an image artifact.  Its local Rasterio
    imports keep GDAL out of API requests that only serve committed artifacts.
    """
    from rasterio.crs import CRS
    from rasterio.warp import transform as warp_transform

    if width_pixels <= 0 or height_pixels <= 0:
        raise ValueError("Raster dimensions must be positive")

    source_crs = CRS.from_user_input(crs)
    geographic = {
        "mars": CRS.from_string("+proj=longlat +a=3396190 +b=3396190 +no_defs"),
        "moon": CRS.from_string("+proj=longlat +a=1737400 +b=1737400 +no_defs"),
    }.get(body, CRS.from_epsg(4326))

    def projected_corners(grid_affine: Any, width: int, height: int) -> list[list[float]]:
        projected = [
            grid_affine * (0, 0),
            grid_affine * (width, 0),
            grid_affine * (width, height),
            grid_affine * (0, height),
        ]
        longitudes, latitudes = warp_transform(
            source_crs,
            geographic,
            [point[0] for point in projected],
            [point[1] for point in projected],
        )
        return [[round(longitude, 8), round(latitude, 8)] for longitude, latitude in zip(longitudes, latitudes)]

    image_corners = projected_corners(affine, width_pixels, height_pixels)
    study_affine = study_window_affine or affine
    study_width = study_window_width_pixels or width_pixels
    study_height = study_window_height_pixels or height_pixels
    return {
        "version": GEOREFERENCING_VERSION,
        "crs": str(source_crs),
        "transform": [float(value) for value in tuple(affine)[:6]],
        "width_pixels": width_pixels,
        "height_pixels": height_pixels,
        "corner_order": CORNER_ORDER,
        "corners_wgs84": image_corners,
        "study_window_corners_wgs84": projected_corners(study_affine, study_width, study_height),
    }


def corners_from_georeferencing(metadata: Any, *, study_window: bool = False) -> list[list[float]]:
    """Return validated committed corners without importing Rasterio."""
    if not isinstance(metadata, dict) or metadata.get("version") != GEOREFERENCING_VERSION:
        raise ValueError(f"Missing {GEOREFERENCING_VERSION} metadata")
    if metadata.get("corner_order") != CORNER_ORDER:
        raise ValueError("Georeferencing corner order is invalid")
    key = "study_window_corners_wgs84" if study_window else "corners_wgs84"
    corners = metadata.get(key)
    if not isinstance(corners, list) or len(corners) != 4:
        raise ValueError("Georeferencing must contain four corners")
    validated: list[list[float]] = []
    for point in corners:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError("Each georeferencing corner must be [longitude, latitude]")
        longitude, latitude = point
        if not isinstance(longitude, (int, float)) or not isinstance(latitude, (int, float)):
            raise ValueError("Georeferencing coordinates must be numeric")
        if not isfinite(longitude) or not isfinite(latitude) or not (-180 <= longitude <= 180) or not (-90 <= latitude <= 90):
            raise ValueError("Georeferencing coordinates are outside WGS84 bounds")
        validated.append([float(longitude), float(latitude)])
    return validated
