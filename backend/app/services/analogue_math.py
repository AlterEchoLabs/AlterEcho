"""analogue-method-v1.0 arithmetic (production implementation).

For feature k measured in the same units on both bodies:
    scalar        d_k = |x_E,k - x_P,k|
    distribution  d_k = W1(F_E,k, F_P,k) = integral_0^1 |F_E,k^-1(u) - F_P,k^-1(u)| du
    transform     s_k = exp(-ln 2 * (d_k / tau_k)^2)          d = tau -> 0.5, d = 2 tau -> 0.0625
Within family g (nonredundant features, a_k|g summing to 1, every required feature eligible):
    S_g = sum_k a_k|g * s_k
Across planned families (w_g summing to 1, I_g = 1 only for families passing comparability rules):
    observed_index    = 100 * sum_g w_g I_g S_g / sum_g w_g I_g     (undefined -> None when no family qualifies)
    evidence_coverage = sum_g w_g I_g
s_k is a project-defined bounded index, not a probability, a confidence level or a percentage of identity.
Missing or incomparable data are never a similarity of zero: they make the feature or family ineligible.
"""

from __future__ import annotations

from math import exp, isfinite, log
from typing import Iterable, Mapping, Sequence

import numpy as np

LN2 = log(2.0)
UNIT_ALIASES = {"m": "metres", "metre": "metres", "metres": "metres", "meter": "metres", "meters": "metres",
                "deg": "degrees", "degree": "degrees", "degrees": "degrees", "°": "degrees", "k": "kelvin", "kelvin": "kelvin"}


class AnalogueMethodError(ValueError):
    pass


def _finite(*values: float) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v) for v in values)


def same_units(a: str | None, b: str | None) -> bool:
    ua, ub = UNIT_ALIASES.get(str(a).lower()), UNIT_ALIASES.get(str(b).lower())
    return ua is not None and ua == ub


def scalar_distance(x_earth: float | None, x_planet: float | None, units_earth: str, units_planet: str) -> float | None:
    """|x_E - x_P| in shared units, or None when a value is missing/non-finite or units differ."""
    if x_earth is None or x_planet is None or not _finite(x_earth, x_planet) or not same_units(units_earth, units_planet):
        return None
    return abs(float(x_earth) - float(x_planet))


def similarity(distance: float | None, tau: float | None) -> float | None:
    """s = exp(-ln2 (d/tau)^2) in [0, 1]; None for missing, negative, non-finite inputs or tau <= 0."""
    if distance is None or tau is None or not _finite(distance, tau) or distance < 0 or tau <= 0:
        return None
    return exp(-LN2 * (float(distance) / float(tau)) ** 2)


def w1_samples(values_a: Sequence[float], values_b: Sequence[float], weights_a: Sequence[float] | None = None,
               weights_b: Sequence[float] | None = None) -> float:
    """Exact W1 between two weighted empirical distributions (NaN samples are masked out first)."""
    a, b = np.asarray(values_a, dtype=float), np.asarray(values_b, dtype=float)
    wa = np.ones_like(a) if weights_a is None else np.asarray(weights_a, dtype=float)
    wb = np.ones_like(b) if weights_b is None else np.asarray(weights_b, dtype=float)
    if a.shape != wa.shape or b.shape != wb.shape:
        raise AnalogueMethodError("values and weights must have equal length")
    keep_a, keep_b = np.isfinite(a) & np.isfinite(wa) & (wa > 0), np.isfinite(b) & np.isfinite(wb) & (wb > 0)
    if (wa < 0).any() or (wb < 0).any():
        raise AnalogueMethodError("weights must be non-negative")
    a, wa, b, wb = a[keep_a], wa[keep_a], b[keep_b], wb[keep_b]
    if a.size == 0 or b.size == 0:
        raise AnalogueMethodError("each distribution needs at least one valid weighted sample")
    xs = np.unique(np.concatenate([a, b]))
    cdf_a = np.array([wa[a <= x].sum() for x in xs]) / wa.sum()
    cdf_b = np.array([wb[b <= x].sum() for x in xs]) / wb.sum()
    return float(np.sum(np.abs(cdf_a - cdf_b)[:-1] * np.diff(xs)))


