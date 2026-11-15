"""Detailed Sentinel-2 L2A true-colour crops registered to each site's exact metric study window.

Every crop is warped onto the same grid construction as the terrain analysis: a 10 km square in the
AOI's UTM zone, centred on the AOI centre, north up, 1000 x 1000 px (10 m). Pixels outside the scene
stay nodata, so the reported footprint coverage is exact. (Phase 6 used a clipped window read that
silently stretched a partial tile overlap to the full image; see docs/PHASE7_AUDIT.md.)

Scene selection (search mode): Planetary Computer STAC, collection sentinel-2-l2a, last 365 days,
catalog cloud <= 1 %, footprint polygon containing the AOI, ranked by catalog cloud then recency. A scene is accepted only when it covers
>= 99 % of the AOI, the AOI cloud fraction from the SCL band is <= 5 % and AOI snow is <= 10 %.

Usage (from ``backend/``)::

    python -m app.scripts.acquire_planetary_computer_imagery --site-id earth-ladakh --aoi-id earth-ladakh-aoi-v1
    python -m app.scripts.acquire_planetary_computer_imagery --site-id earth-atacama --aoi-id earth-atacama-aoi-v1 --item-id <STAC id>
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from math import ceil
import time
from urllib.parse import urlsplit

import httpx
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT

from app.services.geospatial_service import GEO_DATA, _analysis_crs, _center_in_crs, load_aoi, sha256_file
from app.services.georeferencing import build_grid_georeferencing

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
SAS_TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/{account}/{container}"
COLLECTION = "sentinel-2-l2a"
MAX_CATALOG_CLOUD = 1
MAX_SCENE_ATTEMPTS = 12
OUTPUT_PX = 1000
PIXEL_M = 10.0
MIN_FOOTPRINT = 0.99
MAX_AOI_CLOUD = 0.05
MAX_AOI_SNOW = 0.10
SCL_NO_DATA, SCL_CLOUD, SCL_SNOW = {0, 1}, {3, 8, 9, 10}, {11}
ALLOWED_ASSET_HOST_SUFFIX = ".blob.core.windows.net"


class Rejected(RuntimeError):
    pass


def _point_in_ring(x: float, y: float, ring: list[list[float]]) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _contains_aoi(item: dict, aoi_ring: list[list[float]]) -> bool:
    """True when the scene's footprint polygon contains every AOI corner (cheap pre-filter)."""
    geometry = item.get("geometry") or {}
    polygons = [geometry["coordinates"]] if geometry.get("type") == "Polygon" else geometry.get("coordinates", []) if geometry.get("type") == "MultiPolygon" else []
    return any(all(_point_in_ring(x, y, [list(p[:2]) for p in polygon[0]]) for x, y in aoi_ring[:-1]) for polygon in polygons)


def _allowed_sites() -> set[str]:
    from app.services.catalog_service import SITES
    return {site.id for site in SITES if site.body.value == "earth" and site.aoi_id}


def _redact(href: str) -> str:
    parts = urlsplit(href)
    return f"{parts.scheme}://{parts.hostname}{parts.path}"


def _request(client: httpx.Client, method: str, url: str, **kwargs) -> httpx.Response:
    """Polite retries: Planetary Computer returns 429 when signing bursts of assets."""
    for attempt in range(6):
        response = client.request(method, url, **kwargs)
        if response.status_code == 429 or response.status_code >= 500:
            time.sleep(min(30, 2 ** attempt + 1))
            continue
        response.raise_for_status()
        return response
    response.raise_for_status()
    return response


class Signer:
    """One SAS token per storage container instead of one sign call per asset."""

    def __init__(self, client: httpx.Client):
        self.client, self.tokens = client, {}

    def __call__(self, href: str) -> str:
        parts = urlsplit(href)
        if parts.scheme != "https" or not (parts.hostname or "").endswith(ALLOWED_ASSET_HOST_SUFFIX):
            raise RuntimeError(f"Refusing unexpected asset host: {parts.hostname!r}")
        key = (parts.hostname.split(".")[0], parts.path.lstrip("/").split("/")[0])
        if key not in self.tokens:
            self.tokens[key] = _request(self.client, "GET", SAS_TOKEN.format(account=key[0], container=key[1])).json()["token"]
        return f"{href}?{self.tokens[key]}"


def _grid(aoi):
    """The analysis grid construction: UTM zone of the AOI centre, square around the centre."""
    crs = _analysis_crs(None, "earth", aoi.center_longitude, aoi.center_latitude)
    cx, cy = _center_in_crs(crs, "earth", aoi.center_longitude, aoi.center_latitude)
    n = ceil(aoi.width_m / PIXEL_M)
    transform = from_origin(cx - n * PIXEL_M / 2, cy + n * PIXEL_M / 2, PIXEL_M, PIXEL_M)
    return crs, transform, n


