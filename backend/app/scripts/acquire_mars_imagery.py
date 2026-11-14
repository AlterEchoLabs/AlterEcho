import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import httpx
import numpy as np

from app.services.geospatial_service import GEO_DATA, _center_in_crs, load_aoi, sha256_file


PRODUCT_ID = "JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0"
SOURCE_URL = f"https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/{PRODUCT_ID}.tif"
SOURCE_PAGE = "https://astrogeology.usgs.gov/search/map/mars_2020_terrain_relative_navigation_context_camera_orthorectified_image_mosaic"
MAX_BYTES = 100 * 1024 * 1024


def acquire(output_root: Path = GEO_DATA) -> dict:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.windows import from_bounds as window_from_bounds

    aoi = load_aoi("mars-jezero-aoi-v1")
    cache_dir = output_root / "cache" / "imagery"; cache_dir.mkdir(parents=True, exist_ok=True)
    source_path = cache_dir / f"{PRODUCT_ID}.tif"
    if not source_path.exists():
        with httpx.stream("GET", SOURCE_URL, timeout=60, follow_redirects=True) as response:
            response.raise_for_status()
            declared = int(response.headers.get("content-length", 0))
            if declared and declared > MAX_BYTES:
                raise ValueError("Remote imagery exceeds the configured 100 MB download limit")
            size = 0
            with source_path.open("wb") as output:
                for chunk in response.iter_bytes(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        output.close(); source_path.unlink(missing_ok=True)
                        raise ValueError("Remote imagery exceeded the configured 100 MB download limit")
                    output.write(chunk)
    source_checksum = sha256_file(source_path)
    preview_dir = output_root / "processed" / "imagery"; preview_dir.mkdir(parents=True, exist_ok=True)
    preview_path = preview_dir / "mars-jezero-ctx-reference.png"
    with rasterio.open(source_path) as dataset:
        if not dataset.crs or not dataset.crs.is_projected:
            raise ValueError("Official Mars imagery must have a projected planetary CRS")
        center_x, center_y = _center_in_crs(dataset.crs, "mars", aoi.center_longitude, aoi.center_latitude)
        bounds = (center_x - aoi.width_m / 2, center_y - aoi.height_m / 2, center_x + aoi.width_m / 2, center_y + aoi.height_m / 2)
        window = window_from_bounds(*bounds, transform=dataset.transform)
        data = dataset.read(1, window=window, out_shape=(1000, 1000), masked=True, resampling=Resampling.bilinear)
        valid = ~np.ma.getmaskarray(data)
        if valid.mean() < 0.9:
            raise ValueError("Official imagery covers less than 90% of the registered AOI")
        values = data.compressed().astype(float)
        low, high = np.percentile(values, [2, 98])
        display = np.clip((data.filled(low) - low) / max(high - low, 1e-9) * 255, 0, 255).astype("uint8")
        transform = from_bounds(*bounds, 1000, 1000)
        with rasterio.open(preview_path, "w", driver="PNG", width=1000, height=1000, count=1, dtype="uint8", crs=dataset.crs, transform=transform) as output:
            output.write(display, 1)
        native_resolution = list(dataset.res); source_crs = str(dataset.crs)
    metadata = {
        "imagery_id": "mars-jezero-ctx-reference", "site_id": "mars-jezero", "body": "mars", "mode": "reference",
        "provider": "USGS Astrogeology Science Center / NASA PDS", "collection": "Mars 2020 CTX orthorectified image mosaic",
        "product_id": PRODUCT_ID, "acquisition_datetime": None, "publication_datetime": "2020-07-24T00:00:00Z",
        "resolution_m": 6.0, "display_resolution_m": 10.0, "cloud_cover_pct": None, "processing_level": "Orthorectified CTX mosaic",
        "bbox": [min(p[0] for p in aoi.geometry["coordinates"][0]), min(p[1] for p in aoi.geometry["coordinates"][0]), max(p[0] for p in aoi.geometry["coordinates"][0]), max(p[1] for p in aoi.geometry["coordinates"][0])],
        "aoi_id": aoi.aoi_id, "preview_url": "/api/imagery-assets/mars-jezero-ctx-reference.png", "tile_url": None,
        "attribution": "USGS Astrogeology Science Center / NASA PDS; CTX aboard Mars Reconnaissance Orbiter",
        "official_source_url": SOURCE_PAGE, "source_download_url": SOURCE_URL, "cache_status": "cached",
        "cache_date": datetime.now(timezone.utc).isoformat(), "data_status": "available",
        "source_checksum": source_checksum, "preview_checksum": sha256_file(preview_path), "source_crs": source_crs,
        "native_resolution": native_resolution, "aoi_coverage_fraction": float(valid.mean()),
        "limitations": ["Grayscale planetary reference imagery; it is not an Earth satellite basemap.", "Acquisition time is not represented because the mosaic combines CTX observations; publication date is recorded separately.", "The display preview is contrast-stretched and resampled to 10 m for visualization."],
    }
    metadata_path = preview_dir / "mars-jezero-ctx-reference.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main() -> None:
    argparse.ArgumentParser(description="Download and clip the official Jezero CTX orthomosaic to the registered AOI").parse_args()
    result = acquire()
    print(json.dumps({key: result[key] for key in ("product_id", "publication_datetime", "resolution_m", "source_checksum", "preview_checksum", "aoi_coverage_fraction")}, indent=2))


if __name__ == "__main__":
    main()
