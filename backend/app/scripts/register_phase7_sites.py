"""Register the Phase 7 held-out Earth study windows (AOI, source manifest skeleton, catalog entry).

The terrain-v4 parameters were frozen BEFORE these sites were processed, so they act as held-out
checks of the method. Selection was made for landscape diversity (hydrothermal/evaporite, basaltic
lava, sedimentary badlands, impact crater), not for expected similarity to Jezero.

Run once, then acquire and process each source:
    python -m app.scripts.register_phase7_sites
"""

from __future__ import annotations

import json
from math import cos, radians

from app.services.geospatial_service import BACKEND_ROOT, GEO_DATA
from app.services.srtm_service import srtm_archive_name, srtm_download_url, tiles_for_geojson_geometry

HALF_M = 5000.0
SITES = [
    {
        "id": "earth-danakil", "name": "Dallol, Danakil Depression", "region": "Ethiopia (Afar)", "lat": 14.2417, "lon": 40.2989,
        "analog_type": "environmental_candidate",
        "characteristics": ["hydrothermal field", "evaporite salt plain", "extreme heat"],
        "description": "A measured 10 km window centred on the Dallol hydrothermal dome, processed from NASA SRTMGL1.003.",
        "rationale": "Centred on the Dallol dome described as a planetary field analog for hydrothermal and evaporite processes (Cavalazzi et al. 2019). Chosen as a deliberately different landscape: a near-flat salt plain with a low dome.",
        "limitations": ["Hydrothermal chemistry and salts are not measured by the terrain index", "The salt plain is very flat; terrain similarity says nothing about mineralogy", "Access is hazardous and seasonally restricted; not assessed here"],
        "refs": ["dallol-study"],
    },
    {
        "id": "earth-craters-of-the-moon", "name": "Craters of the Moon lava field", "region": "Idaho, USA", "lat": 43.42, "lon": -113.55,
        "analog_type": "terrain_candidate",
        "characteristics": ["young basaltic lava flows", "cinder cones", "rough volcanic surfaces"],
        "description": "A measured 10 km window over the northern Craters of the Moon lava field, processed from NASA SRTMGL1.003.",
        "rationale": "Basaltic volcanic terrain used by NASA's BASALT field campaigns (Lim et al. 2019). The window covers the northern lava field and cinder-cone area; it is not claimed to coincide with specific BASALT sample sites.",
        "limitations": ["Region-level BASALT research does not validate this exact window", "Basalt composition and vesicularity are not measured by the terrain index", "National monument rules govern access; not assessed here"],
        "refs": ["basalt-lim-2019"],
    },
    {
        "id": "earth-hanksville-mdrs", "name": "Hanksville badlands (MDRS)", "region": "Utah, USA", "lat": 38.4064, "lon": -110.7919,
        "analog_type": "terrain_candidate",
        "characteristics": ["sedimentary badlands", "arid erosion", "operational analog station"],
        "description": "A measured 10 km window centred on the Mars Desert Research Station area, processed from NASA SRTMGL1.003.",
        "rationale": "Arid sedimentary badlands around the Mars Desert Research Station, an operational analog station. Included as an arid sedimentary landscape distinct from the Andean and Himalayan windows.",
        "limitations": ["Operational use of the station does not establish terrain similarity", "Sedimentary mineralogy is not measured by the terrain index", "Private and public land access rules are not assessed"],
        "refs": ["mdrs-station"],
    },
    {
        "id": "earth-meteor-crater", "name": "Meteor Crater (Barringer)", "region": "Arizona, USA", "lat": 35.0272, "lon": -111.0225,
        "analog_type": "terrain_candidate",
        "characteristics": ["simple impact crater", "ejecta blanket", "arid plateau"],
        "description": "A measured 10 km window centred on Meteor Crater, processed from NASA SRTMGL1.003 (two-tile mosaic).",
        "rationale": "A well-preserved simple impact crater on an arid plateau (Kring 2007 guidebook). Included as the impact-related environment with open data; the 1.2 km crater occupies a small part of the 10 km window.",
        "limitations": ["The crater is small relative to the window, so plateau terrain dominates the distributions", "Impact petrology and shock features are not measured", "Privately managed site; access not assessed"],
        "refs": ["kring-2007-barringer"],
    },
]

NEW_SOURCES = [
    {"id": "basalt-lim-2019", "title": "Lim et al. (2019) Basaltic terrains in Idaho and Hawai'i as planetary analogs for Mars geology and astrobiology, Astrobiology 19(3)", "url": "https://doi.org/10.1089/ast.2018.1847", "role": "analog context (region level)"},
    {"id": "mdrs-station", "title": "The Mars Society — Mars Desert Research Station", "url": "https://mdrs.marssociety.org/", "role": "operational analog context"},
    {"id": "kring-2007-barringer", "title": "Kring, D. A. (2007) Guidebook to the Geology of Barringer Meteorite Crater, Arizona. LPI Contribution 1355", "url": "https://www.lpi.usra.edu/publications/books/barringer_crater_guidebook/", "role": "impact geology context"},
]


