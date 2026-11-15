"""analog-evidence-v1: missing data, comparability gates, profile weighting, fairness and reproducibility."""
import copy
import json
from math import isclose

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import evidence_service as ev
from app.services.terrain_v3_service import compare_v3, load_v3_artifact

client = TestClient(app)
EARTH = ["earth-atacama", "earth-upper-mustang", "earth-ladakh"]


def compare(profile: str, candidates=EARTH):
    response = client.post("/api/evidence/compare", json={"candidate_site_ids": candidates, "profile_id": profile})
    assert response.status_code == 200, response.text
    return response.json()


def test_profiles_are_versioned_and_marked_provisional():
    profiles = client.get("/api/evidence/profiles").json()
    assert {p["id"] for p in profiles} == {"balanced_science", "rover_mobility", "biosignature_fieldwork", "mars_base_field_testing"}
    for profile in profiles:
        assert isclose(sum(profile["weights"].values()), 1.0, abs_tol=1e-9)
        assert profile["review_status"] == "provisional_pending_expert_review"
    assert client.get("/api/evidence/model").json()["default_profile"] == "balanced_science"


def test_balanced_profile_ranks_on_a_common_measured_basis_and_discloses_denominator():
    data = compare("balanced_science")
    assert data["ranking_status"] == "ranked"
    assert data["common_basis"] == ["terrain", "temperature"]
    assert isclose(data["common_basis_weight_fraction"], 0.5)
    for result in data["results"]:
        assert result["scoring_basis"] == ["terrain", "temperature"]
        assert isclose(result["backed_weight_fraction"], 0.5)
        assert 0 <= result["index"] <= 100


def test_missing_and_context_evidence_never_becomes_zero():
    for result in compare("balanced_science")["results"]:
        for dim in result["dimensions"]:
            if dim["status"] != "measured":
                assert dim["similarity"] is None and dim["used_in_score"] is False


def test_profile_without_required_evidence_withholds_ranking_but_keeps_terrain_baseline():
    data = compare("biosignature_fieldwork")
    assert data["ranking_status"] == "insufficient_evidence" and data["common_basis"] == []
    for result in data["results"]:
        assert result["index"] is None and result["rank"] is None
        assert result["terrain_baseline"]["index"] > 0
        assert all(f["kind"] == "gap" for f in result["factors"])
        assert not any("(measured)" in f["text"] for f in result["factors"])


def test_terrain_baseline_equals_unchanged_terrain_v3():
    reference = load_v3_artifact("mars-jezero")
    for result in compare("rover_mobility")["results"]:
        expected = compare_v3(reference, load_v3_artifact(result["site_id"]))["display_index"]
        assert result["terrain_baseline"]["index"] == expected


def test_profile_weights_change_index_values_reproducibly():
    balanced = {r["site_id"]: r["index"] for r in compare("balanced_science")["results"]}
    rover = {r["site_id"]: r["index"] for r in compare("rover_mobility")["results"]}
    assert balanced != rover
    ev._compare_cached.cache_clear()
    again = {r["site_id"]: r["index"] for r in compare("balanced_science")["results"]}
    assert again == balanced


def test_index_matches_documented_formula():
    data = compare("balanced_science")
    weights = data["profile"]["weights"]
    for result in data["results"]:
        sims = {d["dimension"]: d["similarity"] for d in result["dimensions"] if d["used_in_score"]}
        expected = 100 * sum(weights[d] * s for d, s in sims.items()) / sum(weights[d] for d in sims)
        assert isclose(result["index"], round(expected, 1), abs_tol=0.051)


def test_unchanged_order_is_explained_not_manufactured():
    data = compare("rover_mobility")
    terrain_order = sorted(data["results"], key=lambda r: r["terrain_baseline"]["rank"])
    if [r["site_id"] for r in data["results"]] == [r["site_id"] for r in terrain_order]:
        assert "terrain-only baseline" in data["ordering_note"]


def test_sensitivity_is_reported_for_ranked_results():
    for result in compare("mars_base_field_testing")["results"]:
        sens = result["sensitivity"]
        assert sens["tested_configurations"] > 1
        assert sens["index_range"][0] <= result["index"] <= sens["index_range"][1]
        assert "Not a confidence interval" in sens["notice"]


def test_gaussian_similarity_is_one_for_identical_and_monotonic():
    assert ev._gaussian(0, 10) == 1.0
    values = [ev._gaussian(d, 10) for d in (0, 5, 10, 20, 40)]
    assert values == sorted(values, reverse=True)
    with pytest.raises(ev.EvidenceError):
        ev._gaussian(1, 0)


def _thermal(site_id):
    return copy.deepcopy(ev.load_thermal(site_id))


