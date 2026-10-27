import pytest

from gateway_harness.contracts import Verdict
from gateway_harness.probe.stats import decide, wilson


def test_wilson_known_values():
    assert wilson(0, 0) == (0.0, 1.0)

    # k=45, n=50 -> p_hat = 0.90
    lo, hi = wilson(45, 50)
    assert lo == pytest.approx(0.7859, abs=0.01)
    assert hi == pytest.approx(0.9576, abs=0.01)


def test_decide_early_reject():
    # 10 losses out of 10 -> non-loss = 0
    verdicts = [Verdict.LOSS] * 10
    # p0 = 0.85, delta = 0.05 -> theta = 0.80
    assert decide(verdicts, p0=0.85, delta=0.05, n_early=10) == "reject"


def test_decide_early_accept():
    # 30 wins out of 30 -> non-loss = 30
    verdicts = [Verdict.WIN] * 30
    # p0 = 0.80, delta = 0.05 -> theta = 0.75
    # Wilson lo for 30/30 is ~0.887 > 0.75
    assert decide(verdicts, p0=0.80, delta=0.05, n_min=30) == "accept"


def test_decide_continue():
    # Only 15 samples with mixed results
    verdicts = [Verdict.WIN] * 10 + [Verdict.LOSS] * 5
    assert decide(verdicts, p0=0.80, delta=0.05, n_min=30, n_early=10) == "continue"


def test_decide_max_samples_boundary():
    # At n_max = 60
    # 30 wins, 30 losses -> p_hat = 0.50, lo ~ 0.38
    verdicts = [Verdict.WIN] * 30 + [Verdict.LOSS] * 30
    # theta = 0.75 -> lo < theta -> reject
    assert decide(verdicts, p0=0.80, delta=0.05, n_max=60) == "reject"
