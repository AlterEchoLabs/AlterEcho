"""Register additional Mars reference windows from USGS controlled CTX DTMs (final phase).

Gate for each candidate (all must pass, otherwise the candidate is rejected and the reason recorded):
  1. a controlled CTX DTM (STAC mro_ctx_controlled_usgs_dtms) whose valid data cover >= 99 % of the 10 km window
     and >= 98 % of the 1.2 km processing halo at 20 m;
  2. the window is placed by a documented rule stated below, never by its score;
     among products that pass gate 1, the one with the lowest median stereo intersection error is used;
  3. a CTX orthoimage from the same product covers the window for display.
Products are CC0-1.0 (DOI 10.5066/P9JKVWR3). Each DTM window is reprojected once (bilinear, 20 m) onto a local
equirectangular grid true to scale at the window latitude and saved; its SHA-256 is the input checksum, and the
source item, asset URL and grid are recorded in the manifest. No product is bulk-downloaded.

Usage (from backend/):  python -m app.scripts.register_mars_references
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from math import degrees

import httpx
import numpy as np

from app.services.geospatial_service import BACKEND_ROOT, GEO_DATA, sha256_file
from app.services.mars_ctx import COLLECTION, MARS_RADIUS_M, STAC, checked_href, dem_asset, local_crs, read_local, search

CORE_M, HALO_M, MARGIN_M = 10_000.0, 1_200.0, 600.0
RAW_DIR = GEO_DATA / "raw" / "mars"
IMAGERY_DIR = GEO_DATA / "processed" / "imagery"
CANDIDATES = [
    {"id": "mars-gale-aeolis-palus", "name": "Gale Crater floor (Aeolis Palus)", "region": "Mars - Gale crater", "lat": -4.5625, "lon": 137.4417,
     "placement": "Centred 3 km north of the Curiosity (Bradbury) landing point (4.5895 S, 137.4417 E) to keep the window on the Aeolis Palus plains; fixed before any terrain value was computed. The CTX image shows the dark-toned band still reaching the south-east corner (roughly a tenth of the window).",
     "characteristics": ["crater-floor plains (Aeolis Palus)", "alluvial fan material", "Curiosity landing region"],
     "context": "Curiosity found evidence of an ancient habitable fluvio-lacustrine environment at Yellowknife Bay, a few kilometres from the landing site (Grotzinger et al. 2014). That finding concerns rocks studied by the rover, not the whole window.",
     "limitations": ["The window covers plains and, in its south-east corner, part of a dark-toned band; Aeolis Mons (Mount Sharp) is outside it", "Rover-scale observations do not validate window-scale terrain statistics", "Terrain metrics do not establish geology, habitability, safety or radiation"],
     "refs": ["grotzinger-2014-gale", "usgs-ctx-dtms"]},
    {"id": "mars-insight-elysium", "name": "Elysium Planitia (InSight landing site)", "region": "Mars - Elysium Planitia", "lat": 4.5024, "lon": 135.6234,
     "placement": "Centred on the InSight lander position (4.5024 N, 135.6234 E); fixed before any terrain value was computed.",
     "characteristics": ["smooth volcanic plains", "degraded impact craters", "InSight landing region"],
     "context": "Orbital and lander observations describe a smooth, cratered lava plain with an impact-generated regolith several metres thick (Golombek et al. 2020).",
     "limitations": ["A 20 m DTM cannot resolve the metre-scale rocks and hollows described at the lander", "CTX stereo noise adds short-wavelength texture; on very smooth plains it inflates 60 m slopes (median 60 m slope 3.1 deg here)", "Regolith thickness and mechanical properties are not measured", "Terrain metrics do not establish geology, habitability, safety or radiation"],
     "refs": ["golombek-2020-insight", "usgs-ctx-dtms"]},
    {"id": "mars-gusev-plains", "name": "Gusev crater plains (Spirit landing site)", "region": "Mars - Gusev crater", "lat": -14.5684, "lon": 175.4726,
     "placement": "Centred on the Spirit landing site (14.5684 S, 175.4726 E); the window includes the western Columbia Hills. Fixed before any terrain value was computed.",
     "characteristics": ["basaltic cratered plains", "western Columbia Hills", "Spirit traverse region"],
     "context": "Spirit's traverse showed the plains to be basaltic lava with impact-generated regolith and few signs of water-lain sediments (Golombek et al. 2006).",
     "limitations": ["The window mixes plains and part of the Columbia Hills", "Rover-scale observations do not validate window-scale statistics", "Terrain metrics do not establish geology, habitability, safety or radiation"],
     "refs": ["golombek-2006-gusev", "usgs-ctx-dtms"]},
    {"id": "mars-eberswalde-delta", "name": "Eberswalde crater delta", "region": "Mars - Eberswalde crater", "lat": -23.85, "lon": -33.55,
     "placement": "Centred on the fan-shaped deposit inside Eberswalde crater, confirmed in a 30 km CTX orthoimage survey before any terrain value was computed.",
     "characteristics": ["fan delta with distributary channels", "inverted channel deposits", "crater-floor sediments"],
     "context": "A fan-shaped deposit with meandering, branching channels has been interpreted as evidence of persistent flow and aqueous sedimentation (Malin & Edgett 2003).",
     "limitations": ["A delta deposit and a desert landscape can share slope statistics without sharing a process", "Mineralogy is not measured", "Terrain metrics do not establish geology, habitability, safety or radiation"],
     "refs": ["malin-edgett-2003-eberswalde", "usgs-ctx-dtms"]},
]
NEW_SOURCES = [
    {"id": "grotzinger-2014-gale", "title": "Grotzinger et al. (2014) A habitable fluvio-lacustrine environment at Yellowknife Bay, Gale Crater, Mars. Science 343, 1242777", "url": "https://doi.org/10.1126/science.1242777", "role": "mission context (rover scale)"},
    {"id": "golombek-2020-insight", "title": "Golombek et al. (2020) Geology of the InSight landing site on Mars. Nature Communications 11, 1014", "url": "https://doi.org/10.1038/s41467-020-14679-1", "role": "landing-site context"},
    {"id": "golombek-2006-gusev", "title": "Golombek et al. (2006) Geology of the Gusev cratered plains from the Spirit rover transverse. JGR Planets 111, E02S07", "url": "https://doi.org/10.1029/2005JE002503", "role": "mission context (rover scale)"},
    {"id": "malin-edgett-2003-eberswalde", "title": "Malin & Edgett (2003) Evidence for persistent flow and aqueous sedimentation on early Mars. Science 302, 1931-1934", "url": "https://doi.org/10.1126/science.1090544", "role": "geomorphic context (regional)"},
    {"id": "usgs-ctx-dtms", "title": "USGS Astrogeology: Mars Reconnaissance Orbiter Context Camera controlled digital terrain models (STAC mro_ctx_controlled_usgs_dtms), DOI 10.5066/P9JKVWR3", "url": "https://stac.astrogeology.usgs.gov/docs/data/mars/ctxdtms/", "role": "planetary elevation input"},
]


def _coverage(client: httpx.Client, item: dict, lat: float, lon: float) -> tuple[float, float]:
    _, href = dem_asset(item)
    arr, _, _ = read_local(href, lat, lon, CORE_M + 2 * HALO_M, 120.0)
    n = arr.shape[0]
    h = int(round(HALO_M / 120.0))
    return float(np.isfinite(arr[h:n - h, h:n - h]).mean()), float(np.isfinite(arr).mean())


def _intersection_median(item: dict, lat: float, lon: float) -> float | None:
    if "intersection_error" not in item["assets"]:
        return None
    try:
        e, _, _ = read_local(checked_href(item["assets"]["intersection_error"]["href"]), lat, lon, CORE_M, 120.0, "nearest")
        v = e[np.isfinite(e)]
        return round(float(np.median(v)), 3) if v.size else None
    except Exception:
        return None


def _ring(lat: float, lon: float) -> list[list[float]]:
    from rasterio.crs import CRS
    from rasterio.warp import transform
    crs = local_crs(lat, lon)
    cy = MARS_RADIUS_M * np.radians(lat)
    h = CORE_M / 2
    xs, ys = [-h, h, h, -h, -h], [cy - h, cy - h, cy + h, cy + h, cy - h]
    lons, lats = transform(crs, CRS.from_proj4(f"+proj=longlat +R={MARS_RADIUS_M:.0f} +no_defs"), xs, ys)
    return [[round(a, 5), round(b, 5)] for a, b in zip(lons, lats)]


def _stretch(arr: np.ndarray) -> np.ndarray:
    v = arr[np.isfinite(arr)]
    lo, hi = np.percentile(v, [2, 98]) if v.size else (0.0, 1.0)
    return np.clip((np.nan_to_num(arr, nan=lo) - lo) / max(hi - lo, 1e-9) * 255, 0, 255).astype("uint8")


def register(client: httpx.Client, cand: dict) -> dict:
    import rasterio
    from PIL import Image

    lat, lon = cand["lat"], cand["lon"]
    items = search(client, lat, lon, CORE_M / 2 + HALO_M)
    scored, full = [], []
    for item in items[:30]:
        try:
            core, halo = _coverage(client, item, lat, lon)
        except Exception as error:  # an unreadable product is skipped, never substituted
            core, halo = 0.0, 0.0
            print(" ", item["id"], "unreadable:", type(error).__name__)
        scored.append((core, halo, item))
        if core >= 0.99 and halo >= 0.98:
            full.append((core, halo, item, _intersection_median(item, lat, lon)))
        if len(full) >= 6:
            break
    if not scored:
        return {"id": cand["id"], "status": "rejected", "reason": "No controlled CTX DTM intersects the window"}
    if not full:
        core, halo, item = max(scored, key=lambda t: (t[0], t[1]))
        return {"id": cand["id"], "status": "rejected", "reason": f"Best DTM ({item['id']}) covers {core:.1%} of the window and {halo:.1%} with halo (gate 99 % / 98 %)"}
    # Quality-first: among products covering the window, take the lowest median stereo intersection error.
    core, halo, item, _ = min(full, key=lambda t: (t[3] if t[3] is not None else 1e9, -t[0]))
    selection = [{"item": f[2]["id"], "core_valid": round(f[0], 4), "intersection_error_median_m": f[3]} for f in full]
    asset_key, href = dem_asset(item)
    extent = CORE_M + 2 * (HALO_M + MARGIN_M)
    dem, transform, meta = read_local(href, lat, lon, extent, 20.0)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    clip = RAW_DIR / f"{cand['id']}-ctx-dtm-local.tif"
    with rasterio.open(clip, "w", driver="GTiff", height=dem.shape[0], width=dem.shape[1], count=1, dtype="float32", crs=local_crs(lat, lon),
                       transform=transform, nodata=-32767.0, compress="deflate", tiled=True) as dst:
        dst.write(np.where(np.isfinite(dem), dem, -32767.0).astype("float32"), 1)
    checksum = sha256_file(clip)
    n = dem.shape[0]
    m = int(round((HALO_M + MARGIN_M) / 20.0))
    core20 = dem[m:n - m, m:n - m]
    err = None
    if "intersection_error" in item["assets"]:
        try:
            e, _, _ = read_local(checked_href(item["assets"]["intersection_error"]["href"]), lat, lon, CORE_M, 20.0, "nearest")
            ev = e[np.isfinite(e)]
            err = {"median_m": round(float(np.median(ev)), 3), "p95_m": round(float(np.percentile(ev, 95)), 3)} if ev.size else None
        except Exception:
            err = None
    ortho_href = checked_href(item["assets"]["orthoimage"]["href"])
    ortho, _, ometa = read_local(ortho_href, lat, lon, CORE_M, 10.0)
    png = IMAGERY_DIR / f"{cand['id']}-ctx-reference.png"
    Image.fromarray(_stretch(ortho)).save(png, optimize=True)
    props = item["properties"]
    now = datetime.now(timezone.utc).isoformat()
    aoi_id, source_id = f"{cand['id']}-aoi-v1", f"{cand['id']}-ctx-dtm"
    ring = _ring(lat, lon)
    aoi = {"type": "Feature", "id": aoi_id, "properties": {
        "aoi_id": aoi_id, "site_id": cand["id"], "version": "1.0", "planetary_body": "mars", "center_latitude": lat, "center_longitude": lon,
        "width_m": CORE_M, "height_m": CORE_M, "selection_rationale": cand["placement"],
        "intended_analog_characteristics": ["local slope distribution", "relative elevation distribution"], "known_limitations": cand["limitations"],
        "creation_method": "Planetocentric latitude, east-positive longitude on the Mars sphere (R = 3,396,190 m); processing builds a local equirectangular grid true to scale at the window latitude.",
        "source_references": [source_id, *cand["refs"]], "planetary_target": "Reference window for terrain-only comparison with Earth windows.",
        "analogy_dimensions_not_covered": ["atmosphere", "gravity", "radiation", "geology", "temperature", "habitability"],
        "representativeness": "One 10 km window; it does not represent the whole crater or plain.", "known_selection_bias": "Placed at a mission site by a documented rule.",
    }, "geometry": {"type": "Polygon", "coordinates": [ring]}}
    (GEO_DATA / "aoi" / f"{aoi_id}.geojson").write_text(json.dumps(aoi, indent=2), encoding="utf-8", newline="\n")
    manifest = {
        "source_id": source_id, "title": f"USGS controlled CTX DTM {item['id']}", "planetary_body": "mars", "provider": "USGS Astrogeology Science Center",
        "mission": "Mars Reconnaissance Orbiter", "instrument": "Context Camera (CTX)", "product_name": "MRO_CTX_controlled_USGS_DTM", "product_version": item["id"],
        "source_page_url": f"{STAC}/collections/{COLLECTION}/items/{item['id']}", "download_url": href, "doi": "10.5066/P9JKVWR3", "access_date": now[:10],
        "license_or_use_constraints": "CC0-1.0 (USGS Astrogeology). Cite the product DOI.", "native_resolution": meta["src_res"], "native_crs": meta["src_crs"],
        "native_bounds": item["bbox"], "native_nodata": meta["src_nodata"], "file_size": clip.stat().st_size, "filename": clip.name, "sha256_checksum": checksum,
        "citation_text": f"USGS Astrogeology Science Center, MRO CTX controlled DTM {item['id']} (asset {asset_key}), DOI 10.5066/P9JKVWR3.",
        "processing_status": "processed",
        "notes": (f"Window read from the cloud-optimised {asset_key} asset with HTTP range requests and reprojected once (bilinear) to a 20 m local equirectangular grid "
                  f"true to scale at {lat} deg (+proj=eqc +lat_ts={lat} +lon_0={lon} +R=3396190). The SHA-256 is of this derived clip; the full product was not downloaded. "
                  f"Core valid fraction {float(np.isfinite(core20).mean()):.4f}; intersection error {err}."),
        "extracted_filename": f"mars/{clip.name}", "extracted_sha256_checksum": checksum, "aoi_id": aoi_id, "tiles": [], "mosaic_filename": None, "mosaic_sha256_checksum": None,
    }
    (GEO_DATA / "manifests" / f"{source_id}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")
    record = {
        "imagery_id": f"{cand['id']}-ctx-reference", "site_id": cand["id"], "body": "mars", "mode": "reference", "provider": "USGS Astrogeology Science Center",
        "collection": "MRO CTX controlled DTM orthoimage", "product_id": item["id"], "acquisition_datetime": None, "publication_datetime": props.get("created"),
        "resolution_m": round(float(ometa["src_res"][0]), 2), "display_resolution_m": 10.0, "cloud_cover_pct": None, "processing_level": "Orthorectified CTX image from the stereo pair",
        "bbox": [min(p[0] for p in ring), min(p[1] for p in ring), max(p[0] for p in ring), max(p[1] for p in ring)], "aoi_id": aoi_id,
        "preview_url": f"/api/imagery-assets/{png.name}", "tile_url": None, "attribution": "USGS Astrogeology Science Center; MRO Context Camera (NASA/JPL/MSSS). CC0-1.0.",
        "official_source_url": f"{STAC}/collections/{COLLECTION}/items/{item['id']}", "source_download_url": ortho_href, "cache_status": "cached", "cache_date": now,
        "data_status": "available", "preview_checksum": sha256_file(png), "source_crs": ometa["src_crs"][:120], "native_resolution": ometa["src_res"],
        "aoi_coverage_fraction": round(float(np.isfinite(ortho).mean()), 4),
        "registration": {"grid": "local equirectangular, true to scale at the window latitude, identical in construction to the terrain grid", "pixel_m": 10.0, "pixels": 1000, "ground_extent_m": [CORE_M, CORE_M]},
        "limitations": ["Grayscale CTX image; it is not a colour photograph.", "The two stereo images were acquired on different dates; the image is display context and never enters a score.",
                        "Shadows depend on the acquisition illumination."],
    }
    (IMAGERY_DIR / f"{cand['id']}-ctx-reference.json").write_text(json.dumps(record, indent=2), encoding="utf-8", newline="\n")
    return {"id": cand["id"], "status": "accepted", "item": item["id"], "asset": asset_key, "core_valid": round(float(np.isfinite(core20).mean()), 4),
            "halo_valid": halo, "relief_m": [round(float(np.nanmin(core20)), 1), round(float(np.nanmax(core20)), 1)], "intersection_error": err, "checksum": checksum,
            "candidates_checked": len(scored), "selection": selection}


def main() -> None:
    results = []
    with httpx.Client(timeout=120, headers={"User-Agent": "TerraLuna-analysis/1.0"}) as client:
        for cand in CANDIDATES:
            r = register(client, cand)
            print(json.dumps(r))
            results.append(r)
    catalog_path = BACKEND_ROOT / "app" / "data" / "sites.json"
    sources_path = BACKEND_ROOT / "app" / "data" / "sources.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    known = {s["id"] for s in sources}
    sources += [s for s in NEW_SOURCES if s["id"] not in known]
    for cand, r in zip(CANDIDATES, results):
        if r["status"] != "accepted":
            continue
        entry = {"id": cand["id"], "name": cand["name"], "body": "mars", "country_or_region": cand["region"], "latitude": cand["lat"], "longitude": cand["lon"],
                 "short_description": f"A measured 10 km Mars reference window processed from a USGS controlled CTX DTM ({r['item']}).",
                 "analog_type": "planetary_reference", "relevant_characteristics": cand["characteristics"], "known_limitations": cand["limitations"],
                 "source_references": cand["refs"], "data_status": "real_processed", "processing_status": "integrity_checked",
                 "scientific_validation_status": "methodology_review_pending", "aoi_id": f"{cand['id']}-aoi-v1", "source_id": f"{cand['id']}-ctx-dtm",
                 "available_metrics": ["slope_p50_deg", "slope_p90_deg", "local_relief_p50_m", "local_relief_p90_m", "roughness_mean", "roughness_p90"],
                 "thumbnail_url": None, "map_display": {"marker_color": "#ef4444", "display_coordinate_status": "measured_aoi_center"}}
        catalog = [s for s in catalog if s["id"] != cand["id"]]
        index = next(i for i, s in enumerate(catalog) if s["id"] == "mars-jezero") + 1
        catalog.insert(index, entry)
    catalog_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8", newline="\n")
    sources_path.write_text(json.dumps(sources, indent=2), encoding="utf-8", newline="\n")
    (GEO_DATA / "processed" / "evaluation" / "mars-reference-registration.json").write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "results": results,
        "context": {c["id"]: c["context"] for c in CANDIDATES}}, indent=2), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
