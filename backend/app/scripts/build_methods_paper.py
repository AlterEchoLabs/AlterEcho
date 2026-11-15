"""Build the research-paper Methods and Results sections from the running implementation.

Every number in docs/paper/ comes from the backend: method configuration, calibration and discrimination files,
terrain-v5 artifacts and a live comparison. The worked example is recomputed independently with the reference
arithmetic of the methodology handoff (analogue_reference.py) and must agree with the service.

Outputs (docs/paper/):
  paper-data.json      numbers and provenance used in the text (tests compare it with a fresh build)
  paper-content.json   ordered content blocks (headings, paragraphs, equations, tables) for the .docx builder
  methods.md           Markdown with LaTeX equations (reproducible plain-text source)
  methods.tex          LaTeX source of the same blocks; compiled with xelatex to methods.pdf
  methods.docx         built by docs/paper/tools/build_docx.cjs with native Word equations (OMML)

Usage (from backend/):  python -m app.scripts.build_methods_paper [--check]
"""

from __future__ import annotations

import argparse
import json
from math import exp, log
from pathlib import Path
import sys

import numpy as np

from app.services import analogue_reference as ref
from app.services import analogue_v1_service as av
from app.services.analogue_math import w1_exact
from app.services.catalog_service import get_site
from app.services.geospatial_service import BACKEND_ROOT, GEO_DATA, canonical_text_sha256, load_aoi, load_manifest, sha256_file

DOCS = BACKEND_ROOT.parent / "docs" / "paper"
EXAMPLE = {"reference": "mars-jezero", "site": "earth-atacama-south", "profile": "terrain_analogy"}
TOL = 1e-9


def _r(x: float | None, n: int = 6) -> float | None:
    return None if x is None else round(float(x), n)


def _summary_text(feature: str, art: dict) -> str:
    """Slope: median and 90th percentile. Relative elevation: 10th-90th percentile (its median is 0 by construction)."""
    v = art["scales"]["60"]["features"][feature]
    q = v["quantiles"]
    p10, p90 = (q[49] + q[50]) / 2, (q[449] + q[450]) / 2
    if feature == "relative_elevation":
        return f"{p10:.1f} to {p90:.1f} m (p10–p90)"
    return f"{v['median']:.2f}° median, {p90:.2f}° p90"


