from datetime import datetime, timezone
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.imagery_service import (
    build_sentinel_search, credentials_status, load_dataset_registry, parse_gibs_capabilities,
    rank_sentinel_scenes, request_copernicus_token, safe_cache_path, sentinel_search_plan,
)
from app.services.terrain_v3_service import compare_v3, compute_scale, load_v3_artifact, normalized_wasserstein, sensitivity_v3


client = TestClient(app)
AOI = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}


def test_stac_query_policy_and_deterministic_scene_ranking():
    end = datetime(2026, 11, 14, tzinfo=timezone.utc)
    plan = sentinel_search_plan(AOI, end)
    assert [(item["query"]["eo:cloud_cover"]["lte"], item["datetime"].split("/")[0][:10]) for item in plan] == [(10, "2026-08-16"), (15, "2026-08-16"), (15, "2025-11-14")]
    scenes = [
        {"id": "older", "properties": {"eo:cloud_cover": 3, "datetime": "2026-11-01T00:00:00Z"}},
        {"id": "newer", "properties": {"eo:cloud_cover": 3, "datetime": "2026-11-10T00:00:00Z"}},
        {"id": "cloudy", "properties": {"eo:cloud_cover": 12, "datetime": "2026-11-12T00:00:00Z"}},
    ]
    assert [item["id"] for item in rank_sentinel_scenes(scenes)] == ["newer", "older", "cloudy"]
    with pytest.raises(ValueError):
        build_sentinel_search({"type": "Point", "coordinates": [0, 0]}, end)


def test_gibs_capabilities_parser_and_safe_cache_paths():
    xml = '''<Capabilities xmlns="http://www.opengis.net/wmts/1.0" xmlns:ows="http://www.opengis.net/ows/1.1"><Contents><Layer><ows:Identifier>Verified_Layer</ows:Identifier><Format>image/jpeg</Format><Dimension><ows:Identifier>Time</ows:Identifier><Default>2026-11-13</Default><Value>2026-11-13</Value></Dimension><ResourceURL format="image/jpeg" template="https://example.invalid/{TileMatrix}"/></Layer></Contents></Capabilities>'''
    layer = parse_gibs_capabilities(xml)[0]
    assert layer["identifier"] == "Verified_Layer" and layer["dimensions"]["Time"]["default"] == "2026-11-13"
    assert safe_cache_path("a" * 64, ".json").name == "a" * 64 + ".json"
    with pytest.raises(ValueError):
        safe_cache_path("../secret", ".json")


def test_copernicus_authentication_failure_never_leaks_secret(monkeypatch):
    secret = "do-not-leak-this-value"
    monkeypatch.setenv("CDSE_CLIENT_ID", "test-client"); monkeypatch.setenv("CDSE_CLIENT_SECRET", secret)
    class FailedResponse:
        def raise_for_status(self): raise RuntimeError(f"upstream rejected {secret}")
    class Client:
        def post(self, *args, **kwargs): return FailedResponse()
    with pytest.raises(RuntimeError) as error:
        request_copernicus_token(Client())
    assert secret not in str(error.value)


def test_halo_core_feature_coverage_and_flat_terrain():
    elevation = np.full((25, 25), 100.0)
    result = compute_scale(elevation, (slice(4, 21), slice(4, 21)), 60)
    assert result.metrics["slope_p90_deg"] == pytest.approx(0)
    assert result.metrics["local_relief_p90_m"] == pytest.approx(0)
    assert result.metrics["roughness_p90"] == pytest.approx(0)
    assert all(item.coverage_fraction == 1 for item in result.feature_coverage.values())


def test_versioned_v3_artifacts_distributions_and_sensitivity():
    reference, candidate = load_v3_artifact("mars-jezero"), load_v3_artifact("earth-atacama")
    assert reference and candidate and reference.methodology_version == "terrain-v3.0"
    assert set(reference.scales) == {"60", "120", "240"}
    comparison = compare_v3(reference, candidate)
    assert 0 <= comparison["overall_similarity"] <= 1
    assert comparison["scale_stability_range"][0] <= comparison["scale_stability_range"][1]
    assert normalized_wasserstein(reference.scales["60"].distributions["slope_deg"], reference.scales["60"].distributions["slope_deg"]) == pytest.approx(0)
    sensitivity = sensitivity_v3(reference, candidate)
    assert sensitivity["tested_index_range"][0] <= sensitivity["nominal_index"] <= sensitivity["tested_index_range"][1]


def test_phase5_api_registry_imagery_quality_and_v2_preservation():
    datasets = client.get("/api/datasets")
    assert datasets.status_code == 200 and len(datasets.json()) >= 7
    assert all("api_endpoint" not in item or "token" not in json.dumps(item).lower() for item in datasets.json())
    imagery = client.get("/api/sites/earth-atacama/imagery")
    assert imagery.status_code == 200
    records = imagery.json()
    assert {item["mode"] for item in records} == {"reference", "latest_observation", "terrain"}
    reference = next(item for item in records if item["mode"] == "reference")
    if not credentials_status()["copernicus"]:
        assert reference["data_status"] == "available" and reference["preview_url"] is not None
    assert client.get("/api/sites/earth-atacama/terrain/quality").json()["quality_status"] == "quality_checked"
    assert client.get("/api/sites/earth-atacama/terrain/distributions").status_code == 200
    assert client.get("/api/sites/earth-atacama/terrain/sensitivity").status_code == 200
    v3 = client.post("/api/discover", json={"candidate_site_ids": ["earth-atacama"], "methodology_version": "terrain-v3.0"}).json()
    assert v3["methodology_version"] == "terrain-v3.0" and v3["results"][0]["comparison_classification"] == "real_comparison"
    assert "terrain_v3" in v3["results"][0]["quality"]
    v2 = client.post("/api/discover", json={"candidate_site_ids": ["earth-atacama"], "methodology_version": "terrain-v2.0"}).json()
    assert v2["methodology_version"] == "terrain-v2.0" and v2["results"][0]["display_percentage"] == 99.6
    assert client.get("/api/sites/earth-atacama/terrain/preview.svg").headers["content-type"].startswith("image/svg+xml")
    mars = client.get("/api/sites/mars-jezero/imagery").json()
    mars_reference = next(item for item in mars if item["mode"] == "reference")
    assert mars_reference["product_id"] == "JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0"
    assert mars_reference["resolution_m"] == 6 and mars_reference["data_status"] == "available"
    assert client.get(mars_reference["preview_url"]).headers["content-type"] == "image/png"
    assert client.get("/api/imagery-assets/../../app/config.py").status_code == 404


def test_dataset_registry_is_schema_valid_and_has_no_secrets():
    records = load_dataset_registry()
    assert {record.local_status for record in records} >= {"processed", "evaluated for later use", "visualization tiles", "discovery only"}  # Phase 7 registry vocabulary
    assert "secret" not in json.dumps([record.model_dump(mode="json") for record in records]).lower()
