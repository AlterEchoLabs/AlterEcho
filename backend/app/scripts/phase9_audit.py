"""Phase 9 audit: trace the terrain index from DEM to display, and decompose the v4 -> v1.0 change.

Prints Markdown tables (used in docs/PHASE9_AUDIT.md) built only from stored artifacts:
terrain-v3 binned distributions (v4 inputs), terrain-v5 quantile artifacts, the v4 evaluation and the
analogue-v1 calibration. Usage (from backend/):  python -m app.scripts.phase9_audit
"""

from __future__ import annotations

import json
from math import exp, log

from app.services import analogue_v1_service as av
from app.services.analogue_math import w1_quantile_functions
from app.services.geospatial_service import GEO_DATA, load_manifest
from app.services.catalog_service import get_site
from app.services.terrain_v3_service import load_v3_artifact
from app.services.terrain_v4_service import CONFIG as V4, compare_v4, wasserstein_1

SITES = ["earth-atacama", "earth-craters-of-the-moon", "earth-hanksville-mdrs", "earth-meteor-crater", "earth-atacama-south", "earth-danakil", "earth-upper-mustang", "earth-ladakh"]
V4_FAMILY = {"slope": "slope_deg", "local_relief": "local_relief_m", "roughness": "roughness_m", "relative_elevation": "elevation_relative_m"}


def binned_w1(ref, cand, family, scale="60"):
    d = V4_FAMILY[family]
    return wasserstein_1(ref.scales[scale].distributions[d], cand.scales[scale].distributions[d])


def exact_w1(ref5, cand5, family, scale="60"):
    return w1_quantile_functions(cand5["scales"][scale]["features"][family]["quantiles"], ref5["scales"][scale]["features"][family]["quantiles"])


def idx(w1s: dict, taus: dict, families, k: float) -> float:
    return 100 * sum(exp(-k * (w1s[f] / taus[f]) ** 2) for f in families) / len(families)


