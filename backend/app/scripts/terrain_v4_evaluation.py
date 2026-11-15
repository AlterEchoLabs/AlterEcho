"""terrain-v4.0 evaluation: placement, boundary, DEM-choice, base-rate and redundancy checks.

All checks are deterministic. None is a statistical confidence interval.

1. Reference stability   Jezero window shifted 2 km N/S/E/W, and without its halo, vs the registered reference.
2. Site placement        each processed Earth window shifted 2 km N/S/E/W, and without its halo.
3. DEM choice            each Earth window re-measured from NASADEM (SRTM lineage) and Copernicus GLO-30
                         (TanDEM-X lineage), both via Microsoft Planetary Computer.
4. Base rate             a 3 x 3 grid of unselected windows inside every downloaded SRTM tile, to show how
                         often an arbitrary Earth window scores high against Jezero.
5. Redundancy            Spearman correlation of family W1 distances (60 m) across all windows.
6. MOLA vs CTX           slope distributions at 480 m over 30 km, the finest scale MOLA (463 m) can support.
7. Method sensitivity    ranks of processed sites under every perturbed terrain-v4 configuration.

Usage (from ``backend/``)::

    python -m app.scripts.terrain_v4_evaluation
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from math import cos, radians
from urllib.parse import urlsplit

import httpx
import numpy as np

from app.services.catalog_service import SITES, get_validated_processed_summary
from app.services.geospatial_service import GEO_DATA, load_aoi, load_manifest
from app.services.terrain_measure import as_artifact, measure_window
from app.services.terrain_v3_service import load_v3_artifact
from app.services.terrain_v4_service import CONFIG as V4, compare_v4, perturbed_configurations, wasserstein_1

OUT = GEO_DATA / "processed" / "evaluation" / "terrain-v4-evaluation.json"
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/token/{account}/{container}"
PC_DEMS = {"nasadem": ("nasadem", "elevation", "NASADEM_HGT v001 (reprocessed SRTM; shared lineage with SRTMGL1)"),
           "cop-dem-glo-30": ("cop-dem-glo-30", "data", "Copernicus DEM GLO-30 (TanDEM-X; independent lineage, surface model)")}
SHIFT_M = 2000.0
MOLA_URL = "/vsicurl/https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif"


def _shift(lat: float, lon: float, north_m: float, east_m: float, body: str) -> tuple[float, float]:
    radius = 3_396_190.0 if body == "mars" else 6_371_008.8
    dlat = north_m / radius * 180 / np.pi
    dlon = east_m / (radius * cos(radians(lat))) * 180 / np.pi
    return lat + dlat, lon + dlon


def _source_path(site):
    manifest = load_manifest(site.source_id)
    if manifest.mosaic_filename:
        return GEO_DATA / "interim" / manifest.mosaic_filename
    return GEO_DATA / "raw" / (manifest.extracted_filename or manifest.filename)


def _family_w1(reference, candidate, scale="60") -> dict[str, float]:
    return {name: wasserstein_1(reference.scales[scale].distributions[spec["distribution"]], candidate.scales[scale].distributions[spec["distribution"]])
            for name, spec in V4["families"].items()}


def _summary(reference, artifact) -> dict:
    if artifact.quality_status != "quality_checked":
        return {"status": "insufficient_coverage", "core_valid_coverage": artifact.core_valid_coverage}
    result = compare_v4(reference, artifact)
    return {"status": "ok", "index": round(result["terrain_index"], 2),
            "families": {k: round(v["index"], 2) for k, v in result["families"].items()},
            "w1_60m": {k: round(v, 3) for k, v in _family_w1(reference, artifact).items()}}


def _pc_dem_array(client: httpx.Client, collection: str, asset: str, lon: float, lat: float, half_deg: float):
    """Merge every intersecting PC DEM tile for the window (plus halo) into an in-memory dataset."""
    import rasterio
    from rasterio.io import MemoryFile
    from rasterio.merge import merge

    bbox = [lon - half_deg / cos(radians(lat)), lat - half_deg, lon + half_deg / cos(radians(lat)), lat + half_deg]
    items = client.post(STAC, json={"collections": [collection], "bbox": bbox, "limit": 10}).raise_for_status().json()["features"]
    if not items:
        raise RuntimeError(f"No {collection} tile intersects the window")
    datasets, item_ids = [], []
    for item in items:
        href = item["assets"][asset]["href"]
        parts = urlsplit(href)
        if parts.scheme != "https" or not (parts.hostname or "").endswith(".blob.core.windows.net"):
            raise RuntimeError("Unexpected asset host")
        account, container = parts.hostname.split(".")[0], parts.path.lstrip("/").split("/")[0]
        token = client.get(SAS.format(account=account, container=container)).raise_for_status().json()["token"]
        datasets.append(rasterio.open(f"{href}?{token}"))
        item_ids.append(item["id"])
    try:
        array, transform = merge(datasets, bounds=bbox, nodata=-32768.0)
        profile = {"driver": "GTiff", "height": array.shape[1], "width": array.shape[2], "count": 1, "dtype": array.dtype,
                   "crs": datasets[0].crs, "transform": transform, "nodata": -32768.0}
    finally:
        for dataset in datasets:
            dataset.close()
    memfile = MemoryFile()
    with memfile.open(**profile) as target:
        target.write(array[0], 1)
    return memfile, item_ids


def run() -> dict:
    reference = load_v3_artifact("mars-jezero")
    jezero = next(s for s in SITES if s.id == "mars-jezero")
    jezero_aoi = load_aoi(jezero.aoi_id)
    earth = [s for s in SITES if s.body.value == "earth" and s.data_status.value == "real_processed" and get_validated_processed_summary(s.id)]
    result: dict = {"methodology_version": V4["methodology_version"], "generated_at": datetime.now(timezone.utc).isoformat(),
                    "notice": "Deterministic checks. Ranges are not statistical confidence intervals."}

    # 1. reference stability
    stability = {}
    src = _source_path(jezero)
    for label, (dn, de) in {"north_2km": (SHIFT_M, 0), "south_2km": (-SHIFT_M, 0), "east_2km": (0, SHIFT_M), "west_2km": (0, -SHIFT_M)}.items():
        lat, lon = _shift(jezero_aoi.center_latitude, jezero_aoi.center_longitude, dn, de, "mars")
        stability[label] = _summary(reference, as_artifact(f"mars-jezero-{label}", measure_window(src, "mars", lon, lat)))
    stability["no_halo"] = _summary(reference, as_artifact("mars-jezero-no-halo", measure_window(src, "mars", jezero_aoi.center_longitude, jezero_aoi.center_latitude, halo_m=0), halo_m=0))
    result["reference_stability"] = stability
    print("reference stability", {k: v.get("index") for k, v in stability.items()})

    # 2 + 3. per-site placement, boundary and DEM checks
    sites = {}
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        for site in earth:
            aoi = load_aoi(site.aoi_id)
            src = _source_path(site)
            entry = {"nominal": _summary(reference, load_v3_artifact(site.id))}
            for label, (dn, de) in {"north_2km": (SHIFT_M, 0), "south_2km": (-SHIFT_M, 0), "east_2km": (0, SHIFT_M), "west_2km": (0, -SHIFT_M)}.items():
                lat, lon = _shift(aoi.center_latitude, aoi.center_longitude, dn, de, "earth")
                try:
                    entry[label] = _summary(reference, as_artifact(f"{site.id}-{label}", measure_window(src, "earth", lon, lat)))
                except Exception as error:  # window leaves the downloaded tile
                    entry[label] = {"status": "not_measured", "reason": str(error)[:160]}
            entry["no_halo"] = _summary(reference, as_artifact(f"{site.id}-no-halo", measure_window(src, "earth", aoi.center_longitude, aoi.center_latitude, halo_m=0), halo_m=0))
            for key, (collection, asset, label) in PC_DEMS.items():
                try:
                    memfile, item_ids = _pc_dem_array(client, collection, asset, aoi.center_longitude, aoi.center_latitude, 0.08)
                    with memfile.open() as dataset:
                        measured = measure_window(dataset, "earth", aoi.center_longitude, aoi.center_latitude)
                    memfile.close()
                    entry[f"dem_{key}"] = {**_summary(reference, as_artifact(f"{site.id}-{key}", measured)), "product": label, "items": item_ids}
                except Exception as error:
                    entry[f"dem_{key}"] = {"status": "not_measured", "reason": str(error)[:160], "product": label}
            sites[site.id] = entry
            print(site.id, {k: v.get("index") for k, v in entry.items()})
    result["sites"] = sites

    # 4. base rate over unselected windows in each downloaded tile
    pool = []
    for site in earth:
        manifest = load_manifest(site.source_id)
        tiles = manifest.tiles or []
        for tile in tiles:
            path = GEO_DATA / "raw" / tile.get("extracted_filename", "")
            if not path.exists():
                continue
            tid = tile["tile_id"]
            lat0 = int(tid[1:3]) * (1 if tid[0] == "N" else -1)
            lon0 = int(tid[4:7]) * (1 if tid[3] == "E" else -1)
            for fy in (0.2, 0.5, 0.8):
                for fx in (0.2, 0.5, 0.8):
                    lat, lon = lat0 + fy, lon0 + fx
                    key = f"{tid}@{fy:.1f},{fx:.1f}"
                    if any(p["window"] == key for p in pool):
                        continue
                    try:
                        artifact = as_artifact(key, measure_window(path, "earth", lon, lat))
                    except Exception:
                        continue
                    summary = _summary(reference, artifact)
                    if summary["status"] == "ok":
                        pool.append({"window": key, "lat": round(lat, 3), "lon": round(lon, 3), **summary})
    indices = np.array([p["index"] for p in pool])
    result["base_rate"] = {
        "windows": pool, "count": len(pool),
        "share_at_or_above": {str(t): round(float((indices >= t).mean()), 3) for t in (50, 90, 95, 99)} if len(pool) else {},
        "median_index": round(float(np.median(indices)), 2) if len(pool) else None,
        "note": "Unselected windows on a regular grid inside the downloaded SRTM tiles (ocean or void windows are excluded by the coverage gate).",
    }
    print("base rate", result["base_rate"]["share_at_or_above"], "n", len(pool))

    # 5. redundancy across all measured windows
    rows = [p["w1_60m"] for p in pool] + [v["nominal"]["w1_60m"] for v in sites.values()]
    names = list(V4["families"])
    ranks = np.array([[np.argsort(np.argsort([r[n] for r in rows]))[i] for n in names] for i in range(len(rows))], dtype=float)
    corr = np.corrcoef(ranks.T) if len(rows) > 2 else np.eye(len(names))
    result["redundancy"] = {"families": names, "spearman_w1_60m": [[round(float(x), 3) for x in row] for row in corr], "n_windows": len(rows),
                            "interpretation": "Values near 1 mean two families rank windows almost identically, so they add little independent evidence."}

    # 6. MOLA vs CTX at a scale MOLA can resolve
    try:
        import rasterio
        mola = measure_window(MOLA_URL, "mars", jezero_aoi.center_longitude, jezero_aoi.center_latitude, width_m=30_000, halo_m=1_920, scales=(480,))
        ctx = measure_window(_source_path(jezero), "mars", jezero_aoi.center_longitude, jezero_aoi.center_latitude, width_m=30_000, halo_m=1_920, scales=(480,))
        m, c = mola["scales"]["480"], ctx["scales"]["480"]
        result["mola_vs_ctx"] = {
            "scale_m": 480, "window_m": 30_000, "mola_product": "Mars_MGS_MOLA_DEM_mosaic_global_463m (USGS)", "ctx_product": "M20_JezeroCrater_CTXDEM_20m (aggregated)",
            "slope_p50_deg": {"mola": m.metrics.get("slope_p50_deg"), "ctx": c.metrics.get("slope_p50_deg")},
            "local_relief_p50_m": {"mola": m.metrics.get("local_relief_p50_m"), "ctx": c.metrics.get("local_relief_p50_m")},
            "slope_w1_deg": round(wasserstein_1(m.distributions["slope_deg"], c.distributions["slope_deg"]), 3),
            "coverage": {"mola": mola["core_valid_coverage"], "ctx": ctx["core_valid_coverage"]},
            "note": "MOLA cannot validate the 60-240 m analysis scales; this compares regional slope only.",
        }
    except Exception as error:
        result["mola_vs_ctx"] = {"status": "not_measured", "reason": str(error)[:200]}
    print("mola vs ctx", result["mola_vs_ctx"])

    # 7. method sensitivity of the processed-site ranking
    artifacts = {s.id: load_v3_artifact(s.id) for s in earth}
    rankings = {}
    positions = {sid: [] for sid in artifacts}
    index_ranges = {sid: [] for sid in artifacts}
    for label, families, scale_weights in perturbed_configurations():
        scores = {sid: compare_v4(reference, a, families, scale_weights)["terrain_index"] for sid, a in artifacts.items()}
        order = sorted(scores, key=lambda sid: (-scores[sid], sid))
        rankings[label] = order
        for pos, sid in enumerate(order, 1):
            positions[sid].append(pos)
            index_ranges[sid].append(scores[sid])
    result["method_sensitivity"] = {
        "configurations": len(rankings), "rank_range": {sid: [min(v), max(v)] for sid, v in positions.items()},
        "index_range": {sid: [round(min(v), 2), round(max(v), 2)] for sid, v in index_ranges.items()},
        "rankings": rankings, "ranking_sensitive": any(min(v) != max(v) for v in positions.values()),
    }
    print("method sensitivity rank ranges", result["method_sensitivity"]["rank_range"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8", newline="\n")
    return result


if __name__ == "__main__":
    run()
