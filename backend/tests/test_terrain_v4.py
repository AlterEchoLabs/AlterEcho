"""terrain-v4.0: the Gaussian formula, Wasserstein-1, weights, unit checks and preservation of v3."""
from math import exp, isclose

import pytest

from app.models.schemas import DistributionSummary
from app.services.terrain_v3_service import compare_v3, load_v3_artifact
from app.services.terrain_v4_service import CONFIG, TerrainMethodError, compare_v4, gaussian_similarity, perturbed_configurations, wasserstein_1


def dist(counts, edges=(0, 1, 2, 3, 4)):
    return DistributionSummary(feature="slope_deg", bin_edges=list(edges), normalized_counts=list(counts), valid_sample_count=100)


@pytest.mark.parametrize("difference,expected", [(0, 100.0), (8, 60.653), (16, 13.534), (-8, 60.653)])
def test_gaussian_reference_values(difference, expected):
    assert isclose(gaussian_similarity(difference, 0, 8), expected, abs_tol=1e-3)


@pytest.mark.parametrize("args", [(None, 1, 1), (1, None, 1), (1, 1, None), (1, 1, 0), (1, 1, -2), (float("nan"), 1, 1), (1, float("inf"), 1)])
def test_gaussian_invalid_inputs_have_no_score(args):
    assert gaussian_similarity(*args) is None


def test_gaussian_unit_mismatch_has_no_score():
    assert gaussian_similarity(10, 12, 5, "m", "degrees") is None
    assert gaussian_similarity(10, 12, 5, "km", "m") is None
    assert gaussian_similarity(10, 12, 5, "metres", "m") == pytest.approx(100 * exp(-0.5 * (2 / 5) ** 2))


def test_gaussian_decreases_monotonically():
    values = [gaussian_similarity(d, 0, 5) for d in range(0, 30, 3)]
    assert values == sorted(values, reverse=True)


def test_wasserstein_identical_is_zero_and_shift_equals_bin_width():
    a = dist([0.5, 0.5, 0, 0])
    b = dist([0, 0.5, 0.5, 0])
    assert wasserstein_1(a, a) == 0
    assert isclose(wasserstein_1(a, b), 1.0)  # all mass moved by one 1-unit bin
    assert isclose(wasserstein_1(a, b), wasserstein_1(b, a))


def test_wasserstein_rejects_different_bins():
    with pytest.raises(TerrainMethodError):
        wasserstein_1(dist([1, 0, 0, 0]), dist([1, 0, 0, 0], edges=(0, 2, 4, 6, 8)))


def test_config_weights_are_valid_and_frozen_before_held_out_sites():
    assert isclose(sum(f["weight"] for f in CONFIG["families"].values()), 1.0)
    assert all(f["tau"] > 0 for f in CONFIG["families"].values())
    assert set(CONFIG["frozen_before_sites"]) == {"earth-danakil", "earth-craters-of-the-moon", "earth-hanksville-mdrs", "earth-meteor-crater"}
    # one distribution per family: no overlapping percentile statistics are scored
    assert len({f["distribution"] for f in CONFIG["families"].values()}) == len(CONFIG["families"])


def test_terrain_index_matches_formula_by_hand():
    ref, cand = load_v3_artifact("mars-jezero"), load_v3_artifact("earth-ladakh")
    result = compare_v4(ref, cand)
    manual = 0.0
    for name, spec in CONFIG["families"].items():
        family = 0.0
        for scale, w in CONFIG["scale_weights"].items():
            d = wasserstein_1(ref.scales[scale].distributions[spec["distribution"]], cand.scales[scale].distributions[spec["distribution"]])
            family += w * 100 * exp(-0.5 * (d / spec["tau"]) ** 2)
        manual += spec["weight"] * family
    assert isclose(result["terrain_index"], manual, rel_tol=1e-9)


def test_unit_and_quality_checks_block_comparison():
    ref, cand = load_v3_artifact("mars-jezero"), load_v3_artifact("earth-atacama")
    with pytest.raises(TerrainMethodError):
        compare_v4(ref, cand.model_copy(update={"vertical_units": "feet"}))
    with pytest.raises(TerrainMethodError):
        compare_v4(ref, cand.model_copy(update={"quality_status": "failed_validation"}))


def test_invalid_weights_rejected():
    ref, cand = load_v3_artifact("mars-jezero"), load_v3_artifact("earth-atacama")
    bad = {k: dict(v, weight=0.5) for k, v in CONFIG["families"].items()}
    with pytest.raises(TerrainMethodError):
        compare_v4(ref, cand, bad)
    bad_tau = {k: dict(v, tau=0) for k, v in CONFIG["families"].items()}
    with pytest.raises(TerrainMethodError):
        compare_v4(ref, cand, bad_tau)


def test_perturbations_keep_weights_normalised():
    for label, families, scales in perturbed_configurations():
        assert isclose(sum(f["weight"] for f in families.values()), 1.0, abs_tol=1e-9), label
        assert isclose(sum(scales.values()), 1.0, abs_tol=1e-3), label


def test_historical_terrain_v3_is_preserved():
    ref = load_v3_artifact("mars-jezero")
    assert compare_v3(ref, load_v3_artifact("earth-atacama"))["display_index"] == 96.1
    assert compare_v3(ref, load_v3_artifact("earth-upper-mustang"))["display_index"] == 34.1
    assert compare_v3(ref, load_v3_artifact("earth-ladakh"))["display_index"] == 24.8
