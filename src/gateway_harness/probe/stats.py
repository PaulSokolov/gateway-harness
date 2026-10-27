"""Pure statistical evaluation functions: Wilson score confidence intervals and sequential testing."""

import math
from typing import Literal

from gateway_harness.contracts import Verdict


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Calculate the Wilson score confidence interval for a binomial proportion.

    Returns (lower_bound, upper_bound).
    """
    if n <= 0:
        return 0.0, 1.0

    p_hat = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p_hat + z2 / (2.0 * n)) / denom
    margin = (z * math.sqrt((p_hat * (1.0 - p_hat) / n) + (z2 / (4.0 * n * n)))) / denom

    lo = max(0.0, center - margin)
    hi = min(1.0, center + margin)
    return round(lo, 4), round(hi, 4)


def decide(
    verdicts: list[Verdict],
    p0: float,
    delta: float = 0.05,
    n_min: int = 30,
    n_early: int = 10,
    n_max: int = 60,
) -> Literal["accept", "reject", "continue"]:
    """Sequential probability ratio test (SPRT) early-stopping decision on pairwise verdicts.

    Non-loss = WIN or TIE. Non-inferiority threshold = p0 - delta.
    """
    n = len(verdicts)
    if n == 0:
        return "continue"

    k = sum(1 for v in verdicts if v in (Verdict.WIN, Verdict.TIE, "win", "tie"))
    lo, hi = wilson(k, n)
    theta = p0 - delta

    # 1. Early rejection: upper bound below non-inferiority threshold
    if n >= n_early and hi < theta:
        return "reject"

    # 2. Acceptance: lower bound clears non-inferiority threshold after minimum sample size
    if n >= n_min and lo >= theta:
        return "accept"

    # 3. Maximum sample cap reached
    if n >= n_max:
        return "accept" if lo >= theta else "reject"

    return "continue"
