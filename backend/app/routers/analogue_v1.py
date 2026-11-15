"""analogue-method-v1.0 API (/api/v3). Historical methods remain at /api/v2 and /api/evidence."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.models.analogue_v1 import CompareV3, DataRole, ExplorerWindow, ProfileIdV3, ProfileV3, ResultDetail
from app.models.ids import SITE_ID_PATTERN, SiteIdPath
from app.services import analogue_v1_service as av1
from app.services.analogue_audit import decomposition
from app.services.catalog_service import get_site

router = APIRouter(prefix="/v3")
SiteQuery = Annotated[str, Query(pattern=SITE_ID_PATTERN, max_length=64)]


def _not_found():
    raise HTTPException(status_code=404, detail={"code": "site_not_found", "message": "Unknown or unprocessed site ID"})


def _invalid(error: Exception):
    raise HTTPException(status_code=422, detail={"code": "invalid_request", "message": str(error)}) from None


@router.get("/method")
def method():
    cal = av1.calibration()
    return {**{k: av1.CONFIG[k] for k in ("method_version", "terrain_method", "status", "review_status", "comparison_definition", "notice", "formulas",
                                          "parameters", "primary_scale_m", "sensitivity_scales_m", "minimum_feature_coverage", "families", "aoi_exclusions",
                                          "validation_status", "compatibility")},
            "tolerances": [t.model_dump() for t in av1.tolerances()],
            "calibration": {k: cal[k] for k in ("rules", "resolution_floor", "redundancy", "synthetic_negatives", "base_rate", "remote_dem_status", "notice", "generated_at")},
            "decomposition": decomposition(),
            "profiles": [p.model_dump() for p in av1.profiles()],
            "references": [{k: ref[k] for k in ("id", "name", "body", "region", "scorable", "scorable_reason", "resolution_floor", "slope_median_60m", "dem", "selection_rationale")} for ref in av1.references()],
            "discrimination": {rid: {"background": v["background"], "single_feature": {f: s.get("share_at_or_above") for f, s in v["single_feature"].items()},
                                     "leave_one_region_out_tau": {f: [min(x["tau"][f] for x in v["leave_one_region_out"].values()), max(x["tau"][f] for x in v["leave_one_region_out"].values())]
                                                                  for f in av1.scored_features()} if v.get("leave_one_region_out") else {}}
                               for rid, v in av1.discrimination().get("references", {}).items()},
            "discrimination_population": av1.discrimination().get("population"),
            "paper": {"markdown": "docs/paper/methods.md", "latex": "docs/paper/methods.tex", "pdf": "docs/paper/methods.pdf", "docx": "docs/paper/methods.docx",
                      "generator": "backend/app/scripts/build_methods_paper.py", "test": "backend/tests/test_paper_numbers.py"}}


@router.get("/references")
def references():
    return av1.references()


@router.get("/profiles", response_model=list[ProfileV3])
def profiles():
    return av1.profiles()


@router.get("/compare", response_model=CompareV3)
def compare(reference: SiteQuery = "mars-jezero", profile: ProfileIdV3 = "terrain_analogy"):
    if not get_site(reference):
        _not_found()
    try:
        return av1.compare(reference, profile)
    except KeyError:
        _not_found()
    except av1.AnalogueError as error:
        _invalid(error)


@router.get("/result", response_model=ResultDetail)
def result(site: SiteQuery, reference: SiteQuery = "mars-jezero", profile: ProfileIdV3 = "terrain_analogy"):
    if not get_site(site) or not get_site(reference):
        _not_found()
    try:
        return av1.result_detail(reference, profile, site)
    except KeyError:
        _not_found()
    except av1.AnalogueError as error:
        _invalid(error)


@router.get("/data-roles", response_model=list[DataRole])
def data_roles():
    return av1.data_roles()


@router.get("/sites/{site_id}/explorer", response_model=ExplorerWindow)
def explorer(site_id: SiteIdPath):
    try:
        return av1.explorer(site_id)
    except KeyError:
        _not_found()
