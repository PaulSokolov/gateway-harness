from gateway_harness.catalog import CatalogModel
from gateway_harness.funnel.cluster import ClusterStats
from gateway_harness.funnel.gate import gate
from gateway_harness.funnel.value import ScoredCluster
from gateway_harness.settings import Settings


def _make_scored_cluster(count: int = 500, distinct_days: int = 5, savings: float = 50.0):
    stats = ClusterStats(
        tenant_id="tenant_1",
        requested_model="claude-3-5-sonnet",
        workflow_sig="sig1",
        template_id="tpl1",
        count=count,
        distinct_days=distinct_days,
        total_cost=25.0,
        p50_prompt_tokens=500,
        p99_prompt_tokens=1000,
        p50_completion_tokens=200,
        p99_completion_tokens=500,
        cached_token_share=0.0,
        shape_mode="one_shot_templated",
        has_tools=False,
        has_images=False,
        has_response_format=False,
        error_rate=0.0,
        length_trunc_rate=0.0,
        first_seen=None,
        last_seen=None,
    )
    cand = CatalogModel(
        "gemini-2.5-flash",
        "google/gemini-2.5-flash",
        in_price=0.075,
        out_price=0.3,
        max_input_tokens=1000000,
        supports_tools=True,
        supports_vision=True,
        supports_response_schema=True,
    )
    return ScoredCluster(
        cluster=stats,
        eligible=True,
        ineligible_reason=None,
        best_candidate=cand,
        best_candidate_name="gemini-2.5-flash",
        projected_monthly_savings=savings,
        projected_savings_pct=0.75,
        current_unit_cost=0.05,
        projected_unit_cost=0.005,
    )


def test_gate_passing():
    settings = Settings(
        OBSERVATION_DAYS=10,
        MIN_CLUSTER_REQUESTS=200,
        MIN_RECURRENCE_DAYS=3,
        GATE_MARGIN=3.0,
        MIN_SAVINGS_PCT=0.30,
    )
    sc = _make_scored_cluster(count=500, distinct_days=5, savings=50.0)

    res = gate(sc, settings, observation_days=10)
    assert res.passed is True
    assert len(res.reasons) == 0
    assert res.savings_to_probe_ratio >= 3.0


def test_gate_failing_conditions():
    settings = Settings(
        OBSERVATION_DAYS=10,
        MIN_CLUSTER_REQUESTS=200,
        MIN_RECURRENCE_DAYS=3,
        GATE_MARGIN=3.0,
        MIN_SAVINGS_PCT=0.30,
    )

    # 1. Volume too low
    sc_low_vol = _make_scored_cluster(count=50)
    res_vol = gate(sc_low_vol, settings, observation_days=10)
    assert res_vol.passed is False
    assert any("below minimum threshold" in r for r in res_vol.reasons)

    # 2. Distinct days too low
    sc_low_days = _make_scored_cluster(distinct_days=1)
    res_days = gate(sc_low_days, settings, observation_days=10)
    assert res_days.passed is False
    assert any("below recurrence requirement" in r for r in res_days.reasons)

    # 3. Observation window not reached
    sc_normal = _make_scored_cluster()
    res_obs = gate(sc_normal, settings, observation_days=4)
    assert res_obs.passed is False
    assert any("Observation period" in r for r in res_obs.reasons)
