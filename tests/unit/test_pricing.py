from gateway_harness.pricing import cost, price_per_mtok


def test_pricing_known_model():
    c = cost("gpt-4o", prompt_tokens=1000, completion_tokens=500, cached_tokens=0)
    assert c is not None
    assert c > 0.0
    # 1000 * 2.5e-6 ($0.0025) + 500 * 1e-5 ($0.005) = $0.0075
    assert abs(c - 0.0075) < 1e-5

    # With caching
    c_cached = cost("gpt-4o", prompt_tokens=1000, completion_tokens=500, cached_tokens=500)
    assert c_cached is not None
    assert c_cached < c

    prices = price_per_mtok("gpt-4o")
    assert prices is not None
    assert prices[0] > 0
    assert prices[1] > 0


def test_pricing_unknown_model():
    c = cost("unknown-nonexistent-model-xyz", prompt_tokens=100, completion_tokens=10)
    assert c is None

    p = price_per_mtok("unknown-nonexistent-model-xyz")
    assert p is None
