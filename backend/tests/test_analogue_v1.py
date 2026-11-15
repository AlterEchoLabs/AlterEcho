"""analogue-method-v1.0: arithmetic, measurement, eligibility, profiles, negatives and API contract."""
from math import exp, isclose, log
import random

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import analogue_math as am
from app.services import analogue_reference as ref
from app.services import analogue_v1_service as av
from app.services.terrain_quantiles import U, feature_arrays, quantile_function, w1_quantiles

client = TestClient(app)
RANKABLE = {"earth-atacama-south", "earth-upper-mustang", "earth-ladakh", "earth-danakil", "earth-craters-of-the-moon", "earth-hanksville-mdrs", "earth-meteor-crater"}


def get(path, **params):
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------------ the handoff's reference arithmetic

def test_reference_arithmetic_from_the_methodology_document_passes():
    assert ref.similarity(0, 10) == 1.0
    assert abs(ref.similarity(10, 10) - 0.5) < 1e-12
    assert abs(ref.similarity(20, 10) - 0.0625) < 1e-12
    assert ref.similarity(5, 10) > ref.similarity(10, 10) > ref.similarity(20, 10)
    assert abs(ref.weighted_w1([0, 2], [1, 1], [1, 3], [1, 1]) - 1) < 1e-12
    assert ref.weighted_w1([2], [4], [2], [8]) == 0
    assert abs(ref.weighted_w1([0, 10], [3, 1], [0], [1]) - 2.5) < 1e-12
    score, coverage = ref.observed_index({"terrain": (0.3, True, 0.8), "geology": (0.7, False, None)})
    assert abs(score - 80) < 1e-12 and abs(coverage - 0.3) < 1e-12
    assert ref.observed_index({"terrain": (1.0, False, None)}) == (None, 0.0)


@pytest.mark.parametrize("d,tau,expected", [(0, 8, 1.0), (8, 8, 0.5), (16, 8, 0.0625), (5.8, 5.8, 0.5)])
def test_similarity_transform_reference_values(d, tau, expected):
    assert isclose(am.similarity(d, tau), expected, abs_tol=1e-12)
    assert isclose(am.similarity(d, tau), ref.similarity(d, tau), abs_tol=1e-12)


@pytest.mark.parametrize("d,tau", [(None, 1), (1, None), (1, 0), (1, -2), (-1, 1), (float("nan"), 1), (1, float("inf"))])
def test_invalid_similarity_inputs_give_no_score_not_zero(d, tau):
    assert am.similarity(d, tau) is None


def test_similarity_decreases_monotonically_with_mismatch():
    values = [am.similarity(d, 5.0) for d in np.linspace(0, 20, 41)]
    assert all(a > b for a, b in zip(values, values[1:]))


def test_scalar_distance_requires_matching_units():
    assert am.scalar_distance(3.0, 1.0, "m", "metres") == 2.0
    assert am.scalar_distance(3.0, 1.0, "m", "degrees") is None
    assert am.scalar_distance(3.0, 1.0, "ft", "m") is None
    assert am.scalar_distance(None, 1.0, "m", "m") is None


# ------------------------------------------------------------------ distances

def test_area_weighted_w1_matches_the_reference_implementation():
    rng = random.Random(7)
    for _ in range(20):
        a = [rng.uniform(-50, 50) for _ in range(rng.randint(1, 30))]
        b = [rng.uniform(-50, 50) for _ in range(rng.randint(1, 30))]
        wa = [rng.uniform(0, 3) for _ in a]
        wb = [rng.uniform(0, 3) for _ in b]
        if sum(wa) == 0 or sum(wb) == 0:
            continue
        assert isclose(am.w1_samples(a, b, wa, wb), ref.weighted_w1(a, wa, b, wb), rel_tol=1e-9, abs_tol=1e-9)


