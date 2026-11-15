"""User-AOI screening jobs: validation, bounds, credentials, state transitions and recovery (no network)."""
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import jobs

client = TestClient(app)


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Isolate job storage and raw tiles; reset limits."""
    data = tmp_path / "data"
    (data / "raw").mkdir(parents=True)
    monkeypatch.setattr(jobs, "GEO_DATA", data)
    monkeypatch.setattr(jobs, "JOB_DIR", data / "jobs")
    monkeypatch.setattr(jobs, "WORK_DIR", data / "user-aoi")
    monkeypatch.setattr(jobs, "_client_hits", {})
    monkeypatch.setattr(jobs, "_global_hits", jobs.deque())
    monkeypatch.setattr(jobs, "_pending", 0)
    return data


def _synthetic_tile(path, lat0, lon0, slope=0.02):
    """A 1-degree tile at ~0.001 deg posting with a gentle tilt (GeoTIFF content; GDAL detects it regardless of the .hgt name)."""
    import rasterio
    from rasterio.transform import from_origin
    n = 1001
    yy, xx = np.mgrid[0:n, 0:n]
    z = (500 + xx * slope * 100 + yy * 0.5).astype("float32")
    with rasterio.open(path, "w", driver="GTiff", width=n, height=n, count=1, dtype="float32", crs="EPSG:4326",
                       transform=from_origin(lon0, lat0 + 1, 1 / (n - 1), 1 / (n - 1)), nodata=-32768) as out:
        out.write(z, 1)


def test_preflight_rejects_areas_outside_srtm_and_bad_coordinates(sandbox):
    assert jobs.preflight(75.38, -89.68)["supported"] is False
    assert client.post("/api/explore/preflight", json={"lat": 95, "lon": 0}).status_code == 422
    assert client.post("/api/explore/preflight", content='{"lat": NaN, "lon": 0}', headers={"Content-Type": "application/json"}).status_code == 422


def test_vercel_runtime_reports_processing_unavailable_without_writing(sandbox, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    preflight = client.post("/api/explore/preflight", json={"lat": 36.23, "lon": -116.77})
    assert preflight.status_code == 200
    assert preflight.json()["processing"]["available"] is False

    response = client.post(
        "/api/explore/jobs",
        json={"lat": 36.23, "lon": -116.77},
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 503
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "Rasterio/GDAL" in response.json()["error"]["message"]
    assert not (sandbox / "jobs").exists()


def test_unsupported_and_missing_credentials_states_fetch_nothing(sandbox, monkeypatch):
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    monkeypatch.delenv("EARTHDATA_USERNAME", raising=False)
    monkeypatch.delenv("EARTHDATA_PASSWORD", raising=False)
    assert jobs.submit(75.0, 10.0, None, "t")["state"] == "unsupported"
    job = jobs.submit(36.23, -116.77, "x", "t")
    assert job["state"] == "requires_credentials" and not (sandbox / "raw" / "N36W117.SRTMGL1.hgt.zip").exists()


def test_job_runs_through_every_state_with_a_cached_tile(sandbox, monkeypatch):
    _synthetic_tile(sandbox / "raw" / "N36W117.hgt", 36, -117)
    monkeypatch.setattr(jobs, "_imagery", lambda job, work: {"status": "unavailable", "reason": "mocked"})
    monkeypatch.setattr(jobs._executor, "submit", lambda fn, *a: None)  # run synchronously below
    job = jobs.submit(36.5, -116.5, "synthetic <b>label</b>", "client-a")
    assert job["state"] == "queued" and "<" not in job["label"]
    jobs._run(job["job_id"])
    done = jobs.load(job["job_id"])
    assert [entry["state"] for entry in done["log"]] == ["queued", "acquiring", "processing", "quality_check", "ready"]
    result = done["result"]
    assert result["label"] == "screening" and "mars-jezero" in result["comparisons"]
    assert 0 <= result["comparisons"]["mars-jezero"]["terrain_index"] <= 100
    assert result["inputs"][0]["tile_id"] == "N36W117" and len(result["inputs"][0]["sha256"]) == 64


def test_void_window_fails_quality_gate_without_an_index(sandbox, monkeypatch):
    import rasterio
    path = sandbox / "raw" / "N10E020.hgt"
    _synthetic_tile(path, 10, 20)
    with rasterio.open(path, "r+") as ds:
        data = ds.read(1)
        data[:, :] = -32768
        ds.write(data, 1)
    monkeypatch.setattr(jobs._executor, "submit", lambda fn, *a: None)
    job = jobs.submit(10.5, 20.5, None, "client-b")
    jobs._run(job["job_id"])
    done = jobs.load(job["job_id"])
    assert done["state"] == "failed" and "comparisons" not in (done["result"] or {})


def test_rate_limit_and_queue_cap(sandbox, monkeypatch):
    _synthetic_tile(sandbox / "raw" / "N36W117.hgt", 36, -117)
    monkeypatch.setattr(jobs._executor, "submit", lambda fn, *a: None)
    for _ in range(jobs.PER_CLIENT_PER_HOUR):
        monkeypatch.setattr(jobs, "_pending", 0)
        jobs.submit(36.5, -116.5, None, "same-client")
    monkeypatch.setattr(jobs, "_pending", 0)
    with pytest.raises(jobs.JobRejected) as error:
        jobs.submit(36.5, -116.5, None, "same-client")
    assert error.value.status == 429
    monkeypatch.setattr(jobs, "_pending", jobs.MAX_QUEUE)
    with pytest.raises(jobs.JobRejected):
        jobs.submit(36.5, -116.5, None, "other-client")


def test_restart_recovery_marks_in_flight_jobs_failed(sandbox):
    (sandbox / "jobs").mkdir()
    job = {"job_id": "a" * 32, "state": "processing", "log": [], "label": "x", "center": {}, "created_at": "", "updated_at": ""}
    (sandbox / "jobs" / f"{'a' * 32}.json").write_text(json.dumps(job), encoding="utf-8")
    assert jobs.recover_interrupted() == 1
    assert jobs.load("a" * 32)["state"] == "failed"


def test_job_ids_are_validated(sandbox):
    assert client.get("/api/explore/jobs/not-a-job").status_code == 404
    assert client.get("/api/explore/jobs/..%5C..%5Cx").status_code == 404
    assert client.get(f"/api/explore/jobs/{'b' * 32}").status_code == 404
    assert client.get(f"/api/explore/jobs/{'b' * 32}/imagery.png").status_code == 404
