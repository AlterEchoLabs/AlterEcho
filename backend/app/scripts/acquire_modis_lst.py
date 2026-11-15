"""Earth thermal evidence: MODIS Aqua MYD11A2 v061 8-day land-surface temperature over each AOI.

What is measured
    Land-surface (skin) temperature retrieved from thermal infrared, Kelvin, 1 km grid, from the
    Aqua platform whose equator crossings are near 13:30 (day) and 01:30 (night) local solar time.
    The per-pixel view time is read and summarised so the local-time match to the Mars MEDA
    windows can be audited rather than assumed.

What it is not
    Not air temperature, not a daily extreme, not a climatology. 8-day composites favour
    clear-sky retrievals, so cloudy-season temperatures are under-represented.

Processing
    For every MYD11A2 composite in the observation period, the AOI polygon is projected into the
    MODIS sinusoidal grid and the intersecting window is read from the cloud-optimised GeoTIFFs
    (Microsoft Planetary Computer, collection ``modis-11A2-061``). Pixels are kept when the
    mandatory QA is 0 or 1 *and* the LST error flag is <= 2 K. The AOI value of a composite is the
    mean of kept pixels, and only when kept pixels cover >= 50 % of the AOI. A SHA-256 of the
    extracted raw arrays is stored per composite so the extraction is reproducible.

Usage (from ``backend/``)::

    python -m app.scripts.acquire_modis_lst                     # all three Earth AOIs, calendar 2024
    python -m app.scripts.acquire_modis_lst --site-id earth-atacama
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import json
from urllib.parse import urlsplit

import httpx
import numpy as np

from app.services.geospatial_service import GEO_DATA, load_aoi

STAC_SEARCH = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SAS_TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/{account}/{container}"
COLLECTION = "modis-11A2-061"
PRODUCT_PREFIX = "MYD11A2."  # Aqua only: keeps the ~13:30 / ~01:30 local solar time pair
ALLOWED_ASSET_HOST_SUFFIX = ".blob.core.windows.net"
def _catalog_sites() -> dict[str, str]:
    from app.services.catalog_service import SITES as CATALOG
    return {site.id: site.aoi_id for site in CATALOG if site.body.value == "earth" and site.aoi_id and site.data_status.value == "real_processed"}


SITES = _catalog_sites()
ASSETS = ("LST_Day_1km", "LST_Night_1km", "QC_Day", "QC_Night", "Day_view_time", "Night_view_time")
MIN_AOI_FRACTION = 0.5
LST_SCALE = 0.02
VIEW_TIME_SCALE = 0.1
OUTPUT_DIR = GEO_DATA / "processed" / "evidence"


def _check_host(href: str) -> None:
    parts = urlsplit(href)
    if parts.scheme != "https" or not (parts.hostname or "").endswith(ALLOWED_ASSET_HOST_SUFFIX):
        raise RuntimeError(f"Refusing unexpected asset host: {parts.hostname!r}")


def _search(client: httpx.Client, geometry: dict, period: str) -> list[dict]:
    features, body = [], {"collections": [COLLECTION], "intersects": geometry, "datetime": period, "limit": 200}
    url = STAC_SEARCH
    while url:
        response = client.post(url, json=body)
        response.raise_for_status()
        payload = response.json()
        features += payload.get("features", [])
        nxt = next((link for link in payload.get("links", []) if link.get("rel") == "next"), None)
        url, body = (nxt["href"], nxt.get("body", body)) if nxt else (None, None)
        if len(features) > 2000:
            raise RuntimeError("Unexpectedly large STAC result; refusing to continue")
    return [item for item in features if item["id"].startswith(PRODUCT_PREFIX)]


def _token(client: httpx.Client, href: str, cache: dict[str, str]) -> str:
    _check_host(href)
    parts = urlsplit(href)
    account = parts.hostname.split(".")[0]
    container = parts.path.lstrip("/").split("/")[0]
    key = f"{account}/{container}"
    if key not in cache:
        response = client.get(SAS_TOKEN.format(account=account, container=container))
        response.raise_for_status()
        cache[key] = response.json()["token"]
    return cache[key]


def _qc_ok(qc: np.ndarray) -> np.ndarray:
    mandatory = qc & 0b11
    lst_error = (qc >> 6) & 0b11
    return (mandatory <= 1) & (lst_error <= 1)


def _read_item(item: dict, aoi_geometry: dict, token: str) -> dict:
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.warp import transform_geom
    from rasterio.windows import from_bounds

    arrays: dict[str, np.ndarray] = {}
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT="60", GDAL_HTTP_MAX_RETRY="3"):
        first = item["assets"][ASSETS[0]]["href"]
        with rasterio.open(f"{first}?{token}") as dataset:
            projected = transform_geom("EPSG:4326", dataset.crs, aoi_geometry)
            xs = [point[0] for point in projected["coordinates"][0]]
            ys = [point[1] for point in projected["coordinates"][0]]
            window = from_bounds(min(xs), min(ys), max(xs), max(ys), transform=dataset.transform).round_offsets().round_lengths()
            window = window.intersection(rasterio.windows.Window(0, 0, dataset.width, dataset.height))
            transform = dataset.window_transform(window)
            inside = ~geometry_mask([projected], out_shape=(int(window.height), int(window.width)), transform=transform, all_touched=False)
            expected = int(inside.sum())
        for key in ASSETS:
            href = item["assets"][key]["href"]
            _check_host(href)
            with rasterio.open(f"{href}?{token}") as dataset:
                arrays[key] = dataset.read(1, window=window)
    digest = sha256(b"".join(arrays[key].tobytes() for key in ASSETS)).hexdigest()
    result = {"item_id": item["id"], "start": item["properties"]["start_datetime"][:10], "end": item["properties"]["end_datetime"][:10],
              "expected_aoi_pixels": expected, "raw_window_sha256": digest}
    for period in ("Day", "Night"):
        lst, qc, view = arrays[f"LST_{period}_1km"], arrays[f"QC_{period}"], arrays[f"{period}_view_time"]
        keep = inside & (lst > 0) & _qc_ok(qc)
        fraction = float(keep.sum() / expected) if expected else 0.0
        key = period.lower()
        result[f"{key}_valid_fraction"] = round(fraction, 4)
        if fraction >= MIN_AOI_FRACTION:
            result[f"{key}_lst_k"] = round(float(lst[keep].mean() * LST_SCALE), 2)
            views = view[keep & (view < 255)]
            result[f"{key}_view_time_h"] = round(float(np.median(views) * VIEW_TIME_SCALE), 2) if views.size else None
        else:
            result[f"{key}_lst_k"] = None
            result[f"{key}_view_time_h"] = None
    return result


def _pct(values: list[float], q: float) -> float | None:
    return round(float(np.percentile(values, q)), 2) if values else None


def summarise(samples: list[dict]) -> dict:
    day = [s["day_lst_k"] for s in samples if s["day_lst_k"] is not None]
    night = [s["night_lst_k"] for s in samples if s["night_lst_k"] is not None]
    paired = [s["day_lst_k"] - s["night_lst_k"] for s in samples if s["day_lst_k"] is not None and s["night_lst_k"] is not None]
    day_times = [s["day_view_time_h"] for s in samples if s.get("day_view_time_h") is not None]
    night_times = [s["night_view_time_h"] for s in samples if s.get("night_view_time_h") is not None]
    return {
        "day_temperature_p50_k": _pct(day, 50), "day_temperature_p95_k": _pct(day, 95),
        "night_temperature_p50_k": _pct(night, 50), "night_temperature_p05_k": _pct(night, 5),
        "diurnal_range_p50_k": _pct(paired, 50), "diurnal_range_p05_k": _pct(paired, 5), "diurnal_range_p95_k": _pct(paired, 95),
        "day_samples": len(day), "night_samples": len(night), "paired_samples": len(paired), "planned_samples": len(samples),
        "day_local_solar_time_p50_h": _pct(day_times, 50), "night_local_solar_time_p50_h": _pct(night_times, 50),
    }


def acquire(site_id: str, period: str) -> dict:
    if site_id not in SITES:
        raise ValueError(f"Unsupported site: {site_id}")
    aoi = load_aoi(SITES[site_id])
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        items = _search(client, aoi.geometry, period)
        by_start: dict[str, dict] = {}
        for item in sorted(items, key=lambda value: value["id"]):
            by_start.setdefault(item["properties"]["start_datetime"][:10], item)  # one tile per composite
        tokens: dict[str, str] = {}
        tasks = [(item, _token(client, item["assets"][ASSETS[0]]["href"], tokens)) for item in by_start.values()]
    with ThreadPoolExecutor(max_workers=6) as pool:
        samples = sorted(pool.map(lambda task: _read_item(task[0], aoi.geometry, task[1]), tasks), key=lambda value: value["start"])
    summary = summarise(samples)
    artifact = {
        "evidence_version": "thermal-lst-v1",
        "site_id": site_id, "body": "earth", "dimension": "temperature",
        "quantity": "land_surface_skin_temperature",
        "status": "measured",
        "aoi_id": aoi.aoi_id,
        "product": {
            "product_id": "MYD11A2.061", "collection": COLLECTION, "platform": "Aqua", "instrument": "MODIS",
            "provider": "NASA LP DAAC, served by Microsoft Planetary Computer",
            "source_url": "https://planetarycomputer.microsoft.com/dataset/modis-11A2-061",
            "doi": "10.5067/MODIS/MYD11A2.061",
            "units": "K", "native_resolution_m": 926.6, "analysis_resolution": "AOI mean of 1 km pixels (about 100 pixels per 10 km AOI)",
            "observation_period": period, "temporal_sampling": "8-day clear-sky composites",
        },
        "local_time_policy": "Aqua day/night overpasses near 13:30 and 01:30 local solar time; medians of per-pixel view time are reported.",
        "quality_policy": f"Mandatory QA in {{0,1}} and LST error <= 2 K; composite kept when valid pixels cover >= {MIN_AOI_FRACTION:.0%} of the AOI.",
        "summary": summary,
        "samples": samples,
        "quality_flags": [flag for flag in [
            "clear_sky_bias" ,
            "aoi_mean_smooths_pixel_extremes",
            None if summary["paired_samples"] >= 30 else "fewer_than_30_paired_composites",
        ] if flag],
        "limitations": [
            "Skin temperature from thermal infrared, not air temperature.",
            "8-day composites favour clear-sky retrievals; cloudy-season temperatures are under-represented.",
            "AOI mean of ~1 km pixels smooths local extremes compared with a point sensor.",
            "One calendar year; interannual variability is not characterised.",
        ],
        "processing": {"script": "app/scripts/acquire_modis_lst.py", "generated_at": datetime.now(timezone.utc).isoformat()},
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"{site_id}.thermal-v1.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8", newline="\n")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire MODIS Aqua 8-day LST evidence for registered Earth AOIs")
    parser.add_argument("--site-id", choices=sorted(SITES), action="append")
    parser.add_argument("--period", default="2024-01-01T00:00:00Z/2024-12-31T23:59:59Z", help="Calendar 2024: the Planetary Computer catalog has a Jul-Nov 2025 gap for this collection")
    args = parser.parse_args()
    for site_id in args.site_id or sorted(SITES):
        artifact = acquire(site_id, args.period)
        print(site_id, json.dumps(artifact["summary"]))


if __name__ == "__main__":
    main()
