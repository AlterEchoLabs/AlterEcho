"""Stepwise decomposition of the terrain-v4.0 -> analogue-method-v1.0 change, from stored artifacts only.

Each step changes one thing, so the cause of the historical near-99.9 cluster can be read directly:
v4 published -> 60 m only -> exact quantile W1 -> nonredundant features -> ln 2 transform -> Earth-contrast tau.
"""

from __future__ import annotations

from functools import lru_cache
from math import exp, log

from app.services import analogue_v1_service as av
from app.services.analogue_math import w1_quantile_functions
from app.services.catalog_service import get_site
from app.services.terrain_v3_service import load_v3_artifact
from app.services.terrain_v4_service import CONFIG as V4, compare_v4, wasserstein_1

V4_FAMILY = {"slope": "slope_deg", "local_relief": "local_relief_m", "roughness": "roughness_m", "relative_elevation": "elevation_relative_m"}
AUDIT_SITES = ["earth-atacama", "earth-craters-of-the-moon", "earth-hanksville-mdrs", "earth-meteor-crater", "earth-atacama-south", "earth-danakil", "earth-upper-mustang", "earth-ladakh"]
STEPS = ["v4 published (binned W1, 60/120/240 m, four families, tau v4, exp(-0.5 x^2))", "60 m only", "exact quantile W1",
         "scored features only (slope, relative elevation)", "ln 2 transform", "tau from Earth terrain contrast (= v1.0)"]


def _index(w1s: dict, taus: dict, families, k: float) -> float:
    return 100 * sum(exp(-k * (w1s[f] / taus[f]) ** 2) for f in families) / len(families)


def decomposition() -> dict:
    return _decomposition(av._signature())


@lru_cache(maxsize=2)
def _decomposition(_sig: tuple) -> dict:
    ref3, ref5 = load_v3_artifact("mars-jezero"), av.artifact("mars-jezero")
    cal = av.calibration()
    tau_v4 = {f: V4["families"][f]["tau"] for f in V4_FAMILY}
    tau_v1 = {f: cal["tau"][f]["60"] for f in V4_FAMILY}
    scored = cal["redundancy"]["scored"]
    rows = []
    for s in AUDIT_SITES:
        a3, a5 = load_v3_artifact(s), av.artifact(s)
        if not a3 or not a5:
            continue
        binned = {f: wasserstein_1(ref3.scales["60"].distributions[d], a3.scales["60"].distributions[d]) for f, d in V4_FAMILY.items()}
        exact = {f: w1_quantile_functions(a5["scales"]["60"]["features"][f]["quantiles"], ref5["scales"]["60"]["features"][f]["quantiles"]) for f in V4_FAMILY}
        fam = list(V4_FAMILY)
        steps = [compare_v4(ref3, a3)["terrain_index"], _index(binned, tau_v4, fam, 0.5), _index(exact, tau_v4, fam, 0.5),
                 _index(exact, tau_v4, scored, 0.5), _index(exact, tau_v4, scored, log(2)), _index(exact, tau_v1, scored, log(2))]
        rows.append({"site_id": s, "site_name": get_site(s).name, "steps": [round(v, 2) for v in steps],
                     "v4_d_over_tau": {f: round(binned[f] / tau_v4[f], 3) for f in fam},
                     "binned_w1_60": {f: round(binned[f], 3) for f in fam}, "exact_w1_60": {f: round(exact[f], 3) for f in fam}})
    return {"steps": STEPS, "rows": rows, "tau_v4": tau_v4, "tau_v1": tau_v1,
            "finding": ("Under terrain-v4.0 every low-relief window had d/tau between 0.016 and 0.15 on every family, so each family scored at least 0.99. "
                        "Phase 5 tolerances were 10-20 times the observed differences; local relief and roughness duplicated slope and had the smallest ratios; "
                        "and binned W1 read 10-20 % low. Even after correction, several windows remain inside the measurement resolution floor, "
                        "and about half of unselected Earth windows score 90 or more: a high terrain index mostly means low relief.")}
