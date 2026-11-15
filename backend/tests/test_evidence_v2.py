"""analog-evidence-v2.0: statuses, profile states, ranking eligibility, temperature audit, exports."""
import copy
import json
from math import cos, isclose, radians
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services import evidence_v2_service as ev2

client = TestClient(app)
PROCESSED = {"earth-atacama", "earth-atacama-south", "earth-upper-mustang", "earth-ladakh", "earth-danakil", "earth-craters-of-the-moon", "earth-hanksville-mdrs", "earth-meteor-crater"}
STATUSES = {"measured_comparable", "measured_context_only", "source_available_unprocessed", "missing_earth", "missing_planetary", "incompatible", "review_pending"}


def compare(profile="terrain_analogy", reference="mars-jezero"):
    response = client.post("/api/v2/compare", json={"profile_id": profile, "reference_site_id": reference})
    assert response.status_code == 200, response.text
    return response.json()


def test_terrain_analogy_ranks_processed_sites_with_competition_ranks_and_tie_groups():
    data = compare()
    assert data["profile_state"] == "ranked" and data["included_dimensions"] == ["terrain"]
    ranked = [r for r in data["results"] if r["state"] == "ranked"]
    assert {r["site_id"] for r in ranked} == PROCESSED
    for group in data["tie_groups"]:
        ranks = {next(r["rank"] for r in ranked if r["site_id"] == s) for s in group}
        assert len(ranks) == 1  # every member of a tie group shares one rank
    unmeasured = [r for r in data["results"] if r["state"] == "not_rankable"]
    assert unmeasured and all(r["partial_index"] is None and r["rank"] is None for r in unmeasured)


def test_partial_index_formula_and_coverage():
    data = compare("rover_mobility")
    weights = data["profile"]["weights"]
    for r in (x for x in data["results"] if x["partial_index"] is not None):
        included = [d for d in r["dimensions"] if d["included"]]
        expected = sum(weights[d["dimension"]] * d["index"] for d in included) / sum(weights[d["dimension"]] for d in included)
        assert isclose(r["partial_index"], round(expected, 2), abs_tol=0.011)
        assert isclose(r["evidence_coverage"], sum(weights[d["dimension"]] for d in included))


def test_missing_and_context_evidence_is_never_scored():
    for r in compare("balanced_science")["results"]:
        for d in r["dimensions"]:
            assert d["status"] in STATUSES
            if d["status"] != "measured_comparable":
                assert d["included"] is False
            if not d["included"]:
                assert d["index"] is None or d["dimension"] == "terrain"


def test_task_critical_gaps_withhold_rankings():
    assert compare("balanced_science")["profile_state"] == "experimental_partial"
    assert compare("rover_mobility")["profile_state"] == "experimental_partial"
    assert compare("mars_base_field_testing")["profile_state"] == "experimental_partial"
    bio = compare("biosignature_fieldwork")
    assert bio["profile_state"] == "not_assessed" and bio["tie_groups"] == []
    assert all(r["partial_index"] is None and r["rank"] is None for r in bio["results"])
    for profile in ("balanced_science", "rover_mobility"):
        assert all(r["rank"] is None for r in compare(profile)["results"])


def test_temperature_is_context_only_and_audit_names_the_failed_checks():
    audit = client.get("/api/v2/thermal-audit/earth-atacama").json()
    assert audit["decision"] == "measured_context_only"
    failed = {c["check"] for c in audit["checks"] if c["required"] and not c["passed"]}
    assert failed == {"Spatial support", "Sampling equivalence"}
    passed = {c["check"] for c in audit["checks"] if c["passed"]}
    assert {"Product identity and units", "Local solar time", "Seasonal coverage", "Rover inside the reference AOI"} <= passed
    for r in compare("mars_base_field_testing")["results"]:
        t = next(d for d in r["dimensions"] if d["dimension"] == "temperature")
        assert t["included"] is False and t["index"] is None


def test_thermal_audit_rejects_unit_or_quantity_mismatch():
    mars, earth = ev2.load_thermal("mars-jezero"), copy.deepcopy(ev2.load_thermal("earth-atacama"))
    earth["product"]["units"] = "degC"
    assert next(c for c in ev2.thermal_audit(mars, earth).checks if c.check == "Product identity and units").passed is False
    earth = copy.deepcopy(ev2.load_thermal("earth-atacama"))
    earth["quantity"] = "air_temperature"
    assert next(c for c in ev2.thermal_audit(mars, earth).checks if c.check == "Same physical quantity").passed is False


