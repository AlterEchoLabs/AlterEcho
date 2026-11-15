"""The research-paper text must match the versioned backend: regenerate it and compare with docs/paper."""
import json
from math import exp, isclose, log

from fastapi.testclient import TestClient

from app.main import app
from app.scripts.build_methods_paper import DOCS, EXAMPLE, build

client = TestClient(app)


def test_generated_paper_text_and_blocks_match_the_backend():
    data, blocks, md = build(write=False, exact_check=False)
    assert (DOCS / "methods.md").read_text(encoding="utf-8") == md, "docs/paper/methods.md is stale: run python -m app.scripts.build_methods_paper"
    assert json.loads((DOCS / "paper-content.json").read_text(encoding="utf-8")) == json.loads(json.dumps(blocks, ensure_ascii=False))
    committed = json.loads((DOCS / "paper-data.json").read_text(encoding="utf-8"))
    for key in ("method_version", "terrain_method", "tau", "floor_jezero", "background_jezero", "profiles"):
        assert committed[key] == json.loads(json.dumps(data[key])), key
    assert committed["example"]["features"] == json.loads(json.dumps(data["example"]["features"]))


def test_worked_example_numbers_equal_the_live_api():
    committed = json.loads((DOCS / "paper-data.json").read_text(encoding="utf-8"))["example"]
    api = client.get("/api/v3/result", params={"site": EXAMPLE["site"], "reference": EXAMPLE["reference"], "profile": EXAMPLE["profile"]}).json()
    cand = api["candidate"]
    terrain = next(f for f in cand["families"] if f["family"] == "terrain")
    feats = {f["feature"]: f for f in terrain["features"]}
    assert cand["observed_index"] == committed["observed_index_api"]
    assert cand["evidence_coverage"] == committed["coverage"]
    s_total = 0.0
    for name, v in committed["features"].items():
        assert isclose(feats[name]["distance"], v["d"], abs_tol=1e-4)
        assert isclose(feats[name]["tau"], v["tau"], abs_tol=1e-4)
        assert isclose(feats[name]["delta"], v["delta"], abs_tol=1e-4)
        assert feats[name]["weight"] == v["weight"] == 0.5
        assert isclose(v["s"], exp(-log(2) * (v["d"] / v["tau"]) ** 2), abs_tol=1e-8)  # stored at 9 decimals
        s_total += v["weight"] * v["s"]
    assert isclose(100 * s_total, committed["observed_index_full"], abs_tol=1e-5)
    assert round(committed["observed_index_full"], 2) == cand["observed_index"]
    assert all(f["weight"] == 0 and f["similarity"] is None for f in terrain["features"] if f["role"] == "diagnostic")
    assert api["comparison"]["method_version"] == "analogue-method-v1.0"


def test_quantile_approximation_error_is_reported_and_small():
    exact = json.loads((DOCS / "paper-data.json").read_text(encoding="utf-8"))["example"]["exact_w1_check"]
    for v in exact.values():
        assert v["relative_difference"] < 0.005 and v["cells_earth"] > 25_000
