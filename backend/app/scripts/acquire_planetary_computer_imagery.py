import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import httpx
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.windows import from_bounds as window_from_bounds
from rasterio.warp import transform_bounds

from app.services.geospatial_service import GEO_DATA, load_aoi, sha256_file


STAC_SEARCH = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
STAC_SIGN = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
COLLECTION = "sentinel-2-l2a"
SCENE_ID = "S2C_MSIL2A_20261111T144731_R139_T19KDP_20261111T180413"
MAX_CLOUD = 1
OUTPUT_SIZE = 1000


def _scene_key(feature: dict) -> tuple[float, str]:
    properties = feature.get("properties", {})
    return (float(properties.get("eo:cloud_cover", 100)), properties.get("datetime", ""))


def _find_scene(client: httpx.Client, aoi_geometry: dict) -> dict:
    now = datetime.now(timezone.utc)
    query = {
        "collections": [COLLECTION],
        "intersects": aoi_geometry,
        "datetime": f"{(now - timedelta(days=365)).isoformat()}/{now.isoformat()}",
        "query": {"eo:cloud_cover": {"lte": MAX_CLOUD}},
        "limit": 100,
    }
    response = client.post(STAC_SEARCH, json=query)
    response.raise_for_status()
    features = response.json().get("features", [])
    if not features:
        raise RuntimeError("Planetary Computer returned no Sentinel-2 scene under the cloud threshold")
    return sorted(features, key=_scene_key)[0]


def _signed_asset(client: httpx.Client, scene: dict, key: str) -> str:
    asset = scene.get("assets", {}).get(key)
    if not asset or not asset.get("href"):
        raise RuntimeError(f"Selected scene does not provide the required {key} asset")
    response = client.get(STAC_SIGN, params={"href": asset["href"]})
    response.raise_for_status()
    return response.json()["href"]


def _stretch(values: np.ma.MaskedArray) -> np.ndarray:
    valid = values.compressed().astype(np.float32)
    if valid.size == 0:
        raise RuntimeError("Selected band contains no valid pixels in the registered AOI")
    low, high = np.percentile(valid, [2, 98])
    return np.clip((values.filled(low) - low) / max(high - low, 1e-6) * 255, 0, 255).astype("uint8")