def test_w1_is_zero_for_identical_and_equals_a_constant_shift():
    x = np.random.default_rng(1).normal(10, 3, 5000)
    assert am.w1_samples(x, x) == 0
    assert isclose(am.w1_samples(x, x + 2.5), 2.5, rel_tol=1e-9)
    qx, qy = quantile_function(x), quantile_function(x + 2.5)
    assert isclose(w1_quantiles(qx, qy), 2.5, abs_tol=2e-3)


def test_quantile_w1_approximates_exact_w1_and_ignores_masked_cells():
    rng = np.random.default_rng(3)
    a, b = rng.gamma(2.0, 1.5, 20000), rng.gamma(2.5, 1.2, 20000)
    exact = am.w1_samples(a, b)
    assert isclose(am.w1_quantile_functions(quantile_function(a), quantile_function(b)), exact, rel_tol=0.02)
    masked = a.copy(); masked[:5000] = np.nan
    assert quantile_function(masked) == quantile_function(a[5000:])


def test_w1_rejects_mismatched_grids_and_empty_input():
    with pytest.raises(am.AnalogueMethodError):
        am.w1_quantile_functions([1, 2], [1, 2, 3])
    with pytest.raises(am.AnalogueMethodError):
        am.w1_samples([np.nan], [1.0])


# ------------------------------------------------------------------ aggregation

def test_family_score_needs_every_required_feature():
    assert am.family_score({"slope": (0.5, 0.8, True), "relative_elevation": (0.5, 0.6, True)}) == pytest.approx(0.7)
    assert am.family_score({"slope": (0.5, 0.8, True), "relative_elevation": (0.5, None, True)}) is None
    with pytest.raises(am.AnalogueMethodError):
        am.family_score({"slope": (0.6, 0.8, True), "relative_elevation": (0.5, 0.6, True)})


def test_observed_index_matches_reference_and_is_undefined_without_eligible_families():
    rng = random.Random(11)
    for _ in range(50):
        names = ["terrain", "geology", "temperature", "water"]
        raw = [rng.random() for _ in names]
        weights = [r / sum(raw) for r in raw]
        weights[-1] = 1 - sum(weights[:-1])
        fams = {n: (w, rng.random() < 0.5, rng.random()) for n, w in zip(names, weights)}
        ref_fams = {n: (w, e, s if e else None) for n, (w, e, s) in fams.items()}
        mine, ref_out = am.observed_index(fams), ref.observed_index(ref_fams)
        assert (mine[0] is None) == (ref_out[0] is None)
        if mine[0] is not None:
            assert isclose(mine[0], ref_out[0], rel_tol=1e-12)
        assert isclose(mine[1], ref_out[1], abs_tol=1e-12)
    assert am.observed_index({"terrain": (0.3, False, None), "geology": (0.7, False, None)}) == (None, 0.0)


def test_competition_ranks_share_the_group_position():
    assert am.competition_ranks([["a", "b", "c"], ["d"], ["e", "f"]]) == {"a": 1, "b": 1, "c": 1, "d": 4, "e": 5, "f": 5}


# ------------------------------------------------------------------ calibration and negatives

def test_calibration_rules_hold_in_the_frozen_file():
    cal = av.calibration()
    assert cal["redundancy"]["scored"] == ["slope", "relative_elevation"]
    assert set(cal["redundancy"]["redundant_with"]) == {"local_relief", "roughness"}
    for f in cal["redundancy"]["scored"]:
        t, d = cal["tau"][f], cal["resolution_floor"][f]
        assert t["60"] >= cal["rules"]["noise_factor"] * d["combined"] and t["noise_condition"]["passed"]
        assert isclose(d["combined"], (d["placement"] ** 2 + (d["dem_product"] or 0) ** 2) ** 0.5, abs_tol=1e-3)


def test_synthetic_negatives_score_low_and_identical_copy_scores_100():
    syn = av.calibration()["synthetic_negatives"]
    assert syn["identical_copy"]["index_vs_jezero"] == 100.0
    for kind in ("tilted_plane_15deg", "ridges_150m_2km", "fractal_relief_1500m"):
        assert syn[kind]["index_vs_jezero"] < 50, kind
    # The gentle fractal look-alike is expected to score high: distributions ignore spatial arrangement.
    assert syn["fractal_relief_300m"]["index_vs_jezero"] > 50 and "look-alike" in syn["fractal_relief_300m"]["expectation"]


