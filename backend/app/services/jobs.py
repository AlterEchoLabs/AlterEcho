"""Bounded background jobs for user-defined Earth screening AOIs.

States: queued -> acquiring -> processing -> quality_check -> ready
        or failed / unsupported / requires_credentials.

Safety bounds: fixed 10 km square, SRTM latitude coverage only, at most 4 SRTM tiles, one worker,
a capped queue, a per-client hourly limit and a global daily limit. Only the NASA LP DAAC SRTM URL
pattern (and, optionally, Planetary Computer Sentinel-2) is ever fetched; user input never becomes a URL.
Results are labelled "screening" and are never merged into the reviewed showcase ranking.
"""

from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import cos, isfinite, radians
import os
from pathlib import Path
import re
import threading
import time
from typing import Any
from uuid import uuid4

from app.services.geospatial_service import GEO_DATA, sha256_file

JOB_DIR = GEO_DATA / "jobs"
WORK_DIR = GEO_DATA / "user-aoi"
JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
WIDTH_M = 10_000.0
LAT_RANGE = (-55.9, 59.9)            # SRTMGL1 coverage, keeping a 10 km window inside it
MAX_TILES = 4
MAX_QUEUE = 4
PER_CLIENT_PER_HOUR = 3
GLOBAL_PER_DAY = 40
TERMINAL = {"ready", "failed", "unsupported", "requires_credentials"}

_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aoi-job")
_client_hits: dict[str, deque] = {}
_global_hits: deque = deque()
_pending = 0


class JobRejected(ValueError):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(job_id: str) -> Path:
    if not JOB_ID_RE.fullmatch(job_id):
        raise JobRejected("Invalid job id", 404)
    return JOB_DIR / f"{job_id}.json"


def _save(job: dict) -> None:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path(job["job_id"]).with_suffix(".tmp")
    tmp.write_text(json.dumps(job, indent=2), encoding="utf-8", newline="\n")
    tmp.replace(_path(job["job_id"]))


def load(job_id: str) -> dict:
    path = _path(job_id)
    if not path.exists():
        raise JobRejected("Unknown job", 404)
    return json.loads(path.read_text(encoding="utf-8"))


def recent(limit: int = 12) -> list[dict]:
    if not JOB_DIR.exists():
        return []
    jobs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(JOB_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]]
    return [{k: j.get(k) for k in ("job_id", "label", "state", "center", "created_at", "updated_at")} for j in jobs]


def recover_interrupted() -> int:
    """Mark jobs left mid-flight by a restart as failed (they are never silently resumed)."""
    count = 0
    if not JOB_DIR.exists():
        return 0
    for path in JOB_DIR.glob("*.json"):
        job = json.loads(path.read_text(encoding="utf-8"))
        if job.get("state") not in TERMINAL:
            _transition(job, "failed", "Interrupted by a server restart; submit the area again.")
            count += 1
    return count


def _transition(job: dict, state: str, message: str) -> None:
    job["state"] = state
    job["updated_at"] = _now()
    job["log"].append({"at": job["updated_at"], "state": state, "message": message})
    _save(job)


def square(lat: float, lon: float) -> dict:
    dlat = WIDTH_M / 2 / 111_320
    dlon = WIDTH_M / 2 / (111_320 * cos(radians(lat)))
    w, e, s, n = lon - dlon, lon + dlon, lat - dlat, lat + dlat
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


def preflight(lat: float, lon: float) -> dict:
    from app.services.srtm_service import tiles_for_geojson_geometry
    if not (isfinite(lat) and isfinite(lon)) or not (-90 < lat < 90 and -180 <= lon <= 180):
        raise JobRejected("Latitude and longitude must be finite degrees")
    geometry = square(lat, lon)
    supported = LAT_RANGE[0] <= lat <= LAT_RANGE[1]
    tiles = tiles_for_geojson_geometry(geometry) if supported else []
    cached = [t for t in tiles if (GEO_DATA / "raw" / f"{t}.hgt").exists()]
    credentials = bool(os.getenv("EARTHDATA_TOKEN") or (os.getenv("EARTHDATA_USERNAME") and os.getenv("EARTHDATA_PASSWORD")))
    return {
        "center": {"lat": lat, "lon": lon}, "geometry": geometry, "width_m": WIDTH_M, "supported": supported and len(tiles) <= MAX_TILES,
        "reason": None if supported else "Outside SRTMGL1 coverage (56° S to 60° N); ArcticDEM/REMA integrations are not available for screening.",
        "dem": {"product": "SRTMGL1.003", "native_resolution": "1 arc-second (~30 m)", "analysis_scales_m": [60, 120, 240], "tiles": tiles, "tiles_cached": cached,
                "credentials_available": credentials, "requires_credentials": bool(set(tiles) - set(cached)) and not credentials},
        "imagery": {"product": "Sentinel-2 L2A via Microsoft Planetary Computer", "authentication": "none (public)", "note": "Scene chosen only if it covers ≥ 99 % of the AOI with ≤ 5 % AOI cloud."},
        "references": ["mars-jezero"] + (["moon-south-pole-shackleton"] if (GEO_DATA / "processed" / "moon-south-pole-shackleton.terrain-v3.json").exists() else []),
        "queue": {"pending": _pending, "max": MAX_QUEUE}, "limits": {"per_client_per_hour": PER_CLIENT_PER_HOUR, "global_per_day": GLOBAL_PER_DAY},
        "status_label": "screening — exploratory until reviewed",
    }


