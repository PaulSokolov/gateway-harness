from gateway_harness.metrics import (
    DECISIONS_TOTAL,
    POLICIES_ACTIVE,
    REQUESTS_TOTAL,
)


def test_metrics_increment():
    before = DECISIONS_TOTAL.labels(reason="test_reason")._value.get()
    DECISIONS_TOTAL.labels(reason="test_reason").inc()
    after = DECISIONS_TOTAL.labels(reason="test_reason")._value.get()
    assert after == before + 1

    req_before = REQUESTS_TOTAL.labels(status="success", model="gpt-4o", optimized="true")._value.get()
    REQUESTS_TOTAL.labels(status="success", model="gpt-4o", optimized="true").inc(2)
    req_after = REQUESTS_TOTAL.labels(status="success", model="gpt-4o", optimized="true")._value.get()
    assert req_after == req_before + 2

    POLICIES_ACTIVE.set(5)
    assert POLICIES_ACTIVE._value.get() == 5