def collect(exact_check: bool = True) -> dict:
    cfg, cal, disc = av.CONFIG, av.calibration(), av.discrimination()
    detail = av.result_detail(EXAMPLE["reference"], EXAMPLE["profile"], EXAMPLE["site"])
    cand = detail.candidate
    terrain = next(f for f in cand.families if f.family == "terrain")
    feats = {f.feature: f for f in terrain.features}
    ref_art, site_art = av.artifact(EXAMPLE["reference"]), av.artifact(EXAMPLE["site"])
    floor = av.reference_floor(ref_art)
    scored = cal["redundancy"]["scored"]

    # Independent recomputation with the handoff reference code (equal-weight atoms at the 500 quantiles).
    recompute = {}
    for f in scored:
        qe, qp = site_art["scales"]["60"]["features"][f]["quantiles"], ref_art["scales"]["60"]["features"][f]["quantiles"]
        d = ref.weighted_w1(qe, [1.0] * len(qe), qp, [1.0] * len(qp))
        tau = cal["tau"][f]["60"]
        recompute[f] = {"d": d, "tau": tau, "d_over_tau": d / tau, "s": ref.similarity(d, tau)}
    s_family = sum(0.5 * recompute[f]["s"] for f in scored)
    a_obs, coverage = ref.observed_index({"terrain": (1.0, True, s_family)})
    _, s_service, ok, _ = av.terrain_features(ref_art["scales"], site_art["scales"], floor=floor)
    assert ok and abs(s_service - s_family) < 1e-6, (s_service, s_family)
    assert abs(cand.observed_index - round(a_obs, 2)) < 1e-9
    displayed = {f: round(feats[f].similarity, 4) for f in scored}
    from_displayed = 100 * sum(0.5 * displayed[f] for f in scored)

    exact = None
    committed = DOCS / "paper-data.json"
    if not exact_check and committed.exists():
        # The all-cell check needs the raw DEMs (git-ignored); in --check mode the committed result is reused.
        exact = json.loads(committed.read_text(encoding="utf-8"))["example"]["exact_w1_check"]
    if exact_check:
        from app.scripts.terrain_v4_evaluation import _source_path
        from app.services.terrain_quantiles import landcover_exclusion, measure
        ea, ra = load_aoi(get_site(EXAMPLE["site"]).aoi_id), load_aoi(get_site(EXAMPLE["reference"]).aoi_id)
        clip = GEO_DATA / "processed" / "landcover" / f"{EXAMPLE['site']}.worldcover-v200.tif"
        em = measure(_source_path(get_site(EXAMPLE["site"])), "earth", ea.center_longitude, ea.center_latitude, scales=(60,), exclusion=landcover_exclusion(clip), keep_arrays=True)
        rm = measure(_source_path(get_site(EXAMPLE["reference"])), "mars", ra.center_longitude, ra.center_latitude, scales=(60,), keep_arrays=True)
        exact = {}
        for f in scored:
            ex = w1_exact(em["_arrays"]["60"][f].ravel(), rm["_arrays"]["60"][f].ravel())
            exact[f] = {"exact_all_cells": _r(ex), "quantile_500": _r(recompute[f]["d"]), "abs_difference": _r(abs(ex - recompute[f]["d"]), 6),
                        "relative_difference": _r(abs(ex - recompute[f]["d"]) / ex, 6),
                        "cells_earth": int(np.isfinite(em["_arrays"]["60"][f]).sum()), "cells_reference": int(np.isfinite(rm["_arrays"]["60"][f]).sum())}

    site, refsite = get_site(EXAMPLE["site"]), get_site(EXAMPLE["reference"])
    sm, rmf = load_manifest(site.source_id), load_manifest(refsite.source_id)
    jz = disc["references"]["mars-jezero"]
    loro = jz["leave_one_region_out"]
    others = {k: v["background"]["share_at_or_above"]["90"] for k, v in disc["references"].items() if k.startswith("mars-")}
    import numpy as _np
    import rasterio as _rio
    import fastapi as _fa
    data = {
        "method_version": cfg["method_version"], "terrain_method": cfg["terrain_method"], "status": cfg["status"],
        "software": {"python": sys.version.split()[0], "numpy": _np.__version__, "rasterio": _rio.__version__, "gdal": _rio.__gdal_version__, "fastapi": _fa.__version__},
        "files": {"method_config": {"path": "backend/app/data/analogue.v1.json", "sha256_lf": canonical_text_sha256(BACKEND_ROOT / "app" / "data" / "analogue.v1.json")},
                  "calibration": {"path": "backend/data/processed/evaluation/analogue-v1-calibration.json", "sha256_lf": canonical_text_sha256(av.CALIBRATION_PATH)},
                  "discrimination": {"path": "backend/data/processed/evaluation/analogue-v1-discrimination.json", "sha256_lf": canonical_text_sha256(av.DISCRIMINATION_PATH)},
                  "scoring_code": ["backend/app/services/analogue_math.py (similarity, w1_quantile_functions, family_score, observed_index)",
                                   "backend/app/services/analogue_v1_service.py (terrain_features, reference_floor, compare)",
                                   "backend/app/services/terrain_quantiles.py (measure, quantile_function)"]},
        "grid": {"primary_m": 60, "sensitivity_m": [120, 240], "window_m": 10000, "cells_per_side_60m": 167, "halo_m": 1200, "relief_window_m": 1020, "relief_window_cells": 17,
                 "roughness_window_m": 300, "roughness_window_cells": 5, "min_feature_coverage": cfg["minimum_feature_coverage"], "neighbourhood_min_valid": 0.5, "quantiles": 500},
        "tau": {f: {"60": cal["tau"][f]["60"], "120": cal["tau"][f]["120"], "240": cal["tau"][f]["240"], "loto_60": cal["tau"][f]["leave_one_tile_out_60"]} for f in ("slope", "relative_elevation", "local_relief", "roughness")},
        "population": {"windows": cal["redundancy"]["population_windows"], "pairs": cal["redundancy"]["population_windows"] * (cal["redundancy"]["population_windows"] - 1) // 2,
                       "exclusion_radius_m": cal["rules"]["population_exclusion_radius_m"], "regions": disc["population"]["regions"], "caveat": disc["population"]["caveat"]},
        "redundancy": {"rho": cal["redundancy"]["spearman_medians_60m"], "threshold": cal["rules"]["redundancy_rho"], "scored": scored, "redundant_with": cal["redundancy"]["redundant_with"]},
        "noise_factor": cal["rules"]["noise_factor"],
        "floor_jezero": {f: floor[f] for f in scored}, "dem_floor_pairs": cal["resolution_floor"]["slope"]["dem_pairs"],
        "synthetic": {k: v["index_vs_jezero"] for k, v in cal["synthetic_negatives"].items()},
        "background_jezero": jz["background"], "single_feature_jezero": {f: v["share_at_or_above"] for f, v in jz["single_feature"].items()},
        "alt_tau_jezero": {k: v["background"]["share_at_or_above"] for k, v in jz["alternative_tolerances"].items()},
        "loro_tau": {f: [min(v["tau"][f] for v in loro.values()), max(v["tau"][f] for v in loro.values())] for f in scored},
        "loro_top_order_stable": len({tuple(v["candidate_order"][:5]) for v in loro.values()}) == 1,
        "background_share_90_mars": others,
        "profiles": {pid: {"label": p["label"], "weights": p["weights"], "task_critical": p["task_critical"], "rankable": p["rankable"]} for pid, p in cfg["profiles"].items()},
        "example": {
            "earth": {"site_id": site.id, "name": site.name, "aoi_id": site.aoi_id, "center": [site.latitude, site.longitude], "dem": f"{sm.product_name}.{sm.product_version}",
                      "tile": "S25W070", "dem_sha256": sm.extracted_sha256_checksum, "doi": sm.doi, "grid_crs": "UTM zone 19S (EPSG:32719)",
                      "mask": "ESA WorldCover v200 2021: cells ≥ 50 % built-up excluded", "mask_clip_sha256": sha256_file(GEO_DATA / "processed" / "landcover" / f"{site.id}.worldcover-v200.tif"),
                      "excluded_fraction_60m": site_art["scales"]["60"]["excluded_fraction"]},
            "reference": {"site_id": refsite.id, "name": refsite.name, "aoi_id": refsite.aoi_id, "center": [refsite.latitude, refsite.longitude], "dem": rmf.product_name,
                          "dem_sha256": rmf.sha256_checksum, "doi": rmf.doi, "grid_crs": "Mars-sphere equirectangular, true scale at 18.4663 N (native CTX DEM grid)"},
            "features": {f: {"label": feats[f].label, "units": feats[f].units, "earth_median": feats[f].earth.median, "earth_p90": feats[f].earth.p90,
                             "reference_median": feats[f].planet.median, "reference_p90": feats[f].planet.p90,
                             "earth_coverage": feats[f].earth.coverage, "reference_coverage": feats[f].planet.coverage,
                             "d": _r(recompute[f]["d"], 9), "tau": recompute[f]["tau"], "d_over_tau": _r(recompute[f]["d_over_tau"], 9), "s": _r(recompute[f]["s"], 9),
                             "weight": feats[f].weight, "contribution": _r(100 * 0.5 * recompute[f]["s"], 6), "delta": floor[f]["combined"],
                             "within_floor": recompute[f]["d"] <= floor[f]["combined"],
                             "earth_summary": _summary_text(f, site_art), "reference_summary": _summary_text(f, ref_art)} for f in scored},
            "diagnostics": {f: {"d": feats[f].distance, "units": feats[f].units} for f in ("local_relief", "roughness")},
            "family_score": _r(s_family, 9), "observed_index_full": _r(a_obs, 6), "observed_index_api": cand.observed_index, "coverage": coverage,
            "displayed_s": displayed, "index_from_displayed_s": _r(from_displayed, 4),
            "service_family_score": _r(s_service, 9), "agreement_abs": _r(abs(s_service - s_family) * 100, 12),
            "resolution": cand.resolution, "background_share": cand.background_share, "tie_group_size": len(next(g for g in detail.comparison["tie_groups"] if EXAMPLE["site"] in g)),
            "rank": cand.rank, "index_range": cand.sensitivity.index_range if cand.sensitivity else None, "scenarios": len(cand.sensitivity.scenarios) if cand.sensitivity else 0,
            "exact_w1_check": exact,
        },
    }
    return data