def _rate_limit(client: str) -> None:
    now = time.time()
    hits = _client_hits.setdefault(client, deque())
    while hits and now - hits[0] > 3600:
        hits.popleft()
    while _global_hits and now - _global_hits[0] > 86400:
        _global_hits.popleft()
    if len(hits) >= PER_CLIENT_PER_HOUR:
        raise JobRejected("Hourly screening limit reached for this client; try again later", 429)
    if len(_global_hits) >= GLOBAL_PER_DAY:
        raise JobRejected("Daily screening capacity reached; try again tomorrow", 429)
    hits.append(now)
    _global_hits.append(now)


def submit(lat: float, lon: float, label: str | None, client: str) -> dict:
    global _pending
    pre = preflight(lat, lon)
    label = re.sub(r"[^\w\s,.()'-]", "", (label or "").strip())[:60] or f"{lat:.3f}, {lon:.3f}"
    job = {"job_id": uuid4().hex, "label": label, "center": pre["center"], "geometry": pre["geometry"], "created_at": _now(), "updated_at": _now(),
           "state": "queued", "log": [], "preflight": pre, "result": None, "screening": True}
    with _lock:
        if not pre["supported"]:
            job["log"].append({"at": _now(), "state": "unsupported", "message": pre["reason"] or "Unsupported area"})
            job["state"] = "unsupported"
            _save(job)
            return job
        if pre["dem"]["requires_credentials"]:
            job["log"].append({"at": _now(), "state": "requires_credentials", "message": "Downloading SRTMGL1 needs NASA Earthdata credentials on the server (EARTHDATA_TOKEN). Nothing was fetched."})
            job["state"] = "requires_credentials"
            _save(job)
            return job
        if _pending >= MAX_QUEUE:
            raise JobRejected("The screening queue is full; try again in a few minutes", 429)
        _rate_limit(client)
        _pending += 1
        _transition(job, "queued", "Waiting for the single processing worker.")
    _executor.submit(_run, job["job_id"])
    return job


def _run(job_id: str) -> None:
    global _pending
    job = load(job_id)
    try:
        _pipeline(job)
    except Exception as error:  # every failure is recorded, never swallowed
        message = str(error)
        for secret in (os.getenv("EARTHDATA_TOKEN"), os.getenv("EARTHDATA_PASSWORD")):
            if secret:
                message = message.replace(secret, "[REDACTED]")
        _transition(job, "failed", f"{type(error).__name__}: {message[:300]}")
    finally:
        with _lock:
            _pending = max(0, _pending - 1)


