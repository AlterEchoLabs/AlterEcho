"""Register a lunar south-pole reference window from LRO LOLA LDEM_875S_20M.

Why this window: the lunar south pole lies on or very near the rim of Shackleton crater (centre about
89.67° S, 129.8° E, ~21 km across), in the region studied for sustained lunar surface presence. A
10 km square centred on the pole spans the rim crest, part of Shackleton's inner wall and the outer
plateau. Illumination and permanent shadow are NOT assessed.

Steps:
1. Verify the downloaded PDS image against its recorded SHA-256.
2. Read a 30 km clip around the pole and convert DN to metres (HEIGHT = DN x SCALING_FACTOR, from the
   label; SCALING_FACTOR = 0.5). The derived float32 GeoTIFF keeps the label's polar stereographic CRS.
3. Measure LOLA shot density over the core AOI from the count map (LDEC): cells with zero shots are
   interpolated, and their share is recorded.
4. Write the AOI, source manifest and catalog entry. Then run process_site and process_site_v3.

Usage (from ``backend/``)::

    python -m app.scripts.register_lunar_reference
"""

from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
import re

import numpy as np

from app.services.geospatial_service import BACKEND_ROOT, GEO_DATA, sha256_file

SITE_ID = "moon-south-pole-shackleton"
AOI_ID = f"{SITE_ID}-aoi-v1"
SOURCE_ID = f"{SITE_ID}-lola-ldem"
RAW = GEO_DATA / "raw" / "lola"
BASE_URL = "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/img/"
CLIP_HALF_M = 15_000.0
CORE_HALF_M = 5_000.0


def _label_value(label: str, key: str) -> str:
    match = re.search(rf"^\s*{key}\s*=\s*([^\r\n]+)", label, re.MULTILINE)
    if not match:
        raise ValueError(f"{key} missing from label")
    return match.group(1).strip().strip('"')