def acquire(site_id: str = "earth-atacama", aoi_id: str = "earth-atacama-aoi-v1") -> dict:
    aoi = load_aoi(aoi_id)
    if aoi.site_id != site_id:
        raise ValueError("AOI does not belong to the requested site")
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        scene = _find_scene(client, aoi.geometry)
        signed = {key: _signed_asset(client, scene, key) for key in ("B04", "B03", "B02")}
        with rasterio.open(signed["B04"]) as dataset:
            if not dataset.crs:
                raise RuntimeError("Selected Sentinel-2 band has no CRS")
            bounds = transform_bounds(
                "EPSG:4326",
                dataset.crs,
                min(point[0] for point in aoi.geometry["coordinates"][0]),
                min(point[1] for point in aoi.geometry["coordinates"][0]),
                max(point[0] for point in aoi.geometry["coordinates"][0]),
                max(point[1] for point in aoi.geometry["coordinates"][0]),
            )
            window = window_from_bounds(*bounds, transform=dataset.transform)
            bands = []
            valid_masks = []
            for key in ("B04", "B03", "B02"):
                with rasterio.open(signed[key]) as band:
                    values = band.read(
                        1,
                        window=window,
                        out_shape=(OUTPUT_SIZE, OUTPUT_SIZE),
                        masked=True,
                        resampling=Resampling.bilinear,
                    )
                    bands.append(_stretch(values))
                    valid_masks.append(~np.ma.getmaskarray(values))
            coverage = float(np.logical_and.reduce(valid_masks).mean())
            if coverage < 0.9:
                raise RuntimeError(f"Selected Sentinel-2 scene covers only {coverage:.1%} of the AOI")
            output_dir = GEO_DATA / "processed" / "imagery"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{site_id}-sentinel-reference.png"
            transform = from_bounds(*bounds, OUTPUT_SIZE, OUTPUT_SIZE)
            with rasterio.open(
                output_path,
                "w",
                driver="PNG",
                width=OUTPUT_SIZE,
                height=OUTPUT_SIZE,
                count=3,
                dtype="uint8",
                crs=dataset.crs,
                transform=transform,
            ) as output:
                output.write(np.stack(bands))
            source_crs = str(dataset.crs)
            native_resolution = list(dataset.res)
    scene_properties = scene.get("properties", {})
    scene_url = next((link.get("href") for link in scene.get("links", []) if link.get("rel") == "self"), None)
    metadata = {
        "imagery_id": f"{site_id}-sentinel-2-reference",
        "site_id": site_id,
        "body": "earth",
        "mode": "reference",
        "provider": "Microsoft Planetary Computer / Sentinel-2 L2A",
        "collection": COLLECTION,
        "product_id": scene.get("id"),
        "acquisition_datetime": scene_properties.get("datetime"),
        "publication_datetime": None,
        "resolution_m": 10,
        "cloud_cover_pct": scene_properties.get("eo:cloud_cover"),
        "processing_level": "Level-2A true-colour crop (B04/B03/B02)",
        "bbox": [min(point[0] for point in aoi.geometry["coordinates"][0]), min(point[1] for point in aoi.geometry["coordinates"][0]), max(point[0] for point in aoi.geometry["coordinates"][0]), max(point[1] for point in aoi.geometry["coordinates"][0])],
        "aoi_id": aoi.aoi_id,
        "preview_url": f"/api/imagery-assets/{site_id}-sentinel-reference.png",
        "tile_url": None,
        "attribution": "Copernicus Sentinel data (2026), processed via Microsoft Planetary Computer",
        "official_source_url": scene_url or "https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a",
        "source_download_url": scene_url,
        "cache_status": "verified_local_crop",
        "cache_date": datetime.now(timezone.utc).isoformat(),
        "data_status": "available",
        "limitations": ["True-colour display crop; terrain scoring continues to use the registered DEM.", "Signed source URLs are used only during acquisition; the demo serves this local crop."],
        "display_resolution_m": 10,
        "aoi_coverage_fraction": coverage,
        "preview_checksum": sha256_file(output_path),
        "source_crs": source_crs,
        "native_resolution": native_resolution,
    }
    (output_dir / f"{site_id}-sentinel-reference.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    selection = {
        "site_id": site_id,
        "aoi_id": aoi.aoi_id,
        "provider": metadata["provider"],
        "collection": COLLECTION,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "retrieval_status": "verified_local_rgb_crop",
        "selected_scene": {
            "product_id": scene.get("id"),
            "acquisition_datetime": scene_properties.get("datetime"),
            "cloud_cover_pct": scene_properties.get("eo:cloud_cover"),
            "processing_level": "Sentinel-2 Level-2A",
            "asset_keys": ["B02", "B03", "B04"],
            "official_stac_record": scene_url,
            "preview_checksum": metadata["preview_checksum"],
            "output_resolution_m": metadata["display_resolution_m"],
            "aoi_coverage_fraction": coverage,
        },
    }
    (GEO_DATA / "imagery" / f"{site_id}.sentinel-selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire a signed Planetary Computer Sentinel-2 true-colour AOI crop")
    parser.add_argument("--site-id", default="earth-atacama")
    parser.add_argument("--aoi-id", default="earth-atacama-aoi-v1")
    args = parser.parse_args()
    result = acquire(args.site_id, args.aoi_id)
    print(json.dumps({key: result[key] for key in ("product_id", "cloud_cover_pct", "preview_checksum", "aoi_coverage_fraction")}, indent=2))


if __name__ == "__main__":
    main()
