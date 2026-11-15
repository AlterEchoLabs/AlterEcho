"""USGS Astrogeology controlled CTX DTMs (STAC collection mro_ctx_controlled_usgs_dtms): discovery and windowed reads.

Products are cloud-optimised GeoTIFFs (CC0-1.0, DOI 10.5066/P9JKVWR3) on an equirectangular Mars-sphere grid true to
scale at the equator. Windows are read with HTTP range requests and reprojected once onto a local equirectangular
grid true to scale at the window latitude (R = 3,396,190 m), so 60 m cells are 60 m on the ground in both directions.
Nothing is bulk-downloaded.
"""

from __future__ import annotations

from math import cos, radians
from typing import Any
from urllib.parse import urlsplit

import httpx
import numpy as np

STAC = "https://stac.astrogeology.usgs.gov/api"
COLLECTION = "mro_ctx_controlled_usgs_dtms"
ALLOWED_HOSTS = {"astrogeo-ard.s3-us-west-2.amazonaws.com", "astrogeo-ard.s3.us-west-2.amazonaws.com"}
MARS_RADIUS_M = 3_396_190.0
M_PER_DEG = MARS_RADIUS_M * np.pi / 180.0
DEM_ASSETS = ("geoid_adjusted_dem", "dtm", "dem")


def local_crs(lat: float, lon: float):
    from rasterio.crs import CRS
    return CRS.from_proj4(f"+proj=eqc +lat_ts={lat:.6f} +lat_0=0 +lon_0={lon:.6f} +x_0=0 +y_0=0 +R={MARS_RADIUS_M:.0f} +units=m +no_defs")


def checked_href(href: str) -> str:
    host = urlsplit(href).hostname or ""
    if urlsplit(href).scheme != "https" or host not in ALLOWED_HOSTS:
        raise ValueError(f"Unexpected asset host: {host}")
    return href


def search(client: httpx.Client, lat: float, lon: float, half_m: float) -> list[dict[str, Any]]:
    dlat = half_m / M_PER_DEG
    dlon = dlat / max(cos(radians(lat)), 1e-6)
    body = {"collections": [COLLECTION], "bbox": [lon - dlon, lat - dlat, lon + dlon, lat + dlat], "limit": 50}
    features = client.post(f"{STAC}/search", json=body).raise_for_status().json().get("features", [])
    inside = [f for f in features if f["bbox"][0] <= lon - dlon and f["bbox"][2] >= lon + dlon and f["bbox"][1] <= lat - dlat and f["bbox"][3] >= lat + dlat]
    return inside


def dem_asset(item: dict) -> tuple[str, str]:
    for key in DEM_ASSETS:
        if key in item["assets"]:
            return key, checked_href(item["assets"][key]["href"])
    raise ValueError(f"{item['id']}: no DEM asset")


def read_local(href: str, lat: float, lon: float, extent_m: float, resolution_m: float, resampling: str = "bilinear", band: int = 1) -> tuple[np.ndarray, Any, Any]:
    """Reproject a window of a remote COG onto a north-up local grid centred on lat/lon. NaN outside valid data."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.warp import reproject

    crs = local_crs(lat, lon)
    n = int(round(extent_m / resolution_m))
    half = n * resolution_m / 2
    # lat_0 = 0, so the window centre's northing is R * lat in radians.
    cy = MARS_RADIUS_M * radians(lat)
    transform = from_origin(-half, cy + half, resolution_m, resolution_m)
    out = np.full((n, n), np.nan, dtype="float64")
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_TIMEOUT="60"):
        with rasterio.open(f"/vsicurl/{href}") as src:
            reproject(source=rasterio.band(src, band), destination=out, src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
                      dst_transform=transform, dst_crs=crs, dst_nodata=np.nan, resampling=getattr(Resampling, resampling))
            meta = {"src_crs": src.crs.to_wkt(), "src_res": list(src.res), "src_nodata": src.nodata, "src_dtype": src.dtypes[0]}
    return out, transform, {**meta, "crs": crs.to_wkt()}
