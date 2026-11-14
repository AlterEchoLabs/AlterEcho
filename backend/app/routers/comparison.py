from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.models.schemas import Compatibility, ComparisonResult, DataStatus, DiscoverRequest, DiscoverResponse, MetricComparison
from app.services.catalog_service import get_site, get_validated_processed_summary
from app.services.explanation_service import explain
from app.services.similarity_service import CONFIG_V2, SimilarityInputError, compare_features
from app.services.terrain_v3_service import CONFIG as CONFIG_V3, compare_v3, load_v3_artifact, rank_stability_v3, sensitivity_v3


router = APIRouter()


def _unrankable_result(request_id: str, generated_at: datetime, reference_site, reference, candidate):
    reason = {
        DataStatus.planned: "Planned dataset integration; no validated processed terrain summary exists.",
        DataStatus.metadata_only: "Metadata only; no terrain AOI or processed summary exists.",
        DataStatus.unavailable: "Terrain data are unavailable or failed artifact integrity checks.",
    }.get(candidate.data_status, "A validated real processed terrain summary is required.")
    missing = list(CONFIG_V2["default_weights"])
    return ComparisonResult(
        request_id=request_id,
        reference_site=reference_site,
        candidate_site=candidate,
        overall_similarity=None,
        display_percentage=None,
        rankability="not_rankable",
        metric_similarities=[],
        available_metrics=[],
        missing_metrics=missing,
        explanation=reason,
        limitations=[reason, "Only real processed DEM summaries may receive a production terrain-shape index."],
        provenance={"reference": reference.provenance, "candidate": {}, "notice": "No synthetic fallback was used."},
        data_status=candidate.data_status,
        methodology_version=settings.methodology_version,
        generated_at=generated_at,
        compatibility=Compatibility(
            compatible=False,
            aoi_scale_match=False,
            resolution_match=False,
            methodology_match=False,
            reference_resolution_m=reference.resolution_m,
            candidate_resolution_m=None,
            warnings=[reason],
        ),
        quality={"classification": "not_rankable", "reason": reason},
        ranking_scope="unrankable_only",
        reference_data_status=DataStatus.real_processed,
        candidate_data_status=candidate.data_status,
        comparison_classification=f"not_rankable_{candidate.data_status.value}",
        processing_run_ids={"reference": reference.processing_run_id, "candidate": None},
    )