def test_unrelated_landscapes_are_not_all_near_100():
    base = av.calibration()["base_rate"]
    assert base["share_at_or_above"]["99"] < 0.05 and base["share_at_or_above"]["50"] < 0.9


def test_flat_and_plane_features_on_synthetic_grids():
    flat = np.zeros((60, 60))
    core = (slice(10, 50), slice(10, 50))
    arrays = feature_arrays(flat, core, 60.0)
    assert np.nanmax(arrays["slope"]) == 0 and np.nanmax(arrays["relative_elevation"]) == 0
    yy, xx = np.mgrid[0:60, 0:60] * 60.0
    plane = feature_arrays(np.tan(np.radians(10)) * xx, core, 60.0)
    assert np.nanmedian(plane["slope"]) == pytest.approx(10.0, abs=0.01)


# ------------------------------------------------------------------ service behaviour

def test_terrain_analogy_ranks_with_ties_and_excludes_the_contaminated_window():
    data = get("/api/v3/compare", profile="terrain_analogy")
    assert data["profile_state"] == "ranked" and data["method_version"] == "analogue-method-v1.0"
    ranked = {r["site_id"]: r for r in data["results"] if r["state"] == "ranked"}
    assert set(ranked) == RANKABLE
    for group in data["tie_groups"]:
        assert len({ranked[s]["rank"] for s in group}) == 1
    atacama = next(r for r in data["results"] if r["site_id"] == "earth-atacama")
    assert atacama["state"] == "excluded" and atacama["observed_index"] is None and "industrial" in atacama["exclusion"]["reason"]
    assert any(r["state"] == "not_measured" for r in data["results"])


def test_every_scored_feature_exposes_raw_values_distance_tolerance_and_contribution():
    data = get("/api/v3/compare", profile="terrain_analogy")
    r = next(x for x in data["results"] if x["site_id"] == "earth-hanksville-mdrs")
    terrain = next(f for f in r["families"] if f["family"] == "terrain")
    scored = [f for f in terrain["features"] if f["role"] == "scored"]
    assert {f["feature"] for f in scored} == {"slope", "relative_elevation"}
    for f in scored:
        assert f["eligible"] and f["earth"]["median"] is not None and f["planet"]["median"] is not None
        assert isclose(f["similarity"], exp(-log(2) * (f["distance"] / f["tau"]) ** 2), rel_tol=1e-4)
        assert isclose(f["contribution"], 100 * f["weight"] * f["similarity"], abs_tol=1e-2)
    assert isclose(r["observed_index"], sum(f["contribution"] for f in scored), abs_tol=0.02)
    assert all(f["similarity"] is None and "not scored" in f["reason"] for f in terrain["features"] if f["role"] == "diagnostic")


def test_partial_profiles_report_coverage_and_never_headline_an_index():
    data = get("/api/v3/compare", profile="balanced_science")
    assert data["profile_state"] == "partial" and data["tie_groups"] == []
    assert isclose(data["evidence_coverage"], 0.3)
    for r in data["results"]:
        if r["state"] == "partial":
            assert r["rank"] is None and not r["simple"]["show_index"]
            assert "Terrain evidence available; 30% of planned science evidence measured." in r["simple"]["conclusion"]
            assert r["critical_gates"] == {"terrain": True, "geology": False}
    rover = get("/api/v3/compare", profile="rover_mobility")
    assert rover["profile_state"] == "partial" and isclose(rover["evidence_coverage"], 0.8)
    assert all("Wheel-scale traversability" in r["simple"]["conclusion"] for r in rover["results"] if r["state"] == "partial")
    base = get("/api/v3/compare", profile="mars_base_field_testing")
    assert base["profile_state"] == "partial" and isclose(base["evidence_coverage"], 0.35)
    assert all("not base or landing-site suitability" in r["simple"]["conclusion"] for r in base["results"] if r["state"] == "partial")


