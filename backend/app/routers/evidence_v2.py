from datetime import datetime, timezone
import json

from fastapi import APIRouter, HTTPException, Query

from app.models.evidence_v2 import CompareRequestV2, CompareResponseV2, ProfileV2, ThermalAudit
from app.models.ids import SITE_ID_PATTERN, SiteIdPath
from app.services import evidence_v2_service as ev2
from app.services.catalog_service import get_site, get_validated_processed_summary
from app.services.geospatial_service import GEO_DATA, canonical_text_sha256, load_manifest
from app.services.imagery_service import list_site_imagery
from app.services.terrain_v3_service import load_v3_artifact
from app.services.terrain_v4_service import CONFIG as V4, compare_v4, gaussian_similarity, wasserstein_1

router = APIRouter(prefix="/v2")


def _not_found():
    raise HTTPException(status_code=404, detail={"code": "site_not_found", "message": "Unknown or unprocessed site ID"})


@router.get("/model")
def model():
    return {"model_version": ev2.CONFIG["model_version"], "terrain_method": V4["methodology_version"], "review_status": ev2.CONFIG["review_status"],
            "notice": ev2.CONFIG["notice"], "statuses": ev2.CONFIG["statuses"], "dimensions": ev2.CONFIG["dimensions"],
            "profile_states": ev2.CONFIG["profile_states"], "default_profile": ev2.CONFIG["default_profile"],
            "terrain_v4": {k: V4[k] for k in ("formula", "families", "scale_weights", "scale_support", "tau_provenance", "weight_provenance", "redundancy_policy", "frozen_before_sites")},
            "redundancy_adjusted_weights": ev2.REDUNDANCY_ADJUSTED}


@router.get("/profiles", response_model=list[ProfileV2])
def list_profiles():
    return ev2.profiles()


@router.post("/compare", response_model=CompareResponseV2)
def compare(request: CompareRequestV2):
    try:
        return ev2.compare(request.reference_site_id, request.candidate_site_ids, request.profile_id)
    except KeyError:
        _not_found()
    except ev2.EvidenceV2Error as error:
        raise HTTPException(status_code=422, detail={"code": "invalid_request", "message": str(error)}) from None


@router.get("/evaluation")
def evaluation():
    data = ev2.evaluation()
    if not data:
        raise HTTPException(status_code=404, detail={"code": "evaluation_missing", "message": "Run app.scripts.terrain_v4_evaluation"})
    return data


@router.get("/thermal-audit/{site_id}", response_model=ThermalAudit)
def thermal_audit(site_id: SiteIdPath):
    if not get_site(site_id):
        _not_found()
    return ev2.thermal_audit(ev2.load_thermal("mars-jezero"), ev2.load_thermal(site_id))


@router.get("/method/worked-example")
def worked_example(site_id: str = Query(default="earth-ladakh", pattern=SITE_ID_PATTERN, max_length=64), family: str = Query(default="slope", max_length=32)):
    if family not in V4["families"] or not get_site(site_id):
        _not_found()
    ref, cand = load_v3_artifact("mars-jezero"), load_v3_artifact(site_id)
    if not ref or not cand:
        _not_found()
    spec = V4["families"][family]
    r, c = ref.scales["60"].distributions[spec["distribution"]], cand.scales["60"].distributions[spec["distribution"]]
    cdf_r, cdf_c, acc_r, acc_c, steps = [], [], 0.0, 0.0, []
    for i, width in enumerate(b - a for a, b in zip(r.bin_edges, r.bin_edges[1:])):
        acc_r += r.normalized_counts[i]
        acc_c += c.normalized_counts[i]
        steps.append({"bin": [r.bin_edges[i], r.bin_edges[i + 1]], "jezero_share": round(r.normalized_counts[i], 4), "site_share": round(c.normalized_counts[i], 4),
                      "cdf_gap": round(abs(acc_r - acc_c), 4), "bin_width": width, "contribution": round(abs(acc_r - acc_c) * width, 4)})
    w1 = wasserstein_1(r, c)
    full = compare_v4(ref, cand)
    return {"site_id": site_id, "family": family, "units": spec["units"], "scale_m": 60, "tau": spec["tau"], "steps": steps,
            "w1": round(w1, 4), "index_60m": round(gaussian_similarity(w1, 0.0, spec["tau"]), 3),
            "formula": f"S = 100 × exp(−0.5 × ({w1:.3f} / {spec['tau']})²) = {gaussian_similarity(w1, 0.0, spec['tau']):.2f}",
            "family_index_all_scales": round(full["families"][family]["index"], 3), "terrain_index": round(full["terrain_index"], 3),
            "scale_weights": V4["scale_weights"], "family_weights": {k: v["weight"] for k, v in V4["families"].items()}}