@router.post("/discover", response_model=DiscoverResponse)
def discover(request: DiscoverRequest):
    if request.methodology_version not in {"terrain-v2.0", "terrain-v3.0"}:
        raise HTTPException(status_code=422, detail={"code": "unsupported_methodology", "message": "methodology_version must be terrain-v2.0 or terrain-v3.0"})
    reference_site = get_site(request.reference_site_id)
    if not reference_site:
        raise HTTPException(status_code=404, detail={"code": "reference_not_found", "message": f"Unknown reference site ID: {request.reference_site_id}"})
    reference = get_validated_processed_summary(request.reference_site_id)
    if not reference:
        raise HTTPException(status_code=422, detail={"code": "reference_features_unavailable", "message": "Reference site lacks an integrity-checked real processed terrain summary"})
    unknown = [site_id for site_id in request.candidate_site_ids if not get_site(site_id)]
    if unknown:
        raise HTTPException(status_code=404, detail={"code": "candidate_not_found", "message": f"Unknown candidate site IDs: {', '.join(unknown)}"})

    request_id = str(uuid4())
    generated_at = datetime.now(timezone.utc)
    real_results: list[ComparisonResult] = []
    unrankable_results: list[ComparisonResult] = []
    for candidate_id in request.candidate_site_ids:
        candidate = get_site(candidate_id)
        candidate_summary = get_validated_processed_summary(candidate_id)
        if not candidate_summary or candidate.data_status != DataStatus.real_processed:
            unrankable_results.append(_unrankable_result(request_id, generated_at, reference_site, reference, candidate))
            continue
        if request.methodology_version == "terrain-v3.0":
            reference_v3, candidate_v3 = load_v3_artifact(reference.site_id), load_v3_artifact(candidate_id)
            if not reference_v3 or not candidate_v3 or reference_v3.quality_status != "quality_checked" or candidate_v3.quality_status != "quality_checked":
                result = _unrankable_result(request_id, generated_at, reference_site, reference, candidate)
                result.methodology_version = "terrain-v3.0"
                result.explanation = "A quality-checked terrain-v3 artifact is required. Terrain-v2 remains available by explicit request."
                unrankable_results.append(result)
                continue
            v3 = compare_v3(reference_v3, candidate_v3)
            sensitivity = sensitivity_v3(reference_v3, candidate_v3)
            component_map = v3["by_scale"]["60"]["components"]
            comparison = {
                "overall_similarity": v3["overall_similarity"], "rankability": "rankable", "coverage_ok": True,
                "available_metrics": list(component_map), "missing_metrics": [],
                "metric_similarities": [MetricComparison(metric=f"{name}_distribution", reference_value=0,
                    candidate_value=item["distance"], tolerance=CONFIG_V3["distribution_distance_scales"][name],
                    normalized_weight=item["weight"], similarity=item["similarity"]) for name, item in component_map.items()],
            }
            explanation = f"{candidate.name} is compared with Jezero using fixed-bin terrain distributions at 60, 120 and 240 m scales."
            limitations = ["Distribution bins and distance scales are versioned engineering choices pending independent methodology review."]
            quality_details = {"classification": "real_comparison", "scientific_validation_status": "methodology_review_pending",
                               "terrain_v3": v3, "sensitivity": sensitivity,
                               "cross_validation": {"earth_nasadem": "pending_credentials", "mars_mola": "pending_source_acquisition"}}
            active_method = "terrain-v3.0"
        else:
            try:
                comparison = compare_features(reference, candidate_summary, request.weights, CONFIG_V2)
            except SimilarityInputError as error:
                raise HTTPException(status_code=422, detail={"code": "invalid_comparison", "message": str(error)}) from error
            explanation, limitations = explain(candidate, comparison["metric_similarities"], comparison["rankability"] == "rankable", comparison["coverage_ok"])
            quality_details = {"reference": reference.quality, "candidate": candidate_summary.quality, "classification": "real_comparison", "scientific_validation_status": "methodology_review_pending"}
            active_method = "terrain-v2.0"
        score = comparison["overall_similarity"]
        resolution_match = reference.resolution_m == candidate_summary.resolution_m
        scale_match = reference.analysis_width_m == candidate_summary.analysis_width_m and reference.analysis_height_m == candidate_summary.analysis_height_m
        method_match = reference.calculation_metadata.get("methodology_version") == candidate_summary.calculation_metadata.get("methodology_version")
        compatible = comparison["rankability"] == "rankable" and resolution_match and scale_match and method_match
        real_results.append(ComparisonResult(
            request_id=request_id,
            reference_site=reference_site,
            candidate_site=candidate,
            overall_similarity=score,
            display_percentage=round(score * 100, 1) if score is not None else None,
            rankability=comparison["rankability"],
            metric_similarities=comparison["metric_similarities"],
            available_metrics=comparison["available_metrics"],
            missing_metrics=comparison["missing_metrics"],
            explanation=explanation,
            limitations=[*limitations, f"The configured {active_method} parameters are not scientific confidence intervals."],
            provenance={"reference_feature_source": reference.data_source, "candidate_feature_source": candidate_summary.data_source, "reference": reference.provenance, "candidate": candidate_summary.provenance, "notice": "Comparison generated only from integrity-checked processed elevation datasets."},
            data_status=DataStatus.real_processed,
            methodology_version=active_method,
            generated_at=generated_at,
            compatibility=Compatibility(compatible=compatible, aoi_scale_match=scale_match, resolution_match=resolution_match, methodology_match=method_match, reference_resolution_m=reference.resolution_m, candidate_resolution_m=candidate_summary.resolution_m, warnings=[] if compatible else ["Inputs failed one or more compatibility checks."]),
            quality=quality_details,
            ranking_scope="real_only",
            reference_data_status=DataStatus.real_processed,
            candidate_data_status=DataStatus.real_processed,
            comparison_classification="real_comparison",
            processing_run_ids={"reference": reference.processing_run_id, "candidate": candidate_summary.processing_run_id},
        ))
    real_results.sort(key=lambda item: item.overall_similarity if item.overall_similarity is not None else -1, reverse=True)
    if request.methodology_version == "terrain-v3.0" and len(real_results) > 1:
        reference_v3 = load_v3_artifact(reference.site_id)
        candidate_artifacts = {item.candidate_site.id: load_v3_artifact(item.candidate_site.id) for item in real_results}
        if reference_v3 and all(candidate_artifacts.values()):
            stability = rank_stability_v3(reference_v3, candidate_artifacts)  # type: ignore[arg-type]
            for item in real_results:
                item.quality["rank_stability"] = stability
    results = [*real_results, *unrankable_results]
    return DiscoverResponse(
        request_id=request_id,
        reference_site_id=request.reference_site_id,
        results=results,
        methodology_version=request.methodology_version,
        data_mode="real_with_planned" if unrankable_results else "real",
        generated_at=generated_at,
        ranking_scope="real_only" if real_results else "unrankable_only",
        real_results=real_results,
        preview_results=[],
        unrankable_results=unrankable_results,
    )
