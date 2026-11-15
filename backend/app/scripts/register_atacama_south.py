"""Phase 9: register an uncontaminated Atacama window 8 km south of the original one.

Why: the original earth-atacama window (24.20 S, 69.90 W) contains a large industrial complex
(rectangular pads, buildings, graded ground) visible in Sentinel-2 L2A S2B_MSIL2A_20260927T144729_R139_T19KDP.
ESA WorldCover 2021 classes it as bare ground (built-up 0.0014 %), so no automated mask exists.

Selection rule, fixed before any terrain value of the new window was computed:
    move the window due south until its north edge lies 3 km south of the original centre (beyond the
    complex and a 600 m circular white feature), i.e. 8 km; adopt it only if the 10 m Sentinel-2 crop
    shows no buildings, pads, pits or heaps; it must stay inside the already verified SRTM tile S25W070.
The 8 km window passed: no built structures. Unpaved tracks and a rectilinear survey grid remain;
each line is narrower than one 60 m analysis cell.

The original site and its artifacts are kept unchanged so historical methods (terrain-v3/v4,
analog-evidence-v1/v2) still reproduce. analogue-method-v1.0 excludes it with an explicit reason.

Usage (from backend/):  python -m app.scripts.register_atacama_south
"""

from __future__ import annotations

import json

from app.scripts.register_phase7_sites import square
from app.services.geospatial_service import BACKEND_ROOT, GEO_DATA

SITE_ID = "earth-atacama-south"
AOI_ID = f"{SITE_ID}-aoi-v1"
SOURCE_ID = f"{SITE_ID}-srtmgl1"
LAT, LON = -24.2722, -69.9005  # exactly 8 km south of the original centre on its UTM 19S grid
RATIONALE = ("Uncontaminated replacement for the original Atacama window, which contains a large industrial complex. "
             "Moved 8 km due south under a selection rule fixed before any terrain value was computed (see "
             "app/scripts/register_atacama_south.py). Arid Andean-foreland terrain with alluvial surfaces and low ridges.")
LIMITATIONS = ["The measured window does not represent the complete Atacama Desert",
               "Unpaved tracks and a survey grid cross the window (narrower than one 60 m cell)",
               "Atacama life-detection research elsewhere in the desert does not validate this exact window",
               "Aridity, salts and soil chemistry are not measured by the terrain features"]


def main() -> None:
    aoi = {"type": "Feature", "id": AOI_ID, "properties": {
        "aoi_id": AOI_ID, "site_id": SITE_ID, "version": "1.0", "planetary_body": "earth",
        "center_latitude": LAT, "center_longitude": LON, "width_m": 10000, "height_m": 10000,
        "selection_rationale": RATIONALE,
        "intended_analog_characteristics": ["local slope distribution", "local relief", "surface roughness"],
        "known_limitations": LIMITATIONS,
        "creation_method": "Geodetic display footprint approximated from a 10 km square; processing constructs an exact UTM metric grid around the centre.",
        "source_references": [SOURCE_ID, "atacama-study", "nasa-atacama"],
        "planetary_target": "The registered 10 km Jezero reference window under terrain-only comparison.",
        "analogy_dimensions_not_covered": ["atmosphere", "gravity", "radiation", "geology", "temperature", "habitability"],
        "representativeness": "Feature-focused window; it does not represent the whole region.",
        "known_selection_bias": "Phase 9 replacement chosen by a contamination rule before its terrain was measured; independent AOI review pending.",
        "supersedes": "earth-atacama-aoi-v1",
    }, "geometry": {"type": "Polygon", "coordinates": [square(LAT, LON)]}}
    (GEO_DATA / "aoi" / f"{AOI_ID}.geojson").write_text(json.dumps(aoi, indent=2), encoding="utf-8", newline="\n")

    original = json.loads((GEO_DATA / "manifests" / "earth-atacama-srtmgl1.json").read_text(encoding="utf-8"))
    manifest = {**original, "source_id": SOURCE_ID, "aoi_id": AOI_ID,
                "notes": "Same checksum-verified SRTMGL1 tile (S25W070) as earth-atacama-srtmgl1; registered for the Phase 9 replacement window."}
    (GEO_DATA / "manifests" / f"{SOURCE_ID}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")

    catalog_path = BACKEND_ROOT / "app" / "data" / "sites.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    base = next(s for s in catalog if s["id"] == "earth-atacama")
    entry = {**base, "id": SITE_ID, "name": "Atacama Desert (south window)", "latitude": LAT, "longitude": LON,
             "short_description": "A measured 10 km arid-terrain window 8 km south of the original Atacama window, free of built structures, processed from NASA SRTMGL1.003.",
             "known_limitations": LIMITATIONS, "aoi_id": AOI_ID, "source_id": SOURCE_ID}
    catalog = [s for s in catalog if s["id"] != SITE_ID]
    index = next(i for i, s in enumerate(catalog) if s["id"] == "earth-atacama") + 1
    catalog.insert(index, entry)
    catalog_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8", newline="\n")
    print(SITE_ID, LAT, LON, aoi["geometry"]["coordinates"][0][0], aoi["geometry"]["coordinates"][0][2])


if __name__ == "__main__":
    main()