def main() -> None:
    ref3, ref5 = load_v3_artifact("mars-jezero"), av.artifact("mars-jezero")
    cal = av.calibration()
    tau_v4 = {f: V4["families"][f]["tau"] for f in V4_FAMILY}
    tau_v1 = {f: cal["tau"][f]["60"] for f in V4_FAMILY}
    scored = cal["redundancy"]["scored"]
    comp = {r.site_id: r for r in av.compare("mars-jezero", "terrain_analogy").results}
    print("### Trace at 60 m (Jezero reference)\n")
    print("| Site | DEM tile(s) · SHA-256 | Built-up excluded | Slope median E / P (°) | Rel. elev. p10–p90 E / P (m) | Binned W1 slope (v4) | Exact W1 slope | Binned W1 rel. elev. (v4) | Exact W1 rel. elev. |")
    print("|---|---|---|---|---|---|---|---|---|")
    p = ref5["scales"]["60"]["features"]
    for s in SITES:
        site, a5, a3 = get_site(s), av.artifact(s), load_v3_artifact(s)
        m = load_manifest(site.source_id)
        tiles = "+".join(t["tile_id"] if isinstance(t, dict) else t.tile_id for t in (m.tiles or [])) or m.filename
        e = a5["scales"]["60"]["features"]
        q = lambda feats, f, i: feats[f]["quantiles"][i]
        print(f"| {site.name} | {tiles} · {a5['source_sha256'][:12]}… | {a5['scales']['60']['excluded_fraction']:.2%} | {e['slope']['median']:.2f} / {p['slope']['median']:.2f} | "
              f"{q(e,'relative_elevation',50):.1f}…{q(e,'relative_elevation',449):.1f} / {q(p,'relative_elevation',50):.1f}…{q(p,'relative_elevation',449):.1f} | "
              f"{binned_w1(ref3, a3, 'slope'):.3f} | {exact_w1(ref5, a5, 'slope'):.3f} | {binned_w1(ref3, a3, 'relative_elevation'):.2f} | {exact_w1(ref5, a5, 'relative_elevation'):.2f} |")

    print("\n### Why the v4 values cluster near 99.9: d/τ under v4 (60 m)\n")
    print("| Site | slope d/τ | local relief d/τ | roughness d/τ | rel. elev. d/τ | v4 index (published) |")
    print("|---|---|---|---|---|---|")
    for s in SITES:
        a3 = load_v3_artifact(s)
        r = {f: binned_w1(ref3, a3, f) / tau_v4[f] for f in V4_FAMILY}
        print(f"| {get_site(s).name} | {r['slope']:.3f} | {r['local_relief']:.3f} | {r['roughness']:.3f} | {r['relative_elevation']:.3f} | {compare_v4(ref3, a3)['terrain_index']:.2f} |")

    print("\n### Stepwise decomposition (each column changes one thing)\n")
    print("| Site | v4 published (binned, 3 scales, 4 families, τ v4, exp(−0.5x²)) | 60 m only | exact W1 | scored features only (slope, rel. elev.) | ln 2 transform | τ from Earth contrast = v1.0 | v1.0 scenario range | v1.0 rank |")
    print("|---|---|---|---|---|---|---|---|---|")
    fam4 = list(V4_FAMILY)
    for s in SITES:
        a3, a5 = load_v3_artifact(s), av.artifact(s)
        b = {f: binned_w1(ref3, a3, f) for f in fam4}
        x = {f: exact_w1(ref5, a5, f) for f in fam4}
        steps = [compare_v4(ref3, a3)["terrain_index"], idx(b, tau_v4, fam4, 0.5), idx(x, tau_v4, fam4, 0.5), idx(x, tau_v4, scored, 0.5),
                 idx(x, tau_v4, scored, log(2)), idx(x, tau_v1, scored, log(2))]
        c = comp.get(s)
        rng = c.sensitivity.index_range if c and c.sensitivity else None
        rank = (c.rank if c and c.rank else ("excluded" if c and c.state == "excluded" else "—"))
        print(f"| {get_site(s).name} | " + " | ".join(f"{v:.2f}" for v in steps) + f" | {rng[0]:.1f}–{rng[1]:.1f} | {rank} |" if rng else
              f"| {get_site(s).name} | " + " | ".join(f"{v:.2f}" for v in steps) + f" | — | {rank} |")

    print("\n### v1.0 per-feature values (60 m)\n")
    print("| Site | slope d (°) | τ | d/τ | s | δ | rel. elev. d (m) | τ | d/τ | s | δ | index | resolution |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in SITES:
        c = comp[s]
        t = next(f for f in c.families if f.family == "terrain")
        f = {r.feature: r for r in t.features}
        sl, re_ = f["slope"], f["relative_elevation"]
        fmt = lambda r: f"{r.distance:.3f} | {r.tau:.2f} | {(r.d_over_tau if r.d_over_tau is not None else r.distance / r.tau):.3f} | {(r.similarity if r.similarity is not None else exp(-log(2) * (r.distance / r.tau) ** 2)):.4f} | {r.delta:.2f}"
        print(f"| {c.site_name} | {fmt(sl)} | {fmt(re_)} | {c.observed_index if c.observed_index is not None else 'excluded'} | {c.resolution} |")
    print("\nResolution floor:", json.dumps(cal["resolution_floor"]))
    print("Tolerances (60 m):", {f: cal["tau"][f]["60"] for f in V4_FAMILY}, "leave-one-tile-out:", {f: cal["tau"][f]["leave_one_tile_out_60"] for f in V4_FAMILY})
    print("Base rate v1.0:", cal["base_rate"], " v4:", json.loads((GEO_DATA / "processed" / "evaluation" / "terrain-v4-evaluation.json").read_text())["base_rate"]["share_at_or_above"])


if __name__ == "__main__":
    main()
