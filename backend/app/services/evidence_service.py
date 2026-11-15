"""analog-evidence-v1: multidimensional, evidence-gated comparison built on prepared artifacts.

Principles enforced here (mirrored in the tests):
- terrain-v3.0 is reused unchanged and also reported as the terrain-only baseline;
- only dimensions with *measured and comparable* evidence enter a score;
- missing / context-only / non-comparable evidence is never converted to zero;
- candidates are ranked only on a common scoring basis, and the share of the profile weight that
  the basis covers is always reported;
- the index is not a probability, a confidence value or a percentage of identity.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import json
from math import exp
from pathlib import Path
from typing import Any

from app.models.evidence import (
    CandidateEvidenceResult, DimensionEvidence, DimensionScore, EvidenceCompareResponse, Factor, FeatureComparison,
    MetricEvidence, ProfileSummary, SensitivityResult, SiteEvidence, SourceCitation, TerrainBaseline,
)
from app.services.catalog_service import SOURCES, get_site, get_validated_processed_summary
from app.services.geospatial_service import GEO_DATA, load_manifest
from app.services.terrain_v3_service import CONFIG as TERRAIN_CONFIG, compare_v3, load_v3_artifact, sensitivity_v3

APP_DATA = Path(__file__).resolve().parents[1] / "data"
CONFIG = json.loads((APP_DATA / "evidence.v1.json").read_text(encoding="utf-8"))
CONTEXT = json.loads((APP_DATA / "evidence.context.v1.json").read_text(encoding="utf-8"))
EVIDENCE_DIR = GEO_DATA / "processed" / "evidence"
DIMENSIONS: list[str] = list(CONFIG["dimensions"])
TERRAIN_FEATURE_LABELS = {
    "slope_deg": ("Slope distribution", "slope_p50_deg", "°"),
    "local_relief_m": ("Local relief distribution (1 km window)", "local_relief_p50_m", "m"),
    "roughness_m": ("Roughness distribution (300 m window)", "roughness_mean", "m"),
    "elevation_relative_m": ("Relative-elevation distribution", "elevation_std_m", "m"),
}
SHORT_LABELS = {"slope_deg": "slope", "local_relief_m": "local relief", "roughness_m": "roughness", "elevation_relative_m": "relative elevation",
                "diurnal_range_p50_k": "day–night temperature range", "night_temperature_p50_k": "night temperature", "day_temperature_p50_k": "day temperature"}
TERRAIN_FEATURE_STAT = {"slope_deg": "median", "local_relief_m": "median", "roughness_m": "mean", "elevation_relative_m": "std. dev."}
NOT_ASSESSED = CONTEXT["operational"]["_not_assessed"]
OBSERVATION_PERIODS = {
    "SRTMGL1": "Acquired 2000-02-11 to 2000-02-22 (SRTM shuttle mission)",
    "M20_JezeroCrater_CTXDEM_20m": "Mosaic published 2021-10-14 by USGS from CTX stereo images",
}


class EvidenceError(ValueError):
    pass


def _citations(ids: list[str] | None) -> list[SourceCitation]:
    lookup = {source.id: source for source in SOURCES}
    return [SourceCitation(id=item, title=lookup[item].title, url=lookup[item].url) for item in ids or [] if item in lookup]


def _artifact_signature() -> tuple:
    paths = sorted(EVIDENCE_DIR.glob("*.thermal-v1.json")) + sorted((GEO_DATA / "processed").glob("*.terrain-v3.json"))
    return tuple((path.name, path.stat().st_mtime_ns) for path in paths)


@lru_cache(maxsize=16)
def _thermal_cached(site_id: str, _signature: tuple) -> dict | None:
    path = EVIDENCE_DIR / f"{site_id}.thermal-v1.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def load_thermal(site_id: str) -> dict | None:
    return _thermal_cached(site_id, _artifact_signature())


# ---------------------------------------------------------------- per-site evidence records

def _terrain_evidence(site) -> DimensionEvidence:
    artifact = load_v3_artifact(site.id)
    label = CONFIG["dimensions"]["terrain"]["label"]
    if not artifact or artifact.quality_status != "quality_checked" or not get_validated_processed_summary(site.id):
        return DimensionEvidence(dimension="terrain", label=label, status="missing", quality="none",
                                 reason="No integrity-checked terrain-v3 artifact for this site.")
    manifest = load_manifest(site.source_id)
    metrics60 = artifact.scales["60"].metrics
    coverage = min(c.coverage_fraction for c in artifact.scales["60"].feature_coverage.values())
    common = dict(units="", product_id=f"{manifest.product_name} {manifest.product_version or ''}".strip(),
                  source_url=manifest.source_page_url, native_resolution=str(manifest.native_resolution),
                  analysis_resolution="60 / 120 / 240 m grids, 1.2 km halo cropped to the core AOI",
                  observation_period=OBSERVATION_PERIODS.get(manifest.product_name, "Product epoch not recorded in the manifest"),
                  aoi_overlap=f"Exact registered AOI {artifact.core_aoi_id} (10 km × 10 km)", valid_coverage=coverage,
                  processing_version="terrain-v3.0", quality_flags=["methodology_review_pending", "single_dem_source_cross_validation_pending"],
                  limitations=["Terrain shape only; absolute elevation datums are never compared."])
    metrics = [
        MetricEvidence(metric_id="slope_p50_deg", label="Median slope (60 m)", value=metrics60.get("slope_p50_deg"), **{**common, "units": "°"}),
        MetricEvidence(metric_id="local_relief_p50_m", label="Median local relief, 1 km window (60 m)", value=metrics60.get("local_relief_p50_m"), **{**common, "units": "m"}),
        MetricEvidence(metric_id="roughness_mean", label="Mean roughness, 300 m window (60 m)", value=metrics60.get("roughness_mean"), **{**common, "units": "m"}),
    ]
    return DimensionEvidence(dimension="terrain", label=label, status="measured", quality="moderate",
                             reason=f"Measured from {manifest.title} over the exact AOI; integrity checked. Independent methodology review is pending.",
                             metrics=metrics, sources=_citations(site.source_references))


def _temperature_evidence(site) -> DimensionEvidence:
    label = CONFIG["dimensions"]["temperature"]["label"]
    thermal = load_thermal(site.id)
    if not thermal:
        return DimensionEvidence(dimension="temperature", label=label, status="missing", quality="none",
                                 reason="No thermal artifact has been processed for this site.")
    product, summary = thermal["product"], thermal["summary"]
    common = dict(units="K", product_id=product["product_id"], source_url=product["source_url"],
                  native_resolution=f"{product['native_resolution_m']} m pixels" if product.get("native_resolution_m") else "Point sensor (a few m² footprint)",
                  analysis_resolution=product["analysis_resolution"], observation_period=product["observation_period"],
                  aoi_overlap=("Exact registered AOI (mean of pixels inside the polygon)" if thermal["body"] == "earth"
                               else "Rover positions inside the registered AOI on every sampled sol"),
                  valid_coverage=round(summary["paired_samples"] / summary["planned_samples"], 3) if summary["planned_samples"] else None,
                  processing_version=thermal["evidence_version"], quality_flags=thermal.get("quality_flags", []), limitations=thermal.get("limitations", []))
    metrics = [
        MetricEvidence(metric_id="day_temperature_p50_k", label=f"Day skin temperature, annual median (~{summary['day_local_solar_time_p50_h']:.1f} h local solar time)", value=summary["day_temperature_p50_k"], **common),
        MetricEvidence(metric_id="night_temperature_p50_k", label=f"Night skin temperature, annual median (~{summary['night_local_solar_time_p50_h']:.1f} h local solar time)", value=summary["night_temperature_p50_k"], **common),
        MetricEvidence(metric_id="diurnal_range_p50_k", label="Day − night range, annual median", value=summary["diurnal_range_p50_k"], **common),
    ]
    source_ids = ["modis-myd11a2"] if thermal["body"] == "earth" else ["meda-pds", "m20-waypoints"]
    return DimensionEvidence(dimension="temperature", label=label, status="measured", quality="limited",
                             reason=("Measured skin temperature at matched local solar times across a full annual cycle. "
                                     "Quality is limited: Earth values are AOI means of ~1 km pixels, Mars values come from a point sensor beside the rover."),
                             metrics=metrics, sources=_citations(source_ids))


def _context_evidence(dimension: str, site) -> DimensionEvidence:
    table = CONTEXT["dimensions"][dimension]
    record = table.get(site.id) or (table.get("_earth_default") if site.body.value == "earth" else None) or table.get("_default")
    if not record:
        record = {"status": "missing", "reason": "No evidence registered."}
    return DimensionEvidence(dimension=dimension, label=CONFIG["dimensions"][dimension]["label"], status=record["status"], quality="none",
                             reason=record["reason"], sources=_citations(record.get("source_ids")))


def site_evidence(site_id: str) -> SiteEvidence:
    site = get_site(site_id)
    if not site:
        raise KeyError(site_id)
    dims = [_terrain_evidence(site), _temperature_evidence(site), *(_context_evidence(d, site) for d in DIMENSIONS[2:])]
    operational = CONTEXT["operational"].get(site.id)
    if operational:
        operational = {**operational, "sources": [c.model_dump() for c in _citations(operational.get("source_ids"))], "not_assessed": NOT_ASSESSED}
    return SiteEvidence(site_id=site.id, site_name=site.name, body=site.body.value, dimensions=dims, operational=operational)


# ---------------------------------------------------------------- comparison

def _gaussian(difference: float, tolerance: float) -> float:
    if tolerance <= 0:
        raise EvidenceError("tolerance must be positive")
    return exp(-0.5 * (difference / tolerance) ** 2)


def thermal_comparability(reference: dict, candidate: dict) -> str | None:
    """Return a reason string when the two thermal artifacts must not be compared."""
    gates = CONFIG["thermal_comparison"]["comparability_gates"]
    r, c = reference["summary"], candidate["summary"]
    if reference["product"]["units"] != "K" or candidate["product"]["units"] != "K":
        return "Units differ; temperatures must both be in kelvin."
    if not reference["quantity"].endswith("skin_temperature") or not candidate["quantity"].endswith("skin_temperature"):
        return "Quantities differ (skin vs. air temperature are not the same measurement)."
    for key in ("day_local_solar_time_p50_h", "night_local_solar_time_p50_h"):
        if r.get(key) is None or c.get(key) is None or abs(r[key] - c[key]) > gates["max_local_time_offset_h"]:
            return f"Local solar times differ by more than {gates['max_local_time_offset_h']} h."
    earth, mars = (c, r) if candidate["body"] == "earth" else (r, c)
    if earth["paired_samples"] < gates["min_earth_paired_samples"]:
        return "Too few Earth day/night pairs to represent a full annual cycle."
    if mars["paired_samples"] < gates["min_mars_paired_samples"]:
        return "Too few Mars day/night pairs to represent a full annual cycle."
    span = mars.get("solar_longitude_range_deg")
    if not span or span[1] - span[0] < gates["min_mars_solar_longitude_span_deg"]:
        return "Mars samples do not span enough of the seasonal cycle."
    return None


def compare_thermal(reference: dict, candidate: dict, tolerance_factor: float = 1.0) -> tuple[float, list[FeatureComparison]]:
    features, total, weight_sum = [], 0.0, 0.0
    for key, spec in CONFIG["thermal_comparison"]["features"].items():
        ref, cand = reference["summary"][key], candidate["summary"][key]
        similarity = _gaussian(cand - ref, spec["tolerance_k"] * tolerance_factor)
        features.append(FeatureComparison(dimension="temperature", feature=key, label=spec["label"], reference_value=ref, candidate_value=cand,
                                          difference=round(cand - ref, 2), units="K", similarity=similarity, weight_in_dimension=spec["weight"]))
        total += similarity * spec["weight"]
        weight_sum += spec["weight"]
    return total / weight_sum, features


def _terrain_features(reference, candidate, v3: dict) -> list[FeatureComparison]:
    features = []
    weights = TERRAIN_CONFIG["feature_weights"]
    for feature, weight in weights.items():
        label, metric, units = TERRAIN_FEATURE_LABELS[feature]
        similarity = sum(v3["by_scale"][scale]["components"][feature]["similarity"] * TERRAIN_CONFIG["scale_weights"][scale] for scale in v3["by_scale"])
        ref, cand = reference.scales["60"].metrics.get(metric), candidate.scales["60"].metrics.get(metric)
        features.append(FeatureComparison(dimension="terrain", feature=feature, label=label, reference_value=ref, candidate_value=cand,
                                          difference=round(cand - ref, 2) if ref is not None and cand is not None else None,
                                          units=units, similarity=min(1.0, similarity), weight_in_dimension=weight))
    return features


def profile_summary(profile_id: str) -> ProfileSummary:
    if profile_id not in CONFIG["profiles"]:
        raise EvidenceError(f"Unknown profile: {profile_id}")
    spec = CONFIG["profiles"][profile_id]
    return ProfileSummary(id=profile_id, label=spec["label"], purpose=spec["purpose"], weights=spec["weights"],
                          required_dimensions=spec["required_dimensions"], min_backed_weight_fraction=spec["min_backed_weight_fraction"],
                          review_status=CONFIG["review_status"])


def list_profiles() -> list[ProfileSummary]:
    return [profile_summary(pid) for pid in CONFIG["profiles"]]


def _dimension_similarities(reference_id: str, candidate_id: str) -> dict[str, dict[str, Any]]:
    """Measured similarities per dimension for one candidate, or a reason when not comparable."""
    out: dict[str, dict[str, Any]] = {}
    reference_v3, candidate_v3 = load_v3_artifact(reference_id), load_v3_artifact(candidate_id)
    terrain_ok = (reference_v3 and candidate_v3 and reference_v3.quality_status == candidate_v3.quality_status == "quality_checked"
                  and get_validated_processed_summary(reference_id) and get_validated_processed_summary(candidate_id))
    if terrain_ok:
        v3 = compare_v3(reference_v3, candidate_v3)
        tested = sensitivity_v3(reference_v3, candidate_v3)["tested_index_range"]
        out["terrain"] = {"similarity": v3["overall_similarity"], "features": _terrain_features(reference_v3, candidate_v3, v3),
                          "status": "measured", "quality": "moderate", "tested_range": [tested[0] / 100, tested[1] / 100],
                          "reason": "terrain-v3.0 distributions at 60/120/240 m on integrity-checked artifacts."}
    else:
        out["terrain"] = {"similarity": None, "status": "missing", "quality": "none", "reason": "Integrity-checked terrain-v3 artifacts are required for both sites."}
    ref_thermal, cand_thermal = load_thermal(reference_id), load_thermal(candidate_id)
    if ref_thermal and cand_thermal:
        blocker = thermal_comparability(ref_thermal, cand_thermal)
        if blocker:
            out["temperature"] = {"similarity": None, "status": "not_comparable", "quality": "none", "reason": blocker}
        else:
            similarity, features = compare_thermal(ref_thermal, cand_thermal)
            out["temperature"] = {"similarity": similarity, "features": features, "status": "measured", "quality": "limited",
                                  "reason": "Matched local solar times and full annual cycles; point sensor (Mars) versus AOI mean (Earth)."}
    else:
        out["temperature"] = {"similarity": None, "status": "missing", "quality": "none", "reason": "A thermal artifact is missing for one of the two sites."}
    candidate = get_site(candidate_id)
    for dimension in DIMENSIONS[2:]:
        record = _context_evidence(dimension, candidate)
        out[dimension] = {"similarity": None, "status": record.status, "quality": "none", "reason": record.reason}
    return out


def _score(sims: dict[str, dict], weights: dict[str, float], basis: list[str], thermal_factor: float = 1.0,
           weight_override: dict[str, float] | None = None, terrain_override: float | None = None,
           thermal_pair: tuple[dict, dict] | None = None) -> float:
    w = {**weights, **(weight_override or {})}
    total = weight_sum = 0.0
    for dimension in basis:
        similarity = sims[dimension]["similarity"]
        if dimension == "terrain" and terrain_override is not None:
            similarity = terrain_override
        if dimension == "temperature" and thermal_factor != 1.0 and thermal_pair:
            similarity = compare_thermal(*thermal_pair, tolerance_factor=thermal_factor)[0]
        total += w[dimension] * similarity
        weight_sum += w[dimension]
    return 100 * total / weight_sum


def _fmt(value: float | None, units: str) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}{units}" if units in {"°"} else f"{value:.1f} {units}"


def _factors(dimension_scores: list[DimensionScore], basis_weight: float) -> list[Factor]:
    helped, hurt, gaps = [], [], []
    for dim in dimension_scores:
        if not dim.used_in_score:
            if dim.profile_weight > 0 and dim.status != "measured":
                gaps.append(Factor(kind="gap", dimension=dim.dimension, weight_share=dim.profile_weight, short_label=dim.label.lower(),
                                   text=f"{dim.label} carries {dim.profile_weight:.0%} of this profile but has no comparable evidence ({dim.status.replace('_', ' ')})."))
            continue
        for feature in dim.features:
            share = dim.profile_weight / basis_weight * feature.weight_in_dimension
            stat = TERRAIN_FEATURE_STAT.get(feature.feature)
            values = (f" ({stat} {_fmt(feature.candidate_value, feature.units)} vs {_fmt(feature.reference_value, feature.units)} at Jezero)" if stat
                      else f" ({_fmt(feature.candidate_value, feature.units)} vs {_fmt(feature.reference_value, feature.units)} at Jezero)")
            if feature.similarity >= 0.6:
                helped.append((share * feature.similarity, Factor(kind="helped", dimension=dim.dimension, weight_share=round(share, 3), short_label=SHORT_LABELS.get(feature.feature, feature.label.lower()),
                                                                   text=f"{feature.label} is close{values}.")))
            elif feature.similarity < 0.4:
                hurt.append((share * (1 - feature.similarity), Factor(kind="hurt", dimension=dim.dimension, weight_share=round(share, 3), short_label=SHORT_LABELS.get(feature.feature, feature.label.lower()),
                                                                       text=f"{feature.label} differs{values}.")))
    top = lambda items: [factor for _, factor in sorted(items, key=lambda pair: pair[0], reverse=True)[:3]]  # noqa: E731
    return top(helped) + top(hurt) + sorted(gaps, key=lambda factor: factor.weight_share, reverse=True)


def compare(reference_id: str, candidate_ids: list[str], profile_id: str) -> EvidenceCompareResponse:
    return _compare_cached(reference_id, tuple(candidate_ids), profile_id, _artifact_signature())


@lru_cache(maxsize=64)
def _compare_cached(reference_id: str, candidate_ids: tuple[str, ...], profile_id: str, _signature: tuple) -> EvidenceCompareResponse:
    profile = profile_summary(profile_id)
    weights = {d: profile.weights.get(d, 0.0) for d in DIMENSIONS}
    total_weight = sum(weights.values())
    reference = get_site(reference_id)
    if not reference or reference.body.value != "mars":
        raise EvidenceError("The reference must be a registered Mars site with evidence.")
    per_candidate: dict[str, dict[str, dict]] = {}
    for candidate_id in candidate_ids:
        site = get_site(candidate_id)
        if not site:
            raise KeyError(candidate_id)
        if site.body.value != "earth":
            raise EvidenceError("Candidates must be Earth sites.")
        per_candidate[candidate_id] = _dimension_similarities(reference_id, candidate_id)

    backed = {cid: {d for d in DIMENSIONS if weights[d] > 0 and sims[d]["status"] == "measured" and sims[d]["similarity"] is not None}
              for cid, sims in per_candidate.items()}
    eligible = [cid for cid in candidate_ids if set(profile.required_dimensions) <= backed[cid]]
    common = sorted(set.intersection(*(backed[cid] for cid in eligible)) if eligible else set(), key=DIMENSIONS.index)
    common_fraction = sum(weights[d] for d in common) / total_weight if total_weight else 0.0
    profile_ok = bool(eligible) and common_fraction >= profile.min_backed_weight_fraction

    # terrain-only baseline order across all candidates with terrain evidence
    terrain_scores = {cid: sims["terrain"]["similarity"] for cid, sims in per_candidate.items() if sims["terrain"]["similarity"] is not None}
    terrain_order = sorted(terrain_scores, key=lambda cid: (-terrain_scores[cid], cid))

    scores = {cid: _score(per_candidate[cid], weights, common) for cid in eligible} if profile_ok else {}
    order = sorted(scores, key=lambda cid: (-scores[cid], cid))

    # sensitivity: weight perturbations, thermal tolerance perturbations, terrain tested range
    configurations: list[dict] = []
    if profile_ok:
        delta_w = CONFIG["sensitivity"]["weight_perturbation_fraction"]
        delta_t = CONFIG["sensitivity"]["tolerance_perturbation_fraction"]
        for dimension in common:
            for factor in (1 - delta_w, 1 + delta_w):
                configurations.append({"weight_override": {dimension: weights[dimension] * factor}})
        if "temperature" in common:
            for factor in (1 - delta_t, 1 + delta_t):
                configurations.append({"thermal_factor": factor})
        if "terrain" in common:
            configurations += [{"terrain_bound": 0}, {"terrain_bound": 1}]
    sensitivity_scores: dict[str, list[float]] = {cid: [scores[cid]] for cid in scores}
    sensitivity_ranks: dict[str, list[int]] = {cid: [order.index(cid) + 1] for cid in scores}
    reference_thermal = load_thermal(reference_id)
    for config in configurations:
        trial = {}
        for cid in scores:
            terrain_override = None
            if "terrain_bound" in config:
                terrain_override = per_candidate[cid]["terrain"]["tested_range"][config["terrain_bound"]]
            trial[cid] = _score(per_candidate[cid], weights, common, thermal_factor=config.get("thermal_factor", 1.0),
                                weight_override=config.get("weight_override"), terrain_override=terrain_override,
                                thermal_pair=(reference_thermal, load_thermal(cid)) if "thermal_factor" in config else None)
        trial_order = sorted(trial, key=lambda cid: (-trial[cid], cid))
        for cid in trial:
            sensitivity_scores[cid].append(trial[cid])
            sensitivity_ranks[cid].append(trial_order.index(cid) + 1)

    results: list[CandidateEvidenceResult] = []
    unranked = sorted((c for c in candidate_ids if c not in order), key=lambda c: (c not in terrain_order, terrain_order.index(c) if c in terrain_order else 0, c))
    for cid in (order + unranked):
        site = get_site(cid)
        sims = per_candidate[cid]
        ranked = cid in scores
        basis = common if ranked else sorted(backed[cid], key=DIMENSIONS.index)
        basis_weight = sum(weights[d] for d in basis)
        dimension_scores = [DimensionScore(dimension=d, label=CONFIG["dimensions"][d]["label"], profile_weight=weights[d] / total_weight if total_weight else 0,
                                           status=sims[d]["status"], quality=sims[d]["quality"], similarity=sims[d]["similarity"],
                                           used_in_score=ranked and d in basis, reason=sims[d]["reason"], features=sims[d].get("features", []))
                            for d in DIMENSIONS]
        factors = _factors(dimension_scores, basis_weight / total_weight if ranked and basis_weight else 1.0)
        qualities = [sims[d]["quality"] for d in basis]
        quality = "limited" if "limited" in qualities else ("moderate" if qualities else "none")
        terrain_rank = terrain_order.index(cid) + 1 if cid in terrain_order else None
        baseline = TerrainBaseline(method=CONFIG["terrain_baseline_method"], index=round(100 * terrain_scores[cid], 1) if cid in terrain_scores else 0.0, rank=terrain_rank)
        missing_required = [d for d in profile.required_dimensions if d not in backed[cid]]
        if ranked:
            index = round(scores[cid], 1)
            labels = " + ".join(CONFIG["dimensions"][d]["label"].lower() for d in basis)
            helped = next((f.text for f in factors if f.kind == "helped"), None)
            hurt = next((f.text for f in factors if f.kind == "hurt"), None)
            explanation = (f"{site.name} scores {index:.1f}/100 on {labels}, which covers {common_fraction:.0%} of the {profile.label} weight. "
                           + (f"Closest: {helped[0].lower() + helped[1:]} " if helped else "")
                           + (f"Largest mismatch: {hurt[0].lower() + hurt[1:]}" if hurt else ""))
            sensitivity = SensitivityResult(tested_configurations=len(configurations) + 1,
                                            index_range=[round(min(sensitivity_scores[cid]), 1), round(max(sensitivity_scores[cid]), 1)],
                                            rank_range=[min(sensitivity_ranks[cid]), max(sensitivity_ranks[cid])],
                                            notice="Deterministic perturbation of profile weights (±20%), thermal tolerances (±20%) and the terrain-v3 tested range. Not a confidence interval.")
        else:
            index, sensitivity = None, None
            if missing_required:
                why = "; ".join(CONFIG["dimensions"][d]["label"].lower() for d in missing_required)
                explanation = f"Not ranked under {profile.label}: the profile requires comparable evidence for {why}. That evidence is not available for {site.name}."
            else:
                explanation = (f"Not ranked under {profile.label}: comparable evidence covers only {common_fraction:.0%} of the profile weight "
                               f"(minimum {profile.min_backed_weight_fraction:.0%}).")
        results.append(CandidateEvidenceResult(
            site_id=cid, site_name=site.name, rank=order.index(cid) + 1 if ranked else None,
            ranking_status="ranked" if ranked else "insufficient_evidence", index=index,
            backed_weight_fraction=round((common_fraction if ranked else basis_weight / total_weight) if total_weight else 0, 4),
            scoring_basis=basis if ranked else [], evidence_quality=quality, dimensions=dimension_scores, factors=factors,
            terrain_baseline=baseline, sensitivity=sensitivity, explanation=explanation.strip(), not_assessed=NOT_ASSESSED))

    ordering_note = _ordering_note(profile, profile_ok, order, terrain_order, per_candidate, common, common_fraction)
    return EvidenceCompareResponse(
        model_version=CONFIG["model_version"], review_status=CONFIG["review_status"], reference_site_id=reference_id, profile=profile,
        common_basis=common if profile_ok else [], common_basis_weight_fraction=round(common_fraction if profile_ok else 0.0, 4),
        ranking_status="ranked" if profile_ok else "insufficient_evidence", ordering_note=ordering_note, results=results,
        generated_at=datetime.now(timezone.utc), notice=CONFIG["notice"])


def _ordering_note(profile, profile_ok, order, terrain_order, per_candidate, common, common_fraction) -> str:
    if not profile_ok:
        required = "; ".join(CONFIG["dimensions"][d]["label"].lower() for d in profile.required_dimensions)
        return (f"{profile.label} needs comparable evidence for {required}. That evidence is not available yet, so this profile shows no ranking. "
                "The terrain-only baseline is still shown for each site.")
    ranked_terrain = [cid for cid in terrain_order if cid in order]
    if order == ranked_terrain:
        others = [d for d in common if d != "terrain"]
        if not others:
            return "Only terrain evidence is comparable under this profile, so the order is the terrain-only order."
        spreads = []
        for d in others:
            values = [per_candidate[cid][d]["similarity"] for cid in order]
            spreads.append(f"{CONFIG['dimensions'][d]['label'].lower()} similarities range only {min(values):.2f}–{max(values):.2f}")
        return ("The order matches the terrain-only baseline: " + "; ".join(spreads)
                + ", so terrain decides the order. Adding those dimensions changes the index values, not the order.")
    moved = [cid for cid in order if order.index(cid) != ranked_terrain.index(cid)]
    return f"The order differs from the terrain-only baseline for {len(moved)} site(s) because the added dimensions separate the candidates."
