from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.models.ids import SiteIdPath
from app.models.schemas import Body, DataStatus
from app.services import catalog_service


router = APIRouter()


@router.get("/planets")
def planets():
    return catalog_service.PLANETS


@router.get("/sites")
def sites(body: Body | None = None, data_status: DataStatus | None = None, analog_type: str | None = Query(default=None, max_length=80)):
    return catalog_service.list_sites(body.value if body else None, data_status.value if data_status else None, analog_type)


@router.get("/sites/{site_id}")
def site(site_id: SiteIdPath):
    result = catalog_service.get_site(site_id)
    if not result:
        raise HTTPException(status_code=404, detail={"code": "site_not_found", "message": "Unknown site ID"})
    return result


@router.get("/methodology")
def methodology():
    return {
        "version": settings.methodology_version,
        "display_name": settings.methodology_display_name,
        "available_versions": ["terrain-v3.0", "terrain-v2.0"],
        "multidimensional_model": "analog-evidence-v1.0 (see /api/evidence/model); terrain-v3.0 is its terrain baseline and is unchanged",
        "metrics": ["fixed-bin relative-elevation distribution", "slope distribution", "local-relief distribution over 1,000 m", "local elevation-standard-deviation distribution over 300 m"],
        "formula": "terrain-v3 uses normalized fixed-bin Wasserstein distances converted by exp(-distance / versioned distance scale), then combines 60, 120 and 240 m results with versioned weights.",
        "historical_method": "terrain-v2.0 remains reproducible by explicit request and is not overwritten.",
        "data_statuses": {"real_processed": "Computed from a traceable source raster", "planned": "Future dataset integration; no score", "metadata_only": "Catalog context without computed metrics", "unavailable": "Not available"},
        "processing_statuses": {"not_processed": "No terrain artifact", "processed": "Processing completed", "integrity_checked": "Manifest, AOI, run, checksum, dimensions, resolution, and coverage checks passed"},
        "scientific_validation_statuses": {"not_reviewed": "No scientific review claimed", "methodology_review_pending": "Processed result; scientific methodology review remains pending", "research_reviewed": "Reserved for documented external review"},
        "harmonization": "terrain-v3 processes a 1,200 m outer halo before cropping derivatives to the core AOI and reports 60, 120 and 240 m scales.",
        "ranking_gate": "Real v3 comparisons require quality-checked v3 artifacts, fixed versioned bins, feature-level coverage of at least 90%, and traceable source checksums.",
        "interpretation_bands": {"very_high": "85-100", "high": "65-84.9", "moderate": "40-64.9", "low": "20-39.9", "very_low": "0-19.9", "notice": "Application interpretation bands, not scientific standards."},
        "limitations": ["The index compares terrain shape only and excludes absolute elevation datum", "Scores are indices out of 100, not probabilities or scientific confidence", "Distribution distance scales and weights await independent scientific review", "NASADEM and MOLA cross-validation remain pending", "Earth cannot reproduce planetary gravity, pressure, radiation, geology, temperature cycles, or habitability"],
    }