def main() -> None:
    import rasterio
    from rasterio.windows import from_bounds

    label = (RAW / "ldem_875s_20m.lbl").read_text(encoding="utf-8", errors="replace")
    scale = float(_label_value(label, "SCALING_FACTOR"))
    if _label_value(label, "UNIT").upper() != "METER" or scale <= 0:
        raise SystemExit("Unexpected vertical units in the LOLA label")
    img_sha = sha256_file(RAW / "ldem_875s_20m.img")
    count_sha = sha256_file(RAW / "ldec_875s_20m.img")
    with rasterio.open(RAW / "ldem_875s_20m.lbl") as dem:
        if not dem.crs or not dem.crs.is_projected:
            raise SystemExit("LOLA label did not yield a projected polar CRS")
        window = from_bounds(-CLIP_HALF_M, -CLIP_HALF_M, CLIP_HALF_M, CLIP_HALF_M, transform=dem.transform).round_offsets().round_lengths()
        raw = dem.read(1, window=window).astype("float32")
        heights = raw * scale  # metres relative to the 1737.4 km reference sphere
        transform = dem.window_transform(window)
        crs = dem.crs
        native = list(dem.res)
    clip = RAW / "ldem_875s_20m_southpole_30km_m.tif"
    with rasterio.open(clip, "w", driver="GTiff", width=heights.shape[1], height=heights.shape[0], count=1, dtype="float32",
                       crs=crs, transform=transform, nodata=None, compress="deflate") as out:
        out.write(heights, 1)
    clip_sha = sha256_file(clip)
    with rasterio.open(RAW / "ldec_875s_20m.lbl") as counts:
        cw = from_bounds(-CORE_HALF_M, -CORE_HALF_M, CORE_HALF_M, CORE_HALF_M, transform=counts.transform).round_offsets().round_lengths()
        shots = counts.read(1, window=cw)
    measured_fraction = float((shots > 0).mean())

    corners = [(-CORE_HALF_M, -CORE_HALF_M), (CORE_HALF_M, -CORE_HALF_M), (CORE_HALF_M, CORE_HALF_M), (-CORE_HALF_M, CORE_HALF_M)]
    from rasterio.warp import transform as warp
    lons, lats = warp(crs, "+proj=longlat +a=1737400 +b=1737400 +no_defs", [c[0] for c in corners], [c[1] for c in corners])
    ring = [[round(lo, 4), round(la, 5)] for lo, la in zip(lons, lats)]
    aoi = {"type": "Feature", "id": AOI_ID, "properties": {
        "aoi_id": AOI_ID, "site_id": SITE_ID, "version": "1.0", "planetary_body": "moon", "center_latitude": -90.0, "center_longitude": 0.0,
        "width_m": 10000, "height_m": 10000,
        "selection_rationale": "10 km square centred on the lunar south pole, which lies on or very near Shackleton crater's rim. It spans the rim crest, part of the inner wall and the outer plateau. Chosen before any Earth comparison was run.",
        "intended_analog_characteristics": ["local slope distribution", "local relief", "surface roughness"],
        "known_limitations": ["Mixes rim, steep inner wall and plateau terrain", f"{1 - measured_fraction:.1%} of core cells have no LOLA shot and are interpolated", "Illumination, permanent shadow and volatiles are not assessed"],
        "creation_method": "Square defined in the LOLA polar stereographic grid (metres) around the pole; the lon/lat ring is a display approximation only.",
        "source_references": [SOURCE_ID], "planetary_target": "Lunar south-pole reference window (limited terrain comparison).",
        "analogy_dimensions_not_covered": ["illumination", "temperature", "volatiles", "regolith", "radiation", "gravity"],
        "representativeness": "One 10 km window at the pole; not representative of the wider south-polar region.",
        "known_selection_bias": "Chosen for its relevance to lunar surface-presence studies, not for expected Earth similarity.",
        "lola_measured_cell_fraction": round(measured_fraction, 4),
    }, "geometry": {"type": "Polygon", "coordinates": [ring + [ring[0]]]}}
    (GEO_DATA / "aoi" / f"{AOI_ID}.geojson").write_text(json.dumps(aoi, indent=2), encoding="utf-8", newline="\n")
    manifest = {
        "source_id": SOURCE_ID, "title": "LRO LOLA Gridded Data Record, south polar DEM 87.5° S, 20 m (LDEM_875S_20M)", "planetary_body": "moon",
        "provider": "NASA PDS Geosciences Node / LRO LOLA team", "mission": "Lunar Reconnaissance Orbiter", "instrument": "Lunar Orbiter Laser Altimeter",
        "product_name": "LDEM_875S_20M", "product_version": "LRO-L-LOLA-3-RDR-V1", "source_page_url": "https://pds-geosciences.wustl.edu/missions/lro/lola.htm",
        "download_url": BASE_URL + "ldem_875s_20m.img", "doi": None, "access_date": date.today().isoformat(),
        "license_or_use_constraints": "NASA PDS data; cite the LOLA team and PDS Geosciences Node.", "native_resolution": native,
        "native_crs": str(crs), "native_bounds": None, "native_nodata": None, "file_size": (RAW / "ldem_875s_20m.img").stat().st_size,
        "filename": "lola/ldem_875s_20m.img", "sha256_checksum": img_sha,
        "citation_text": "Smith, D. E. et al., LRO LOLA Gridded Data Records, NASA PDS, LRO-L-LOLA-3-RDR-V1 (LDEM_875S_20M).",
        "processing_status": "processed",
        "notes": f"Derived 30 km clip in metres (DN x {scale} from the label). Count map ldec_875s_20m.img SHA-256 {count_sha}; {measured_fraction:.1%} of core cells have at least one LOLA shot.",
        "extracted_filename": "lola/" + clip.name, "extracted_sha256_checksum": clip_sha, "aoi_id": AOI_ID, "tiles": [], "mosaic_filename": None, "mosaic_sha256_checksum": None,
    }
    (GEO_DATA / "manifests" / f"{SOURCE_ID}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")
    catalog_path = BACKEND_ROOT / "app" / "data" / "sites.json"
    catalog = [s for s in json.loads(catalog_path.read_text(encoding="utf-8")) if s["id"] != SITE_ID]
    catalog.append({
        "id": SITE_ID, "name": "Lunar south pole (Shackleton rim)", "body": "moon", "country_or_region": "Moon - south polar region",
        "latitude": -90.0, "longitude": 0.0,
        "short_description": "A measured 10 km window centred on the lunar south pole, on Shackleton crater's rim, processed from LRO LOLA 20 m polar topography.",
        "analog_type": "planetary_reference", "relevant_characteristics": ["crater rim", "steep inner wall", "polar plateau"],
        "known_limitations": ["Terrain shape only; illumination, permanent shadow, volatiles and regolith are not assessed", "Limited lunar comparison: Earth terrain is shaped by atmosphere and water"],
        "source_references": ["lola-pds"], "data_status": "real_processed", "processing_status": "integrity_checked",
        "scientific_validation_status": "methodology_review_pending", "aoi_id": AOI_ID, "source_id": SOURCE_ID,
        "available_metrics": ["slope_p50_deg", "slope_p90_deg", "local_relief_p50_m", "local_relief_p90_m", "roughness_mean", "roughness_p90"],
        "thumbnail_url": None, "map_display": {"marker_color": "#b9bfc9", "display_coordinate_status": "measured_aoi_center"},
    })
    catalog_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8", newline="\n")
    sources_path = BACKEND_ROOT / "app" / "data" / "sources.json"
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    if not any(s["id"] == "lola-pds" for s in sources):
        sources.append({"id": "lola-pds", "title": "LRO LOLA Gridded Data Records (PDS Geosciences Node)", "url": "https://pds-geosciences.wustl.edu/missions/lro/lola.htm", "role": "lunar terrain source"})
        sources_path.write_text(json.dumps(sources, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps({"clip": str(clip.name), "clip_sha256": clip_sha, "img_sha256": img_sha, "scale": scale, "measured_fraction": measured_fraction,
                      "height_range_m": [float(np.nanmin(heights)), float(np.nanmax(heights))], "crs": str(crs)[:80]}, indent=2))


if __name__ == "__main__":
    main()