@router.get("/reports/{site_id}")
def report(site_id: SiteIdPath, profile_id: str = Query(default="terrain_analogy", max_length=40), reference_site_id: str = Query(default="mars-jezero", pattern=SITE_ID_PATTERN)):
    site, ref = get_site(site_id), get_site(reference_site_id)
    if not site or not ref or site.body.value != "earth":
        _not_found()
    try:
        comparison = ev2.compare(reference_site_id, None, profile_id)
    except ev2.EvidenceV2Error as error:
        raise HTTPException(status_code=422, detail={"code": "invalid_request", "message": str(error)}) from None
    result = next((r for r in comparison.results if r.site_id == site_id), None)
    if not result:
        _not_found()

    def aoi(s):
        return json.loads((GEO_DATA / "aoi" / f"{s.aoi_id}.geojson").read_text(encoding="utf-8")) if s.aoi_id else None

    def artifact_record(s):
        a = load_v3_artifact(s.id)
        path = GEO_DATA / "processed" / f"{s.id}.terrain-v3.json"
        summary = get_validated_processed_summary(s.id)
        return {"terrain_v3_artifact": f"backend/data/processed/{s.id}.terrain-v3.json", "artifact_sha256_lf": canonical_text_sha256(path) if path.exists() else None,
                "processing_run_id": summary.processing_run_id if summary else None, "provenance": a.provenance if a else None,
                "quality_status": a.quality_status if a else None, "feature_coverage_60m": {k: v.coverage_fraction for k, v in a.scales["60"].feature_coverage.items()} if a else None,
                "metrics_by_scale": {sc: v.metrics for sc, v in a.scales.items()} if a else None,
                "distributions_by_scale": {sc: {k: d.model_dump() for k, d in v.distributions.items()} for sc, v in a.scales.items()} if a else None}

    def manifest(s):
        return load_manifest(s.source_id).model_dump() if s.source_id else None

    return {
        "report_type": "terraluna-comparison-record", "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": comparison.model_version, "terrain_method": comparison.terrain_method, "review_status": comparison.review_status,
        "profile": comparison.profile.model_dump(), "profile_state": comparison.profile_state, "profile_state_reason": comparison.profile_state_reason,
        "reference": {"site": ref.model_dump(mode="json"), "aoi": aoi(ref), "source_manifest": manifest(ref), "measurements": artifact_record(ref),
                      "imagery": [i.model_dump(mode="json") for i in list_site_imagery(ref.id)]},
        "candidate": {"site": site.model_dump(mode="json"), "aoi": aoi(site), "source_manifest": manifest(site), "measurements": artifact_record(site),
                      "imagery": [i.model_dump(mode="json") for i in list_site_imagery(site.id)]},
        "result": result.model_dump(mode="json"),
        "formulas": {"terrain_v4": V4["formula"], "partial_index": "sum(w_k * C_k for k in A) / sum(w_k for k in A)", "evidence_coverage": "sum(w_k for k in A)"},
        "parameters": {"families": V4["families"], "scale_weights": V4["scale_weights"], "tau_provenance": V4["tau_provenance"]},
        "ordering_note": comparison.ordering_note, "tie_groups": comparison.tie_groups, "ranking_sensitive": comparison.ranking_sensitive,
        "evaluation": comparison.evaluation, "physical_limits": comparison.physical_limits,
        "statement": "A high index means only that this Earth AOI matches the selected planetary AOI on the measured features at the tested scales under this method.",
        "reproduce": ["cd backend", "python -m app.scripts.validate_catalog_integrity",
                      f"python -c \"from app.services.evidence_v2_service import compare; print(compare('{reference_site_id}', None, '{profile_id}').model_dump_json(indent=2))\""],
    }
