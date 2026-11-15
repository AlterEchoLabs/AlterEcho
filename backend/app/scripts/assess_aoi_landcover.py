"""Land-cover check of every processed Earth AOI with ESA WorldCover 10 m v200 (2021).

Purpose: find built infrastructure inside the study windows (the Atacama window visibly contains a
large industrial complex). Built-up cells (class 50) can then be excluded from terrain features.
WorldCover is a 2021 classification; SRTM elevation dates from February 2000, so excluding cells
that were built after 2000 only removes data (conservative) and never adds a structure to the DEM.
Mine pits, heaps and graded ground are often classed as bare (60) and are NOT detected by this check.

Writes data/processed/landcover/<site>.worldcover-v200.tif (clip incl. halo, EPSG:4326, uint8) and
<site>.worldcover-v200.json (item ID, version, class fractions inside the core AOI, checksum).
Reads only the window from the provider's cloud-optimised GeoTIFF; nothing is bulk-downloaded.

Usage (from backend/):  python -m app.scripts.assess_aoi_landcover
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from math import cos, radians
from urllib.parse import urlsplit

import httpx
import numpy as np

from app.services.catalog_service import SITES
from app.services.geospatial_service import GEO_DATA, canonical_text_sha256, load_aoi, sha256_file

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/token/{account}/{container}"
OUT = GEO_DATA / "processed" / "landcover"
HALO_M = 1200.0
CLASSES = {10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland", 50: "Built-up", 60: "Bare / sparse vegetation",
           70: "Snow and ice", 80: "Permanent water bodies", 90: "Herbaceous wetland", 95: "Mangroves", 100: "Moss and lichen"}
ATTRIBUTION = "© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium"


def _sign(client: httpx.Client, href: str) -> str:
    parts = urlsplit(href)
    if parts.scheme != "https" or not (parts.hostname or "").endswith(".blob.core.windows.net"):
        raise RuntimeError("Unexpected asset host")
    account, container = parts.hostname.split(".")[0], parts.path.lstrip("/").split("/")[0]
    token = client.get(SAS.format(account=account, container=container)).raise_for_status().json()["token"]
    return f"{href}?{token}"


def assess(site_id: str, client: httpx.Client) -> dict:
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.merge import merge
    from rasterio.windows import from_bounds

    site = next(s for s in SITES if s.id == site_id)
    aoi = load_aoi(site.aoi_id)
    geometry = json.loads((GEO_DATA / "aoi" / f"{site.aoi_id}.geojson").read_text(encoding="utf-8"))["geometry"]
    lat, lon = aoi.center_latitude, aoi.center_longitude
    half_lat = (aoi.height_m / 2 + HALO_M) / 111_320.0
    half_lon = (aoi.width_m / 2 + HALO_M) / (111_320.0 * cos(radians(lat)))
    bounds = (lon - half_lon, lat - half_lat, lon + half_lon, lat + half_lat)
    items = client.post(f"{STAC}/search", json={"collections": ["esa-worldcover"], "bbox": list(bounds), "limit": 20}).raise_for_status().json()["features"]
    items = [i for i in items if i["properties"].get("esa_worldcover:product_version") == "2.0.0"]
    if not items:
        raise RuntimeError(f"No WorldCover v200 item intersects {site_id}")
    datasets = [rasterio.open(_sign(client, i["assets"]["map"]["href"])) for i in items]
    try:
        array, transform = merge(datasets, bounds=bounds, nodata=0)
        crs = datasets[0].crs
    finally:
        for d in datasets:
            d.close()
    clip = array[0].astype("uint8")
    OUT.mkdir(parents=True, exist_ok=True)
    tif = OUT / f"{site_id}.worldcover-v200.tif"
    with rasterio.open(tif, "w", driver="GTiff", height=clip.shape[0], width=clip.shape[1], count=1, dtype="uint8", crs=crs,
                       transform=transform, nodata=0, compress="deflate") as dst:
        dst.write(clip, 1)
    inside = ~geometry_mask([geometry], out_shape=clip.shape, transform=transform, invert=False)
    values = clip[inside & (clip > 0)]
    counts = {int(k): int(v) for k, v in zip(*np.unique(values, return_counts=True))}
    total = int(values.size)
    fractions = {CLASSES.get(k, str(k)): round(v / total, 6) for k, v in sorted(counts.items())} if total else {}
    record = {
        "site_id": site_id, "aoi_id": site.aoi_id, "product": "ESA WorldCover 10 m v200", "collection": "esa-worldcover",
        "item_ids": [i["id"] for i in items], "product_version": "2.0.0", "reference_year": 2021, "pixel_size": "10 m (1/12000 deg)",
        "provider": "ESA via Microsoft Planetary Computer", "licence": "CC-BY-4.0", "attribution": ATTRIBUTION,
        "official_stac_records": [f"{STAC}/collections/esa-worldcover/items/{i['id']}" for i in items],
        "core_pixel_count": total, "class_fractions_core": fractions, "built_up_fraction_core": round(counts.get(50, 0) / total, 6) if total else None,
        "clip_file": f"data/processed/landcover/{tif.name}", "clip_sha256": sha256_file(tif),
        "limitations": ["WorldCover is a 2021 classification with a stated global accuracy near 77 %; class errors are not quantified per AOI here.",
                        "Mine pits, heaps and graded ground are usually classed as bare/sparse (60), so this check under-detects mining disturbance.",
                        "SRTM elevation dates from February 2000; built-up land mapped in 2021 may postdate the DEM."],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = OUT / f"{site_id}.worldcover-v200.json"
    path.write_text(json.dumps(record, indent=2), encoding="utf-8", newline="\n")
    path.with_suffix(".sha256").write_text(canonical_text_sha256(path), encoding="ascii", newline="\n")
    return record


def main() -> None:
    earth = [s.id for s in SITES if s.body.value == "earth" and s.data_status.value == "real_processed"]
    with httpx.Client(timeout=120, follow_redirects=False, headers={"User-Agent": "TerraLuna-analysis/1.0"}) as client:
        for site_id in earth:
            r = assess(site_id, client)
            print(f"{site_id:28s} built-up {r['built_up_fraction_core']:.4%}  {r['class_fractions_core']}")


if __name__ == "__main__":
    main()
