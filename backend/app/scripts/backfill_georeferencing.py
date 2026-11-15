"""Backfill exact, versioned georeferencing into committed display artifacts.

This migration uses the same registered AOI centre, projected CRS and pixel grid as
the original preprocessors.  It does not read or alter scientific measurements.
Future acquisitions write the same metadata directly.
"""

from __future__ import annotations

import json
from math import ceil

from rasterio.crs import CRS
from rasterio.transform import from_origin

from app.services.catalog_service import get_site
from app.services.georeferencing import build_grid_georeferencing
from app.services.geospatial_service import GEO_DATA, _center_in_crs, load_aoi


def _write(path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")


def backfill_sentinel_metadata() -> list[str]:
    updated: list[str] = []
    imagery_dir = GEO_DATA / "processed" / "imagery"
    for path in sorted(imagery_dir.glob("earth-*-sentinel-reference.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        aoi = load_aoi(payload["aoi_id"])
        registration = payload["registration"]
        crs = CRS.from_user_input(registration["crs"])
        pixels = int(registration["pixels"])
        pixel_m = float(registration["pixel_m"])
        cx, cy = _center_in_crs(crs, "earth", aoi.center_longitude, aoi.center_latitude)
        affine = from_origin(cx - pixels * pixel_m / 2, cy + pixels * pixel_m / 2, pixel_m, pixel_m)
        payload["georeferencing"] = build_grid_georeferencing(crs, affine, pixels, pixels, body="earth")
        _write(path, payload)
        updated.append(path.name)
    return updated


def backfill_layer_metadata() -> list[str]:
    updated: list[str] = []
    preview_dir = GEO_DATA / "processed" / "terrain-preview"
    for path in sorted(preview_dir.glob("*.layers.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        site = get_site(payload["site_id"])
        if not site or not site.aoi_id:
            raise ValueError(f"Unknown registered site for {path.name}")
        aoi = load_aoi(site.aoi_id)
        heightmap = json.loads((preview_dir / f"{site.id}.heightmap.json").read_text(encoding="utf-8"))
        crs = CRS.from_user_input(heightmap["crs"])
        resolution_m = float(payload["resolution_m"])
        pixels = int(payload["pixels"])
        cx, cy = _center_in_crs(crs, aoi.planetary_body, aoi.center_longitude, aoi.center_latitude)
        image_affine = from_origin(cx - pixels * resolution_m / 2, cy + pixels * resolution_m / 2, resolution_m, resolution_m)
        study_columns = ceil(aoi.width_m / resolution_m)
        study_rows = ceil(aoi.height_m / resolution_m)
        study_affine = from_origin(
            cx - aoi.width_m / 2,
            cy + aoi.height_m / 2,
            aoi.width_m / study_columns,
            aoi.height_m / study_rows,
        )
        payload["georeferencing"] = build_grid_georeferencing(
            crs,
            image_affine,
            pixels,
            pixels,
            body=aoi.planetary_body,
            study_window_affine=study_affine,
            study_window_width_pixels=study_columns,
            study_window_height_pixels=study_rows,
        )
        _write(path, payload)
        updated.append(path.name)
    return updated


def main() -> None:
    imagery = backfill_sentinel_metadata()
    layers = backfill_layer_metadata()
    print(json.dumps({"imagery_metadata": imagery, "layer_metadata": layers}, indent=2))


if __name__ == "__main__":
    main()