def test_thermal_gate_rejects_incompatible_units_quantities_and_local_times():
    mars, earth = _thermal("mars-jezero"), _thermal("earth-atacama")
    assert ev.thermal_comparability(mars, earth) is None
    bad_units = copy.deepcopy(earth); bad_units["product"]["units"] = "degC"
    assert "kelvin" in ev.thermal_comparability(mars, bad_units)
    air = copy.deepcopy(earth); air["quantity"] = "air_temperature"
    assert "air" in ev.thermal_comparability(mars, air)
    shifted = copy.deepcopy(earth); shifted["summary"]["day_local_solar_time_p50_h"] = 10.5
    assert "Local solar times" in ev.thermal_comparability(mars, shifted)
    sparse = copy.deepcopy(mars); sparse["summary"]["solar_longitude_range_deg"] = [10, 90]
    assert "seasonal" in ev.thermal_comparability(sparse, earth)


def test_non_comparable_thermal_evidence_is_excluded_not_zeroed(monkeypatch):
    original = ev.load_thermal

    def patched(site_id):
        data = copy.deepcopy(original(site_id))
        if data and site_id == "earth-ladakh":
            data["summary"]["night_local_solar_time_p50_h"] = 22.0
        return data

    monkeypatch.setattr(ev, "load_thermal", patched)
    ev._compare_cached.cache_clear()
    data = ev.compare("mars-jezero", EARTH, "rover_mobility").model_dump()
    ladakh = next(r for r in data["results"] if r["site_id"] == "earth-ladakh")
    thermal = next(d for d in ladakh["dimensions"] if d["dimension"] == "temperature")
    assert thermal["status"] == "not_comparable" and thermal["similarity"] is None
    # Fairness: the common basis shrinks to terrain for EVERY candidate rather than mixing bases.
    assert data["common_basis"] == ["terrain"]
    assert all(r["scoring_basis"] == ["terrain"] for r in data["results"])
    # Under Balanced science terrain alone is 35% of the weight (< 40% floor): no ranking is shown.
    balanced = ev.compare("mars-jezero", EARTH, "balanced_science").model_dump()
    assert balanced["ranking_status"] == "insufficient_evidence"
    ev._compare_cached.cache_clear()


def test_mars_thermal_samples_are_inside_the_aoi_and_cover_a_mars_year():
    mars = ev.load_thermal("mars-jezero")
    used = [s for s in mars["samples"] if s.get("day_ground_temp_k") is not None or s.get("night_ground_temp_k") is not None]
    assert used and all(s["rover_inside_aoi"] for s in used)
    span = mars["summary"]["solar_longitude_range_deg"]
    assert span[1] - span[0] >= 270
    assert all(item["sha256"] and len(item["sha256"]) == 64 for item in mars["inputs"])


def test_earth_thermal_artifacts_record_view_time_and_quality_policy():
    for site_id in EARTH:
        data = ev.load_thermal(site_id)
        assert data["product"]["product_id"] == "MYD11A2.061" and data["product"]["units"] == "K"
        assert data["summary"]["paired_samples"] >= 30
        assert all(len(s["raw_window_sha256"]) == 64 for s in data["samples"])


def test_site_evidence_reports_status_for_every_dimension():
    for site_id in ["mars-jezero", *EARTH]:
        payload = client.get(f"/api/sites/{site_id}/evidence").json()
        assert [d["dimension"] for d in payload["dimensions"]] == ev.DIMENSIONS
        for dim in payload["dimensions"]:
            assert dim["status"] in {"measured", "proxy", "context_only", "missing", "not_comparable"}
            assert dim["reason"]


def test_compare_rejects_unknown_profiles_sites_and_wrong_bodies():
    assert client.post("/api/evidence/compare", json={"candidate_site_ids": EARTH, "profile_id": "nope"}).status_code == 422
    assert client.post("/api/evidence/compare", json={"candidate_site_ids": ["earth-nowhere"]}).status_code == 404
    assert client.post("/api/evidence/compare", json={"candidate_site_ids": ["mars-jezero"]}).status_code == 422
    assert client.post("/api/evidence/compare", json={"candidate_site_ids": ["earth-atacama"], "reference_site_id": "earth-ladakh"}).status_code == 422


def test_planned_site_is_listed_as_insufficient_not_scored():
    data = compare("balanced_science", EARTH + ["earth-holuhraun"])
    holuhraun = next(r for r in data["results"] if r["site_id"] == "earth-holuhraun")
    assert holuhraun["ranking_status"] == "insufficient_evidence" and holuhraun["index"] is None
    assert data["common_basis"] == ["terrain", "temperature"]


def test_evidence_config_profiles_reference_known_dimensions():
    config = json.loads((ev.APP_DATA / "evidence.v1.json").read_text(encoding="utf-8"))
    for profile in config["profiles"].values():
        assert set(profile["weights"]) <= set(config["dimensions"])
        assert set(profile["required_dimensions"]) <= set(profile["weights"])
