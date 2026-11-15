"""analog-evidence-v2.0: measured analogy, field-test evidence and evidence quality kept separate.

partial_index = sum(w_k * C_k for k in A) / sum(w_k for k in A)     A = measured_comparable dimensions
evidence_coverage = sum(w_k for k in A)                               (profile weights sum to 1)

Rules (each covered by tests):
* only measured_comparable dimensions enter an index; nothing missing becomes zero;
* a profile ranks only when every task-critical dimension is measured_comparable for every candidate
  and all candidates share one eligibility key; otherwise it is experimental_partial or not_assessed;
* candidates whose placement, DEM and method ranges overlap form a tie group with no ordering claim;
* no threshold on coverage is used as a scientific standard.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
import json
from math import exp
from pathlib import Path
from typing import Any

from app.models.evidence_v2 import (
    AuditCheck, CandidateResult, Citation, CompareResponseV2, DimensionRecord, Eligibility, FamilyScore, ProfileV2, Sensitivity, ThermalAudit,
)
from app.services.catalog_service import SOURCES, SITES, get_site, get_validated_processed_summary
from app.services.geospatial_service import GEO_DATA, load_manifest
from app.services.terrain_v3_service import CONFIG as V3, compare_v3, load_v3_artifact
from app.services.terrain_v4_service import CONFIG as V4, TerrainMethodError, compare_v4, perturbed_configurations

APP_DATA = Path(__file__).resolve().parents[1] / "data"
CONFIG = json.loads((APP_DATA / "evidence.v2.json").read_text(encoding="utf-8"))
CONTEXT = json.loads((APP_DATA / "evidence.context.v2.json").read_text(encoding="utf-8"))
THERMAL = json.loads((APP_DATA / "evidence.v1.json").read_text(encoding="utf-8"))["thermal_comparison"]
DIMENSIONS = list(CONFIG["dimensions"])
FAMILY_LABELS = {"slope": ("Slope", "slope_p50_deg", "median"), "local_relief": ("Local relief (1 km window)", "local_relief_p50_m", "median"),
                 "roughness": ("Roughness (300 m window)", "roughness_mean", "mean"), "relative_elevation": ("Relative elevation", "elevation_std_m", "std. dev.")}
PHYSICAL_LIMITS = {
    "mars": ["Gravity: Earth 9.81 m/s², Mars 3.71 m/s².", "Surface pressure: Earth ~1013 hPa, Mars ~6 hPa (CO₂).",
             "Mars has no global magnetic field and a thin atmosphere, so surface radiation is far higher.",
             "Earth surfaces are shaped by liquid water, vegetation and biology that are absent on present-day Mars."],
    "moon": ["Gravity: Earth 9.81 m/s², Moon 1.62 m/s².", "The Moon has no atmosphere, so there is no wind or water erosion and extreme thermal cycling.",
             "Lunar polar illumination and permanently shadowed regions have no Earth equivalent.", "Lunar regolith forms by impact gardening, not by weathering."],
}
REDUNDANCY_ADJUSTED = {"slope": 1 / 6, "local_relief": 1 / 6, "roughness": 1 / 6, "relative_elevation": 0.5}


class EvidenceV2Error(ValueError):
    pass


def _citations(ids) -> list[Citation]:
    lookup = {s.id: s for s in SOURCES}
    return [Citation(id=i, title=lookup[i].title, url=lookup[i].url) for i in ids or [] if i in lookup]


def _signature() -> tuple:
    paths = [*(GEO_DATA / "processed").glob("*.terrain-v3.json"), *(GEO_DATA / "processed" / "evidence").glob("*.json"),
             GEO_DATA / "processed" / "evaluation" / "terrain-v4-evaluation.json"]
    return tuple(sorted((p.name, p.stat().st_mtime_ns) for p in paths if p.exists()))


@lru_cache(maxsize=4)
def _evaluation_cached(_sig: tuple) -> dict:
    path = GEO_DATA / "processed" / "evaluation" / "terrain-v4-evaluation.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def evaluation() -> dict:
    return _evaluation_cached(_signature())


@lru_cache(maxsize=32)
def _thermal_cached(site_id: str, _sig: tuple) -> dict | None:
    path = GEO_DATA / "processed" / "evidence" / f"{site_id}.thermal-v1.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def load_thermal(site_id: str) -> dict | None:
    return _thermal_cached(site_id, _signature())


# ------------------------------------------------------------------ temperature comparability audit

def thermal_audit(reference: dict | None, candidate: dict | None) -> ThermalAudit:
    if not reference or not candidate:
        return ThermalAudit(decision="missing", checks=[], summary="A thermal record is missing for one of the two sites.")
    r, c = reference["summary"], candidate["summary"]
    earth, planet = (candidate, reference) if candidate["body"] == "earth" else (reference, candidate)
    used = [s for s in planet.get("samples", []) if s.get("day_ground_temp_k") is not None or s.get("night_ground_temp_k") is not None]
    span = planet["summary"].get("solar_longitude_range_deg")
    dt_day = abs((r.get("day_local_solar_time_p50_h") or 99) - (c.get("day_local_solar_time_p50_h") or -99))
    dt_night = abs((r.get("night_local_solar_time_p50_h") or 99) - (c.get("night_local_solar_time_p50_h") or -99))
    checks = [
        AuditCheck(check="Product identity and units", required=True, passed=reference["product"]["units"] == candidate["product"]["units"] == "K",
                   detail=f"{earth['product']['product_id']} and {planet['product']['product_id']}, both in kelvin."),
        AuditCheck(check="Same physical quantity", required=True, passed=all(x["quantity"].endswith("skin_temperature") for x in (earth, planet)),
                   detail="Both are thermal-infrared retrievals of surface skin temperature (not air temperature). Emissivity assumptions differ between the retrievals."),
        AuditCheck(check="Spatial support", required=True, passed=False,
                   detail=f"Earth: mean of ~{earth.get('samples', [{}])[0].get('expected_aoi_pixels', 100)} one-kilometre pixels over the 10 km AOI (~10⁸ m²). Mars: a few square metres beside the rover. Daytime skin temperature varies by tens of kelvin between sand, bedrock and dust at metre scale, so a point does not represent the window."),
        AuditCheck(check="Local solar time", required=True, passed=dt_day <= 1.0 and dt_night <= 1.0,
                   detail=f"Day windows differ by {dt_day:.1f} h and night windows by {dt_night:.1f} h (gate: 1 h)."),
        AuditCheck(check="Seasonal coverage", required=True, passed=earth["summary"]["paired_samples"] >= 30 and bool(span) and span[1] - span[0] >= 270,
                   detail=f"Earth: {earth['summary']['paired_samples']} paired 8-day composites over one year. Mars: {planet['summary']['paired_samples']} paired sols spanning Ls {span[0]:.0f}–{span[1]:.0f}°." if span else "Mars seasonal span unknown."),
        AuditCheck(check="Sampling equivalence", required=True, passed=False,
                   detail="Earth values are 8-day clear-sky composites, so cloudy conditions are excluded. Mars values are medians of single-sol 1-hour windows under all conditions, dust included. The two sampling schemes are not equivalent."),
        AuditCheck(check="Observation period", required=False, passed=False,
                   detail=f"Earth {earth['product']['observation_period']}; Mars {planet['product']['observation_period']}. Interannual variability is not characterised on either body."),
        AuditCheck(check="Quality flags applied", required=True, passed=True, detail="MODIS QA ≤ 1 with LST error ≤ 2 K; MEDA rover still, low tilt, wheel and shadow flags."),
        AuditCheck(check="Rover inside the reference AOI", required=True, passed=bool(used) and all(s.get("rover_inside_aoi") for s in used),
                   detail=f"{len(used)} sols used; rover position from NASA/JPL MMGIS waypoints on each sol."),
        AuditCheck(check="Uncertainty propagated", required=False, passed=False,
                   detail="Per-sample uncertainties are recorded but not propagated to the annual medians."),
    ]
    failed = [ch.check for ch in checks if ch.required and not ch.passed]
    decision = "measured_comparable" if not failed else "measured_context_only"
    context = {key: {"earth": earth["summary"].get(key), "planetary": planet["summary"].get(key)} for key in ("day_temperature_p50_k", "night_temperature_p50_k", "diurnal_range_p50_k")}
    summary = ("Temperature passes every required comparability check." if not failed else
               f"Shown as context only. It fails: {', '.join(failed).lower()}. The two measurements do not answer the same question at the same scale.")
    return ThermalAudit(decision=decision, checks=checks, summary=summary, context_values=context)


def _thermal_index(reference: dict, candidate: dict) -> float:
    total = weight = 0.0
    for key, spec in THERMAL["features"].items():
        d = candidate["summary"][key] - reference["summary"][key]
        total += 100 * exp(-0.5 * (d / spec["tolerance_k"]) ** 2) * spec["weight"]
        weight += spec["weight"]
    return total / weight


# ------------------------------------------------------------------ profiles

def profile(profile_id: str) -> ProfileV2:
    if profile_id not in CONFIG["profiles"]:
        raise EvidenceV2Error(f"Unknown profile: {profile_id}")
    spec = CONFIG["profiles"][profile_id]
    return ProfileV2(id=profile_id, review_status=CONFIG["review_status"], **{k: spec[k] for k in (
        "label", "question", "required_measurements", "weights", "task_critical", "allowed_missing", "ranking_conditions", "permitted_conclusion", "unassessed")})


def profiles() -> list[ProfileV2]:
    return [profile(pid) for pid in CONFIG["profiles"]]


# ------------------------------------------------------------------ dimension records

def _terrain_record(reference_id: str, candidate_id: str, weight: float) -> tuple[DimensionRecord, dict | None]:
    label = CONFIG["dimensions"]["terrain"]["label"]
    ref, cand = load_v3_artifact(reference_id), load_v3_artifact(candidate_id)
    integrity_ok = bool(get_validated_processed_summary(reference_id)) and bool(get_validated_processed_summary(candidate_id) or candidate_id.startswith("user-"))
    if not ref:
        return DimensionRecord(dimension="terrain", label=label, scorable=True, status="missing_planetary", profile_weight=weight, included=False,
                               reason="The reference has no terrain artifact."), None
    if not cand or not integrity_ok:
        return DimensionRecord(dimension="terrain", label=label, scorable=True, status="missing_earth", profile_weight=weight, included=False,
                               reason="No integrity-checked terrain artifact for this Earth site."), None
    try:
        v4 = compare_v4(ref, cand)
    except TerrainMethodError as error:
        return DimensionRecord(dimension="terrain", label=label, scorable=True, status="incompatible", profile_weight=weight, included=False,
                               reason=str(error)), None
    families = []
    for name, f in v4["families"].items():
        fam_label, metric, stat = FAMILY_LABELS[name]
        families.append(FamilyScore(family=name, label=fam_label, units=f["units"], tau=f["tau"], weight=f["weight"],
                                    w1_by_scale={s: round(v["w1"], 4) for s, v in f["by_scale"].items()},
                                    index_by_scale={s: round(v["index"], 3) for s, v in f["by_scale"].items()}, index=round(f["index"], 3),
                                    reference_stat=ref.scales["60"].metrics.get(metric), candidate_stat=cand.scales["60"].metrics.get(metric), stat_label=stat))
    record = DimensionRecord(dimension="terrain", label=label, scorable=True, status="measured_comparable", profile_weight=weight, included=weight > 0,
                             index=round(v4["terrain_index"], 2),
                             reason="terrain-v4.0: Wasserstein-1 distances between identically binned distributions at 60, 120 and 240 m, converted with S = 100·exp(−0.5·(W1/τ)²).",
                             families=families)
    return record, v4


def _temperature_record(reference_id: str, candidate_id: str, weight: float) -> DimensionRecord:
    label = CONFIG["dimensions"]["temperature"]["label"]
    ref, cand = load_thermal(reference_id), load_thermal(candidate_id)
    audit = thermal_audit(ref, cand)
    if audit.decision == "missing":
        status = "missing_planetary" if not ref else "missing_earth"
        return DimensionRecord(dimension="temperature", label=label, scorable=True, status=status, profile_weight=weight, included=False,
                               reason=audit.summary, thermal_audit=audit)
    comparable = audit.decision == "measured_comparable"
    return DimensionRecord(dimension="temperature", label=label, scorable=True, status=audit.decision, profile_weight=weight,
                           included=comparable and weight > 0, index=round(_thermal_index(ref, cand), 2) if comparable else None,
                           reason=audit.summary, thermal_audit=audit,
                           earth_note=f"{cand['product']['product_id']} · {cand['product']['observation_period']}",
                           planetary_note=f"{ref['product']['instrument']} · {ref['product']['observation_period']}",
                           sources=_citations(["modis-myd11a2", "meda-pds", "m20-waypoints"]))


def _context_record(dimension: str, candidate_id: str, weight: float) -> DimensionRecord:
    spec = CONTEXT["pair_status"][dimension]
    record = spec.get(candidate_id) or spec["default"]
    return DimensionRecord(dimension=dimension, label=CONFIG["dimensions"][dimension]["label"], scorable=True, status=record["status"],
                           profile_weight=weight, included=False, reason=CONFIG["statuses"][record["status"]],
                           earth_note=record.get("earth"), planetary_note=record.get("planetary"), sources=_citations(record.get("source_ids")))


def _field_test(site_id: str) -> dict[str, Any]:
    base = {k: dict(v) for k, v in CONTEXT["field_test"]["_default"].items()}
    for key, value in CONTEXT["field_test"].get(site_id, {}).items():
        base[key] = {**value, "sources": [c.model_dump() for c in _citations(value.get("source_ids"))]}
    return base


def _field_record(site_id: str, weight: float) -> DimensionRecord:
    return DimensionRecord(dimension="field_test_suitability", label=CONFIG["dimensions"]["field_test_suitability"]["label"], scorable=False,
                           status="missing_earth", profile_weight=weight, included=False,
                           reason="Evidence record only (access, permits, safety, logistics, terrain detail). No numeric operational score is defined; most fields are unknown.")


# ------------------------------------------------------------------ comparison

def _eligibility(reference_id: str, candidate_id: str, included: list[str], weights: dict) -> Eligibility:
    ref = get_site(reference_id)
    site = get_site(candidate_id)
    features = json.dumps({"bins": V3["distributions"], "families": {k: {"distribution": v["distribution"], "tau": v["tau"], "weight": v["weight"]} for k, v in V4["families"].items()},
                           "local_relief_m": V3["local_relief_neighborhood_m"], "roughness_m": V3["roughness_neighborhood_m"]}, sort_keys=True)
    weight_text = json.dumps({k: weights.get(k, 0) for k in included}, sort_keys=True)
    dem = "unknown"
    if site and site.source_id:
        manifest = load_manifest(site.source_id)
        dem = f"{manifest.product_name}.{manifest.product_version}"
    data = {"reference_aoi_id": ref.aoi_id, "method_version": f"{CONFIG['model_version']}+{V4['methodology_version']}", "included_dimensions": included,
            "feature_definitions_sha256": sha256(features.encode()).hexdigest()[:16], "resolution_policy": "60/120/240 m, 1.2 km halo, bilinear before derivatives",
            "weights_sha256": sha256(weight_text.encode()).hexdigest()[:16], "dem_product": dem}
    key = sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
    return Eligibility(**data, key=key)


EVALUATION_REFERENCE = "mars-jezero"  # placement, DEM and base-rate checks were run against this reference


def _sensitivity(site_id: str, method_ranges: dict, method_ranks: dict, reference_id: str) -> Sensitivity:
    if reference_id != EVALUATION_REFERENCE:
        return Sensitivity(method_index_range=method_ranges.get(site_id), method_rank_range=method_ranks.get(site_id),
                           notice="Method perturbations only. Placement and DEM checks were run against Jezero, not this reference. Not a confidence interval.")
    ev = evaluation().get("sites", {}).get(site_id, {})
    shifts = [ev[k]["index"] for k in ("north_2km", "south_2km", "east_2km", "west_2km") if ev.get(k, {}).get("status") == "ok"]
    return Sensitivity(
        method_index_range=method_ranges.get(site_id), method_rank_range=method_ranks.get(site_id),
        placement_index_range=[round(min(shifts), 2), round(max(shifts), 2)] if shifts else None,
        dem_index={k.replace("dem_", ""): v.get("index") for k, v in ev.items() if k.startswith("dem_")},
        halo_effect_index=ev.get("no_halo", {}).get("index"),
    )


def _method_sensitivity(reference_id: str, site_ids: list[str]) -> tuple[dict, dict, bool]:
    ref = load_v3_artifact(reference_id)
    arts = {s: load_v3_artifact(s) for s in site_ids}
    configs = perturbed_configurations() + [("redundancy_adjusted", {k: dict(v, weight=REDUNDANCY_ADJUSTED[k]) for k, v in V4["families"].items()}, V4["scale_weights"])]
    scores_by_site = {s: [] for s in site_ids}
    ranks_by_site = {s: [] for s in site_ids}
    for _, fam, scales in configs:
        scores = {s: compare_v4(ref, a, fam, scales)["terrain_index"] for s, a in arts.items()}
        order = sorted(scores, key=lambda s: (-scores[s], s))
        for pos, s in enumerate(order, 1):
            scores_by_site[s].append(scores[s])
            ranks_by_site[s].append(pos)
    ranges = {s: [round(min(v), 2), round(max(v), 2)] for s, v in scores_by_site.items()}
    ranks = {s: [min(v), max(v)] for s, v in ranks_by_site.items()}
    return ranges, ranks, any(r[0] != r[1] for r in ranks.values())


def _tie_groups(order: list[str], nominal: dict[str, float], sens: dict[str, Sensitivity]) -> list[list[str]]:
    intervals = {}
    for s in order:
        values = [nominal[s]]
        se = sens[s]
        for rng in (se.method_index_range, se.placement_index_range):
            if rng:
                values += rng
        values += [v for v in se.dem_index.values() if v is not None]
        intervals[s] = (min(values), max(values))
    groups: list[list[str]] = []
    low = None
    for s in order:
        lo, hi = intervals[s]
        if groups and hi >= low:
            groups[-1].append(s)
            low = min(low, lo)
        else:
            groups.append([s])
            low = lo
    return groups


def compare(reference_id: str, candidate_ids: list[str] | None, profile_id: str) -> CompareResponseV2:
    return _compare_cached(reference_id, tuple(candidate_ids or ()), profile_id, _signature())


@lru_cache(maxsize=64)
def _compare_cached(reference_id: str, candidate_ids: tuple[str, ...], profile_id: str, _sig: tuple) -> CompareResponseV2:
    ref = get_site(reference_id)
    if not ref or ref.body.value not in {"mars", "moon"} or not load_v3_artifact(reference_id):
        raise EvidenceV2Error("The reference must be a processed Mars or Moon AOI")
    prof = profile(profile_id)
    weights = {d: prof.weights.get(d, 0.0) for d in DIMENSIONS}
    if not candidate_ids:
        candidate_ids = tuple(s.id for s in SITES if s.body.value == "earth")
    results: list[CandidateResult] = []
    terrain_index: dict[str, float] = {}
    for cid in candidate_ids:
        site = get_site(cid)
        if not site or site.body.value != "earth":
            raise KeyError(cid)
        terrain, v4 = _terrain_record(reference_id, cid, weights["terrain"])
        dims = [terrain, _context_record("geology", cid, weights["geology"]), _temperature_record(reference_id, cid, weights["temperature"]),
                *(_context_record(d, cid, weights[d]) for d in ("water_ice", "surface_processes", "subsurface_habitability")),
                _field_record(cid, weights["field_test_suitability"])]
        dims.sort(key=lambda d: DIMENSIONS.index(d.dimension))
        included = [d.dimension for d in dims if d.included]
        coverage = round(sum(weights[d] for d in included), 4)
        partial = round(sum(weights[d.dimension] * d.index for d in dims if d.included) / sum(weights[d] for d in included), 2) if included else None
        missing_tc = [d for d in prof.task_critical if not next(x for x in dims if x.dimension == d).status == "measured_comparable"]
        if terrain.index is not None:
            terrain_index[cid] = terrain.index
        fams = sorted(terrain.families, key=lambda f: f.index)
        v3 = compare_v3(load_v3_artifact(reference_id), load_v3_artifact(cid))["display_index"] if v4 else None
        rc = CONTEXT["research_context"].get(cid)
        results.append(CandidateResult(
            site_id=cid, site_name=site.name, rank=None, state="not_rankable" if not included else "not_assessed", partial_index=partial,
            evidence_coverage=coverage, included_dimensions=included, missing_task_critical=missing_tc, dimensions=dims,
            closest=[f.label for f in reversed(fams[-2:])] if fams else [], furthest=[f.label for f in fams[:2]] if fams else [],
            historical_terrain_v3_index=v3, sensitivity=Sensitivity(), eligibility=_eligibility(reference_id, cid, included, weights) if included else None,
            field_test=_field_test(cid), research_context={**rc, "sources": [c.model_dump() for c in _citations(rc.get("source_ids"))]} if rc else None,
            explanation="", permitted_conclusion=prof.permitted_conclusion, unassessed=prof.unassessed))

    scored = [r for r in results if r.partial_index is not None]
    keys = {r.eligibility.key for r in scored if r.eligibility}
    method_ranges, method_ranks, method_sensitive = _method_sensitivity(reference_id, [r.site_id for r in scored]) if scored else ({}, {}, False)
    for r in scored:
        r.sensitivity = _sensitivity(r.site_id, method_ranges, method_ranks, reference_id)
    tc_measured = {d for r in scored for d in prof.task_critical if d not in r.missing_task_critical}
    # Unmeasured catalog sites are listed as not_rankable; they do not block ranking of measured sites.
    all_tc = bool(scored) and all(not r.missing_task_critical for r in scored) and len(keys) == 1
    if all_tc:
        state, reason = "ranked", "Every task-critical dimension is measured_comparable for every candidate, and all candidates share one eligibility key."
    elif tc_measured:
        missing = sorted({d for r in results for d in r.missing_task_critical}, key=DIMENSIONS.index)
        state = "experimental_partial"
        reason = ("Task-critical evidence is missing: " + "; ".join(CONFIG["dimensions"][d]["label"].lower() for d in missing)
                  + ". The partial index below covers the included dimensions only and is not a ranking or a task conclusion.")
    else:
        state, reason = "not_assessed", "None of this profile's task-critical dimensions has comparable evidence, so no index is shown."
    order = sorted((r.site_id for r in scored), key=lambda s: (-next(r.partial_index for r in scored if r.site_id == s), s))
    nominal = {r.site_id: r.partial_index for r in scored}
    groups = _tie_groups(order, nominal, {r.site_id: r.sensitivity for r in scored}) if scored else []
    for gi, group in enumerate(groups, 1):
        for s in group:
            next(r for r in scored if r.site_id == s).sensitivity.tie_group = gi
    for r in results:
        if r.partial_index is None:
            r.state = "not_rankable"
            r.explanation = f"{r.site_name}: no dimension of this profile has comparable evidence, so no index is shown."
            continue
        r.state = state if state != "not_assessed" else "not_assessed"
        if state == "ranked":
            # Standard competition ranking over tie groups: every member of a group shares the group's first position.
            group_start = next(order.index(g[0]) + 1 for g in groups if r.site_id in g)
            r.rank = group_start
        if state == "not_assessed":
            r.partial_index = None
        included_labels = " + ".join(CONFIG["dimensions"][d]["label"].lower() for d in r.included_dimensions)
        group = next((g for g in groups if r.site_id in g), [r.site_id])
        tied = f" It is indistinguishable from {', '.join(get_site(s).name for s in group if s != r.site_id)} once placement, DEM and method checks are considered." if len(group) > 1 else ""
        if state == "not_assessed":
            r.explanation = f"{r.site_name}: not assessed under {prof.label}. {reason}"
        else:
            r.explanation = (f"{r.site_name}: {r.partial_index:.1f}/100 on {included_labels}, covering {r.evidence_coverage:.0%} of the {prof.label} weight."
                             f" Closest family: {r.closest[0].lower() if r.closest else 'n/a'}; furthest: {r.furthest[0].lower() if r.furthest else 'n/a'}.{tied}")
    ordered = sorted(results, key=lambda r: (r.partial_index is None, -(r.partial_index or 0), r.site_id))
    ev = evaluation()
    base = ev.get("base_rate", {}) if reference_id == EVALUATION_REFERENCE else {}
    note = _ordering_note(state, groups, base, method_sensitive)
    if reference_id != EVALUATION_REFERENCE and state != "not_assessed":
        note += " Limited lunar terrain comparison: Earth relief is shaped by atmosphere and water; illumination and regolith are not assessed."
    included_all = sorted({d for r in scored for d in r.included_dimensions}, key=DIMENSIONS.index)
    return CompareResponseV2(
        model_version=CONFIG["model_version"], terrain_method=V4["methodology_version"], review_status=CONFIG["review_status"],
        reference_site_id=reference_id, reference_aoi_id=ref.aoi_id, reference_body=ref.body.value, profile=prof, profile_state=state,
        profile_state_reason=reason, included_dimensions=included_all, evidence_coverage=round(sum(weights[d] for d in included_all), 4),
        ordering_note=note, tie_groups=groups if state != "not_assessed" else [], ranking_sensitive=method_sensitive, results=ordered,
        physical_limits=PHYSICAL_LIMITS[ref.body.value],
        evaluation={"base_rate_share_at_or_above": base.get("share_at_or_above"), "base_rate_windows": base.get("count"), "base_rate_median": base.get("median_index"),
                    "reference_stability": {k: v.get("index") for k, v in ev.get("reference_stability", {}).items()} if reference_id == "mars-jezero" else None,
                    "redundancy": ev.get("redundancy"), "mola_vs_ctx": ev.get("mola_vs_ctx") if reference_id == "mars-jezero" else None},
        generated_at=datetime.now(timezone.utc), notice=CONFIG["notice"])


def _ordering_note(state: str, groups: list[list[str]], base: dict, method_sensitive: bool) -> str:
    if state == "not_assessed":
        return "This profile cannot be assessed with the evidence that exists today."
    parts = []
    named = [[get_site(s).name for s in g] for g in groups if len(g) > 1]
    if named:
        parts.append("Tie groups (no ordering inside a group): " + " | ".join(", ".join(g) for g in named) + ".")
    share = (base.get("share_at_or_above") or {}).get("99")
    if share is not None:
        parts.append(f"Base rate: {share:.0%} of {base.get('count')} unselected Earth windows also score 99 or more, so a high terrain index is common for low-relief terrain.")
    parts.append("Ranking sensitive to method." if method_sensitive else "No rank changes under the tested weight, τ and scale perturbations.")
    if state == "experimental_partial":
        parts.insert(0, "Experimental partial comparison: listed by partial index for exploration, not ranked.")
    return " ".join(parts)