def _pipeline(job: dict) -> None:
    from app.scripts.acquire_dataset import download, earthdata_headers, extract_dem
    from app.services.srtm_service import mosaic_rasters, srtm_archive_name, srtm_download_url
    from app.services.terrain_measure import as_artifact, measure_window
    from app.services.terrain_v3_service import load_v3_artifact
    from app.services.terrain_v4_service import compare_v4

    lat, lon = job["center"]["lat"], job["center"]["lon"]
    work = WORK_DIR / job["job_id"]
    work.mkdir(parents=True, exist_ok=True)
    _transition(job, "acquiring", f"Fetching SRTMGL1 tile(s) {', '.join(job['preflight']['dem']['tiles'])}.")
    inputs, paths = [], []
    raw = GEO_DATA / "raw"
    for tile in job["preflight"]["dem"]["tiles"][:MAX_TILES]:
        hgt = raw / f"{tile}.hgt"
        if not hgt.exists():
            archive = raw / srtm_archive_name(tile)
            if not archive.exists():
                download(srtm_download_url(tile), archive, earthdata_headers(dict(os.environ)))
            hgt = extract_dem(archive, raw)
        paths.append(hgt)
        inputs.append({"tile_id": tile, "file": hgt.name, "sha256": sha256_file(hgt), "product": "SRTMGL1.003"})
    source = paths[0] if len(paths) == 1 else mosaic_rasters(paths, work / "mosaic.tif")
    _transition(job, "processing", "Measuring slope, local relief, roughness and relative elevation at 60, 120 and 240 m with a 1.2 km halo.")
    measured = measure_window(source, "earth", lon, lat, width_m=WIDTH_M)
    artifact = as_artifact(f"user-{job['job_id'][:8]}", measured, provenance={"inputs": inputs, "method": "terrain-v3 kernels"})
    _transition(job, "quality_check", "Checking per-feature valid coverage against the 90 % gate.")
    coverage = {scale: {f: c.coverage_fraction for f, c in s.feature_coverage.items()} for scale, s in measured["scales"].items()}
    if artifact.quality_status != "quality_checked":
        job["result"] = {"coverage": coverage}
        _transition(job, "failed", "Less than 90 % of the window has valid elevation for at least one feature (ocean, lake or SRTM void). No index is computed.")
        return
    comparisons = {}
    for reference_id in job["preflight"]["references"]:
        reference = load_v3_artifact(reference_id)
        if reference:
            v4 = compare_v4(reference, artifact)
            comparisons[reference_id] = {"terrain_index": round(v4["terrain_index"], 2), "method": "terrain-v4.0",
                                         "families": {k: {"index": round(v["index"], 2), "w1_60m": round(v["by_scale"]["60"]["w1"], 3), "units": v["units"], "tau": v["tau"]} for k, v in v4["families"].items()}}
    imagery = None
    try:
        imagery = _imagery(job, work)
    except Exception as error:
        imagery = {"status": "unavailable", "reason": str(error)[:200]}
    from app.services.evidence_v2_service import evaluation
    base = evaluation().get("base_rate", {})
    job["result"] = {
        "label": "screening", "inputs": inputs, "coverage": coverage,
        "metrics_60m": measured["scales"]["60"].metrics, "comparisons": comparisons, "imagery": imagery,
        "base_rate": {"share_at_or_above": base.get("share_at_or_above"), "windows": base.get("count")},
        "limitations": ["Screening result: not reviewed, not part of the showcase ranking.", "Terrain shape only at 60–240 m; materials, temperature, water, access and safety are not assessed.",
                        "A high terrain index is common for low-relief Earth terrain (see base rate)."],
        "result_sha256": None,
    }
    job["result"]["result_sha256"] = sha256(json.dumps(job["result"], sort_keys=True, default=str).encode()).hexdigest()
    _transition(job, "ready", "Screening measurements and comparison are ready.")


def _imagery(job: dict, work: Path) -> dict:
    import httpx
    import rasterio
    from app.models.schemas import AOIRecord
    from app.scripts.acquire_planetary_computer_imagery import COLLECTION, MAX_CATALOG_CLOUD, STAC, Rejected, Signer, _contains_aoi, _evaluate, _request

    lat, lon = job["center"]["lat"], job["center"]["lon"]
    aoi = AOIRecord(aoi_id=f"user-{job['job_id'][:8]}", site_id="user", version="1", planetary_body="earth", center_latitude=lat, center_longitude=lon,
                    width_m=WIDTH_M, height_m=WIDTH_M, selection_rationale="user screening", intended_analog_characteristics=[], known_limitations=[],
                    creation_method="user", source_references=[], geometry=job["geometry"])
    with httpx.Client(timeout=90, follow_redirects=False) as client:
        sign = Signer(client)
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        query = {"collections": [COLLECTION], "intersects": job["geometry"], "limit": 50,
                 "datetime": f"{(now - timedelta(days=365)).isoformat()}/{now.isoformat()}", "query": {"eo:cloud_cover": {"lte": MAX_CATALOG_CLOUD}}}
        features = [f for f in _request(client, "POST", f"{STAC}/search", json=query).json().get("features", []) if _contains_aoi(f, job["geometry"]["coordinates"][0])]
        for scene in sorted(features, key=lambda f: (float(f["properties"].get("eo:cloud_cover", 100)), f["properties"]["datetime"]), reverse=False)[:6]:
            try:
                result = _evaluate(scene, sign, aoi, True)
            except Rejected:
                continue
            with rasterio.open(work / "sentinel.png", "w", driver="PNG", width=result["n"], height=result["n"], count=3, dtype="uint8", crs=result["crs"], transform=result["transform"]) as out:
                out.write(result["rgb"])
            return {"status": "available", "product_id": scene["id"], "acquisition_datetime": scene["properties"]["datetime"], "cloud_cover_pct": scene["properties"].get("eo:cloud_cover"),
                    **result["stats"], "preview_url": f"/api/explore/jobs/{job['job_id']}/imagery.png", "attribution": f"Contains modified Copernicus Sentinel data ({scene['properties']['datetime'][:4]})"}
    return {"status": "unavailable", "reason": "No scene in the last 365 days covered the AOI with ≤ 5 % cloud."}
