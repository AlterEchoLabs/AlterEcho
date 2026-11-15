from fastapi import APIRouter, HTTPException

from app.models.evidence import EvidenceCompareRequest, EvidenceCompareResponse, ProfileSummary, SiteEvidence
from app.models.ids import SiteIdPath
from app.services import evidence_service

router = APIRouter()


@router.get("/evidence/model")
def evidence_model():
    config = evidence_service.CONFIG
    return {"model_version": config["model_version"], "review_status": config["review_status"], "notice": config["notice"],
            "dimensions": config["dimensions"], "thermal_comparison": config["thermal_comparison"], "default_profile": config["default_profile"],
            "status_definitions": {"measured": "Observed quantity processed by TerraLuna for both bodies under a documented method.",
                                   "proxy": "Indirect indicator of the quantity; never presented as the quantity itself.",
                                   "context_only": "Published or coarse evidence shown for interpretation; never scored.",
                                   "missing": "No evidence processed. Not a zero and not absence.",
                                   "not_comparable": "Evidence exists but scale, quantity or method do not allow a fair comparison."},
            "quality_levels": config["quality_levels"]}


@router.get("/evidence/profiles", response_model=list[ProfileSummary])
def evidence_profiles():
    return evidence_service.list_profiles()


@router.get("/sites/{site_id}/evidence", response_model=SiteEvidence)
def site_evidence(site_id: SiteIdPath):
    try:
        return evidence_service.site_evidence(site_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={"code": "site_not_found", "message": "Unknown site ID"}) from None


@router.post("/evidence/compare", response_model=EvidenceCompareResponse)
def evidence_compare(request: EvidenceCompareRequest):
    try:
        return evidence_service.compare(request.reference_site_id, request.candidate_site_ids, request.profile_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={"code": "site_not_found", "message": "One or more site IDs are not in the catalog"}) from None
    except evidence_service.EvidenceError as error:
        raise HTTPException(status_code=422, detail={"code": "invalid_evidence_request", "message": str(error)}) from None
