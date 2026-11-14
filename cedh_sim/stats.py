"""Small statistics helpers: confidence intervals and the games a verdict needs."""
from __future__ import annotations

import math

Z95 = 1.959964


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """95% Wilson interval for a rate of k out of n."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def rate_line(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{pct(k / n if n else 0)} ({k}/{n}, 95% range {pct(lo)} to {pct(hi)})"


def paired(diffs: list[float]) -> tuple[float, float, float]:
    """Mean of paired differences and its 95% interval."""
    n = len(diffs)
    if n == 0:
        return (0.0, -1.0, 1.0)
    m = sum(diffs) / n
    if n == 1:
        return (m, -1.0, 1.0)
    var = sum((d - m) ** 2 for d in diffs) / (n - 1)
    se = math.sqrt(var / n) if var > 0 else 0.0
    # with no variance at all yet (every pair identical), keep the interval honest-wide
    if se == 0.0:
        se = 0.5 / math.sqrt(n)
    return (m, m - Z95 * se, m + Z95 * se)


def games_needed(var: float, effect: float, power_z: float = 0.8416) -> int:
    """Pairs needed to detect a difference of `effect` (as a fraction) at 95% confidence and 80% power."""
    if effect <= 0:
        return 0
    return int(math.ceil((Z95 + power_z) ** 2 * var / (effect * effect)))


def variance(xs: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.25
    m = sum(xs) / n
    return sum((x - m) ** 2 for x in xs) / (n - 1)
