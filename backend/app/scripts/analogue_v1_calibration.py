"""analogue-method-v1.0 terrain measurement and calibration (terrain-v5.0 artifacts).

Rules below were written down before any candidate index under this method was computed. Candidate
windows were already known from earlier phases, so this is not a blind test; the rules therefore use
only the reference, DEM-product comparisons and an independent population of unselected windows.

1. Measurement      exact per-cell quantile functions (terrain_quantiles) on the 60 m primary grid;
                    120 and 240 m are sensitivity scenarios. WorldCover 2021 built-up cells (+1 cell)
                    are excluded on Earth AOIs.
2. Resolution floor delta_k = sqrt(delta_place^2 + delta_dem^2):
                    delta_place = largest W1 between the Jezero window and the same window moved 2 km
                    N/S/E/W (what re-placing the reference inside one landform does);
                    delta_dem   = largest W1 between SRTMGL1 and NASADEM / Copernicus GLO-30 for the
                    same Earth window (what the choice of DEM product does).
                    A candidate with d_k <= delta_k is not resolvable from the reference on feature k.
3. Redundancy       features whose per-window medians have Spearman |rho| >= 0.95 across the unselected
                    population measure one construct; only the first in the order slope, relative
                    elevation, local relief, roughness is scored, the others are shown as diagnostics.
4. Tolerance        tau_k = median pairwise W1 between unselected Earth windows (task-relevant contrast:
                    a difference as large as that between a typical pair of real land windows halves the
                    similarity). Valid only if tau_k >= 3 * delta_k, so measurement noise alone can cost at
                    most ~7 % (exp(-ln2/9)); otherwise the feature is shown as a distance without a score.
                    Unselected windows within 10 km of a candidate AOI centre are excluded.
5. Tests            leave-one-tile-out tau spread; synthetic negatives (tilted plane, ridges, rough relief)
                    and a synthetic identical copy; base-rate distribution under the new tau.

Usage (from backend/):  python -m app.scripts.analogue_v1_calibration [--skip-remote]
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from itertools import combinations
import json
from math import cos, exp, log, radians, sqrt
from pathlib import Path

import httpx
import numpy as np

from app.scripts.terrain_v4_evaluation import PC_DEMS, SHIFT_M, _pc_dem_array, _shift, _source_path
from app.services.catalog_service import SITES, get_validated_processed_summary
from app.services.geospatial_service import BACKEND_ROOT, GEO_DATA, canonical_text_sha256, load_aoi, sha256_file
from app.services.terrain_quantiles import EXCLUSION_RULE, FEATURES, N_QUANTILES, feature_arrays, landcover_exclusion, measure, quantile_function, w1_quantiles

OUT_DIR = GEO_DATA / "processed" / "terrain-v5"
CALIBRATION = GEO_DATA / "processed" / "evaluation" / "analogue-v1-calibration.json"
CONFIG_PATH = BACKEND_ROOT / "app" / "data" / "analogue.v1.json"
V4_EVALUATION = GEO_DATA / "processed" / "evaluation" / "terrain-v4-evaluation.json"
FEATURE_ORDER = ["slope", "relative_elevation", "local_relief", "roughness"]
SHIFTS = {"north_2km": (SHIFT_M, 0), "south_2km": (-SHIFT_M, 0), "east_2km": (0, SHIFT_M), "west_2km": (0, -SHIFT_M)}
REDUNDANCY_RHO = 0.95
NOISE_FACTOR = 3.0
EXCLUSION_RADIUS_M = 10_000.0


def _strip(measured: dict, scales=None) -> dict:
    """Keep quantiles plus coverage/median for the requested scales (all if None)."""
    return {s: v for s, v in measured.items() if scales is None or s in scales}


def _exclusion(site_id: str):
    clip = GEO_DATA / "processed" / "landcover" / f"{site_id}.worldcover-v200.tif"
    return landcover_exclusion(clip) if clip.exists() else None


def _write_artifact(site, nominal: dict, sensitivity: dict, exclusion_record: dict | None) -> Path:
    aoi = load_aoi(site.aoi_id)
    source = _source_path(site)
    payload = {
        "site_id": site.id, "aoi_id": site.aoi_id, "body": site.body.value, "methodology_version": "terrain-v5.0",
        "center_latitude": aoi.center_latitude, "center_longitude": aoi.center_longitude, "core_width_m": aoi.width_m,
        "source_id": site.source_id, "source_file": str(Path(source).relative_to(GEO_DATA.parent)).replace("\\", "/"), "source_sha256": sha256_file(source),
        "quantile_grid": {"n": N_QUANTILES, "u": "(i + 0.5) / n, i = 0..n-1", "definition": "inverted-CDF empirical quantile of valid core cells"},
        "kernels": {"slope": "metric numpy.gradient", "local_relief": "max-min in 1,000 m square", "roughness": "std. dev. in 300 m square",
                    "relative_elevation": "z - median(z) over the valid core"},
        "halo_m": 1200.0, "resampling": "bilinear elevation before derivatives", "primary_scale_m": 60,
        "exclusion": exclusion_record, "scales": nominal, "sensitivity_windows": sensitivity,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{site.id}.terrain-v5.json"
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8", newline="\n")
    path.with_suffix(".sha256").write_text(canonical_text_sha256(path), encoding="ascii", newline="\n")
    return path


def _w1(a: dict, b: dict, scale: str, feature: str) -> float | None:
    qa, qb = a[scale]["features"][feature]["quantiles"], b[scale]["features"][feature]["quantiles"]
    return w1_quantiles(qa, qb) if qa and qb else None


def _spearman(x: list[float], y: list[float]) -> float:
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y))
    return float(np.corrcoef(rx, ry)[0, 1])


def _synthetic(kind: str, resolution: float = 60.0, n: int = 167, halo: int = 20) -> dict:
    size = n + 2 * halo
    yy, xx = np.mgrid[0:size, 0:size] * resolution
    rng = np.random.default_rng(20261114)
    if kind == "tilted_plane_15deg":
        z = np.tan(radians(15)) * xx
    elif kind == "ridges_150m_2km":
        z = 150 * np.sin(2 * np.pi * xx / 2000.0)
    elif kind.startswith("fractal_relief_"):
        amplitude = float(kind.split("_")[2].rstrip("m"))
        noise = rng.normal(size=(size, size))
        f = np.fft.fft2(noise)
        ky, kx = np.meshgrid(np.fft.fftfreq(size), np.fft.fftfreq(size), indexing="ij")
        k = np.sqrt(kx ** 2 + ky ** 2); k[0, 0] = 1
        z = np.real(np.fft.ifft2(f / k ** 1.6)); z = (z - z.min()) / (z.max() - z.min()) * amplitude
    else:
        raise ValueError(kind)
    core = (slice(halo, halo + n), slice(halo, halo + n))
    arrays = feature_arrays(z.astype("float64"), core, resolution)
    return {"60": {"features": {name: {"quantiles": quantile_function(a)} for name, a in arrays.items()}}}


def run(skip_remote: bool = False) -> dict:
    by_id = {s.id: s for s in SITES}
    jezero, moon = by_id["mars-jezero"], by_id["moon-south-pole-shackleton"]
    earth = [s for s in SITES if s.body.value == "earth" and s.data_status.value == "real_processed" and get_validated_processed_summary(s.id)]
    measured: dict[str, dict] = {}

    # References ---------------------------------------------------------------------------------
    j_aoi = load_aoi(jezero.aoi_id)
    j_src = _source_path(jezero)
    measured["mars-jezero"] = measure(j_src, "mars", j_aoi.center_longitude, j_aoi.center_latitude)
    j_shift = {}
    for label, (dn, de) in SHIFTS.items():
        lat, lon = _shift(j_aoi.center_latitude, j_aoi.center_longitude, dn, de, "mars")
        j_shift[label] = measure(j_src, "mars", lon, lat)
    _write_artifact(jezero, measured["mars-jezero"], {k: _strip(v, ["60"]) for k, v in j_shift.items()}, None)
    m_aoi = load_aoi(moon.aoi_id)
    measured[moon.id] = measure(_source_path(moon), "moon", m_aoi.center_longitude, m_aoi.center_latitude)
    _write_artifact(moon, measured[moon.id], {}, None)

    # Earth sites --------------------------------------------------------------------------------
    dem_w1: dict[str, dict] = {}
    remote_status: dict[str, str] = {}
    client = httpx.Client(timeout=120, follow_redirects=False, headers={"User-Agent": "AlterEcho-analysis/1.0"})
    for site in earth:
        aoi = load_aoi(site.aoi_id)
        src = _source_path(site)
        excl = _exclusion(site.id)
        nominal = measure(src, "earth", aoi.center_longitude, aoi.center_latitude, exclusion=excl)
        measured[site.id] = nominal
        sens: dict[str, dict] = {}
        for label, (dn, de) in SHIFTS.items():
            lat, lon = _shift(aoi.center_latitude, aoi.center_longitude, dn, de, "earth")
            sens[label] = measure(src, "earth", lon, lat, scales=(60,), exclusion=excl)
        dem_w1[site.id] = {}
        if not skip_remote:
            for key, (collection, asset, label) in PC_DEMS.items():
                try:
                    memfile, items = _pc_dem_array(client, collection, asset, aoi.center_longitude, aoi.center_latitude, 0.075)
                    with memfile.open() as ds:
                        alt = measure(ds, "earth", aoi.center_longitude, aoi.center_latitude, scales=(60,), exclusion=excl)
                    sens[f"dem_{key}"] = {**alt, "items": items, "product": label}
                    dem_w1[site.id][key] = {f: _w1(nominal, alt, "60", f) for f in FEATURES}
                    remote_status[f"{site.id}:{key}"] = "measured"
                except Exception as error:  # provider failure is recorded, never substituted
                    remote_status[f"{site.id}:{key}"] = f"not measured: {type(error).__name__}"
        landcover = GEO_DATA / "processed" / "landcover" / f"{site.id}.worldcover-v200.json"
        lc = json.loads(landcover.read_text(encoding="utf-8")) if landcover.exists() else None
        record = {"product": "ESA WorldCover 10 m v200 (2021)", "classes_excluded": ["Built-up (50)"], "rule": EXCLUSION_RULE,
                  "built_up_fraction_core": lc["built_up_fraction_core"] if lc else None,
                  "excluded_fraction_60m": nominal["60"]["excluded_fraction"], "record": f"data/processed/landcover/{site.id}.worldcover-v200.json"} if excl else None
        _write_artifact(site, nominal, sens, record)
        print(site.id, "excluded", nominal["60"]["excluded_fraction"], "dem", {k: {f: round(v, 3) for f, v in d.items() if v is not None} for k, d in dem_w1[site.id].items()})

    # Population of unselected windows ----------------------------------------------------------------
    v4 = json.loads(V4_EVALUATION.read_text(encoding="utf-8"))
    centres = [(load_aoi(s.aoi_id).center_latitude, load_aoi(s.aoi_id).center_longitude) for s in earth]
    population: dict[str, dict] = {}
    excluded_windows = []
    for w in v4["base_rate"]["windows"]:
        if w.get("status") != "ok":
            continue
        near = any(sqrt(((w["lat"] - la) * 111_320) ** 2 + ((w["lon"] - lo) * 111_320 * cos(radians(la))) ** 2) < EXCLUSION_RADIUS_M for la, lo in centres)
        if near:
            excluded_windows.append(w["window"])
            continue
        tile = w["window"].split("@")[0]
        path = GEO_DATA / "raw" / f"{tile}.hgt"
        m = measure(path, "earth", w["lon"], w["lat"])
        if all(m[s]["features"][f]["coverage"] >= 0.9 for s in m for f in FEATURES):
            population[w["window"]] = m
    names = sorted(population)

    # Rule 2: resolution floor -------------------------------------------------------------------------
    delta = {}
    for scale in ("60",):
        for f in FEATURES:
            place = max(_w1(measured["mars-jezero"], j_shift[k], scale, f) for k in SHIFTS)
            dem_values = [v[f] for site in dem_w1.values() for v in site.values() if v.get(f) is not None]
            dem = max(dem_values) if dem_values else None
            delta[f] = {"placement": round(place, 4), "dem_product": round(dem, 4) if dem is not None else None,
                        "combined": round(sqrt(place ** 2 + (dem or 0) ** 2), 4), "dem_pairs": len(dem_values)}

    # Rule 3: redundancy -------------------------------------------------------------------------------
    medians = {f: [population[n]["60"]["features"][f]["median"] for n in names] for f in FEATURES}
    rho = {f"{a}~{b}": round(_spearman(medians[a], medians[b]), 3) for a, b in combinations(FEATURE_ORDER, 2)}
    scored: list[str] = []
    redundant: dict[str, str] = {}
    for f in FEATURE_ORDER:
        clash = next((g for g in scored if abs(rho.get(f"{g}~{f}", rho.get(f"{f}~{g}", 0))) >= REDUNDANCY_RHO), None)
        if clash:
            redundant[f] = clash
        else:
            scored.append(f)

    # Rule 4: tolerance --------------------------------------------------------------------------------
    tau: dict[str, dict] = {}
    for f in FEATURES:
        tau[f] = {}
        for scale in ("60", "120", "240"):
            pair = [_w1(population[a], population[b], scale, f) for a, b in combinations(names, 2)]
            tau[f][scale] = round(float(np.median(pair)), 4)
        tiles = sorted({n.split("@")[0] for n in names})
        loo = []
        for t in tiles:
            keep = [n for n in names if not n.startswith(t)]
            loo.append(float(np.median([_w1(population[a], population[b], "60", f) for a, b in combinations(keep, 2)])))
        tau[f]["leave_one_tile_out_60"] = [round(min(loo), 4), round(max(loo), 4)]
        tau[f]["noise_condition"] = {"delta_60": delta[f]["combined"], "required_min": round(NOISE_FACTOR * delta[f]["combined"], 4),
                                     "passed": tau[f]["60"] >= NOISE_FACTOR * delta[f]["combined"]}

    # Rule 5: synthetic negatives and base rate -----------------------------------------------------------
    def index(a: dict, b: dict, scale: str = "60") -> float | None:
        parts = []
        for f in scored:
            if not tau[f]["noise_condition"]["passed"]:
                return None
            d = _w1(a, b, scale, f)
            parts.append(exp(-log(2) * (d / tau[f][scale]) ** 2))
        return round(100 * sum(parts) / len(parts), 2) if parts else None

    synthetic = {}
    expectations = {"tilted_plane_15deg": "negative: uniform 15 deg slope", "ridges_150m_2km": "negative: regular 150 m ridges every 2 km",
                    "fractal_relief_1500m": "negative: rough fractal relief 1,500 m",
                    "fractal_relief_300m": "look-alike: gentle fractal relief 300 m with slope and relief distributions close to Jezero's; a high value is expected and shows that distributions ignore spatial arrangement"}
    for kind, expectation in expectations.items():
        s = _synthetic(kind)
        synthetic[kind] = {"expectation": expectation, "index_vs_jezero": index(measured["mars-jezero"], s),
                           "w1": {f: round(_w1(measured["mars-jezero"], s, "60", f), 3) for f in FEATURES}}
    synthetic["identical_copy"] = {"index_vs_jezero": index(measured["mars-jezero"], measured["mars-jezero"])}
    pop_index = [index(measured["mars-jezero"], population[n]) for n in names]
    pop_index = [v for v in pop_index if v is not None]
    base = {"count": len(pop_index), "median_index": round(float(np.median(pop_index)), 2) if pop_index else None,
            "share_at_or_above": {str(t): round(float(np.mean([v >= t for v in pop_index])), 3) for t in (99, 95, 90, 50)} if pop_index else None}

    result = {
        "methodology_version": "analogue-method-v1.0", "terrain_method": "terrain-v5.0", "generated_at": datetime.now(timezone.utc).isoformat(),
        "notice": "Deterministic calibration. Ranges are scenario sensitivities, not confidence intervals. Candidate windows were known from earlier phases; the rules use only the reference, DEM-product pairs and unselected windows.",
        "rules": {"redundancy_rho": REDUNDANCY_RHO, "noise_factor": NOISE_FACTOR, "population_exclusion_radius_m": EXCLUSION_RADIUS_M,
                  "primary_scale_m": 60, "quantiles": N_QUANTILES},
        "resolution_floor": delta, "redundancy": {"spearman_medians_60m": rho, "scored": scored, "redundant_with": redundant, "population_windows": len(names)},
        "tau": tau, "synthetic_negatives": synthetic, "base_rate": base, "remote_dem_status": remote_status,
        "population": {"windows": names, "excluded_near_candidates": excluded_windows},
        "dem_w1_60m": {s: {k: {f: (round(v, 4) if v is not None else None) for f, v in d.items()} for k, d in v.items()} for s, v in dem_w1.items()},
    }
    CALIBRATION.write_text(json.dumps(result, indent=2), encoding="utf-8", newline="\n")
    CALIBRATION.with_suffix(".sha256").write_text(canonical_text_sha256(CALIBRATION), encoding="ascii", newline="\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-remote", action="store_true", help="Skip NASADEM/GLO-30 (the DEM-product floor is then missing)")
    result = run(parser.parse_args().skip_remote)
    print(json.dumps({k: result[k] for k in ("resolution_floor", "redundancy", "tau", "synthetic_negatives", "base_rate", "remote_dem_status")}, indent=1))


if __name__ == "__main__":
    main()
