"""Phase 6 security regressions (OWASP API Top 10 driven)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)

TRAVERSAL_IDS = ["..%5C..%5Cx", "..%5Cprocessed%5Cmars-jezero", "C:%5Cx", "%5C%5Chost%5Cshare%5Cx", "a*", "%5Bx%5D", "MARS-JEZERO", "-x"]
ID_ROUTES = [
    "/api/sites/{id}", "/api/sites/{id}/aoi", "/api/sites/{id}/terrain", "/api/sites/{id}/terrain/quality",
    "/api/sites/{id}/terrain/distributions", "/api/sites/{id}/terrain/sensitivity", "/api/sites/{id}/terrain/preview.svg",
    "/api/sites/{id}/imagery", "/api/sites/{id}/evidence", "/api/sources/{id}", "/api/processing-runs/{id}",
]


@pytest.mark.parametrize("route", ID_ROUTES)
@pytest.mark.parametrize("bad_id", TRAVERSAL_IDS)
def test_path_ids_are_constrained(route, bad_id):
    response = client.get(route.format(id=bad_id))
    assert response.status_code in {404, 422}, (route, bad_id, response.status_code)


def test_existing_file_outside_catalog_is_not_reachable_through_source_route():
    # A processing report exists on disk but is not a manifest: must be 404, never 500/200.
    assert client.get("/api/sources/mars-jezero-20261113T132106Z-15c3367f").status_code in {404, 422}
    assert client.get("/api/sources/mars-jezero-20261113t132106z-15c3367f").status_code == 404


@pytest.mark.parametrize("body", [
    '{"candidate_site_ids":["earth-atacama"],"methodology_version":"terrain-v2.0","weights":{"slope_p50_deg":NaN}}',
    '{"candidate_site_ids":["earth-atacama"],"methodology_version":"terrain-v2.0","weights":{"slope_p50_deg":Infinity}}',
])
def test_non_finite_weights_are_rejected(body):
    response = client.post("/api/discover", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422


def test_unbounded_weight_maps_are_rejected():
    weights = {f"k{i}": 1.0 for i in range(100)}
    assert client.post("/api/discover", json={"candidate_site_ids": ["earth-atacama"], "weights": weights}).status_code == 422


def test_validation_errors_do_not_echo_input():
    marker = "x" * 5000
    response = client.post("/api/discover", json={"candidate_site_ids": [marker]})
    assert response.status_code == 422
    assert marker not in response.text and len(response.text) < 2000


def test_oversized_body_is_rejected_before_parsing():
    response = client.post("/api/discover", content="{" + " " * 40_000 + "}", headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_streamed_body_without_length_is_bounded():
    def chunks():
        yield b" " * 20000
        yield b" " * 20000
    response = client.post("/api/discover", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_archive_rejects_traversal_before_writing_and_preserves_raw(tmp_path):
    import zipfile
    from app.scripts.acquire_dataset import AcquisitionError, extract_dem
    raw = tmp_path / "raw"
    raw.mkdir()
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../escape.hgt", b"test")
    with pytest.raises(AcquisitionError):
        extract_dem(archive, raw)
    assert not (tmp_path / "escape.hgt").exists()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("tile.hgt", b"first")
    source = extract_dem(archive, raw)
    assert extract_dem(archive, raw) == source
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("tile.hgt", b"changed")
    with pytest.raises(AcquisitionError):
        extract_dem(archive, raw)
    assert source.read_bytes() == b"first"
    assert not list(raw.glob("*.part"))


def test_security_headers_present():
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in response.headers["content-security-policy"]


def test_cors_allows_only_configured_origins():
    allowed = client.options("/api/health", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
    denied = client.options("/api/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers


def test_svg_preview_escapes_site_name(monkeypatch):
    from app.routers import geospatial
    real = geospatial.get_site

    def fake(site_id):
        site = real(site_id)
        return site.model_copy(update={"name": "<script>alert(1)</script>&"}) if site else None

    monkeypatch.setattr(geospatial, "get_site", fake)
    response = client.get("/api/sites/earth-atacama/terrain/preview.svg")
    assert response.status_code == 200
    assert "<script>" not in response.text and "&lt;script&gt;" in response.text


def test_imagery_assets_are_allowlisted_from_metadata():
    for name in ["earth-atacama-sentinel-reference.png", "earth-ladakh-sentinel-reference.png", "earth-upper-mustang-sentinel-reference.png", "mars-jezero-ctx-reference.png"]:
        response = client.get(f"/api/imagery-assets/{name}")
        assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    for name in ["mars-jezero-ctx-reference.png.aux.xml", "..%5Cearth-atacama-sentinel-reference.json", "earth-atacama-sentinel-reference.json"]:
        assert client.get(f"/api/imagery-assets/{name}").status_code == 404


def test_unhandled_errors_are_generic(monkeypatch):
    from app.routers import health

    def boom():
        raise RuntimeError("secret internal path C:/x")

    monkeypatch.setattr(health, "data_status_summary", boom)
    response = client.get("/api/health")
    assert response.status_code == 500 and "secret" not in response.text


def test_committed_imagery_metadata_has_no_signed_urls():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "data"
    for path in list(root.rglob("*.json")):
        text = path.read_text(encoding="utf-8")
        assert "sig=" not in text and "se=20" not in text, path