def test_eligibility_keys_match_for_co_ranked_sites():
    keys = {r["eligibility"]["key"] for r in compare()["results"] if r["state"] == "ranked"}
    assert len(keys) == 1


def test_lunar_reference_is_limited_and_uses_method_sensitivity_only():
    data = compare(reference="moon-south-pole-shackleton")
    assert data["reference_body"] == "moon"
    assert data["evaluation"]["reference_stability"] is None
    ranked = [r for r in data["results"] if r["state"] == "ranked"]
    assert ranked[0]["site_id"] in {"earth-ladakh", "earth-upper-mustang"}  # steep terrain is closest to the pole window
    assert all(r["sensitivity"]["placement_index_range"] is None for r in ranked)
    assert "Limited lunar terrain comparison" in data["ordering_note"]
    temp = next(d for d in ranked[0]["dimensions"] if d["dimension"] == "temperature")
    assert temp["status"] == "missing_planetary"


def test_base_rate_and_reference_stability_are_reported_for_jezero():
    data = compare()
    assert data["evaluation"]["base_rate_windows"] >= 50
    assert 0 <= data["evaluation"]["base_rate_share_at_or_above"]["99"] <= 1
    assert all(v >= 99 for v in data["evaluation"]["reference_stability"].values())


def test_worked_example_contributions_sum_to_w1():
    data = client.get("/api/v2/method/worked-example?site_id=earth-ladakh&family=slope").json()
    assert isclose(sum(s["contribution"] for s in data["steps"]), data["w1"], abs_tol=1e-3)
    assert isclose(data["index_60m"], 100 * 2.718281828 ** (-0.5 * (data["w1"] / data["tau"]) ** 2), rel_tol=1e-4)


def test_report_export_is_complete_and_reproducible():
    first = client.get("/api/v2/reports/earth-ladakh?profile_id=terrain_analogy").json()
    second = client.get("/api/v2/reports/earth-ladakh?profile_id=terrain_analogy").json()
    for key in ("reference", "candidate", "result", "formulas", "parameters", "evaluation", "physical_limits", "reproduce", "statement"):
        assert key in first
    assert first["candidate"]["aoi"]["geometry"]["type"] == "Polygon"
    assert first["candidate"]["source_manifest"]["product_name"] == "SRTMGL1"
    assert first["candidate"]["measurements"]["distributions_by_scale"]["60"]["slope_deg"]["bin_edges"]
    assert first["result"]["partial_index"] == second["result"]["partial_index"]
    assert first["result"]["dimensions"] == second["result"]["dimensions"]


def test_report_rejects_unknown_sites_and_bad_ids():
    assert client.get("/api/v2/reports/earth-nowhere").status_code == 404
    assert client.get("/api/v2/reports/..%5Cx").status_code in {404, 422}


def test_historical_v1_endpoint_still_works():
    response = client.post("/api/evidence/compare", json={"candidate_site_ids": ["earth-atacama", "earth-ladakh"], "profile_id": "balanced_science"})
    assert response.status_code == 200 and response.json()["model_version"] == "analog-evidence-v1.0"


def test_sentinel_metadata_separates_footprint_scene_cloud_and_aoi_cloud():
    folder = Path(__file__).resolve().parents[1] / "data" / "processed" / "imagery"
    for path in folder.glob("earth-*-sentinel-reference.json"):
        meta = json.loads(path.read_text(encoding="utf-8"))
        assert meta["aoi_coverage_fraction"] >= 0.99, path.name
        assert meta["aoi_cloud_fraction"] is not None and meta["aoi_cloud_fraction"] <= 0.05
        assert "NOT a clear-sky fraction" in meta["aoi_coverage_meaning"]
        assert meta["registration"]["pixels"] == 1000 and meta["registration"]["pixel_m"] == 10.0
        assert str(meta["acquisition_datetime"])[:4] in meta["attribution"]


def test_ctx_crop_covers_the_same_ground_as_the_dem_window():
    meta = json.loads((Path(__file__).resolve().parents[1] / "data" / "processed" / "imagery" / "mars-jezero-ctx-reference.json").read_text(encoding="utf-8"))
    reg = meta["registration"]
    assert reg["crs_latitude_of_true_scale_deg"] == 0.0
    assert isclose(reg["east_west_grid_to_ground_factor"], 1 / cos(radians(18.44)), rel_tol=1e-4)
    assert reg["ground_extent_m"] == [10000, 10000]
