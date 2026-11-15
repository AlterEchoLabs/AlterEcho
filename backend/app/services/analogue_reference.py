"""Standard-library reference arithmetic from the AlterEcho analogue-method handoff (section 9), verbatim.

Used only as an independent cross-check of the production implementation in analogue_math.py.
It does not read DEMs, choose tolerances or validate an analogue.
"""

from math import exp, isfinite, log


def similarity(distance, tolerance):
    if not (isfinite(distance) and isfinite(tolerance)):
        raise ValueError("distance and tolerance must be finite")
    if distance < 0 or tolerance <= 0:
        raise ValueError("distance >= 0 and tolerance > 0 required")
    return exp(-log(2) * (distance / tolerance) ** 2)


def weighted_w1(values_a, weights_a, values_b, weights_b):
    def clean(values, weights):
        if len(values) != len(weights) or not values:
            raise ValueError("equal nonempty value and weight lists required")
        out = []
        for x, w in zip(values, weights):
            if not (isfinite(x) and isfinite(w)) or w < 0:
                raise ValueError("finite values and nonnegative weights required")
            if w:
                out.append((float(x), float(w)))
        total = sum(w for _, w in out)
        if total <= 0:
            raise ValueError("at least one positive weight required")
        return [(x, w / total) for x, w in out]
    a = clean(values_a, weights_a)
    b = clean(values_b, weights_b)
    events = []
    events.extend((x, w, 0.0) for x, w in a)
    events.extend((x, 0.0, w) for x, w in b)
    events.sort(key=lambda item: item[0])
    cdf_a = cdf_b = total = 0.0
    i = 0
    while i < len(events):
        x = events[i][0]
        while i < len(events) and events[i][0] == x:
            cdf_a += events[i][1]
            cdf_b += events[i][2]
            i += 1
        if i < len(events):
            total += abs(cdf_a - cdf_b) * (events[i][0] - x)
    return total


def observed_index(families):
    # Mapping family -> (planned_weight, eligible, similarity_or_None).
    # All planned weights must sum to 1. Family similarity is in [0,1].
    if not families:
        raise ValueError("profile requires planned families")
    weight_sum = sum(row[0] for row in families.values())
    if any(not isfinite(row[0]) or row[0] < 0 for row in families.values()):
        raise ValueError("invalid family weight")
    if abs(weight_sum - 1.0) > 1e-9:
        raise ValueError("planned family weights must sum to one")
    coverage = numerator = 0.0
    for weight, eligible, score in families.values():
        if eligible:
            if score is None or not isfinite(score) or not 0 <= score <= 1:
                raise ValueError("eligible family requires score in [0,1]")
            coverage += weight
            numerator += weight * score
    return (None if coverage == 0 else 100 * numerator / coverage), coverage
