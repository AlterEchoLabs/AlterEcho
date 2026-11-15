"""Release pass: every index is read against ordinary land, sites are grouped by terrain class, context is shown but never scored,
and Explore scores a window exactly as the atlas does."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import analogue_v1_service as av1
from app.services.geospatial_service import GEO_DATA

client = TestClient(app)


def _row(comp, site_id):
    return next(r for r in comp.results if r.site_id == site_id)


def test_standing_counts_ordinary_windows_beaten_and_matches_the_background_share():
    comp = av1.compare("mars-jezero", "terrain_analogy")
    assert len(comp.background_scores) == comp.base_rate["count"] == 88
    assert comp.background_scores == sorted(comp.background_scores)
    for r in comp.results:
        if r.state != "ranked":
            assert r.standing is None
            continue
        st = r.standing
        assert st.of == 88 and st.closer_than + st.as_close_or_closer == 88
        # same definition as the stored background share (share at or above)
        assert st.as_close_or_closer == round(r.background_share * 88)
        if r.observed_index >= 1:  # published scores are rounded to 0.01, so near-zero indices cannot be recounted from them
            assert st.closer_than == sum(1 for b in comp.background_scores if b < r.observed_index - 0.01)
    atacama = _row(comp, "earth-atacama-south")
    assert atacama.site_name == "Atacama Desert"
    assert (atacama.standing.closer_than, atacama.terrain_class) == (73, "same")
    ladakh = _row(comp, "earth-ladakh")
    assert (ladakh.standing.closer_than, ladakh.terrain_class) == (6, "different")


def test_terrain_class_follows_the_tolerance_on_every_scored_feature():
    comp = av1.compare("mars-gale-aeolis-palus", "terrain_analogy")
    for r in comp.results:
        if r.state != "ranked":
            continue
        ratios = [f.d_over_tau for f in r.families[0].features if f.role == "scored"]
        expected = "same" if all(x < 1 for x in ratios) else "different" if all(x >= 1 for x in ratios) else "partial"
        assert r.terrain_class == expected


def test_class_groups_replace_rank_labels_and_say_when_order_is_not_resolved():
    comp = av1.compare("mars-jezero", "terrain_analogy")
    assert [g.terrain_class for g in comp.class_groups] == ["same", "different"]
    same = comp.class_groups[0]
    assert len(same.site_ids) == 5 and not same.order_resolved and "not meaningful" in same.note
    assert "Ranked" not in comp.headline and "88 ordinary Earth land windows" in comp.headline
    r = _row(comp, "earth-atacama-south")
    assert r.simple.class_label == "Same terrain class as Jezero Crater"
    assert r.simple.standing_text == "Closer to Jezero Crater than 73 of 88 ordinary Earth land windows"
    assert r.simple.verdict.startswith("Close terrain match")
    assert "%" not in r.simple.index_label.split("Not a probability")[0]


def test_lunar_reference_gets_no_standing_or_groups():
    comp = av1.compare("moon-south-pole-shackleton", "terrain_analogy")
    assert comp.class_groups == []
    assert all(r.standing is None and r.observed_index is None for r in comp.results)


def test_context_endpoint_shows_measured_temperature_and_fieldwork_without_scores():
    body = client.get("/api/v3/context", params={"reference": "mars-jezero"}).json()
    temp = body["temperature"]
    assert temp["reference"]["instrument"].startswith("MEDA")
    assert {s["site_id"] for s in temp["sites"]} >= {"earth-atacama-south", "earth-ladakh", "earth-hanksville-mdrs"}
    assert "earth-atacama" not in {s["site_id"] for s in temp["sites"]}  # the contaminated first window is not offered
    atacama = next(s for s in temp["sites"] if s["site_id"] == "earth-atacama-south")
    assert atacama["record"]["day_c"] > atacama["record"]["night_c"]
    assert atacama["audit"]["decision"] == "measured_context_only"
    field = {s["site_id"]: s["analog_status"] for s in body["fieldwork"]["sites"]}
    assert field["earth-hanksville-mdrs"] == "window" and field["earth-upper-mustang"] == "none" and field["earth-atacama-south"] == "region"
    assert "index" not in str(body["temperature"]["sites"][0]).lower()
    gale = client.get("/api/v3/context", params={"reference": "mars-gale-aeolis-palus"}).json()
    assert gale["temperature"]["reference"] is None and "no ground-temperature record" in gale["temperature"]["note"]


def test_context_rejects_earth_or_malformed_references():
    assert client.get("/api/v3/context", params={"reference": "earth-ladakh"}).status_code == 404
    assert client.get("/api/v3/context", params={"reference": "../etc/passwd"}).status_code == 422


def test_formulas_are_served_as_latex_from_one_configuration():
    method = client.get("/api/v3/method").json()
    comp = client.get("/api/v3/compare", params={"reference": "mars-jezero"}).json()
    assert method["formulas_tex"] == comp["formulas_tex"]
    assert {"feature_similarity", "distribution_distance", "standing", "observed_index"} <= set(method["formulas_tex"])
    assert "\\ln 2" in method["formulas_tex"]["feature_similarity"]


@pytest.mark.skipif(not (GEO_DATA / "raw" / "S25W070.hgt").exists(), reason="raw SRTM tile is git-ignored")
def test_explore_scores_a_window_exactly_like_the_atlas():
    from app.services.jobs import screening_comparisons
    out = screening_comparisons(GEO_DATA / "raw" / "S25W070.hgt", -24.2722, -69.9005)
    jez = out["mars-jezero"]
    assert jez["method"] == "analogue-method-v1.0" and jez["scored"]
    assert jez["terrain_index"] == pytest.approx(97.90, abs=0.01)
    assert jez["standing"]["closer_than"] == 73 and jez["terrain_class"] == "same"
    assert out["moon-south-pole-shackleton"]["terrain_index"] is None
