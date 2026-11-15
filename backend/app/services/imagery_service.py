from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from app.models.schemas import Body, DatasetRecord, ImageryRecord
from app.services.catalog_service import get_site
from app.services.geospatial_service import GEO_DATA, load_aoi


APP_DATA = Path(__file__).resolve().parents[1] / "data"
IMAGERY_CACHE = GEO_DATA / "cache" / "imagery"
ALLOWED_IMAGERY_MODES = {"reference", "latest_observation", "terrain"}


def load_dataset_registry() -> list[DatasetRecord]:
    payload = json.loads((APP_DATA / "datasets.json").read_text(encoding="utf-8"))
    return [DatasetRecord.model_validate(item) for item in payload]


def load_verified_providers() -> dict[str, Any]:
    return json.loads((APP_DATA / "imagery.providers.json").read_text(encoding="utf-8"))


def build_sentinel_search(aoi_geometry: dict[str, Any], end: datetime, days: int = 90, cloud_limit: float = 10) -> dict[str, Any]:
    if aoi_geometry.get("type") != "Polygon" or not aoi_geometry.get("coordinates"):
        raise ValueError("A valid AOI Polygon is required")
    if days not in {90, 365} or cloud_limit not in {10, 15}:
        raise ValueError("Search window or cloud threshold is outside the documented policy")
    start = end - timedelta(days=days)
    return {
        "collections": ["sentinel-2-l2a"],
        "intersects": aoi_geometry,
        "datetime": f"{start.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')}/{end.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')}",
        "query": {"eo:cloud_cover": {"lte": cloud_limit}},
        "limit": 100,
    }


def sentinel_search_plan(aoi_geometry: dict[str, Any], end: datetime | None = None) -> list[dict[str, Any]]:
    end = end or datetime.now(timezone.utc)
    return [
        build_sentinel_search(aoi_geometry, end, 90, 10),
        build_sentinel_search(aoi_geometry, end, 90, 15),
        build_sentinel_search(aoi_geometry, end, 365, 15),
    ]