def eq(n: int, latex: str, umath: str) -> dict:
    return {"type": "eq", "n": n, "latex": latex, "umath": umath}


def blocks(d: dict) -> list[dict]:
    ex, f = d["example"], d["example"]["features"]
    sl, re_ = f["slope"], f["relative_elevation"]
    bg = d["background_jezero"]
    t = d["tau"]
    fl = d["floor_jezero"]
    pct = lambda x: f"{100 * x:.0f}%"
    B: list[dict] = []
    B.append({"type": "h1", "text": "Methods: Earth–Planetary Terrain Analogue Comparison"})
    B.append({"type": "p", "text": f"This section describes the method implemented in the TerraLuna application as {d['method_version']} with the terrain measurement {d['terrain_method']}. "
              "Every number below is generated from the versioned configuration, calibration files and a live comparison of the running backend; a test fails if the text and the backend diverge."})
    B.append({"type": "h2", "text": "Research question and scope"})
    B.append({"type": "p", "text": "We ask a narrow question: at a specified 10 km Earth window and a specified 10 km planetary reference window, how closely do the distributions of two measured terrain properties agree on a common 60 m grid, and is that agreement larger than what the measurement itself can resolve? "
              "A result is conditional on the comparison definition"})
    B.append(eq(1, r"\mathcal{R} = \mathcal{R}(E,\,P,\,T,\,H,\,V)", "R=R(E,P,T,H,V)#(1)"))
    B.append({"type": "p", "text": "where $E$ is the Earth area of interest (AOI), $P$ the planetary reference AOI, $T$ the task profile, $H$ the epoch (the present-day surface recorded by the elevation models, not the ancient environment that formed it) and $V$ the method version. "
              "Results with different definitions are never ranked together. The output is an experimental terrain evidence index, not a probability that a place is like Mars, not a measure of geology, atmosphere, water, habitability, access or mission safety, and not a NASA or USGS endorsement."})
    B.append({"type": "h2", "text": "Areas of interest and sources"})
    B.append({"type": "p", "text": "Earth windows are 10 km squares centred on registered points and processed from NASA SRTMGL1.003 (1 arc-second, about 30 m; elevations in metres above the EGM96 geoid; acquired February 2000). "
              f"The Jezero reference ({ex['reference']['aoi_id']}, centred at 18.44° N, 77.45° E) uses the Mars 2020 Science Investigation CTX DEM mosaic (20 m posting; DOI {ex['reference']['doi']}). "
              "Four further Mars references (Gale crater floor, Elysium Planitia at the InSight site, Gusev crater plains and the Eberswalde delta) use USGS controlled CTX DTMs (20 m; CC0; DOI 10.5066/P9JKVWR3), read as windows from cloud-optimised GeoTIFFs and reprojected once onto a local equirectangular grid true to scale at the window latitude. "
              "Among products covering a window, the one with the lowest median stereo intersection error was used. A lunar south-pole window uses LRO LOLA LDEM_875S_20M. "
              "Windows were placed by documented rules before their terrain was measured; one Earth window (the original Atacama window) was excluded because it contains an industrial complex and was replaced by a window 8 km south."})
    B.append({"type": "h2", "text": "Raster preparation and quality rules"})
    B.append({"type": "p", "text": f"Each DEM is resampled bilinearly from its native posting onto a north-up metric grid centred on the AOI: UTM for Earth, the native or local equirectangular grid for Mars and polar stereographic for the Moon. All three are true to scale over a 10 km window to better than 0.1 %. "
              f"The primary analysis grid is {d['grid']['primary_m']} m ({d['grid']['cells_per_side_60m']} × {d['grid']['cells_per_side_60m']} cells, at least twice the native posting); 120 and 240 m grids are used only as sensitivity scenarios. "
              f"A {d['grid']['halo_m']:.0f} m halo is processed around every window so neighbourhood statistics are complete at the edges, and only core cells are summarised. Source no-data become missing values and are never filled. "
              "On Earth, cells that are at least half built-up in ESA WorldCover v200 (2021) are set to missing before derivatives are computed. "
              f"A feature is eligible only if at least {pct(d['grid']['min_feature_coverage'])} of core cells are valid on both windows."})
    B.append({"type": "p", "text": "Four terrain constructs are measured on every valid cell: slope; local relief (maximum minus minimum elevation in a "
              f"{d['grid']['relief_window_cells']} × {d['grid']['relief_window_cells']}-cell, {d['grid']['relief_window_m']} m neighbourhood); roughness (standard deviation of elevation in a {d['grid']['roughness_window_cells']} × {d['grid']['roughness_window_cells']}-cell, {d['grid']['roughness_window_m']} m neighbourhood); and relative elevation. "
              "Neighbourhood statistics require at least half the window to be valid. Slope uses central differences on the metric grid,"})
    B.append(eq(2, r"\theta = \arctan\sqrt{\left(\frac{\partial z}{\partial x}\right)^{2} + \left(\frac{\partial z}{\partial y}\right)^{2}}", "θ=arctan√((∂z/∂x)^2+(∂z/∂y)^2 )#(2)"))
    B.append({"type": "p", "text": "with $z$ the elevation in metres and $x$, $y$ ground distances in metres, giving $\\theta$ in degrees. Relative elevation removes the incomparable vertical datums of Earth, Mars and the Moon:"})
    B.append(eq(3, r"z_{\mathrm{rel}} = z - \operatorname{median}(z)", "z_rel=z-median(z)#(3)"))
    B.append({"type": "h2", "text": "Distances between distributions"})
    B.append({"type": "p", "text": "For a scalar feature $k$ measured in the same units on both bodies, the difference is"})
    B.append(eq(4, r"d_{k} = \left| x_{E,k} - x_{P,k} \right|", "d_k=|x_(E,k)-x_(P,k) |#(4)"))
    B.append({"type": "p", "text": "No scalar feature is scored in the current version; all scored terrain features are distributions. For a distribution feature, $F_{E,k}$ and $F_{P,k}$ are the empirical cumulative distribution functions of the valid core cells (equal-area cells, so every cell has the same weight), and the distance is the one-dimensional Wasserstein-1 distance"})
    B.append(eq(5, r"d_{k} = W_{1}\!\left(F_{E,k}, F_{P,k}\right) = \int_{0}^{1} \left| F_{E,k}^{-1}(u) - F_{P,k}^{-1}(u) \right| \mathrm{d}u", "d_k=W_1 (F_(E,k),F_(P,k) )=∫_0^1▒|F_(E,k)^(-1) (u)-F_(P,k)^(-1) (u) | du#(5)"))
    B.append({"type": "p", "text": f"in degrees for slope and metres for relative elevation. The implementation evaluates Equation 5 with the midpoint rule on {d['grid']['quantiles']} quantiles,"})
    B.append(eq(6, r"\hat{d}_{k} = \frac{1}{N}\sum_{i=1}^{N} \left| Q_{E,k}(u_{i}) - Q_{P,k}(u_{i}) \right|, \qquad u_{i} = \frac{i - \tfrac{1}{2}}{N}, \quad N = 500", "d̂_k=1/N ∑_(i=1)^N▒|Q_(E,k) (u_i )-Q_(P,k) (u_i ) | ,  u_i=(i-1/2)/N,  N=500#(6)"))
    exs = ex["exact_w1_check"] or {}
    B.append({"type": "p", "text": "where $Q$ is the inverted-CDF empirical quantile function. For the worked example below, the quantile approximation differs from the exact all-cell W1 by "
              + "; ".join(f"{v['abs_difference']:.4f} {'°' if k == 'slope' else 'm'} ({100 * v['relative_difference']:.2f} %) for {k.replace('_', ' ')}" for k, v in exs.items())
              + ". W1 compares distributions only: two windows with the same slope histogram but different arrangements of ridges, channels or craters have zero distance."})
    B.append({"type": "h2", "text": "Feature similarity and tolerances"})
    B.append({"type": "p", "text": "Each distance is converted to a bounded feature similarity"})
    B.append(eq(7, r"s_{k} = \exp\!\left[-\ln 2\,\left(\frac{d_{k}}{\tau_{k}}\right)^{2}\right]", "s_k=exp[-ln⁡2 (d_k/τ_k )^2 ]#(7)"))
    B.append({"type": "p", "text": "so that $s_k = 1$ at $d_k = 0$, $s_k = 0.5$ at $d_k = \\tau_k$ and $s_k = 0.0625$ at $d_k = 2\\tau_k$ (these values are unit-tested). The tolerance $\\tau_k$ has the units of $d_k$. It is the median pairwise distance among unselected Earth land windows,"})
    B.append(eq(8, r"\tau_{k} = \operatorname*{median}_{i<j} W_{1}\!\left(F_{i,k}, F_{j,k}\right)", "τ_k=median┬(i<j) W_1 (F_(i,k),F_(j,k) )#(8)"))
    B.append({"type": "p", "text": f"computed over all {d['population']['pairs']} pairs of {d['population']['windows']} windows on a regular grid inside the downloaded SRTM tiles, excluding any window within {d['population']['exclusion_radius_m'] / 1000:.0f} km of a candidate centre. "
              f"This gives $\\tau_{{\\mathrm{{slope}}}}$ = {t['slope']['60']:.4f}° and $\\tau_{{\\mathrm{{rel}}}}$ = {t['relative_elevation']['60']:.4f} m at 60 m. "
              "The interpretation is a task-relevant contrast: a candidate that differs from the reference as much as a typical pair of real Earth landscapes differ from each other receives 0.5. "
              f"The tolerance is a project definition, not an empirically validated threshold. It depends on the background sample: leaving one source tile out gives {t['slope']['loto_60'][0]:.2f}–{t['slope']['loto_60'][1]:.2f}° and {t['relative_elevation']['loto_60'][0]:.1f}–{t['relative_elevation']['loto_60'][1]:.1f} m, "
              f"and leaving one region out gives {d['loro_tau']['slope'][0]:.2f}–{d['loro_tau']['slope'][1]:.2f}° and {d['loro_tau']['relative_elevation'][0]:.1f}–{d['loro_tau']['relative_elevation'][1]:.1f} m. "
              "The candidate windows were known before this rule was fixed, so it is not a blind test."})
    B.append({"type": "h2", "text": "Feature selection and family score"})
    rho = d["redundancy"]["rho"]
    B.append({"type": "p", "text": f"Features whose window medians correlate at Spearman |ρ| ≥ {d['redundancy']['threshold']} across the background windows are treated as one construct. "
              f"Slope correlates with roughness (ρ = {rho['slope~roughness']}) and with local relief (ρ = {rho['slope~local_relief']}), whereas relative elevation does not (ρ = {rho['slope~relative_elevation']} with slope). "
              "Slope and relative elevation are therefore the scored features; local relief and roughness are reported as diagnostics with zero weight. Within the terrain family $g$,"})
    B.append(eq(9, r"S_{g} = \sum_{k} a_{k|g}\, s_{k}, \qquad \sum_{k} a_{k|g} = 1", "S_g=∑_k▒〖a_(k|g) s_k 〗,  ∑_k▒a_(k|g) =1#(9)"))
    B.append({"type": "p", "text": "with $a_{\\mathrm{slope}|g} = a_{\\mathrm{rel}|g} = 0.5$. A family is eligible ($I_g = 1$) only if every scored feature is eligible; a family is never scored from an incomplete feature set."})
    B.append({"type": "h2", "text": "Resolution floor and eligibility"})
    B.append({"type": "p", "text": "The resolution floor is the distance produced by the measurement itself, not by a terrain difference:"})
    B.append(eq(10, r"\delta_{k} = \sqrt{\delta_{\mathrm{place},k}^{2} + \delta_{\mathrm{dem},k}^{2}}", "δ_k=√(δ_(place,k)^2+δ_(dem,k)^2 )#(10)"))
    B.append({"type": "p", "text": "where $\\delta_{\\mathrm{place},k}$ is the largest W1 between the reference window and the same window moved 2 km north, south, east and west, and $\\delta_{\\mathrm{dem},k}$ is the largest W1 between SRTMGL1 and NASADEM or Copernicus GLO-30 for the same Earth window "
              f"({d['dem_floor_pairs']} measured pairs). For Jezero, $\\delta_{{\\mathrm{{slope}}}}$ = {fl['slope']['combined']:.4f}° and $\\delta_{{\\mathrm{{rel}}}}$ = {fl['relative_elevation']['combined']:.4f} m. "
              f"A scored feature is used only if $\\tau_k \\ge {d['noise_factor']:.0f}\\,\\delta_k$; otherwise its distance is reported without a similarity. "
              "The floor never changes $s_k$. It decides eligibility and interpretation: when every scored distance is at or below its floor, the candidate is reported as not resolved from the reference by these tests. "
              "The tests are a 2 km reference move and a change of Earth DEM product; they do not cover every source of error, so the wording is limited to them. The lunar window fails the condition (moving it 2 km changes relative elevation by about 195 m against a 77 m tolerance), so lunar comparisons show distances without an index."})
    B.append({"type": "h2", "text": "Observed index, evidence coverage and ranking"})
    B.append({"type": "p", "text": "Each task profile assigns planned weights $w_g$ ($\\sum_g w_g = 1$) to evidence families. With $I_g$ the eligibility indicator,"})
    B.append(eq(11, r"A_{\mathrm{obs}} = 100 \times \frac{\sum_{g} w_{g} I_{g} S_{g}}{\sum_{g} w_{g} I_{g}}", "A_obs=100×(∑_g▒〖w_g I_g S_g 〗)/(∑_g▒〖w_g I_g 〗)#(11)"))
    B.append(eq(12, r"C = \sum_{g} w_{g} I_{g}", "C=∑_g▒〖w_g I_g 〗#(12)"))
    B.append({"type": "p", "text": "$A_{\\mathrm{obs}}$ is undefined, never zero, when no family qualifies. $C$ is the share of the planned profile weight that is measured and comparable; it is not statistical confidence and not DEM pixel coverage. "
              "Only terrain is currently measured, so $C$ = 1 for the terrain-analogy profile and 0.30, 0.80 and 0.35 for the balanced-science, rover-mobility and Mars-base field-testing profiles. "
              "A profile is ranked only if it is declared rankable, every task-critical family is eligible for every candidate and all candidates share one eligibility key (reference AOI, method, weights, scored features, tolerances, grid, DEM product and mask). "
              "Today only terrain analogy is ranked; the other profiles are reported as partial evidence or not assessed. "
              "Ties are formed from scenario ranges: each candidate's index is recomputed with the Earth window moved 2 km in four directions, the reference moved 2 km in four directions, each alternative DEM, the 120 and 240 m grids, all tolerances × 0.75 and × 1.25, and feature weights 0.25/0.75; candidates whose ranges overlap, chained in order of nominal index, share a competition rank. These ranges are scenario sensitivities, not confidence intervals."})
    B.append({"type": "table", "caption": "Table 1. Planned family weights and task-critical families by profile.",
              "header": ["Profile", "Planned weights $w_g$", "Task-critical", "Ranked"],
              "rows": [[p["label"], ", ".join(f"{k.replace('_', ' ')} {v:.2f}" for k, v in p["weights"].items()), ", ".join(x.replace("_", " ") for x in p["task_critical"]), "yes" if p["rankable"] else "no"] for p in d["profiles"].values()]})
    B.append({"type": "h2", "text": "Worked example: Atacama Desert (south window) compared with Jezero"})
    B.append({"type": "p", "text": f"Earth window {ex['earth']['aoi_id']} (centre {abs(ex['earth']['center'][0]):.4f}° S, {abs(ex['earth']['center'][1]):.4f}° W; SRTMGL1.003 tile {ex['earth']['tile']}, extracted file SHA-256 {ex['earth']['dem_sha256'][:16]}…; {ex['earth']['grid_crs']}; {ex['earth']['mask']}, {100 * ex['earth']['excluded_fraction_60m']:.2f} % of cells excluded) "
              f"is compared with {ex['reference']['aoi_id']} (CTX DEM SHA-256 {ex['reference']['dem_sha256'][:16]}…) under the terrain-analogy profile, {d['method_version']}."})
    B.append({"type": "table", "caption": "Table 2. Worked example at 60 m. d, τ and δ in the feature units; s and contributions from full-precision values.",
              "header": ["Feature", "Earth window", "Jezero window", "$d$", r"$\tau$", r"$d/\tau$", "$s$", "$a$", "Points", r"$\delta$"],
              "rows": [[v["label"], v["earth_summary"], v["reference_summary"], f"{v['d']:.4f}", f"{v['tau']:.4f}", f"{v['d_over_tau']:.5f}", f"{v['s']:.6f}", f"{v['weight']:.2f}", f"{v['contribution']:.4f}", f"{v['delta']:.4f}"]
                       for v in (sl, re_)]})
    B.append({"type": "p", "text": f"With the full-precision values, $S_g$ = 0.5 × {sl['s']:.6f} + 0.5 × {re_['s']:.6f} = {ex['family_score']:.6f} and $A_{{\\mathrm{{obs}}}}$ = {ex['observed_index_full']:.4f}, reported by the API as {ex['observed_index_api']:.2f}; the service and an independent recomputation with the reference arithmetic agree " + ("exactly (difference below 10⁻⁹ index points)" if ex['agreement_abs'] < 1e-9 else f"to {ex['agreement_abs']:.1e} index points") + ". "
              f"Recombining the four-decimal similarities shown in the interface ({ex['displayed_s']['slope']:.4f} and {ex['displayed_s']['relative_elevation']:.4f}) gives {ex['index_from_displayed_s']:.3f}, which differs in the last decimal only because of display rounding. "
              f"Evidence coverage is $C$ = {ex['coverage']:.2f} (terrain only). Both scored distances are below their floors, so the window is not resolved from Jezero by these tests. "
              f"Across {ex['scenarios']} scenarios the index ranges {ex['index_range'][0]:.2f}–{ex['index_range'][1]:.2f}; the window shares rank {ex['rank']} with {ex['tie_group_size'] - 1} other windows. Local relief ({ex['diagnostics']['local_relief']['d']:.2f} m) and roughness ({ex['diagnostics']['roughness']['d']:.2f} m) are reported as diagnostics only."})
    B.append({"type": "h2", "text": "Discrimination checks"})
    B.append({"type": "p", "text": f"Against Jezero, the {bg['count']} background windows have a median index of {bg['median']:.1f}; {pct(bg['share_at_or_above']['90'])} score 90 or more and {pct(bg['share_at_or_above']['99'])} score 99 or more. "
              f"Slope alone and relative elevation alone give {pct(d['single_feature_jezero']['slope']['90'])} and {pct(d['single_feature_jezero']['relative_elevation']['90'])} at 90 or more. "
              f"The previous Phase 5 tolerances would give {pct(d['alt_tau_jezero']['phase5_tau']['90'])}, half the current tolerances {pct(d['alt_tau_jezero']['tau_x0.5']['90'])} and double {pct(d['alt_tau_jezero']['tau_x2']['90'])}. "
              f"Against the other Mars references, {min(d['background_share_90_mars'].values()) * 100:.0f}–{max(d['background_share_90_mars'].values()) * 100:.0f} % of background windows score 90 or more. "
              f"Synthetic controls scored {d['synthetic']['tilted_plane_15deg']:.1f} (a 15° tilted plane), {d['synthetic']['ridges_150m_2km']:.1f} (150 m ridges every 2 km), {d['synthetic']['fractal_relief_1500m']:.1f} (rough 1,500 m fractal relief) and {d['synthetic']['identical_copy']:.1f} (an identical copy of Jezero); "
              f"a gentle 300 m fractal surface scored {d['synthetic']['fractal_relief_300m']:.1f} because its distributions resemble Jezero's even though its spatial arrangement does not. "
              f"{d['population']['caveat']} The order of the five highest-scoring candidates {'is unchanged' if d['loro_top_order_stable'] else 'changes'} when the tolerance is recomputed with each region left out."})
    B.append({"type": "h2", "text": "Limitations and validation status"})
    B.append({"type": "list", "items": [
        "The equations, the reference values of Equation 7, the W1 implementation, eligibility gates and determinism are verified by automated tests against an independent reference implementation. The scientific claim that the index identifies useful analogues has not been validated against expert-labelled analogues, expert-chosen negative controls or field outcomes.",
        "Tolerances, weights and the redundancy threshold are project definitions. They are not fitted to labelled data and they depend on the background sample.",
        "At a 60 m grid the index separates low-relief from rugged terrain but does not order low-relief windows; about half of unselected Earth windows score 90 or more against each Mars reference.",
        "Distributions ignore spatial arrangement; no morphology descriptor is scored.",
        "Only terrain is measured. Geology, temperature (which fails a comparability audit), water and ice, surface processes, habitability, field access and mission safety are not assessed.",
        "SRTM (2000), CTX stereo (2006 onward) and LOLA record present-day surfaces. CTX stereo noise inflates slopes on very smooth plains, and planetary DEM vertical references differ from Earth's (relative elevation removes the offset but not tilts).",
        "Existing NASA and USGS work supports measuring terrain and using Earth analogues for specific questions; it does not endorse this index, its weights or its tolerances.",
    ]})
    B.append({"type": "h2", "text": "Software and versions"})
    sw = d["software"]
    B.append({"type": "p", "text": f"Python {sw['python']}, NumPy {sw['numpy']}, Rasterio {sw['rasterio']} with GDAL {sw['gdal']}, FastAPI {sw['fastapi']}. Method configuration {d['files']['method_config']['path']} (SHA-256 of LF text {d['files']['method_config']['sha256_lf'][:16]}…); calibration {d['files']['calibration']['path']} ({d['files']['calibration']['sha256_lf'][:16]}…). "
              "Scoring functions: " + "; ".join(d["files"]["scoring_code"]) + "."})
    B.append({"type": "h1", "text": "Results: measured terrain resemblance, Atacama south and Jezero"})
    B.append({"type": "p", "text": f"On the two scored terrain features at a 60 m grid, the Atacama south window differs from the Jezero window by {sl['d']:.2f}° in slope distribution and {re_['d']:.1f} m in relative-elevation distribution, "
              f"giving an experimental terrain evidence index of {ex['observed_index_api']:.1f} (scenario range {ex['index_range'][0]:.1f}–{ex['index_range'][1]:.1f}) with 100 % terrain-profile coverage. Both differences are within the resolution floor of these tests, "
              f"and the window shares rank {ex['rank']} with {ex['tie_group_size'] - 1} other low-relief windows whose order the data cannot resolve. The score is not distinctive: {pct(ex['background_share'])} of {bg['count']} unselected Earth windows score at least as high, and {pct(bg['share_at_or_above']['90'])} score 90 or more. "
              "The result shows that the two windows share low-relief terrain at this scale; it does not show that Atacama is the best overall Mars analogue, and it says nothing about geology, habitability or the safety of a base or landing site."})
    B.append({"type": "h2", "text": "References"})
    B.append({"type": "list", "items": [
        "NASA JPL (2013). NASA Shuttle Radar Topography Mission Global 1 arc second, V003. NASA EOSDIS Land Processes DAAC. doi:10.5067/MEaSUREs/SRTM/SRTMGL1.003.",
        "USGS Astrogeology Science Center (2021). Mars 2020 Science Investigation CTX DEM Mosaic. doi:10.5066/P906QQT8.",
        "USGS Astrogeology Science Center. Mars Reconnaissance Orbiter Context Camera controlled digital terrain models (STAC collection mro_ctx_controlled_usgs_dtms). doi:10.5066/P9JKVWR3.",
        "Smith, D. E. et al. LRO LOLA Gridded Data Records, LDEM_875S_20M. NASA Planetary Data System, LRO-L-LOLA-3-RDR-V1.",
        "ESA WorldCover project (2022). ESA WorldCover 10 m 2021 v200. CC-BY-4.0.",
        "Copernicus DEM GLO-30 (DLR e.V. and Airbus, provided under COPERNICUS by the European Union and ESA) and NASADEM_HGT.001, via Microsoft Planetary Computer.",
        "Grotzinger, J. P. et al. (2014). A habitable fluvio-lacustrine environment at Yellowknife Bay, Gale Crater, Mars. Science 343, 1242777. doi:10.1126/science.1242777.",
        "Golombek, M. et al. (2020). Geology of the InSight landing site on Mars. Nature Communications 11, 1014. doi:10.1038/s41467-020-14679-1.",
        "Golombek, M. P. et al. (2006). Geology of the Gusev cratered plains from the Spirit rover transverse. JGR Planets 111. doi:10.1029/2005JE002503.",
        "Malin, M. C. & Edgett, K. S. (2003). Evidence for persistent flow and aqueous sedimentation on early Mars. Science 302, 1931–1934. doi:10.1126/science.1090544.",
        "Stepinski, T. F. & Coradetti, S. (2004). Comparing morphologies of drainage basins on Mars and Earth using integral-geometry and neural maps. Geophysical Research Letters 31. doi:10.1029/2004GL020359.",
        "OECD/JRC (2008). Handbook on Constructing Composite Indicators: Methodology and User Guide. OECD Publishing.",
        "Watson, K. & Blaisdell, G. (2000). Salient characteristics for terrestrial analog engineering test sites. NASA NTRS 20000105009.",
    ]})
    return B


