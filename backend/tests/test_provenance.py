"""Adversarial tests of production input validation, not fixture science."""
import copy
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import analogue_v1_service as av
from app.services.geospatial_service import BACKEND_ROOT, canonical_text_sha256
from app.services.provenance_service import future_date, official_url, validate_scoring_artifact


def test_registered_scoring_artifacts_pass():
    for path in av.V5_DIR.glob("*.json"):
        assert validate_scoring_artifact(path, json.loads(path.read_text())) == []


@pytest.mark.parametrize("field,value", [("body", "venus"), ("center_latitude", 91), ("center_longitude", float("nan")),
    ("source_sha256", "0" * 64), ("generated_at", "2099-01-01"), ("source_file", "tests/fixtures/fake.tif"),
    ("aoi_id", "../../secret"), ("primary_scale_m", 1)])
def test_reject_invalid_scientific_identity(field, value):
    path = av.V5_DIR / "earth-atacama-south.terrain-v5.json"
    art = json.loads(path.read_text())
    art[field] = value
    assert validate_scoring_artifact(path, art)


def test_checksum_tamper_and_missing_sidecar(tmp_path):
    path = tmp_path / "tampered.json"
    source = av.V5_DIR / "earth-atacama-south.terrain-v5.json"
    art = json.loads(source.read_text())
    path.write_text(source.read_text())
    assert "derived checksum missing or mismatched" in validate_scoring_artifact(path, art)
    path.with_suffix(".sha256").write_text(canonical_text_sha256(path))
    path.write_text(source.read_text() + " ")
    assert "derived checksum missing or mismatched" in validate_scoring_artifact(path, art)


@pytest.mark.parametrize("field,value", [("units", "kelvin"), ("coverage", 0.1), ("quantiles", [0] * 499)])
def test_invalid_measurement_rejected(field, value):
    path = av.V5_DIR / "earth-atacama-south.terrain-v5.json"
    art = json.loads(path.read_text())
    art["scales"]["60"]["features"]["slope"][field] = value
    assert validate_scoring_artifact(path, art)


def test_critical_failure_never_exports_overall_score():
    for profile in ("balanced_science", "rover_mobility", "biosignature_fieldwork", "mars_base_field_testing"):
        result = av.result_detail("mars-jezero", profile, "earth-atacama-south")
        assert result.candidate.observed_index is None
        assert result.candidate.scientific_status == "real_context_only"
        assert result.candidate.rank is None
        assert result.candidate.sensitivity is None
        assert result.candidate.evidence_coverage > 0


def test_provenance_export_matches_calculation_files():
    result = av.result_detail("mars-jezero", "terrain_analogy", "earth-atacama-south")
    inputs = result.reproducibility["calculation_inputs"]["files"]
    assert any("mars-jezero.terrain-v5" in p["path"] for p in inputs)
    for item in inputs:
        assert canonical_text_sha256(BACKEND_ROOT / item["path"]) == item["sha256_lf"]
        assert not item["path"].startswith(("C:", "/"))


def test_source_registry_exposes_roles_without_credentials():
    response = TestClient(app).get("/api/v3/source-registry")
    assert response.status_code == 200
    assert response.json()["schema_version"] == "source-registry-v1"
    assert all(x["role"] == "display-only" for x in response.json()["imagery"])
    assert "EARTHDATA_TOKEN=" not in response.text


def test_official_host_and_future_time_are_strict():
    assert not official_url("https://stac.astrogeology.usgs.gov.evil.example/data")
    assert not official_url("http://stac.astrogeology.usgs.gov/data")
    assert not official_url("https://secret@stac.astrogeology.usgs.gov/data")
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    assert future_date("2026-11-16", now)
    assert not future_date("2026-11-14", now)


def test_changed_configuration_cannot_export_different_inputs(monkeypatch):
    monkeypatch.setattr(av, "CONFIG_FILE_SHA256", "0" * 64)
    with pytest.raises(av.AnalogueError, match="restart"):
        av.result_detail("mars-jezero", "terrain_analogy", "earth-atacama-south")
