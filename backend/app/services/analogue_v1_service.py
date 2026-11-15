"""analogue-method-v1.0: comparison of an Earth AOI with a planetary reference AOI for one task profile.

Measurements come from terrain-v5.0 artifacts (exact quantile functions); tolerances, resolution
floors and the redundancy decision come from the calibration file written by
app.scripts.analogue_v1_calibration. Nothing here fills a missing value with zero.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
import json
from math import ceil, cos, log2, radians
from pathlib import Path
from typing import Any

from app.models.analogue_v1 import (
    CandidateV3, CompareV3, DataRole, DistributionPair, ExplorerWindow, FamilyRecord, FeatureRecord, ProfileV3, ResultDetail, Scenario,
    SensitivityV3, SimpleResult, ToleranceRecord, WindowStats,
)
from app.services.analogue_math import competition_ranks, family_score, observed_index, similarity, w1_quantile_functions
from app.services.catalog_service import SITES, get_site
from app.services.evidence_v2_service import CONTEXT, _citations, load_thermal, thermal_audit
from app.services.geospatial_service import GEO_DATA, load_aoi, load_manifest

APP_DATA = Path(__file__).resolve().parents[1] / "data"
CONFIG: dict[str, Any] = json.loads((APP_DATA / "analogue.v1.json").read_text(encoding="utf-8"))
ROLES: dict[str, Any] = json.loads((APP_DATA / "data_roles.json").read_text(encoding="utf-8"))
REGISTRY: list[dict] = json.loads((APP_DATA / "datasets.json").read_text(encoding="utf-8"))
V5_DIR = GEO_DATA / "processed" / "terrain-v5"
CALIBRATION_PATH = GEO_DATA / "processed" / "evaluation" / "analogue-v1-calibration.json"
DISCRIMINATION_PATH = GEO_DATA / "processed" / "evaluation" / "analogue-v1-discrimination.json"
FAMILIES = list(CONFIG["families"])
PRIMARY = str(CONFIG["primary_scale_m"])
MIN_COVERAGE = float(CONFIG["minimum_feature_coverage"])
FEATURE_META = {
    "slope": ("Slope distribution", "degrees", "°", "Steepness of the ground between neighbouring 60 m cells"),
    "relative_elevation": ("Relative elevation distribution", "metres", " m", "Height of each cell above or below the window median (no absolute datums)"),
    "local_relief": ("Local relief (1 km neighbourhood)", "metres", " m", "Highest minus lowest point within 1 km of each cell"),
    "roughness": ("Roughness (300 m neighbourhood)", "metres", " m", "Standard deviation of elevation within 300 m of each cell"),
}
STATUS_TEXT = {
    "measured_comparable": "Measured on both bodies and comparable.",
    "measured_context_only": "Measured, but fails at least one comparability check; shown for interpretation only.",
    "source_available_unprocessed": "A suitable public product exists but has not been processed for this AOI.",
    "missing_earth": "No usable Earth measurement for this AOI.",
    "missing_planetary": "No usable measurement for the planetary reference AOI.",
    "incompatible": "Measurements exist but cannot be put on a common basis.",
    "review_pending": "Processed, awaiting scientific review.",
    "excluded": "Excluded by a documented data-quality rule.",
}


class AnalogueError(ValueError):
    pass


# ------------------------------------------------------------------ cached inputs

def _signature() -> tuple:
    paths = [*V5_DIR.glob("*.terrain-v5.json"), CALIBRATION_PATH, DISCRIMINATION_PATH, *(GEO_DATA / "processed" / "evidence").glob("*.json")]
    return tuple(sorted((p.name, p.stat().st_mtime_ns) for p in paths if p.exists()))


@lru_cache(maxsize=4)
def _calibration(_sig: tuple) -> dict:
    if not CALIBRATION_PATH.exists():
        raise AnalogueError("Calibration file missing; run app.scripts.analogue_v1_calibration")
    return json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))


def calibration() -> dict:
    return _calibration(_signature())


@lru_cache(maxsize=32)
def _artifact(site_id: str, _sig: tuple) -> dict | None:
    path = V5_DIR / f"{site_id}.terrain-v5.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def artifact(site_id: str) -> dict | None:
    return _artifact(site_id, _signature())


@lru_cache(maxsize=4)
def _discrimination(_sig: tuple) -> dict:
    return json.loads(DISCRIMINATION_PATH.read_text(encoding="utf-8")) if DISCRIMINATION_PATH.exists() else {}


def discrimination() -> dict:
    return _discrimination(_signature())


def reference_floor(ref_art: dict) -> dict[str, dict]:
    """Resolution floor of one reference: delta = sqrt(delta_place(ref)^2 + delta_dem^2), plus the 3x noise condition.

    delta_place(ref) is the largest W1 between the reference window and the same window moved 2 km N/S/E/W
    (stored in the reference terrain-v5 artifact); delta_dem is the frozen DEM-product floor. For Jezero this
    reproduces the published calibration values exactly.
    """
    cal = calibration()
    nominal = ref_art["scales"][PRIMARY]["features"]
    shifts = [w[PRIMARY]["features"] for k, w in ref_art.get("sensitivity_windows", {}).items() if k.endswith("_2km")]
    out = {}
    for f in FEATURE_META:
        dem = cal["resolution_floor"][f]["dem_product"] or 0.0
        if shifts:
            place = max(w1_quantile_functions(nominal[f]["quantiles"], w[f]["quantiles"]) for w in shifts)
            source = "this reference moved 2 km north, south, east and west"
        else:
            place = cal["resolution_floor"][f]["placement"]
            source = "Jezero placement test (no placement test stored for this reference)"
        combined = (place ** 2 + dem ** 2) ** 0.5
        tau = cal["tau"][f][PRIMARY]
        out[f] = {"placement": round(place, 4), "dem_product": round(dem, 4), "combined": round(combined, 4), "placement_source": source,
                  "noise_condition_passed": tau >= cal["rules"]["noise_factor"] * combined}
    return out


def scored_features() -> list[str]:
    return list(calibration()["redundancy"]["scored"])


def tolerances(reference_id: str = "mars-jezero") -> list[ToleranceRecord]:
    cal = calibration()
    art = artifact(reference_id)
    floor = reference_floor(art) if art else {f: {**cal["resolution_floor"][f], "noise_condition_passed": cal["tau"][f]["noise_condition"]["passed"]} for f in FEATURE_META}
    out = []
    for f in FEATURE_META:
        t, d = cal["tau"][f], floor[f]
        out.append(ToleranceRecord(feature=f, units=FEATURE_META[f][1], role="scored" if f in cal["redundancy"]["scored"] else "diagnostic",
                                   tau=t[PRIMARY], tau_by_scale={s: t[s] for s in ("60", "120", "240")}, leave_one_tile_out=t["leave_one_tile_out_60"],
                                   delta=d["combined"], delta_placement=d["placement"], delta_dem=d["dem_product"],
                                   noise_condition_passed=bool(d["noise_condition_passed"]), redundant_with=cal["redundancy"]["redundant_with"].get(f)))
    return out


def profile(profile_id: str) -> ProfileV3:
    spec = CONFIG["profiles"].get(profile_id)
    if not spec:
        raise AnalogueError(f"Unknown profile: {profile_id}")
    return ProfileV3(id=profile_id, **{k: spec[k] for k in ("label", "question", "rankable", "weights", "task_critical", "permitted_conclusion", "scope_line", "not_assessed")})


def profiles() -> list[ProfileV3]:
    return [profile(p) for p in CONFIG["profiles"]]


# ------------------------------------------------------------------ terrain family

def _stats(entry: dict) -> WindowStats:
    return WindowStats(median=entry.get("median"), p90=entry.get("p90"), coverage=entry.get("coverage", 0.0), valid_cells=entry.get("valid_cells", 0))


def terrain_features(ref: dict, cand: dict, scale: str = PRIMARY, tau_factor: float = 1.0,
                     weights: dict[str, float] | None = None, floor: dict | None = None) -> tuple[list[FeatureRecord], float | None, bool, str]:
    """Feature records, S_terrain, I_terrain and reason for two scale->features measurement sets.

    floor is the reference resolution floor (reference_floor); without it the frozen Jezero floor is used.
    S_terrain is computed from full-precision similarities; the records carry values rounded for display.
    """
    cal = calibration()
    floor = floor or {f: {"combined": cal["resolution_floor"][f]["combined"], "noise_condition_passed": cal["tau"][f]["noise_condition"]["passed"]} for f in FEATURE_META}
    full: dict[str, float] = {}
    scored = cal["redundancy"]["scored"]
    weights = weights or {f: 1.0 / len(scored) for f in scored}
    records: list[FeatureRecord] = []
    for f, (label, units, _, construct) in FEATURE_META.items():
        e = (cand.get(scale) or {}).get("features", {}).get(f)
        p = (ref.get(scale) or {}).get("features", {}).get(f)
        role = "scored" if f in scored else "diagnostic"
        tau_spec = cal["tau"][f]
        tau = tau_spec.get(scale) * tau_factor if tau_spec.get(scale) else None
        delta = floor[f]["combined"] if scale == PRIMARY else None
        rec = FeatureRecord(feature=f, label=label, units=units, role=role, measures=construct, eligible=False, reason="",
                            redundant_with=cal["redundancy"]["redundant_with"].get(f), tau=round(tau, 4) if tau else None,
                            delta=delta, weight=weights.get(f, 0.0) if role == "scored" else 0.0,
                            earth=_stats(e) if e else None, planet=_stats(p) if p else None)
        if not e or not p or not e.get("quantiles") or not p.get("quantiles"):
            rec.reason = "No measurement at this scale for one of the two windows."
        elif e["units"] != p["units"]:
            rec.reason = f"Units differ ({e['units']} vs {p['units']})."
        elif e["coverage"] < MIN_COVERAGE or p["coverage"] < MIN_COVERAGE:
            rec.reason = f"Valid-cell coverage below {MIN_COVERAGE:.0%} (Earth {e['coverage']:.1%}, reference {p['coverage']:.1%})."
        else:
            d = w1_quantile_functions(e["quantiles"], p["quantiles"])
            rec.distance = round(d, 4)
            rec.resolvable = (d > delta) if delta is not None else None
            if role == "diagnostic":
                rec.reason = f"Shown, not scored: it measures the same construct as {rec.redundant_with} (Spearman |rho| >= {cal['rules']['redundancy_rho']} across {cal['redundancy']['population_windows']} unselected windows)."
            elif not floor[f]["noise_condition_passed"]:
                rec.reason = (f"Tolerance ({tau:.2f}) is less than 3x the resolution floor of this reference ({floor[f]['combined']:.2f}): moving the reference window 2 km "
                              "changes this feature too much for a similarity to mean anything. Distance shown without a score.")
            else:
                rec.eligible = True
                rec.d_over_tau = round(d / tau, 4)
                full[f] = similarity(d, tau)
                rec.similarity = round(full[f], 6)
                rec.reason = "Measured on both windows with matching units, grid and coverage."
        records.append(rec)
    scored_records = {r.feature: (r.weight, full.get(r.feature), True) for r in records if r.role == "scored"}
    s_g = family_score(scored_records) if scored_records else None
    eligible = s_g is not None
    for r in records:
        if r.role == "scored" and r.similarity is not None:
            r.contribution = round(100 * r.weight * full[r.feature], 4)
    reason = ("Every scored feature (" + ", ".join(scored) + ") is measured and comparable." if eligible else
              "At least one required feature is not eligible: " + "; ".join(f"{r.label}: {r.reason}" for r in records if r.role == "scored" and not r.eligible))
    return records, s_g, eligible, reason


# ------------------------------------------------------------------ other families

def _context_family(family: str, candidate_id: str, weight: float, critical: bool, reference_body: str) -> FamilyRecord:
    label = CONFIG["families"][family]["label"]
    if family == "field_test_suitability":
        return FamilyRecord(family=family, label=label, weight=weight, eligible=False, status="missing_earth", task_critical=critical,
                            reason="Evidence record only (access, permits, safety, logistics, soil and rock properties, wheel-scale terrain). Never part of a planetary-science index.")
    spec = CONTEXT["pair_status"][family]
    record = spec.get(candidate_id) or spec["default"]
    status = record["status"]
    if reference_body == "moon" and status not in {"missing_earth"}:
        status = "missing_planetary"
    return FamilyRecord(family=family, label=label, weight=weight, eligible=False, status=status, task_critical=critical, reason=STATUS_TEXT[status],
                        context={"earth": record.get("earth"), "planetary": record.get("planetary"),
                                 "sources": [c.model_dump() for c in _citations(record.get("source_ids"))]})


def _temperature_family(reference_id: str, candidate_id: str, weight: float, critical: bool) -> FamilyRecord:
    label = CONFIG["families"]["temperature"]["label"]
    ref, cand = load_thermal(reference_id), load_thermal(candidate_id)
    audit = thermal_audit(ref, cand)
    if audit.decision == "missing":
        return FamilyRecord(family="temperature", label=label, weight=weight, eligible=False, task_critical=critical,
                            status="missing_planetary" if not ref else "missing_earth", reason=audit.summary)
    return FamilyRecord(family="temperature", label=label, weight=weight, eligible=False, task_critical=critical, status=audit.decision,
                        reason=audit.summary, context={"audit": audit.model_dump(),
                                                       "sources": [c.model_dump() for c in _citations(["modis-myd11a2", "meda-pds", "m20-waypoints"])]})


# ------------------------------------------------------------------ helpers

def _measure_sets(art: dict) -> dict:
    return art["scales"]


def _sensitivity_sets(art: dict) -> dict:
    return art.get("sensitivity_windows", {})


def _eligibility_key(reference_id: str, prof: ProfileV3, included: list[str], dem: str) -> str:
    cal = calibration()
    data = {"reference_aoi": get_site(reference_id).aoi_id, "method": CONFIG["method_version"], "profile": prof.id, "weights": prof.weights,
            "included": included, "scored": cal["redundancy"]["scored"], "tau": {f: cal["tau"][f][PRIMARY] for f in cal["redundancy"]["scored"]},
            "scale": PRIMARY, "dem": dem, "mask": "worldcover-v200 built-up >= 50 %"}
    return sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


def _dem_label(site) -> str:
    try:
        m = load_manifest(site.source_id)
        return f"{m.product_name}.{m.product_version}"
    except Exception:
        return "unknown"


def _fmt(value: float | None, unit: str) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}{unit}" if unit == "°" else f"{value:.1f}{unit}"


def _roles(prof: ProfileV3, reference_body: str, reference_id: str = "mars-jezero") -> list[str]:
    planetary = "lola" if reference_body == "moon" else ("ctx-dem" if reference_id == "mars-jezero" else "ctx-dtm-controlled")
    roles = ["srtmgl1", planetary, "dem-alternatives", "worldcover", "sentinel2", "viirs"]
    if "temperature" in prof.weights:
        roles += ["modis-lst", "meda"]
    return roles + ["literature", "globes"]


# ------------------------------------------------------------------ comparison

def compare(reference_id: str, profile_id: str, candidate_ids: list[str] | None = None) -> CompareV3:
    return _compare_cached(reference_id, profile_id, tuple(candidate_ids or ()), _signature())


@lru_cache(maxsize=64)
def _compare_cached(reference_id: str, profile_id: str, candidate_ids: tuple[str, ...], _sig: tuple) -> CompareV3:
    ref_site = get_site(reference_id)
    ref_art = artifact(reference_id)
    if not ref_site or ref_site.body.value not in {"mars", "moon"} or not ref_art:
        raise AnalogueError("The reference must be a processed Mars or Moon AOI with a terrain-v5 artifact")
    prof = profile(profile_id)
    cal = calibration()
    body = ref_site.body.value
    ids = candidate_ids or tuple(s.id for s in SITES if s.body.value == "earth")
    floor = reference_floor(ref_art)
    background = _background(ref_art, floor)
    results: list[CandidateV3] = []
    scenario_values: dict[str, list[tuple[Scenario, float | None]]] = {}
    nominal: dict[str, float] = {}
    terrain_cache: dict[str, tuple] = {}

    for cid in ids:
        site = get_site(cid)
        if not site or site.body.value != "earth":
            raise KeyError(cid)
        art = artifact(cid)
        exclusion = CONFIG["aoi_exclusions"].get(cid)
        families: list[FamilyRecord] = []
        terrain_s = None
        for fam in FAMILIES:
            w = prof.weights.get(fam, 0.0)
            critical = fam in prof.task_critical
            if w == 0 and not critical:
                continue
            if fam == "terrain":
                if not art:
                    families.append(FamilyRecord(family="terrain", label=CONFIG["families"]["terrain"]["label"], weight=w, eligible=False, status="missing_earth",
                                                 task_critical=critical, reason="No terrain-v5 measurement for this Earth window (not processed)."))
                    continue
                feats, s_g, ok, reason = terrain_features(_measure_sets(ref_art), _measure_sets(art), floor=floor)
                terrain_cache[cid] = (feats, s_g, ok)
                noise_failed = any(r.role == "scored" and r.distance is not None and not floor[r.feature]["noise_condition_passed"] for r in feats)
                status = "measured_comparable" if ok else ("measured_context_only" if noise_failed else "incompatible")
                if exclusion:
                    ok, status, reason = False, "excluded", exclusion["reason"]
                terrain_s = s_g if ok else None
                families.append(FamilyRecord(family="terrain", label=CONFIG["families"]["terrain"]["label"], weight=w, eligible=ok and w > 0,
                                             status=status, reason=reason, score=round(s_g, 6) if ok and s_g is not None else None, task_critical=critical, features=feats))
            elif fam == "temperature":
                families.append(_temperature_family(reference_id, cid, w, critical))
            else:
                families.append(_context_family(fam, cid, w, critical, body))
        planned = {f.family: (f.weight, f.eligible, terrain_s if f.family == "terrain" else f.score) for f in families if f.weight > 0}
        index, coverage = observed_index(planned) if planned else (None, 0.0)
        gates = {f.family: f.eligible or (f.family == "terrain" and f.status == "measured_comparable" and f.weight == 0) for f in families if f.task_critical}
        included = [f.family for f in families if f.eligible]
        if exclusion:
            state = "excluded"
        elif not art:
            state = "not_measured"
        elif not included:
            state = "not_assessed"
        else:
            state = "partial"
        feats = terrain_cache.get(cid, ([], None, False))[0]
        scored = [r for r in feats if r.role == "scored" and r.distance is not None]
        resolution = "not_applicable"
        if scored and not exclusion:
            resolution = "unresolved_from_reference" if all(r.distance <= (r.delta or 0) for r in scored) else "resolved"
        cand = CandidateV3(
            site_id=cid, site_name=site.name, state=state, observed_index=round(index, 2) if index is not None else None,
            evidence_coverage=round(coverage, 4), resolution=resolution, critical_gates=gates, families=families,
            eligibility_key=_eligibility_key(reference_id, prof, included, _dem_label(site)) if included else None,
            simple=SimpleResult(conclusion="", measured=[], coverage_text="", validation_status=CONFIG["validation_status"], strength=None, mismatch=None,
                                limitation=prof.scope_line, show_index=False, index_label=None, background_text=None),
            exclusion={**exclusion, "replacement_name": get_site(exclusion["replacement"]).name if get_site(exclusion["replacement"]) else None} if exclusion else None,
            literature_context=_literature(cid), data_roles=_roles(prof, body, reference_id),
            background_share=_share_at_or_above(background, terrain_s) if terrain_s is not None and background else None)
        results.append(cand)
        if terrain_s is not None and index is not None:
            nominal[cid] = index
            scenario_values[cid] = _scenarios(reference_id, ref_art, art, prof, families, floor)

    # Profile state ------------------------------------------------------------------------------------
    eligible = [r for r in results if r.observed_index is not None]
    keys = {r.eligibility_key for r in eligible}
    all_critical = bool(eligible) and all(all(r.critical_gates.values()) for r in eligible)
    if prof.rankable and all_critical and len(keys) == 1:
        state, reason = "ranked", "Every task-critical family is measured and comparable for every listed candidate, on one shared eligibility key."
    elif eligible:
        missing = sorted({f for r in results for f, ok in r.critical_gates.items() if not ok}, key=FAMILIES.index)
        state = "partial"
        reason = ("Task-critical evidence is missing: " + "; ".join(CONFIG["families"][f]["label"] for f in missing)
                  + ". Measured families are shown as partial evidence, without ranks or a task conclusion.")
    else:
        state, reason = "not_assessed", "No family of this profile is measured and comparable for any candidate, so no index is shown."
    if state == "partial" and not any(r.critical_gates.get(f, False) for r in eligible for f in prof.task_critical):
        state, reason = "not_assessed", "None of this profile's task-critical families has comparable evidence. Measured families are listed only as context."

    # Sensitivity, ranks and ties --------------------------------------------------------------------------
    order = sorted(nominal, key=lambda s: (-nominal[s], s))
    per_scenario: dict[str, dict[str, float]] = {}
    for cid, items in scenario_values.items():
        for sc, value in items:
            if value is not None:
                per_scenario.setdefault(sc.id, {})[cid] = value
    for sid, values in per_scenario.items():
        ranked = sorted(values, key=lambda s: (-values[s], s))
        for pos, cid in enumerate(ranked, 1):
            next(sc for sc, _ in scenario_values[cid] if sc.id == sid).rank = pos
    intervals = {}
    for cid in order:
        vals = [v for _, v in scenario_values[cid] if v is not None]
        intervals[cid] = (min(vals), max(vals))
    groups: list[list[str]] = []
    low = None
    for cid in order:
        lo, hi = intervals[cid]
        if groups and hi >= low:
            groups[-1].append(cid)
            low = min(low, lo)
        else:
            groups.append([cid])
            low = lo
    ranks = competition_ranks(groups) if state == "ranked" else {}
    for r in results:
        if r.site_id in scenario_values:
            scen = [sc for sc, _ in scenario_values[r.site_id]]
            vals = [v for _, v in scenario_values[r.site_id] if v is not None]
            rk = [sc.rank for sc in scen if sc.rank is not None]
            r.sensitivity = SensitivityV3(scenarios=scen, index_range=[round(min(vals), 2), round(max(vals), 2)], rank_range=[min(rk), max(rk)] if rk else None,
                                          tie_group=next(i for i, g in enumerate(groups, 1) if r.site_id in g),
                                          notice="Scenario sensitivity (AOI placement, reference placement, DEM product, grid scale, tolerance and weights). Not a confidence interval.")
        if state == "ranked" and r.site_id in ranks:
            r.state, r.rank = "ranked", ranks[r.site_id]
        if state == "not_assessed" and r.state == "partial":
            r.state = "not_assessed"
            r.observed_index = None
        r.simple = _simple(r, prof, ref_site.name, body, state, groups if state == "ranked" else [], terrain_cache.get(r.site_id, ([], None, False))[0],
                           len(background) if background else 0)

    def sort_key(r: CandidateV3):
        st = {"ranked": 0, "partial": 1, "not_assessed": 2, "excluded": 3, "not_measured": 4}[r.state]
        if prof.rankable:
            return (st, -(r.observed_index or -1), r.site_name)
        return (st, r.site_name)
    results.sort(key=sort_key)
    base = _summary(background) if background else None
    return CompareV3(
        method_version=CONFIG["method_version"], terrain_method=CONFIG["terrain_method"], status=CONFIG["status"], review_status=CONFIG["review_status"],
        comparison_definition=CONFIG["comparison_definition"], reference_site_id=reference_id, reference_name=ref_site.name, reference_aoi_id=ref_site.aoi_id,
        reference_body=body, profile=prof, profile_state=state, profile_state_reason=reason, headline=_headline(prof, state, results),
        evidence_coverage=max((r.evidence_coverage for r in results), default=0.0), primary_scale_m=int(PRIMARY), tolerances=tolerances(reference_id),
        base_rate=base, tie_groups=groups if state == "ranked" else [], ordering_note=_ordering_note(state, groups if state == "ranked" else [], base, body),
        results=results, physical_limits=CONFIG["physical_limits"][body], formulas=CONFIG["formulas"], parameters=CONFIG["parameters"],
        validation_status=CONFIG["validation_status"], notice=CONFIG["notice"], generated_at=datetime.now(timezone.utc),
        discrimination=_discrimination_summary(reference_id, base), resolution_floor=floor)


POPULATION_PATH = GEO_DATA / "processed" / "evaluation" / "analogue-v1-population.json"


@lru_cache(maxsize=2)
def _population(_sig: tuple) -> dict:
    return json.loads(POPULATION_PATH.read_text(encoding="utf-8"))["windows"] if POPULATION_PATH.exists() else {}


def _background(ref_art: dict, floor: dict) -> list[float]:
    """Terrain family score (x100) of every unselected Earth window against this reference; empty if ineligible."""
    out = []
    ref60 = {PRIMARY: ref_art["scales"][PRIMARY]}
    for window in _population(_signature()).values():
        _, s_g, ok, _ = terrain_features(ref60, {PRIMARY: {"features": {f: {**v, "units": FEATURE_META[f][1], "valid_cells": 0} for f, v in window[PRIMARY]["features"].items()}}}, floor=floor)
        if ok and s_g is not None:
            out.append(100 * s_g)
    return out


def _share_at_or_above(values: list[float], s_g: float) -> float:
    return round(sum(1 for v in values if v >= 100 * s_g - 1e-9) / len(values), 3)


def _summary(values: list[float]) -> dict:
    import numpy as np
    v = np.asarray(values)
    return {"count": int(v.size), "median_index": round(float(np.median(v)), 2), "p10": round(float(np.percentile(v, 10)), 2), "p90": round(float(np.percentile(v, 90)), 2),
            "share_at_or_above": {str(t): round(float(np.mean(v >= t)), 3) for t in (99, 95, 90, 75, 50)}}


def _discrimination_summary(reference_id: str, base: dict | None) -> dict | None:
    disc = discrimination()
    ref = disc.get("references", {}).get(reference_id)
    if not ref:
        return None
    loro = ref.get("leave_one_region_out", {})
    taus = {f: [v["tau"][f] for v in loro.values()] for f in scored_features()} if loro else {}
    orders = [tuple(v["candidate_order"][:5]) for v in loro.values()]
    return {"background": base, "single_feature": {f: v.get("share_at_or_above") for f, v in ref["single_feature"].items()},
            "alternative_tolerances": {k: v["background"].get("share_at_or_above") for k, v in ref["alternative_tolerances"].items()},
            "leave_one_region_out_tau": {f: [round(min(v), 3), round(max(v), 3)] for f, v in taus.items()},
            "top_five_order_stable_across_regions": len(set(orders)) == 1 if orders else None,
            "population": disc.get("population"), "notice": disc.get("notice"),
            "interpretation": ("At a 60 m grid the index separates low-relief from rugged terrain well, but many unselected low-relief Earth windows also score highly. "
                               "Read a candidate's background share (the fraction of unselected windows that score at least as high) before reading its index.")}


def _profile_index(families: list[FamilyRecord], terrain_score: float | None) -> float | None:
    planned = {f.family: (f.weight, f.eligible, terrain_score if f.family == "terrain" else f.score) for f in families if f.weight > 0}
    if terrain_score is None:
        return None
    index, _ = observed_index(planned)
    return index


def _scenarios(reference_id: str, ref_art: dict, art: dict, prof: ProfileV3, families: list[FamilyRecord], floor: dict) -> list[tuple[Scenario, float | None]]:
    def run(ref_sets, cand_sets, scale=PRIMARY, tau_factor=1.0, weights=None) -> float | None:
        _, s_g, ok, _ = terrain_features(ref_sets, cand_sets, scale, tau_factor, weights, floor)
        return _profile_index(families, s_g if ok else None)

    out: list[tuple[Scenario, float | None]] = []
    base_ref, base_cand = _measure_sets(ref_art), _measure_sets(art)
    out.append((Scenario(id="nominal", kind="nominal", label="Nominal (60 m, SRTM, registered windows)", index=None), run(base_ref, base_cand)))
    for label, sets in _sensitivity_sets(art).items():
        if label.endswith("_2km"):
            out.append((Scenario(id=f"site_{label}", kind="placement", label=f"Earth window moved 2 km {label.split('_')[0]}", index=None), run(base_ref, sets)))
    for label, sets in _sensitivity_sets(ref_art).items():
        out.append((Scenario(id=f"ref_{label}", kind="reference_placement", label=f"Reference window moved 2 km {label.split('_')[0]}", index=None), run(sets, base_cand)))
    for label, sets in _sensitivity_sets(art).items():
        if label.startswith("dem_"):
            out.append((Scenario(id=label, kind="dem", label=f"Earth DEM: {sets.get('product', label)}", index=None), run(base_ref, {k: v for k, v in sets.items() if k.isdigit()})))
    for scale in CONFIG["sensitivity_scales_m"]:
        out.append((Scenario(id=f"scale_{scale}", kind="scale", label=f"{scale} m grid (tolerance at that grid)", index=None), run(base_ref, base_cand, str(scale))))
    for factor in (0.75, 1.25):
        out.append((Scenario(id=f"tau_x{factor}", kind="tolerance", label=f"All tolerances x{factor}", index=None), run(base_ref, base_cand, tau_factor=factor)))
    scored = scored_features()
    if len(scored) == 2:
        for w in (0.25, 0.75):
            weights = {scored[0]: w, scored[1]: 1 - w}
            out.append((Scenario(id=f"weights_{scored[0]}_{w}", kind="weights", label=f"{FEATURE_META[scored[0]][0]} weight {w}, {FEATURE_META[scored[1]][0].lower()} {1 - w}", index=None),
                        run(base_ref, base_cand, weights=weights)))
    for sc, value in out:
        sc.index = round(value, 2) if value is not None else None
    return out


def _literature(site_id: str) -> dict | None:
    rc = CONTEXT["research_context"].get(site_id)
    if not rc:
        return None
    return {**rc, "sources": [c.model_dump() for c in _citations(rc.get("source_ids"))],
            "scope": "Regional research context. It is not a measurement of this 10 km window and never enters a number."}


def _terrain_sentence(feats: list[FeatureRecord], site_name: str, ref_name: str) -> tuple[str, str | None, str | None]:
    scored = [r for r in feats if r.role == "scored" and r.distance is not None]
    if not scored:
        return "Terrain could not be compared for this window.", None, None
    unit = {f: FEATURE_META[f][2] for f in FEATURE_META}
    unresolved = all(r.distance <= (r.delta or 0) for r in scored)
    if unresolved:
        sentence = (f"On the measured 10 km terrain features at a 60 m grid, the {site_name} window is not resolved from the {ref_name} window by these tests: "
                    "every scored difference is at or below the resolution floor set by moving the reference 2 km and swapping the Earth DEM product.")
    else:
        closer = [r for r in scored if r.d_over_tau is not None and r.d_over_tau < 1]
        further = [r for r in scored if r.d_over_tau is not None and r.d_over_tau >= 1]
        if scored and len(closer) == len(scored):
            sentence = (f"On the measured 10 km terrain features at a 60 m grid, the {site_name} window is closer to the {ref_name} window than a typical pair "
                        "of Earth land windows are to each other, on every scored feature.")
        elif further and len(further) == len(scored):
            sentence = (f"On the measured 10 km terrain features at a 60 m grid, the {site_name} window differs from the {ref_name} window by more than a typical "
                        "pair of Earth land windows, on every scored feature.")
        else:
            sentence = (f"On the measured terrain, the {site_name} window is close to the {ref_name} window in "
                        + ", ".join(r.label.lower() for r in closer) + " but differs in " + ", ".join(r.label.lower() for r in further) + ".")
    best = min(scored, key=lambda r: (r.d_over_tau if r.d_over_tau is not None else 9e9))
    worst = max(scored, key=lambda r: (r.d_over_tau if r.d_over_tau is not None else -1))
    def describe(r: FeatureRecord) -> str:
        bits = f"{r.label}: differs by {_fmt(r.distance, unit[r.feature])}"
        if r.tau and r.d_over_tau is not None:
            bits += f" ({r.d_over_tau:.2f} of the {_fmt(r.tau, unit[r.feature])} tolerance"
            bits += ", within the resolution floor)" if r.resolvable is False else ")"
        return bits
    return sentence, describe(best), describe(worst) if worst is not best else None


def _simple(r: CandidateV3, prof: ProfileV3, ref_name: str, body: str, state: str, groups: list[list[str]], feats: list[FeatureRecord], n_background: int = 0) -> SimpleResult:
    measured = [f.label for f in r.families if f.eligible]
    context_only = [f.label for f in r.families if f.status == "measured_context_only"]
    coverage = f"{r.evidence_coverage:.0%} of the planned {prof.label} evidence is measured and comparable"
    if context_only:
        coverage += f"; {', '.join(context_only)} is measured but shown as context only"
    if r.state == "excluded":
        return SimpleResult(conclusion=f"Excluded from this method. {r.exclusion['reason']}", measured=[], coverage_text="Not scored.",
                            validation_status=CONFIG["validation_status"], strength=None, mismatch=None,
                            limitation=f"Historical scores for this window remain available under terrain-v4.0. Use {r.exclusion.get('replacement_name') or 'the replacement window'} instead.",
                            show_index=False, index_label=None, background_text=None)
    if r.state == "not_measured":
        return SimpleResult(conclusion="This site has not been measured, so nothing can be compared yet.", measured=[], coverage_text="0 % measured.",
                            validation_status=CONFIG["validation_status"], strength=None, mismatch=None, limitation=prof.scope_line, show_index=False, index_label=None, background_text=None)
    sentence, strength, mismatch = _terrain_sentence(feats, r.site_name, ref_name)
    terrain = next((f for f in r.families if f.family == "terrain"), None)
    background = (f"{r.background_share:.0%} of {n_background} unselected Earth land windows score at least as high against {ref_name}; "
                  "a high value mostly indicates low relief.") if r.background_share is not None and n_background else None
    if terrain is not None and terrain.status == "measured_context_only":
        scored = [x for x in feats if x.role == "scored" and x.distance is not None]
        unit = {f: FEATURE_META[f][2] for f in FEATURE_META}
        dists = "; ".join(f"{x.label.lower()} differs by {_fmt(x.distance, unit[x.feature])}" for x in scored)
        return SimpleResult(
            conclusion=(f"Distances are measured ({dists}), but no index is given: moving the {ref_name} window by 2 km changes these features by more than a third of "
                        "the tolerance, so a similarity value would mostly reflect where the reference window happens to sit." + (" This lunar comparison is terrain only; illumination and regolith are not assessed." if body == "moon" else "")),
            measured=[], coverage_text="0% of the planned evidence is comparable; terrain is shown as context only.", validation_status=CONFIG["validation_status_short"],
            strength=None, mismatch=None, limitation=prof.scope_line, show_index=False, index_label=None, background_text=None)
    group = next((g for g in groups if r.site_id in g), None)
    tie = ""
    if group and len(group) > 1:
        others = len(group) - 1
        tie = f" Its order relative to the other {others} site{'s' if others != 1 else ''} in its tie group is not resolved by the data."
    lunar = " This is a limited lunar terrain comparison; illumination and regolith are not assessed." if body == "moon" else ""
    background_note = ""
    show, label = False, None
    if prof.id == "terrain_analogy":
        conclusion = sentence + tie + lunar + " " + prof.scope_line
        if r.observed_index is not None:
            show, label = True, "Experimental terrain evidence index (0–100; not a probability or a percentage likeness)"
    elif prof.id == "balanced_science":
        conclusion = (f"Terrain evidence available; {r.evidence_coverage:.0%} of planned science evidence measured. " + sentence +
                      " No Balanced science result or ranking is given until geology is measured comparably.")
        label = f"Terrain-only partial index ({r.evidence_coverage:.0%} of the plan), not a Balanced science result"
    elif prof.id == "rover_mobility":
        conclusion = ("Broad terrain context only (60 m grid). " + sentence +
                      " Wheel-scale traversability, rock hazards and soil bearing strength have not been observed, so no rover-mobility conclusion is possible.")
        label = "Terrain-only partial index; not a mobility rating"
    elif prof.id == "biosignature_fieldwork":
        conclusion = ("Not assessed: there is no evidence for this window's minerals, depositional process or preservation and sampling conditions. "
                      "Research elsewhere in the region is context only. No claim is made that life has been observed on Mars.")
        strength, mismatch = None, None
    else:
        temp = next((f for f in r.families if f.family == "temperature"), None)
        thermal = (" Thermal data exist but fail the comparability audit." if temp is not None and temp.status == "measured_context_only"
                   else " No comparable thermal record exists for this reference.")
        conclusion = ("Comparable terrain only. " + sentence + thermal +
                      " Access, logistics, construction, pressure, gravity and radiation are not assessed; this is not base or landing-site suitability.")
        label = "Terrain-only partial index; not a field-test or base rating"
    if state == "not_assessed":
        show, label = False, None
    return SimpleResult(conclusion=conclusion.strip(), measured=measured, coverage_text=coverage + ".", validation_status=CONFIG["validation_status_short"],
                        strength=strength, mismatch=mismatch, limitation=prof.scope_line, show_index=show, index_label=label,
                        background_text=background if prof.id == "terrain_analogy" and state != "not_assessed" else None)


def _headline(prof: ProfileV3, state: str, results: list[CandidateV3]) -> str:
    coverage = max((r.evidence_coverage for r in results if r.state in {"ranked", "partial"}), default=0.0)
    if state == "ranked":
        return "Ranked on measured terrain only, with ties where the data cannot separate sites."
    if state == "partial":
        return f"Terrain evidence available; {coverage:.0%} of planned {prof.label.lower()} evidence measured. No overall result or ranking."
    return f"{prof.label}: not assessed. The task-critical evidence does not exist for these windows."


def _ordering_note(state: str, groups: list[list[str]], base: dict | None, body: str) -> str:
    if state == "not_assessed":
        return "This profile cannot be assessed with the evidence that exists today."
    parts = []
    named = [[get_site(s).name for s in g] for g in groups if len(g) > 1]
    if named:
        parts.append("Tie groups (order inside a group is not resolved): " + " | ".join(", ".join(g) for g in named) + ".")
    if state == "partial":
        parts.insert(0, "Partial evidence: listed alphabetically for exploration, not ranked.")
    if body == "moon":
        parts.append("Limited lunar terrain comparison: one window, no placement or illumination checks.")
    return " ".join(parts)


# ------------------------------------------------------------------ single result, data roles, explorer

def _downsample(q: list[float], n: int = 49) -> tuple[list[float], list[float]]:
    total = len(q)
    idx = [min(total - 1, round((k + 1) / (n + 1) * total - 0.5)) for k in range(n)]
    return [round((i + 0.5) / total, 4) for i in idx], [q[i] for i in idx]


def _window(site, art: dict | None) -> dict:
    aoi = load_aoi(site.aoi_id)
    out = {"site_id": site.id, "name": site.name, "body": site.body.value, "aoi_id": site.aoi_id, "center": [aoi.center_longitude, aoi.center_latitude],
           "width_m": aoi.width_m, "height_m": aoi.height_m, "selection_rationale": aoi.selection_rationale}
    if art:
        out.update({"source_id": art["source_id"], "source_file": art["source_file"], "source_sha256": art["source_sha256"], "exclusion": art.get("exclusion"),
                    "coverage_60m": {f: v["coverage"] for f, v in art["scales"][PRIMARY]["features"].items()},
                    "excluded_fraction_60m": art["scales"][PRIMARY].get("excluded_fraction")})
    try:
        m = load_manifest(site.source_id)
        out["dem"] = {"product": m.product_name, "version": m.product_version, "doi": m.doi, "provider": m.provider, "native_resolution": m.native_resolution,
                      "native_crs": (m.native_crs or "")[:80], "access_date": m.access_date, "citation": m.citation_text}
    except Exception:
        out["dem"] = None
    return out


def result_detail(reference_id: str, profile_id: str, site_id: str) -> ResultDetail:
    comp = compare(reference_id, profile_id)
    cand = next((r for r in comp.results if r.site_id == site_id), None)
    if cand is None:
        raise KeyError(site_id)
    ref_art, art = artifact(reference_id), artifact(site_id)
    dists = []
    if ref_art and art:
        for f, (label, units, _, _) in FEATURE_META.items():
            u, e = _downsample(art["scales"][PRIMARY]["features"][f]["quantiles"])
            _, p = _downsample(ref_art["scales"][PRIMARY]["features"][f]["quantiles"])
            dists.append(DistributionPair(feature=f, units=units, u=u, earth=e, planet=p))
    cal = calibration()
    sources = []
    lookup = {r["dataset_id"]: r for r in REGISTRY}
    for role_id in cand.data_roles:
        role = next(x for x in ROLES["roles"] if x["id"] == role_id)
        reg = lookup.get(role.get("registry_id") or "")
        sources.append({"role": role_id, "label": role["label"], "product": role["product"], "url": role.get("source_url") or (reg or {}).get("official_landing_page")})
    comparison = comp.model_dump(mode="json", exclude={"results"})
    return ResultDetail(
        comparison=comparison, candidate=cand, distributions=dists, earth_window=_window(get_site(site_id), art), reference_window=_window(get_site(reference_id), ref_art),
        sources=sources,
        calibration={k: cal[k] for k in ("rules", "resolution_floor", "redundancy", "synthetic_negatives", "base_rate", "notice")},
        reproducibility={"method_config": "backend/app/data/analogue.v1.json", "calibration_file": "backend/data/processed/evaluation/analogue-v1-calibration.json",
                         "terrain_artifacts": [f"backend/data/processed/terrain-v5/{reference_id}.terrain-v5.json", f"backend/data/processed/terrain-v5/{site_id}.terrain-v5.json"],
                         "recompute": "cd backend && python -m app.scripts.analogue_v1_calibration", "generated_at": comp.generated_at.isoformat()})


def data_roles() -> list[DataRole]:
    lookup = {r["dataset_id"]: r for r in REGISTRY}
    out = []
    for role in ROLES["roles"]:
        reg = lookup.get(role.get("registry_id") or "")
        out.append(DataRole(**{**role, "source_url": role.get("source_url") or (reg or {}).get("official_landing_page")}))
    return out


def _corners(site, extent_m: float) -> list[list[float]]:
    from rasterio.crs import CRS
    from rasterio.warp import transform
    from app.services.geospatial_service import _analysis_crs, _center_in_crs
    aoi = load_aoi(site.aoi_id)
    crs = _analysis_crs(CRS.from_epsg(4326), "earth", aoi.center_longitude, aoi.center_latitude)
    cx, cy = _center_in_crs(crs, "earth", aoi.center_longitude, aoi.center_latitude)
    h = extent_m / 2
    xs, ys = [cx - h, cx + h, cx + h, cx - h], [cy + h, cy + h, cy - h, cy - h]
    lons, lats = transform(crs, CRS.from_epsg(4326), xs, ys)
    return [[round(lo, 6), round(la, 6)] for lo, la in zip(lons, lats)]


def explorer(site_id: str) -> ExplorerWindow:
    from app.services.imagery_service import list_site_imagery
    site = get_site(site_id)
    if not site or site.body.value != "earth" or not site.aoi_id:
        raise KeyError(site_id)
    aoi = load_aoi(site.aoi_id)
    records = list_site_imagery(site_id)
    detailed = next((r for r in records if r.mode == "reference" and r.data_status == "available" and r.preview_url), None)
    recent = next((r for r in records if r.mode == "latest_observation" and r.tile_url), None)
    imagery = None
    if detailed:
        px = 1000 if detailed.display_resolution_m in (None, 10, 10.0) else round(10_000 / detailed.display_resolution_m)
        imagery = {"url": detailed.preview_url, "corners": _corners(site, px * (detailed.display_resolution_m or 10.0)), "resolution_m": detailed.resolution_m,
                   "product_id": detailed.product_id, "acquired": detailed.acquisition_datetime.isoformat() if detailed.acquisition_datetime else None,
                   "attribution": detailed.attribution, "source_url": detailed.official_source_url}
    layers_path = GEO_DATA / "processed" / "terrain-preview" / f"{site_id}.layers.json"
    hill = slope = None
    if layers_path.exists():
        lay = json.loads(layers_path.read_text(encoding="utf-8"))
        corners = _corners(site, lay["pixels"] * lay["resolution_m"])
        hill = {"url": f"/api/sites/{site_id}/terrain/layers/hillshade.png", "corners": corners, "resolution_m": lay["resolution_m"],
                "source": "Same SRTMGL1.003 DEM as the terrain measurement", "light": "315 deg azimuth, 45 deg altitude"}
        slope = {"url": f"/api/sites/{site_id}/terrain/layers/slope.png", "corners": corners, "resolution_m": lay["resolution_m"], "ramp": lay["slope_ramp"]}
    rec = None
    if recent:
        rec = {"tile_url": recent.tile_url, "resolution_m": recent.resolution_m, "observed": recent.acquisition_datetime.isoformat() if recent.acquisition_datetime else None,
               "attribution": recent.attribution, "product_id": recent.product_id}
    lat = aoi.center_latitude
    native = log2(156_543.03 * cos(radians(lat)) / 10.0)
    return ExplorerWindow(site_id=site_id, name=site.name, center=[aoi.center_longitude, lat], aoi_corners=_corners(site, aoi.width_m),
                          imagery=imagery, hillshade=hill, slope=slope, recent=rec, max_native_zoom=round(native, 2),
                          notes=["The 10 m image covers only the study window; outside it the map shows coarser global imagery.",
                                 f"Zoom stops at about {native + 0.5:.1f}, half a level past the 10 m image's native detail, so no extra detail is implied.",
                                 "Images are dated acquisitions, not live views."])


# ------------------------------------------------------------------ reference catalogue

def references() -> list[dict]:
    """Every processed Mars or Moon reference with provenance, imagery, quality and its own resolution floor."""
    reg_path = GEO_DATA / "processed" / "evaluation" / "mars-reference-registration.json"
    registration = json.loads(reg_path.read_text(encoding="utf-8")) if reg_path.exists() else {"results": [], "context": {}}
    by_reg = {r["id"]: r for r in registration.get("results", [])}
    out = []
    for site in SITES:
        if site.body.value not in {"mars", "moon"} or site.data_status.value != "real_processed":
            continue
        art = artifact(site.id)
        if not art:
            continue
        aoi = load_aoi(site.aoi_id)
        manifest = load_manifest(site.source_id)
        floor = reference_floor(art)
        scored = scored_features()
        imagery_json = GEO_DATA / "processed" / "imagery" / f"{site.id}-ctx-reference.json"
        imagery = json.loads(imagery_json.read_text(encoding="utf-8")) if imagery_json.exists() else None
        reg = by_reg.get(site.id, {})
        out.append({
            "id": site.id, "name": site.name, "body": site.body.value, "region": site.country_or_region, "center": [aoi.center_longitude, aoi.center_latitude],
            "width_m": aoi.width_m, "description": site.short_description, "characteristics": site.relevant_characteristics, "limitations": site.known_limitations,
            "selection_rationale": aoi.selection_rationale, "context": registration.get("context", {}).get(site.id),
            "dem": {"product": manifest.product_name, "item": manifest.product_version, "doi": manifest.doi, "provider": manifest.provider, "source_page": manifest.source_page_url,
                    "native_resolution": manifest.native_resolution, "sha256": manifest.extracted_sha256_checksum or manifest.sha256_checksum, "licence": manifest.license_or_use_constraints,
                    "intersection_error": reg.get("intersection_error")},
            "imagery": {"url": imagery["preview_url"], "product_id": imagery.get("product_id"), "resolution_m": imagery.get("resolution_m"), "attribution": imagery.get("attribution"),
                        "source_url": imagery.get("official_source_url"), "published": imagery.get("publication_datetime")} if imagery else None,
            "hillshade_url": f"/api/sites/{site.id}/terrain/layers/hillshade.png", "slope_url": f"/api/sites/{site.id}/terrain/layers/slope.png",
            "slope_median_60m": art["scales"][PRIMARY]["features"]["slope"]["median"],
            "relative_elevation_p10_p90_60m": [art["scales"][PRIMARY]["features"]["relative_elevation"]["quantiles"][50], art["scales"][PRIMARY]["features"]["relative_elevation"]["quantiles"][449]],
            "resolution_floor": {f: floor[f] for f in scored}, "scorable": all(floor[f]["noise_condition_passed"] for f in scored),
            "scorable_reason": None if all(floor[f]["noise_condition_passed"] for f in scored) else
                "Moving this reference window by 2 km changes the scored terrain features by more than a third of the tolerance, so terrain distances are shown without an index.",
        })
    return out