def rank_sentinel_scenes(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(feature: dict[str, Any]):
        props = feature.get("properties", {})
        cloud = props.get("eo:cloud_cover")
        acquired = props.get("datetime") or props.get("start_datetime") or ""
        try:
            timestamp = datetime.fromisoformat(acquired.replace("Z", "+00:00")).timestamp()
        except (ValueError, AttributeError):
            timestamp = -math.inf
        return (float(cloud) if cloud is not None else math.inf, -timestamp, feature.get("id", ""))
    return sorted(features, key=key)


def parse_gibs_capabilities(xml_text: str) -> list[dict[str, Any]]:
    root = ElementTree.fromstring(xml_text)
    ns = {"wmts": "http://www.opengis.net/wmts/1.0", "ows": "http://www.opengis.net/ows/1.1"}
    layers: list[dict[str, Any]] = []
    for layer in root.findall(".//wmts:Contents/wmts:Layer", ns):
        identifier = layer.findtext("ows:Identifier", default="", namespaces=ns)
        formats = [node.text for node in layer.findall("wmts:Format", ns) if node.text]
        resources = [node.attrib.get("template") for node in layer.findall("wmts:ResourceURL", ns) if node.attrib.get("template")]
        dimensions = {}
        for dimension in layer.findall("wmts:Dimension", ns):
            name = dimension.findtext("ows:Identifier", default="", namespaces=ns)
            values = [node.text for node in dimension.findall("wmts:Value", ns) if node.text]
            default = dimension.findtext("wmts:Default", default=None, namespaces=ns)
            dimensions[name] = {"values": values, "default": default}
        layers.append({"identifier": identifier, "formats": formats, "resource_templates": resources, "dimensions": dimensions})
    return layers


def credentials_status() -> dict[str, bool]:
    return {
        "copernicus": bool(os.getenv("CDSE_CLIENT_ID") and os.getenv("CDSE_CLIENT_SECRET")),
        "earthdata": bool(os.getenv("EARTHDATA_TOKEN") or (os.getenv("EARTHDATA_USERNAME") and os.getenv("EARTHDATA_PASSWORD"))),
    }


def request_copernicus_token(client) -> str:
    client_id, client_secret = os.getenv("CDSE_CLIENT_ID"), os.getenv("CDSE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("Copernicus credentials are not configured")
    try:
        response = client.post("https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
                               data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret})
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            raise ValueError("missing access token")
        return token
    except Exception as error:
        raise RuntimeError("Copernicus authentication failed; verify backend credentials") from error


def deterministic_cache_key(provider: str, site_id: str, product_id: str, aoi_id: str) -> str:
    return sha256(f"{provider}|{site_id}|{product_id}|{aoi_id}".encode()).hexdigest()


def _bbox(geometry: dict[str, Any]) -> list[float]:
    points = geometry["coordinates"][0]
    return [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]


def list_site_imagery(site_id: str) -> list[ImageryRecord]:
    site = get_site(site_id)
    if not site:
        raise KeyError(site_id)
    if not site.aoi_id:
        return []
    aoi = load_aoi(site.aoi_id)
    bbox = _bbox(aoi.geometry)
    terrain = ImageryRecord(
        imagery_id=f"{site_id}-terrain-v3", site_id=site_id, body=site.body, mode="terrain",
        provider="AlterEcho derived terrain", collection="terrain-v3.0", product_id=site.processing_status.value,
        acquisition_datetime=None, resolution_m=60, processing_level="Derived hillshade preview",
        bbox=bbox, aoi_id=site.aoi_id, preview_url=f"/api/sites/{site_id}/terrain/preview.svg",
        attribution="Derived from the registered DEM; see terrain provenance.", official_source_url=f"/api/sites/{site_id}/terrain",
        cache_status="generated_on_request", data_status="available",
        limitations=["Visualization only; use the terrain artifact and provenance for numeric analysis."],
    )
    if site.body == Body.earth:
        gibs = load_verified_providers()["gibs"]
        selection_path = GEO_DATA / "imagery" / f"{site_id}.sentinel-selection.json"
        selection = json.loads(selection_path.read_text(encoding="utf-8")) if selection_path.exists() else None
        selected_scene = selection.get("selected_scene") if selection else None
        local_reference_path = GEO_DATA / "processed" / "imagery" / f"{site_id}-sentinel-reference.json"
        if local_reference_path.exists():
            reference = ImageryRecord.model_validate_json(local_reference_path.read_text(encoding="utf-8"))
        else:
            reference = ImageryRecord(
            imagery_id=f"{site_id}-sentinel-2-reference", site_id=site_id, body=site.body, mode="reference",
            provider="Copernicus Data Space Ecosystem / ESA", collection="sentinel-2-l2a", product_id=selected_scene.get("product_id") if selected_scene else None,
            acquisition_datetime=datetime.fromisoformat(selected_scene["acquisition_datetime"].replace("Z", "+00:00")) if selected_scene else None,
            resolution_m=10, cloud_cover_pct=selected_scene.get("cloud_cover_pct") if selected_scene else None,
            processing_level="Level-2A", bbox=bbox, aoi_id=site.aoi_id,
            preview_url=None, attribution="Copernicus Sentinel data", official_source_url=selected_scene.get("official_stac_record") if selected_scene and selected_scene.get("official_stac_record") else "https://dataspace.copernicus.eu/",
            cache_status="metadata_cached" if selected_scene else "not_cached", data_status="authentication_required" if not credentials_status()["copernicus"] else "acquisition_pending",
            limitations=["Scene metadata may be selected, but no image is displayed until protected band assets are retrieved, cropped and checksummed.", "Cloud screening follows the 90-day/10%, 90-day/15%, then 365-day/15% policy."],
            )
        latest = ImageryRecord(
            imagery_id=f"{site_id}-gibs-latest", site_id=site_id, body=site.body, mode="latest_observation",
            provider=gibs["provider"], collection="GIBS EPSG:3857 best", product_id=gibs["layer_identifier"],
            acquisition_datetime=datetime.fromisoformat(gibs["observation_date"] + "T00:00:00+00:00"),
            resolution_m=375, processing_level=gibs["archive_status"], bbox=bbox,
            aoi_id=site.aoi_id, preview_url=None, tile_url=gibs["tile_template"], attribution="NASA Worldview / GIBS",
            official_source_url=gibs["capabilities_url"], cache_status="remote_tiles", data_status="available",
            limitations=gibs["limitations"],
        )
        return [reference, latest, terrain]
    if site.body == Body.moon:
        return [terrain]  # no lunar orthoimage (LROC) has been processed; the hillshade layer is derived from LOLA
    mars_metadata_path = GEO_DATA / "processed" / "imagery" / f"{site_id}-ctx-reference.json"
    if mars_metadata_path.exists():
        mars_payload = json.loads(mars_metadata_path.read_text(encoding="utf-8"))
        allowed = set(ImageryRecord.model_fields)
        reference = ImageryRecord.model_validate({key: value for key, value in mars_payload.items() if key in allowed})
    else:
        reference = ImageryRecord(
        imagery_id=f"{site_id}-ctx-reference", site_id=site_id, body=site.body, mode="reference",
        provider="USGS Astrogeology / NASA PDS", collection=None, product_id=None, acquisition_datetime=None,
        resolution_m=None, processing_level=None, bbox=bbox, aoi_id=site.aoi_id, preview_url=None,
        attribution="USGS Astrogeology / NASA PDS", official_source_url="https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic",
        cache_status="not_cached", data_status="product_identification_pending",
        limitations=["A matched official CTX orthomosaic has not yet been positively identified; the DEM is not presented as optical imagery."],
        )
    return [reference, terrain]


def get_imagery(site_id: str, imagery_id: str) -> ImageryRecord | None:
    return next((item for item in list_site_imagery(site_id) if item.imagery_id == imagery_id), None)


def safe_cache_path(cache_key: str, suffix: str) -> Path:
    if len(cache_key) != 64 or any(char not in "0123456789abcdef" for char in cache_key) or suffix not in {".json", ".png", ".tif"}:
        raise ValueError("Invalid cache identifier")
    path = (IMAGERY_CACHE / f"{cache_key}{suffix}").resolve()
    if IMAGERY_CACHE.resolve() not in path.parents:
        raise ValueError("Cache path escapes the imagery cache")
    return path