def _warp(href: str, crs, transform, n: int, resampling: Resampling) -> np.ma.MaskedArray:
    with rasterio.open(href) as source:
        nodata = source.nodata if source.nodata is not None else 0
        with WarpedVRT(source, crs=crs, transform=transform, width=n, height=n, resampling=resampling, nodata=nodata) as vrt:
            return vrt.read(1, masked=True)


def _stretch(values: np.ma.MaskedArray) -> np.ndarray:
    valid = values.compressed().astype(np.float32)
    if valid.size == 0:
        raise Rejected("no valid reflectance in the AOI")
    low, high = np.percentile(valid, [2, 98])
    return np.clip((values.filled(low).astype(np.float32) - low) / max(high - low, 1e-6) * 255, 0, 255).astype("uint8")


def _evaluate(scene: dict, sign: Signer, aoi, enforce: bool) -> dict:
    crs, transform, n = _grid(aoi)
    scl = _warp(sign(scene["assets"]["SCL"]["href"]), crs, transform, n, Resampling.nearest)
    footprint = float((~np.ma.getmaskarray(scl)).mean())
    classes = scl.filled(0)
    valid = ~np.isin(classes, list(SCL_NO_DATA))
    valid_count = int(valid.sum())
    stats = {
        "aoi_coverage_fraction": round(footprint, 4),
        "aoi_valid_pixel_fraction": round(valid_count / classes.size, 4),
        "aoi_cloud_fraction": round(float(np.isin(classes, list(SCL_CLOUD)).sum()) / valid_count, 4) if valid_count else None,
        "aoi_snow_fraction": round(float(np.isin(classes, list(SCL_SNOW)).sum()) / valid_count, 4) if valid_count else None,
    }
    if enforce:
        if footprint < MIN_FOOTPRINT:
            raise Rejected(f"footprint covers {footprint:.1%} of the AOI")
        if stats["aoi_cloud_fraction"] is None or stats["aoi_cloud_fraction"] > MAX_AOI_CLOUD:
            raise Rejected(f"AOI cloud {stats['aoi_cloud_fraction']}")
        if stats["aoi_snow_fraction"] is not None and stats["aoi_snow_fraction"] > MAX_AOI_SNOW:
            raise Rejected(f"AOI snow {stats['aoi_snow_fraction']}")
    bands = [_warp(sign(scene["assets"][key]["href"]), crs, transform, n, Resampling.bilinear) for key in ("B04", "B03", "B02")]
    rgb = np.stack([_stretch(band) for band in bands])
    return {"stats": stats, "rgb": rgb, "crs": crs, "transform": transform, "n": n}