def _md_inline(text: str) -> str:
    return text


def render_markdown(d: dict, B: list[dict]) -> str:
    out = [f"<!-- Generated by backend/app/scripts/build_methods_paper.py from {d['method_version']} ({d['terrain_method']}). Do not edit by hand. -->", ""]
    for b in B:
        if b["type"] == "h1":
            out += [f"# {b['text']}", ""]
        elif b["type"] == "h2":
            out += [f"## {b['text']}", ""]
        elif b["type"] == "p":
            out += [_md_inline(b["text"]), ""]
        elif b["type"] == "eq":
            out += ["$$", f"{b['latex']} \\tag{{{b['n']}}}", "$$", ""]
        elif b["type"] == "table":
            out += [f"*{b['caption']}*", "", "| " + " | ".join(b["header"]) + " |", "|" + "---|" * len(b["header"])]
            out += ["| " + " | ".join(str(c) for c in row) + " |" for row in b["rows"]]
            out += [""]
        elif b["type"] == "list":
            out += [f"- {item}" for item in b["items"]] + [""]
    return "\n".join(out).rstrip() + "\n"


TEX_SPECIAL = {"&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "\\": r"\textbackslash{}"}


def _tex_text(text: str) -> str:
    import re
    text = text.replace("10⁻⁹", "$10^{-9}$")
    parts = re.split(r"(\$[^$]+\$)", text)
    out = []
    for p in parts:
        if p.startswith("$") and p.endswith("$") and len(p) > 1:
            out.append(p)
        else:
            out.append("".join(TEX_SPECIAL.get(c, c) for c in p))
    return "".join(out)


def render_latex(d: dict, B: list[dict]) -> str:
    out = [r"% Generated by backend/app/scripts/build_methods_paper.py from " + d["method_version"] + " (" + d["terrain_method"] + "). Do not edit by hand.",
           r"\documentclass[11pt,a4paper]{article}", r"\usepackage{amsmath}", r"\usepackage{fontspec}", r"\usepackage{unicode-math}",
           r"\setmainfont{Calibri}", r"\setmathfont{Cambria Math}", r"\usepackage[margin=2cm]{geometry}", r"\usepackage{booktabs,tabularx,array}",
           r"\usepackage[hidelinks]{hyperref}", r"\usepackage{fancyhdr}", r"\pagestyle{fancy}\fancyhf{}\renewcommand{\headrulewidth}{0pt}",
           r"\cfoot{\footnotesize TerraLuna \textperiodcentered{} " + d["method_version"] + r" \textperiodcentered{} page \thepage}",
           r"\sloppy\setlength{\parskip}{0.55em}\setlength{\parindent}{0pt}\renewcommand{\arraystretch}{1.25}", r"\begin{document}"]
    for b in B:
        if b["type"] == "h1":
            out.append(r"\section*{" + _tex_text(b["text"]) + "}")
        elif b["type"] == "h2":
            out.append(r"\subsection*{" + _tex_text(b["text"]) + "}")
        elif b["type"] == "p":
            out.append(_tex_text(b["text"]) + "\n")
        elif b["type"] == "eq":
            out.append(r"\begin{equation*}" + b["latex"] + r" \tag{" + str(b["n"]) + r"}\end{equation*}")
        elif b["type"] == "table":
            n = len(b["header"])
            spec = "l" + "X" * (n - 1) if n <= 4 else "p{2.2cm}p{2.5cm}p{2.5cm}" + ">{\\raggedleft\\arraybackslash}X" * (n - 3)
            size = "small" if n <= 4 else "scriptsize"
            out.append(r"\begin{" + size + r"}\noindent\textit{" + _tex_text(b["caption"]) + r"}\\[2pt]")
            out.append(r"\begin{tabularx}{\linewidth}{" + spec + r"}\toprule")
            out.append(" & ".join(r"\textbf{" + _tex_text(h) + "}" for h in b["header"]) + r" \\ \midrule")
            for row in b["rows"]:
                out.append(" & ".join(_tex_text(str(c)) for c in row) + r" \\")
            out.append(r"\bottomrule\end{tabularx}\end{" + size + "}" + "\n")
        elif b["type"] == "list":
            out.append(r"\begin{itemize}")
            out += [r"\item " + _tex_text(item) for item in b["items"]]
            out.append(r"\end{itemize}")
    out.append(r"\end{document}")
    return "\n".join(out) + "\n"


def build(write: bool = True, exact_check: bool = True) -> tuple[dict, list[dict], str]:
    data = collect(exact_check)
    B = blocks(data)
    md = render_markdown(data, B)
    if write:
        DOCS.mkdir(parents=True, exist_ok=True)
        (DOCS / "paper-data.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        (DOCS / "paper-content.json").write_text(json.dumps(B, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        (DOCS / "methods.md").write_text(md, encoding="utf-8", newline="\n")
        (DOCS / "methods.tex").write_text(render_latex(data, B), encoding="utf-8", newline="\n")
    return data, B, md


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Rebuild in memory and fail if docs/paper differs")
    args = parser.parse_args()
    if args.check:
        data, B, md = build(write=False, exact_check=False)
        committed = (DOCS / "methods.md").read_text(encoding="utf-8")
        raise SystemExit(0 if committed == md else "docs/paper/methods.md is out of date; run app.scripts.build_methods_paper")
    data, _, _ = build()
    ex = data["example"]
    print(json.dumps({"observed_index_full": ex["observed_index_full"], "api": ex["observed_index_api"], "from_displayed": ex["index_from_displayed_s"],
                      "agreement": ex["agreement_abs"], "exact_w1": ex["exact_w1_check"]}, indent=1))


if __name__ == "__main__":
    main()