def test_biosignature_profile_is_not_assessed_and_makes_no_life_claim():
    data = get("/api/v3/compare", profile="biosignature_fieldwork")
    assert data["profile_state"] == "not_assessed" and data["tie_groups"] == []
    for r in data["results"]:
        assert r["observed_index"] is None and r["rank"] is None
        if r["state"] == "not_assessed":
            assert "No claim is made that life has been observed on Mars" in r["simple"]["conclusion"]


def test_simple_result_text_matches_numeric_coverage_and_resolution():
    data = get("/api/v3/compare", profile="terrain_analogy")
    for r in data["results"]:
        if r["state"] != "ranked":
            continue
        assert r["simple"]["coverage_text"].startswith(f"{r['evidence_coverage']:.0%}")
        assert "terrain only" in r["simple"]["conclusion"]
        if r["resolution"] == "unresolved_from_reference":
            assert "is not resolved from the Jezero Crater window by these tests" in r["simple"]["conclusion"]
        assert r["simple"]["show_index"] is True and r["sensitivity"]["index_range"][0] <= r["observed_index"] <= r["sensitivity"]["index_range"][1]


def test_comparison_is_deterministic():
    a, b = av.compare("mars-jezero", "terrain_analogy"), av.compare("mars-jezero", "terrain_analogy")
    assert a.model_dump(exclude={"generated_at"}) == b.model_dump(exclude={"generated_at"})


def test_wrong_inputs_are_rejected_as_ineligible_not_scored():
    jezero, site = av.artifact("mars-jezero"), av.artifact("earth-hanksville-mdrs")
    broken = {k: {**v, "features": {f: dict(e) for f, e in v["features"].items()}} for k, v in site["scales"].items()}
    broken["60"]["features"]["slope"]["units"] = "percent"
    feats, s_g, ok, reason = av.terrain_features(jezero["scales"], broken)
    assert not ok and s_g is None and "Units differ" in next(f.reason for f in feats if f.feature == "slope")
    low = {k: {**v, "features": {f: dict(e) for f, e in v["features"].items()}} for k, v in site["scales"].items()}
    low["60"]["features"]["relative_elevation"]["coverage"] = 0.5
    feats, s_g, ok, _ = av.terrain_features(jezero["scales"], low)
    assert not ok and s_g is None and "coverage below" in next(f.reason for f in feats if f.feature == "relative_elevation")


def test_api_rejects_earth_reference_unknown_sites_and_bad_profiles():
    assert client.get("/api/v3/compare", params={"reference": "earth-ladakh"}).status_code == 422
    assert client.get("/api/v3/compare", params={"reference": "no-such-site"}).status_code == 404
    assert client.get("/api/v3/compare", params={"profile": "best_analogue"}).status_code == 422
    assert client.get("/api/v3/result", params={"site": "../etc"}).status_code == 422


def test_moon_reference_fails_its_own_resolution_floor_and_shows_distances_only():
    data = get("/api/v3/compare", reference="moon-south-pole-shackleton")
    assert data["reference_body"] == "moon" and data["base_rate"] is None and data["profile_state"] == "not_assessed"
    floor = data["resolution_floor"]
    assert not floor["slope"]["noise_condition_passed"] and not floor["relative_elevation"]["noise_condition_passed"]
    for r in data["results"]:
        assert r["observed_index"] is None and r["rank"] is None
        if r["state"] == "not_assessed":
            terrain = next(f for f in r["families"] if f["family"] == "terrain")
            assert terrain["status"] == "measured_context_only"
            assert all(f["distance"] is not None and f["similarity"] is None for f in terrain["features"] if f["role"] == "scored")
            assert "no index is given" in r["simple"]["conclusion"]


# ------------------------------------------------------------------ full evidence, data roles, explorer