def w1_exact(values_a: Sequence[float], values_b: Sequence[float]) -> float:
    """Exact W1 between two equal-weight empirical distributions of any sizes (NaN masked), O(n log n)."""
    a = np.sort(np.asarray(values_a, dtype=float)[np.isfinite(values_a)])
    b = np.sort(np.asarray(values_b, dtype=float)[np.isfinite(values_b)])
    if a.size == 0 or b.size == 0:
        raise AnalogueMethodError("each distribution needs at least one valid sample")
    xs = np.unique(np.concatenate([a, b]))
    cdf_a = np.searchsorted(a, xs, side="right") / a.size
    cdf_b = np.searchsorted(b, xs, side="right") / b.size
    return float(np.sum(np.abs(cdf_a - cdf_b)[:-1] * np.diff(xs)))


def w1_quantile_functions(q_a: Sequence[float], q_b: Sequence[float]) -> float:
    """W1 from two quantile functions on the same midpoint u grid: mean |Q_E(u) - Q_P(u)|."""
    if len(q_a) == 0 or len(q_a) != len(q_b):
        raise AnalogueMethodError("quantile functions must be non-empty and share one u grid")
    a, b = np.asarray(q_a, dtype=float), np.asarray(q_b, dtype=float)
    if not (np.isfinite(a).all() and np.isfinite(b).all()):
        raise AnalogueMethodError("quantile functions must be finite")
    return float(np.mean(np.abs(a - b)))


def family_score(features: Mapping[str, tuple[float, float | None, bool]]) -> float | None:
    """S_g = sum a_k s_k over features {k: (a_k, s_k or None, required)}.

    Returns None when any required feature has no similarity (a family is never scored from an
    incomplete required set) or when the scored weights do not sum to 1.
    """
    if not features:
        return None
    if any(not _finite(a) or a < 0 for a, _, _ in features.values()):
        raise AnalogueMethodError("feature weights must be finite and non-negative")
    if abs(sum(a for a, _, _ in features.values()) - 1.0) > 1e-9:
        raise AnalogueMethodError("feature weights within a family must sum to 1")
    if any(required and s is None for _, s, required in features.values()):
        return None
    if any(s is not None and not 0.0 <= s <= 1.0 for _, s, _ in features.values()):
        raise AnalogueMethodError("similarities must lie in [0, 1]")
    return float(sum(a * s for a, s, _ in features.values() if s is not None))


def observed_index(families: Mapping[str, tuple[float, bool, float | None]]) -> tuple[float | None, float]:
    """(100 sum w I S / sum w I, sum w I) over {g: (w_g, I_g, S_g)}; index None when no family qualifies."""
    if not families:
        raise AnalogueMethodError("a profile needs planned families")
    weights = [w for w, _, _ in families.values()]
    if any(not _finite(w) or w < 0 for w in weights):
        raise AnalogueMethodError("family weights must be finite and non-negative")
    if abs(sum(weights) - 1.0) > 1e-9:
        raise AnalogueMethodError("planned family weights must sum to 1")
    coverage = numerator = 0.0
    for w, eligible, score in families.values():
        if eligible:
            if score is None or not _finite(score) or not 0.0 <= score <= 1.0:
                raise AnalogueMethodError("an eligible family needs a score in [0, 1]")
            coverage += w
            numerator += w * score
    return (None if coverage == 0 else 100.0 * numerator / coverage), coverage


def contributions(features: Mapping[str, tuple[float, float | None]], family_weight_share: float = 1.0) -> dict[str, float | None]:
    """Each feature's share of the observed index points: 100 * share * a_k * s_k."""
    return {k: (round(100.0 * family_weight_share * a * s, 4) if s is not None else None) for k, (a, s) in features.items()}


def competition_ranks(groups: Iterable[Sequence[str]]) -> dict[str, int]:
    """Standard competition ranking over ordered tie groups: members share the group's first position."""
    ranks: dict[str, int] = {}
    position = 1
    for group in groups:
        for member in group:
            ranks[member] = position
        position += len(group)
    return ranks