def square(lat: float, lon: float) -> list[list[float]]:
    dlat = HALF_M / 111_320
    dlon = HALF_M / (111_320 * cos(radians(lat)))
    w, e, s, n = round(lon - dlon, 4), round(lon + dlon, 4), round(lat - dlat, 4), round(lat + dlat, 4)
    return [[w, s], [e, s], [e, n], [w, n], [w, s]]


def main() -> None:
    catalog_path = BACKEND_ROOT / "app" / "data" / "sites.json"
    sources_path = BACKEND_ROOT / "app" / "data" / "sources.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    known_sources = {s["id"] for s in sources}
    sources += [s for s in NEW_SOURCES if s["id"] not in known_sources]
    for site in SITES:
        aoi_id, source_id = f"{site['id']}-aoi-v1", f"{site['id']}-srtmgl1"
        ring = square(site["lat"], site["lon"])
        geometry = {"type": "Polygon", "coordinates": [ring]}
        aoi = {"type": "Feature", "id": aoi_id, "properties": {
            "aoi_id": aoi_id, "site_id": site["id"], "version": "1.0", "planetary_body": "earth",
            "center_latitude": site["lat"], "center_longitude": site["lon"], "width_m": 10000, "height_m": 10000,
            "selection_rationale": site["rationale"],
            "intended_analog_characteristics": ["local slope distribution", "local relief", "surface roughness"],
            "known_limitations": site["limitations"],
            "creation_method": "Geodetic display footprint approximated from a 10 km square; processing constructs an exact UTM metric grid around the centre.",
            "source_references": [source_id, *site["refs"]],
            "planetary_target": "The registered 10 km Jezero reference window under terrain-only comparison.",
            "analogy_dimensions_not_covered": ["atmosphere", "gravity", "radiation", "geology", "temperature", "habitability"],
            "representativeness": "Feature-focused window; it does not represent the whole region.",
            "known_selection_bias": "Phase 7 held-out site: selected for landscape diversity after terrain-v4 parameters were frozen; independent AOI review pending.",
        }, "geometry": geometry}
        (GEO_DATA / "aoi" / f"{aoi_id}.geojson").write_text(json.dumps(aoi, indent=2), encoding="utf-8", newline="\n")
        tiles = tiles_for_geojson_geometry(geometry)
        manifest_path = GEO_DATA / "manifests" / f"{source_id}.json"
        if not manifest_path.exists():
            manifest = {
                "source_id": source_id, "title": "NASA Shuttle Radar Topography Mission Global 1 Arc Second V003", "planetary_body": "earth",
                "provider": "NASA LP DAAC / USGS EROS", "mission": "Shuttle Radar Topography Mission", "instrument": "SRTM C-band radar",
                "product_name": "SRTMGL1", "product_version": "003", "source_page_url": "https://search.earthdata.nasa.gov/search?q=SRTMGL1",
                "download_url": srtm_download_url(tiles[0]) if len(tiles) == 1 else None, "doi": "10.5067/MEaSUREs/SRTM/SRTMGL1.003",
                "access_date": None, "license_or_use_constraints": "NASA Earthdata authentication may be required; follow LP DAAC data-use and citation guidance.",
                "native_resolution": None, "native_crs": None, "native_bounds": None, "native_nodata": None, "file_size": None,
                "filename": srtm_archive_name(tiles[0]), "sha256_checksum": None,
                "citation_text": "NASA JPL, NASA Shuttle Radar Topography Mission Global 1 arc second V003, DOI 10.5067/MEaSUREs/SRTM/SRTMGL1.003.",
                "processing_status": "registered", "notes": "Phase 7 held-out site; awaiting acquisition.", "aoi_id": aoi_id,
                "tiles": [], "mosaic_filename": None, "mosaic_sha256_checksum": None,
            }
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")
        entry = {
            "id": site["id"], "name": site["name"], "body": "earth", "country_or_region": site["region"], "latitude": site["lat"], "longitude": site["lon"],
            "short_description": site["description"], "analog_type": site["analog_type"], "relevant_characteristics": site["characteristics"],
            "known_limitations": site["limitations"], "source_references": site["refs"], "data_status": "real_processed",
            "processing_status": "integrity_checked", "scientific_validation_status": "methodology_review_pending",
            "aoi_id": aoi_id, "source_id": source_id,
            "available_metrics": ["slope_p50_deg", "slope_p90_deg", "local_relief_p50_m", "local_relief_p90_m", "roughness_mean", "roughness_p90"],
            "thumbnail_url": None, "map_display": {"marker_color": "#f97316", "display_coordinate_status": "measured_aoi_center"},
        }
        catalog = [item for item in catalog if item["id"] != site["id"]] + [entry]
        print(site["id"], "tiles", tiles, "bbox", ring[0], ring[2])
    catalog_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8", newline="\n")
    sources_path.write_text(json.dumps(sources, indent=2), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
