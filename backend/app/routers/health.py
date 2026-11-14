from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.services.catalog_service import data_status_summary


router = APIRouter()


@router.get("/health")
def health():
    summary = data_status_summary()
    return {
        "status": "online",
        "application_id": settings.application_id,
        "product_name": settings.product_name,
        "application_version": settings.app_version,
        "build_identifier": settings.build_identifier,
        "methodology_version": settings.methodology_version,
        "data_mode": summary.pop("data_mode"),
        "data_counts": summary,
        "timestamp": datetime.now(timezone.utc),
    }


@router.get("/config")
def config():
    summary = data_status_summary()
    return {
        "identity": {"application_id": settings.application_id, "product_name": settings.product_name, "subtitle": settings.subtitle, "team_name": settings.team_name, "application_version": settings.app_version, "build_identifier": settings.build_identifier},
        "enabled_bodies": ["earth", "mars", "moon"],
        "enabled_features": ["catalog", "terrain_v2_historical", "terrain_v3_multiscale", "terrain_distributions", "sensitivity_analysis", "aoi_imagery_provider_architecture", "dataset_registry", "artifact_integrity", "srtm_multi_tile_mosaic"],
        "backend_mode": summary["data_mode"],
        "data_counts": {key: value for key, value in summary.items() if key != "data_mode"},
        "methodology_version": settings.methodology_version,
        "methodology_display_name": settings.methodology_display_name,
    }

