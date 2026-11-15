"""analogue-method-v1.0: reference windows, per-reference resolution floors and the discrimination analysis.

Frozen inputs (never recomputed here): tau_k, the redundancy decision and the DEM-product part of the resolution
floor, all from data/processed/evaluation/analogue-v1-calibration.json.

1. Every processed Mars or Moon reference is measured (terrain-v5 quantiles) with the window moved 2 km N/S/E/W.
   delta_place,k(ref) = largest W1 between the nominal and a moved window of that reference;
   delta_k(ref) = sqrt(delta_place,k(ref)^2 + delta_dem,k^2). For Jezero this equals the published floor.
2. The 88 unselected Earth windows are stored as 60 m quantile functions (analogue-v1-population.json).
3. Discrimination analysis per reference (analogue-v1-discrimination.json):
   background distribution of the index; single-feature ablations; alternative tolerances (Phase 5 values, x0.5, x2);
   leave-one-region-out tolerances evaluated on the held-out region only; background percentile of every candidate.
   None of these is a confidence interval.

Usage (from backend/):  python -m app.scripts.analogue_v1_references
"""

from __future__ import annotations

from datetime import datetime, timezone
from itertools import combinations
import json
from math import exp, log, sqrt

import numpy as np

from app.scripts.analogue_v1_calibration import CALIBRATION, SHIFTS, V4_EVALUATION, _shift, _write_artifact
from app.scripts.terrain_v4_evaluation import _source_path
from app.services.catalog_service import SITES
from app.services.geospatial_service import GEO_DATA, canonical_text_sha256, load_aoi
from app.services.terrain_quantiles import FEATURES, measure, w1_quantiles

POPULATION = GEO_DATA / "processed" / "evaluation" / "analogue-v1-population.json"
DISCRIMINATION = GEO_DATA / "processed" / "evaluation" / "analogue-v1-discrimination.json"
V5 = GEO_DATA / "processed" / "terrain-v5"
REGIONS = {"N29E083": "Himalaya and Tibet", "N34E077": "Himalaya and Tibet", "S25W070": "Central Andes", "S21W068": "Central Andes", "N14E040": "Afar",
           "N43W114": "Western USA", "N38W111": "Western USA", "N34W111": "Western USA", "N34W112": "Western USA", "N35W111": "Western USA",
           "N35W112": "Western USA", "N36W117": "Western USA", "N19W156": "Hawaii"}
MOON_RADIUS = 1_737_400.0


def _moon_shift(label: str) -> tuple[float, float]:
    """2 km moves away from the south pole in four directions (lon 0, 180, 90, -90)."""
    dlat = 2000.0 / MOON_RADIUS * 180 / np.pi
    lon = {"north_2km": 0.0, "south_2km": 180.0, "east_2km": 90.0, "west_2km": -90.0}[label]
    return -90.0 + dlat, lon


def _w1(a: dict, b: dict, f: str) -> float | None:
    qa, qb = a["features"][f]["quantiles"], b["features"][f]["quantiles"]
    return w1_quantiles(qa, qb) if qa and qb else None


def _index(ref60: dict, win60: dict, tau: dict, feats: list[str]) -> float | None:
    parts = []
    for f in feats:
        d = _w1(ref60, win60, f)
        if d is None:
            return None
        parts.append(exp(-log(2) * (d / tau[f]) ** 2))
    return 100 * sum(parts) / len(parts)


def _summary(values: list[float]) -> dict:
    v = np.asarray([x for x in values if x is not None])
    if not v.size:
        return {"count": 0}
    return {"count": int(v.size), "median": round(float(np.median(v)), 2), "p10": round(float(np.percentile(v, 10)), 2), "p90": round(float(np.percentile(v, 90)), 2),
            "share_at_or_above": {str(t): round(float(np.mean(v >= t)), 3) for t in (99, 95, 90, 75, 50)}}