def test_full_result_export_is_reproducible_and_complete():
    data = get("/api/v3/result", site="earth-craters-of-the-moon")
    assert data["candidate"]["site_id"] == "earth-craters-of-the-moon"
    assert {d["feature"] for d in data["distributions"]} == {"slope", "relative_elevation", "local_relief", "roughness"}
    assert len(data["distributions"][0]["u"]) == len(data["distributions"][0]["earth"]) == len(data["distributions"][0]["planet"])
    assert "s_k = exp(-ln 2" in data["comparison"]["formulas"]["feature_similarity"]
    assert data["earth_window"]["source_sha256"] and data["reference_window"]["source_sha256"]
    assert data["reproducibility"]["recompute"].endswith("analogue_v1_calibration")
    assert all(s["url"] for s in data["sources"] if s["role"] != "literature")


def test_data_roles_explain_every_product_without_claiming_too_much():
    roles = get("/api/v3/data-roles")
    by = {r["id"]: r for r in roles}
    assert by["sentinel2"]["role"] == "display_context" and "geology or mineralogy" in by["sentinel2"]["cannot_establish"]
    assert by["srtmgl1"]["role"] == "scored_input" and any("soil strength" in c for c in by["srtmgl1"]["cannot_establish"])
    assert all(r["cannot_establish"] and r["measures"] for r in roles)


def test_explorer_returns_exact_ten_kilometre_corners_and_native_zoom():
    data = get("/api/v3/sites/earth-meteor-crater/explorer")
    corners = data["aoi_corners"]
    assert len(corners) == 4
    lat = data["center"][1]
    width_km = (corners[1][0] - corners[0][0]) * 111.32 * np.cos(np.radians(lat))
    height_km = (corners[0][1] - corners[3][1]) * 111.32
    assert width_km == pytest.approx(10, abs=0.15) and height_km == pytest.approx(10, abs=0.15)
    assert 13 < data["max_native_zoom"] < 15 and data["imagery"]["acquired"].startswith("2026")
    assert client.get("/api/v3/sites/mars-jezero/explorer").status_code == 404


def test_committed_routes_do_not_import_rasterio(monkeypatch):
    """Regression for native GDAL libraries being unavailable in a serverless runtime."""
    import builtins

    real_import = builtins.__import__

    def without_rasterio(name, *args, **kwargs):
        if name == "rasterio" or name.startswith("rasterio."):
            raise ImportError("rasterio is unavailable in this runtime")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_rasterio)
    explorer = client.get("/api/v3/sites/earth-hanksville-mdrs/explorer")
    assert explorer.status_code == 200
    payload = explorer.json()
    assert len(payload["aoi_corners"]) == len(payload["imagery"]["corners"]) == 4
    assert payload["aoi_corners"] == payload["imagery"]["corners"]
    assert payload["aoi_corners"][0] == pytest.approx([-110.84907281, 38.45154873], abs=1e-8)
    assert payload["hillshade"]["corners"] != payload["aoi_corners"]  # 334 x 30 m is an explicit 10.02 km display grid.
    assert payload["imagery"]["url"].endswith("earth-hanksville-mdrs-sentinel-reference.png")
    image = client.get(payload["imagery"]["url"])
    assert image.status_code == 200 and image.headers["content-type"] == "image/png" and image.content.startswith(b"\x89PNG")

    health = client.get("/api/health")
    assert health.status_code == 200 and health.json()["data_counts"]["real_processed_sites"] == 14
    assert client.get("/api/v3/references").status_code == 200
    assert client.get("/api/sites").status_code == 200
    assert client.get("/api/sites/earth-hanksville-mdrs/imagery").status_code == 200
    assert client.get("/api/v3/result", params={"site": "earth-hanksville-mdrs", "reference": "mars-jezero", "profile": "terrain_analogy"}).status_code == 200
    assert client.post("/api/explore/preflight", json={"lat": 38.4064, "lon": -110.7919}).status_code == 200
