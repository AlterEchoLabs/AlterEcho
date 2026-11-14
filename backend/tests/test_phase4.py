from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import DataStatus
from app.services.catalog_service import SITES, get_feature_summary
from app.services.integrity_service import validate_catalog_integrity, validate_site_integrity


client = TestClient(app)


def test_production_catalog_has_no_demo_fixtures():
    assert all(site.data_status != DataStatus.demo_fixture for site in SITES)
    assert get_feature_summary("earth-holuhraun") is None
    assert not Path("app/data/comparisons.demo.json").exists()


def test_real_artifact_integrity_and_catalog_consistency():
    assert validate_catalog_integrity() == {}
    real_sites = [site for site in SITES if site.data_status == DataStatus.real_processed]
    assert {site.id for site in real_sites} == {"mars-jezero", "earth-atacama", "earth-upper-mustang", "earth-ladakh"}
    assert all(validate_site_integrity(site) == [] for site in real_sites)


def test_only_three_real_earth_candidates_are_rankable():
    sites = client.get("/api/sites?body=earth").json()
    rankable = [site for site in sites if site["data_status"] == "real_processed"]
    assert {site["id"] for site in rankable} == {"earth-atacama", "earth-upper-mustang", "earth-ladakh"}
    assert all(site["processing_status"] == "integrity_checked" for site in rankable)
    assert all(site["scientific_validation_status"] == "methodology_review_pending" for site in rankable)


def test_planned_sites_are_disabled_by_contract_and_terrain_is_unavailable():
    for site_id in ("earth-holuhraun", "earth-mcmurdo-dry-valleys"):
        site = client.get(f"/api/sites/{site_id}").json()
        assert site["data_status"] == "planned" and site["available_metrics"] == []
        assert client.get(f"/api/sites/{site_id}/terrain").status_code == 404
        result = client.post("/api/discover", json={"reference_site_id": "mars-jezero", "candidate_site_ids": [site_id]}).json()["results"][0]
        assert result["overall_similarity"] is None
        assert result["rankability"] == "not_rankable"
        assert result["comparison_classification"] == "not_rankable_planned"
        assert result["provenance"]["notice"] == "No synthetic fallback was used."


def test_identity_and_backward_compatible_health_aliases():
    health = client.get("/api/health").json()
    assert health["application_id"] == "alterecho-terrain-explorer"
    assert health["build_identifier"]
    assert health["data_counts"]["rankable_real_candidates"] == 3
    assert health["data_counts"]["demo_fixture_sites"] == 0
    config = client.get("/api/config").json()
    assert config["identity"]["application_version"] == health["application_version"]