def run() -> dict:
    cal = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    scored = cal["redundancy"]["scored"]
    tau = {f: cal["tau"][f]["60"] for f in FEATURES}
    dem_floor = {f: cal["resolution_floor"][f]["dem_product"] or 0.0 for f in FEATURES}
    refs = [s for s in SITES if s.body.value in {"mars", "moon"} and s.data_status.value == "real_processed"]
    floors: dict[str, dict] = {}
    ref60: dict[str, dict] = {}
    for site in refs:
        aoi = load_aoi(site.aoi_id)
        src = _source_path(site)
        body = site.body.value
        nominal = measure(src, body, aoi.center_longitude, aoi.center_latitude)
        shifts = {}
        for label, (dn, de) in SHIFTS.items():
            lat, lon = _moon_shift(label) if body == "moon" else _shift(aoi.center_latitude, aoi.center_longitude, dn, de, "mars")
            shifts[label] = measure(src, body, lon, lat, scales=(60,))
        _write_artifact(site, nominal, shifts, None)
        floors[site.id] = {}
        for f in FEATURES:
            place = max(w1_quantiles(nominal["60"]["features"][f]["quantiles"], s["60"]["features"][f]["quantiles"]) for s in shifts.values())
            combined = sqrt(place ** 2 + dem_floor[f] ** 2)
            floors[site.id][f] = {"placement": round(place, 4), "dem_product": round(dem_floor[f], 4), "combined": round(combined, 4),
                                  "noise_condition_passed": tau[f] >= cal["rules"]["noise_factor"] * combined}
        ref60[site.id] = nominal["60"]
        print(site.id, {f: (v["combined"], v["noise_condition_passed"]) for f, v in floors[site.id].items() if f in scored},
              "slope median", nominal["60"]["features"]["slope"]["median"], "coverage", nominal["60"]["features"]["slope"]["coverage"])

    # Population of unselected windows (same rule and exclusions as the frozen calibration).
    v4 = json.loads(V4_EVALUATION.read_text(encoding="utf-8"))
    names = cal["population"]["windows"]
    meta = {w["window"]: w for w in v4["base_rate"]["windows"]}
    population = {}
    for name in names:
        w = meta[name]
        tile = name.split("@")[0]
        m = measure(GEO_DATA / "raw" / f"{tile}.hgt", "earth", w["lon"], w["lat"], scales=(60,))
        population[name] = {"lat": w["lat"], "lon": w["lon"], "tile": tile, "region": REGIONS[tile],
                            "60": {"features": {f: {k: m["60"]["features"][f][k] for k in ("quantiles", "coverage", "median", "p90")} for f in FEATURES}}}
    # Reproduce the frozen tau from the stored population (integrity check of the stored quantiles).
    for f in FEATURES:
        median_pair = float(np.median([w1_quantiles(population[a]["60"]["features"][f]["quantiles"], population[b]["60"]["features"][f]["quantiles"])
                                       for a, b in combinations(names, 2)]))
        assert abs(median_pair - tau[f]) < 1e-3, (f, median_pair, tau[f])
    POPULATION.write_text(json.dumps({"methodology_version": "analogue-method-v1.0", "scale_m": 60, "rule": "unselected windows of the v4 base rate, >= 10 km from candidate centres, >= 90 % coverage",
                                      "windows": population}, separators=(",", ":")), encoding="utf-8", newline="\n")
    POPULATION.with_suffix(".sha256").write_text(canonical_text_sha256(POPULATION), encoding="ascii", newline="\n")

    earth = {s.id: json.loads((V5 / f"{s.id}.terrain-v5.json").read_text(encoding="utf-8"))["scales"]["60"] for s in SITES
             if s.body.value == "earth" and (V5 / f"{s.id}.terrain-v5.json").exists()}
    regions = sorted({p["region"] for p in population.values()})
    alt_tau = {"phase5_tau": {"slope": 8.0, "relative_elevation": 150.0, "local_relief": 200.0, "roughness": 30.0},
               "tau_x0.5": {f: tau[f] * 0.5 for f in FEATURES}, "tau_x2": {f: tau[f] * 2 for f in FEATURES}}
    out: dict = {}
    for rid, r60 in ref60.items():
        pop_idx = {n: _index(r60, population[n]["60"], tau, scored) for n in names}
        cand_idx = {s: _index(r60, e, tau, scored) for s, e in earth.items()}
        res = {
            "resolution_floor": floors[rid],
            "background": _summary(list(pop_idx.values())),
            "background_by_region": {g: _summary([pop_idx[n] for n in names if population[n]["region"] == g]) for g in regions},
            "single_feature": {f: _summary([_index(r60, population[n]["60"], tau, [f]) for n in names]) for f in scored},
            "alternative_tolerances": {k: {"background": _summary([_index(r60, population[n]["60"], t, scored) for n in names]),
                                           "candidates": {s: round(_index(r60, e, t, scored), 2) for s, e in earth.items()}} for k, t in alt_tau.items()},
            "candidates": {s: {"index": round(v, 2), "background_share_at_or_above": round(float(np.mean([p >= v for p in pop_idx.values()])), 3)} for s, v in cand_idx.items()},
            "leave_one_region_out": {},
        }
        for g in regions:
            train = [n for n in names if population[n]["region"] != g]
            test = [n for n in names if population[n]["region"] == g]
            t_g = dict(tau)
            for f in scored:
                t_g[f] = float(np.median([w1_quantiles(population[a]["60"]["features"][f]["quantiles"], population[b]["60"]["features"][f]["quantiles"]) for a, b in combinations(train, 2)]))
            res["leave_one_region_out"][g] = {"tau": {f: round(t_g[f], 3) for f in scored}, "held_out_windows": len(test),
                                              "held_out_background": _summary([_index(r60, population[n]["60"], t_g, scored) for n in test]),
                                              "candidate_order": sorted(earth, key=lambda s: -_index(r60, earth[s], t_g, scored))}
        out[rid] = res
    result = {"methodology_version": "analogue-method-v1.0", "generated_at": datetime.now(timezone.utc).isoformat(),
              "notice": "Discrimination analysis. Ranges and shares describe tested scenarios and an unselected background sample; they are not confidence intervals.",
              "population": {"windows": len(names), "regions": {g: sum(1 for p in population.values() if p["region"] == g) for g in regions},
                             "caveat": (f"The background windows come from tiles first downloaded for candidate sites: arid and mountainous regions are over-represented, and windows inside one "
                                         f"region are spatially correlated. {len(regions)} regions, not {len(names)} independent samples.")},
              "references": out}
    DISCRIMINATION.write_text(json.dumps(result, indent=2), encoding="utf-8", newline="\n")
    DISCRIMINATION.with_suffix(".sha256").write_text(canonical_text_sha256(DISCRIMINATION), encoding="ascii", newline="\n")
    return result


if __name__ == "__main__":
    r = run()
    for rid, v in r["references"].items():
        print(rid, "background", v["background"], "\n   candidates", v["candidates"])
