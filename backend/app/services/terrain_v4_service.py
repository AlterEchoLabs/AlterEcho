"""terrain-v4.0: Gaussian similarity on Wasserstein-1 distances between terrain-v3 distributions.

S = 100 * exp(-0.5 * ((x_E - x_P) / tau)^2) is the scalar form. For a distribution family the
"difference" is the Wasserstein-1 distance between two identically binned distributions, which is
expressed in the feature's own units (metres or degrees), so tau has the same units.
"""

from __future__ import annotations

import json
from math import exp, isfinite
from pathlib import Path
from typing import Any

import numpy as np

from app.models.schemas import DistributionSummary, TerrainV3Artifact

CONFIG_PATH = Path(__file__).resolve().parents[1] / "data" / "similarity.v4.json"
CONFIG: dict[str, Any] = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
SCALES = ("60", "120", "240")
UNIT_ALIASES = {"m": "metres", "metre": "metres", "metres": "metres", "meter": "metres", "meters": "metres",
                "deg": "degrees", "degree": "degrees", "degrees": "degrees", "°": "degrees"}


class TerrainMethodError(ValueError):
    pass


def gaussian_similarity(earth: float | None, planet: float | None, tau: float | None,
                        earth_units: str | None = None, planet_units: str | None = None) -> float | None:
    """S = 100 * exp(-0.5 * ((earth - planet) / tau)^2), or None when no valid score exists.

    Returns None (never 0) for missing values, non-finite values, tau <= 0, or mismatched units.
    """
    if earth is None or planet is None or tau is None:
        return None
    if not all(isinstance(v, (int, float)) and isfinite(v) for v in (earth, planet, tau)) or tau <= 0:
        return None
    if earth_units is not None or planet_units is not None:
        if UNIT_ALIASES.get(str(earth_units)) is None or UNIT_ALIASES.get(str(earth_units)) != UNIT_ALIASES.get(str(planet_units)):
            return None
    return 100.0 * exp(-0.5 * ((earth - planet) / tau) ** 2)


def wasserstein_1(reference: DistributionSummary, candidate: DistributionSummary) -> float:
    """W1 between two normalised fixed-bin histograms, in the feature's units."""
    if reference.bin_edges != candidate.bin_edges:
        raise TerrainMethodError("Distributions must share identical bin edges")
    ref, cand = np.asarray(reference.normalized_counts, dtype=float), np.asarray(candidate.normalized_counts, dtype=float)
    if ref.sum() <= 0 or cand.sum() <= 0:
        raise TerrainMethodError("Empty distribution")
    ref, cand = ref / ref.sum(), cand / cand.sum()
    # Integral of |F1 - F2| with each bin's mass at its lower edge (values beyond the last edge are
    # clipped into the last bin at processing time). Identical to the terrain-v3 distance.
    return float(np.sum(np.abs(np.cumsum(ref) - np.cumsum(cand)) * np.diff(np.asarray(reference.bin_edges, dtype=float))))


def _validate(families: dict, scale_weights: dict) -> None:
    for name, spec in families.items():
        if not (isinstance(spec["tau"], (int, float)) and spec["tau"] > 0):
            raise TerrainMethodError(f"tau for {name} must be positive")
        if spec["weight"] < 0:
            raise TerrainMethodError(f"weight for {name} must be non-negative")
    if abs(sum(s["weight"] for s in families.values()) - 1) > 1e-6:
        raise TerrainMethodError("family weights must sum to 1")
    if abs(sum(scale_weights.values()) - 1) > 1e-3:
        raise TerrainMethodError("scale weights must sum to 1")


def compare_v4(reference: TerrainV3Artifact, candidate: TerrainV3Artifact, families: dict | None = None,
               scale_weights: dict | None = None) -> dict[str, Any]:
    families = families or CONFIG["families"]
    scale_weights = scale_weights or CONFIG["scale_weights"]
    _validate(families, scale_weights)
    for artifact in (reference, candidate):
        if artifact.vertical_units != "metre" or artifact.horizontal_units != "metre":
            raise TerrainMethodError(f"{artifact.site_id}: horizontal and vertical units must be metres")
        if artifact.quality_status != "quality_checked":
            raise TerrainMethodError(f"{artifact.site_id}: terrain artifact did not pass quality checks")
    out: dict[str, Any] = {}
    for name, spec in families.items():
        per_scale = {}
        for scale in SCALES:
            if scale_weights.get(scale, 0) <= 0:
                continue
            d = wasserstein_1(reference.scales[scale].distributions[spec["distribution"]], candidate.scales[scale].distributions[spec["distribution"]])
            per_scale[scale] = {"w1": d, "index": gaussian_similarity(d, 0.0, spec["tau"]), "scale_weight": scale_weights[scale]}
        weight_sum = sum(v["scale_weight"] for v in per_scale.values())
        family_index = sum(v["index"] * v["scale_weight"] for v in per_scale.values()) / weight_sum
        out[name] = {"index": family_index, "weight": spec["weight"], "tau": spec["tau"], "units": spec["units"], "by_scale": per_scale}
    index = sum(v["index"] * v["weight"] for v in out.values())
    return {"methodology_version": CONFIG["methodology_version"], "terrain_index": index, "families": out}


def perturbed_configurations() -> list[tuple[str, dict, dict]]:
    """Deterministic method-parameter perturbations used for ranking sensitivity."""
    base_f, base_s = CONFIG["families"], CONFIG["scale_weights"]
    sens = CONFIG["sensitivity"]
    configs: list[tuple[str, dict, dict]] = [("nominal", base_f, base_s)]
    for name in base_f:
        for factor in (1 - sens["weight_perturbation_fraction"], 1 + sens["weight_perturbation_fraction"]):
            raw = {k: dict(v, weight=v["weight"] * (factor if k == name else 1.0)) for k, v in base_f.items()}
            total = sum(v["weight"] for v in raw.values())
            configs.append((f"weight_{name}_x{factor:.1f}", {k: dict(v, weight=v["weight"] / total) for k, v in raw.items()}, base_s))
        for factor in (1 - sens["tau_perturbation_fraction"], 1 + sens["tau_perturbation_fraction"]):
            configs.append((f"tau_{name}_x{factor:.1f}", {k: dict(v, tau=v["tau"] * (factor if k == name else 1.0)) for k, v in base_f.items()}, base_s))
    for label, weights in sens["scale_weight_alternatives"].items():
        configs.append((f"scales_{label}", base_f, weights))
    return configs
