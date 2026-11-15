"""Mars and Moon reference windows: provenance, projection, coverage, switching, floors and discrimination."""
import json
from itertools import combinations
from math import cos, radians

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import analogue_v1_service as av
from app.services.geospatial_service import GEO_DATA, load_aoi, load_manifest, sha256_file
from app.services.terrain_quantiles import w1_quantiles

client = TestClient(app)
NEW_MARS = ["mars-gale-aeolis-palus", "mars-insight-elysium", "mars-gusev-plains", "mars-eberswalde-delta"]
ALL_MARS = ["mars-jezero", *NEW_MARS]
MARS_M_PER_DEG = 3_396_190.0 * np.pi / 180


@pytest.mark.parametrize("site_id", NEW_MARS)
def test_new_mars_reference_has_verified_provenance_and_local_projection(site_id):
    import rasterio
    manifest = load_manifest(f"{site_id}-ctx-dtm")
    assert manifest.extracted_sha256_checksum and manifest.extracted_filename.startswith("mars/")
    clip = GEO_DATA / "raw" / manifest.extracted_filename
    if not clip.exists():
        pytest.skip("derived DTM clip not present (data/raw is not committed); run app.scripts.register_mars_references")
    assert sha256_file(clip) == manifest.extracted_sha256_checksum == manifest.sha256_checksum
    assert manifest.doi == "10.5066/P9JKVWR3" and manifest.product_name == "MRO_CTX_controlled_USGS_DTM"
    assert manifest.download_url.startswith("https://astrogeo-ard.s3")
    aoi = load_aoi(f"{site_id}-aoi-v1")
    with rasterio.open(clip) as ds:
        params = ds.crs.to_dict()
        assert params.get("proj") == "eqc" and abs(params.get("lat_ts") - aoi.center_latitude) < 1e-4 and abs(params.get("lon_0") - aoi.center_longitude) < 1e-4
        assert ds.res == (20.0, 20.0)


@pytest.mark.parametrize("site_id", NEW_MARS)
def test_new_mars_reference_covers_a_ten_kilometre_window(site_id):
    art = av.artifact(site_id)
    assert art and art["body"] == "mars" and art["core_width_m"] == 10000
    for f, v in art["scales"]["60"]["features"].items():
        assert v["coverage"] >= 0.99, f
    ring = json.loads((GEO_DATA / "aoi" / f"{site_id}-aoi-v1.geojson").read_text())["geometry"]["coordinates"][0]
    lat = sum(p[1] for p in ring[:4]) / 4
    width_km = (max(p[0] for p in ring) - min(p[0] for p in ring)) * MARS_M_PER_DEG * cos(radians(lat)) / 1000
    height_km = (max(p[1] for p in ring) - min(p[1] for p in ring)) * MARS_M_PER_DEG / 1000
    assert width_km == pytest.approx(10, abs=0.05) and height_km == pytest.approx(10, abs=0.05)
    assert set(art["sensitivity_windows"]) == {"north_2km", "south_2km", "east_2km", "west_2km"}


@pytest.mark.parametrize("site_id", NEW_MARS)
def test_new_mars_reference_imagery_is_its_own_ctx_orthoimage(site_id):
    record = json.loads((GEO_DATA / "processed" / "imagery" / f"{site_id}-ctx-reference.json").read_text())
    png = GEO_DATA / "processed" / "imagery" / f"{site_id}-ctx-reference.png"
    assert record["site_id"] == site_id and record["aoi_id"] == f"{site_id}-aoi-v1" and record["aoi_coverage_fraction"] >= 0.99
    assert sha256_file(png) == record["preview_checksum"]
    assert record["product_id"] == load_manifest(f"{site_id}-ctx-dtm").product_version
    imagery = client.get(f"/api/sites/{site_id}/imagery").json()
    assert any(r["mode"] == "reference" and r["preview_url"] and r["data_status"] == "available" for r in imagery)


def test_jezero_floor_reproduces_the_published_calibration():
    cal = av.calibration()
    floor = av.reference_floor(av.artifact("mars-jezero"))
    for f in ("slope", "relative_elevation"):
        assert floor[f]["combined"] == pytest.approx(cal["resolution_floor"][f]["combined"], abs=1e-3)


def test_switching_reference_changes_values_ranks_and_background():
    by_ref = {r: client.get("/api/v3/compare", params={"reference": r, "profile": "terrain_analogy"}).json() for r in ALL_MARS}
    for ref, data in by_ref.items():
        assert data["reference_site_id"] == ref and data["profile_state"] == "ranked"
        assert data["base_rate"]["count"] == 88 and data["discrimination"]["background"] == data["base_rate"]
    idx = {ref: {r["site_id"]: r["observed_index"] for r in d["results"] if r["observed_index"] is not None} for ref, d in by_ref.items()}
    for a, b in combinations(ALL_MARS, 2):
        assert idx[a] != idx[b], f"{a} and {b} must not reuse each other's values"
        assert by_ref[a]["resolution_floor"] != by_ref[b]["resolution_floor"]


def test_population_reproduces_the_frozen_tolerance_and_background_shares():
    cal = av.calibration()
    pop = json.loads((GEO_DATA / "processed" / "evaluation" / "analogue-v1-population.json").read_text())["windows"]
    names = sorted(pop)
    for f in cal["redundancy"]["scored"]:
        pair = np.median([w1_quantiles(pop[a]["60"]["features"][f]["quantiles"], pop[b]["60"]["features"][f]["quantiles"]) for a, b in combinations(names, 2)])
        assert pair == pytest.approx(cal["tau"][f]["60"], abs=1e-3)
    data = client.get("/api/v3/compare").json()
    background = av._background(av.artifact("mars-jezero"), av.reference_floor(av.artifact("mars-jezero")))
    for r in data["results"]:
        if r["observed_index"] is not None:
            manual = sum(1 for v in background if v >= r["observed_index"] - 0.006) / len(background)
            assert r["background_share"] == pytest.approx(manual, abs=0.012)


def test_discrimination_analysis_covers_every_reference_and_states_its_limits():
    disc = json.loads((GEO_DATA / "processed" / "evaluation" / "analogue-v1-discrimination.json").read_text())
    assert set(disc["references"]) >= {*ALL_MARS, "moon-south-pole-shackleton"}
    assert "not confidence intervals" in disc["notice"] and "independent samples" in disc["population"]["caveat"]
    for ref in ALL_MARS:
        r = disc["references"][ref]
        assert set(r["single_feature"]) == {"slope", "relative_elevation"}
        assert {"phase5_tau", "tau_x0.5", "tau_x2"} == set(r["alternative_tolerances"])
        assert len(r["leave_one_region_out"]) == len(disc["population"]["regions"])


def test_mars_profiles_without_thermal_records_say_so():
    data = client.get("/api/v3/compare", params={"reference": "mars-gale-aeolis-palus", "profile": "mars_base_field_testing"}).json()
    partial = [r for r in data["results"] if r["state"] == "partial"]
    assert partial and all("No comparable thermal record exists for this reference" in r["simple"]["conclusion"] for r in partial)