def acquire(site_id: str, aoi_id: str, item_id: str | None = None) -> dict:
    if site_id not in _allowed_sites():
        raise ValueError(f"Unsupported site for Sentinel-2 acquisition: {site_id}")
    aoi = load_aoi(aoi_id)
    if aoi.site_id != site_id:
        raise ValueError("AOI does not belong to the requested site")
    rejected: list[str] = []
    with httpx.Client(timeout=90, follow_redirects=False) as client:
        sign = Signer(client)
        if item_id:
            candidates, enforce = [_request(client, "GET", f"{STAC}/collections/{COLLECTION}/items/{item_id}").json()], False
        else:
            now = datetime.now(timezone.utc)
            query = {"collections": [COLLECTION], "intersects": aoi.geometry, "limit": 100,
                     "datetime": f"{(now - timedelta(days=365)).isoformat()}/{now.isoformat()}",
                     "query": {"eo:cloud_cover": {"lte": MAX_CATALOG_CLOUD}}}
            features = _request(client, "POST", f"{STAC}/search", json=query).json().get("features", [])
            features = [f for f in features if _contains_aoi(f, aoi.geometry["coordinates"][0])]
            candidates = sorted(features, key=lambda f: (float(f["properties"].get("eo:cloud_cover", 100)), -datetime.fromisoformat(f["properties"]["datetime"].replace("Z", "+00:00")).timestamp()))[:MAX_SCENE_ATTEMPTS]
            enforce = True
        for scene in candidates:
            try:
                result = _evaluate(scene, sign, aoi, enforce)
                break
            except Rejected as error:
                rejected.append(f"{scene['id']}: {error}")
            except rasterio.errors.RasterioError as error:
                rejected.append(f"{scene['id']}: read failed ({str(error)[:80]})")
        else:
            raise RuntimeError("No scene met the AOI coverage/cloud/snow rules: " + "; ".join(rejected))
    output_dir = GEO_DATA / "processed" / "imagery"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{site_id}-sentinel-reference.png"
    with rasterio.open(output_path, "w", driver="PNG", width=result["n"], height=result["n"], count=3, dtype="uint8",
                       crs=result["crs"], transform=result["transform"]) as out:
        out.write(result["rgb"])
    props = scene["properties"]
    scene_url = f"{STAC}/collections/{COLLECTION}/items/{scene['id']}"
    acquired = props.get("datetime")
    ring = aoi.geometry["coordinates"][0]
    georeferencing = build_grid_georeferencing(
        result["crs"], result["transform"], result["n"], result["n"], body="earth"
    )
    metadata = {
        "imagery_id": f"{site_id}-sentinel-2-reference", "site_id": site_id, "body": "earth", "mode": "reference",
        "provider": "Copernicus Sentinel-2 L2A via Microsoft Planetary Computer", "collection": COLLECTION, "product_id": scene["id"],
        "acquisition_datetime": acquired, "publication_datetime": None, "resolution_m": 10, "cloud_cover_pct": props.get("eo:cloud_cover"),
        "processing_level": "Level-2A surface reflectance, true colour B04/B03/B02, 2-98 % stretch",
        "bbox": [min(p[0] for p in ring), min(p[1] for p in ring), max(p[0] for p in ring), max(p[1] for p in ring)], "aoi_id": aoi.aoi_id,
        "preview_url": f"/api/imagery-assets/{site_id}-sentinel-reference.png", "tile_url": None,
        "attribution": f"Contains modified Copernicus Sentinel data ({(acquired or '')[:4]}), processed via Microsoft Planetary Computer",
        "official_source_url": scene_url, "source_download_url": scene_url, "cache_status": "verified_local_crop",
        "cache_date": datetime.now(timezone.utc).isoformat(), "data_status": "available",
        "limitations": ["Display imagery only; the score uses the elevation model, not these pixels.",
                        "Scene-wide cloud is the catalog value for the whole ~110 km tile; AOI cloud and snow come from the SCL band over the AOI.",
                        "Footprint coverage is the share of the AOI inside the scene. It is not a clear-sky fraction."],
        "display_resolution_m": PIXEL_M, **result["stats"],
        "aoi_coverage_meaning": "Share of the AOI footprint inside the scene with valid data. It is NOT a clear-sky fraction.",
        "aoi_statistics_method": "SCL band (20 m) warped with nearest neighbour onto the AOI grid: cloud = classes 3, 8, 9, 10; snow = 11; invalid = 0, 1.",
        "registration": {"grid": "AOI-centred UTM square identical in construction to the terrain analysis grid", "crs": str(result["crs"]),
                         "pixel_m": PIXEL_M, "pixels": result["n"]},
        "georeferencing": georeferencing,
        "preview_checksum": sha256_file(output_path), "source_crs": props.get("proj:epsg") and f"EPSG:{props.get('proj:epsg')}",
        "native_resolution": [10.0, 10.0], "selection_rejections": rejected[:10],
    }
    (output_dir / f"{site_id}-sentinel-reference.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8", newline="\n")
    selection = {"site_id": site_id, "aoi_id": aoi.aoi_id, "provider": metadata["provider"], "collection": COLLECTION,
                 "discovered_at": datetime.now(timezone.utc).isoformat(), "retrieval_status": "verified_local_rgb_crop",
                 "selected_scene": {"product_id": scene["id"], "acquisition_datetime": acquired, "cloud_cover_pct": props.get("eo:cloud_cover"),
                                    "processing_level": "Sentinel-2 Level-2A", "asset_keys": ["B02", "B03", "B04", "SCL"],
                                    "official_stac_record": scene_url, "preview_checksum": metadata["preview_checksum"],
                                    "output_resolution_m": PIXEL_M, **result["stats"]}}
    (GEO_DATA / "imagery" / f"{site_id}.sentinel-selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8", newline="\n")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire an AOI-registered Sentinel-2 L2A true-colour crop")
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--aoi-id", required=True)
    parser.add_argument("--item-id", default=None, help="Re-derive an already selected STAC item (no cloud/coverage gate)")
    args = parser.parse_args()
    result = acquire(args.site_id, args.aoi_id, args.item_id)
    print(json.dumps({k: result[k] for k in ("site_id", "product_id", "acquisition_datetime", "cloud_cover_pct", "aoi_coverage_fraction", "aoi_cloud_fraction", "aoi_snow_fraction")}))


if __name__ == "__main__":
    main()
