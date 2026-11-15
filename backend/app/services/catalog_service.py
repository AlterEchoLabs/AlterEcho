from functools import lru_cache
import json
from pathlib import Path

from app.models.schemas import DataStatus, Planet, ProcessingStatus, Site, SourceReference, TerrainFeatureSummary
from app.services.geospatial_service import GEO_DATA
from app.services.integrity_service import validate_site_integrity


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _read_json(filename: str):
    with (DATA_DIR / filename).open(encoding="utf-8") as handle:
        return json.load(handle)


PLANETS = [Planet.model_validate(item) for item in _read_json("planets.json")]
SITES = [Site.model_validate(item) for item in _read_json("sites.json")]
SOURCES = [SourceReference.model_validate(item) for item in _read_json("sources.json")]
def list_sites(body: str | None = None, data_status: str | None = None, analog_type: str | None = None) -> list[Site]:
    sites = [_with_processed_status(site) for site in SITES]
    return [
        site for site in sites
        if (body is None or site.body.value == body)
        and (data_status is None or site.data_status.value == data_status)
        and (analog_type is None or site.analog_type == analog_type)
    ]


def get_site(site_id: str) -> Site | None:
    site = next((site for site in SITES if site.id == site_id), None)
    return _with_processed_status(site) if site else None


def get_feature_summary(site_id: str) -> TerrainFeatureSummary | None:
    """Deprecated compatibility adapter: production never serves synthetic fixtures."""
    return None


def get_processed_summary(site_id: str) -> TerrainFeatureSummary | None:
    path = GEO_DATA / "processed" / f"{site_id}.terrain.json"
    return TerrainFeatureSummary.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None


def _artifact_signature() -> tuple:
    """Names, sizes and mtimes of every file the integrity check reads; any change invalidates the cache."""
    entries = []
    for folder, pattern in (("processed", "*.json"), ("processed", "*.sha256"), ("manifests", "*.json"), ("aoi", "*.geojson")):
        for path in (GEO_DATA / folder).glob(pattern):
            stat = path.stat()
            entries.append((folder, path.name, stat.st_size, stat.st_mtime_ns))
    return tuple(sorted(entries))


@lru_cache(maxsize=64)
def _validated_summary_cached(site_id: str, _signature: tuple) -> TerrainFeatureSummary | None:
    site = next((item for item in SITES if item.id == site_id), None)
    if not site or validate_site_integrity(site):
        return None
    return get_processed_summary(site_id)


def get_validated_processed_summary(site_id: str) -> TerrainFeatureSummary | None:
    summary = _validated_summary_cached(site_id, _artifact_signature())
    return summary.model_copy(deep=True) if summary else None


def _with_processed_status(site: Site) -> Site:
    if site.data_status != DataStatus.real_processed:
        return site
    processed = get_validated_processed_summary(site.id)
    if not processed:
        return site.model_copy(update={"data_status": DataStatus.unavailable, "processing_status": ProcessingStatus.processed, "available_metrics": []})
    available = [name for name in ("slope_p50_deg", "slope_p90_deg", "local_relief_p50_m", "local_relief_p90_m", "roughness_mean", "roughness_p90") if getattr(processed, name) is not None]
    return site.model_copy(update={"data_status": processed.data_status, "available_metrics": available})


def data_status_summary() -> dict[str, int | str]:
    sites = [_with_processed_status(site) for site in SITES]
    counts = {
        "real_processed_sites": sum(site.data_status == DataStatus.real_processed for site in sites),
        "planned_sites": sum(site.data_status == DataStatus.planned for site in sites),
        "metadata_only_sites": sum(site.data_status == DataStatus.metadata_only for site in sites),
        "unavailable_sites": sum(site.data_status == DataStatus.unavailable for site in sites),
        "production_demo_sites": 0,
    }
    rankable = sum(site.body.value == "earth" and site.data_status == DataStatus.real_processed and len(site.available_metrics) >= 4 for site in sites)
    counts["rankable_real_earth_candidates"] = rankable
    counts["rankable_real_candidates"] = rankable  # Deprecated Phase 3 alias.
    counts["demo_fixture_sites"] = 0  # Deprecated Phase 3 alias.
    counts["data_mode"] = "real_with_planned" if counts["planned_sites"] or counts["metadata_only_sites"] else "real"
    return counts

