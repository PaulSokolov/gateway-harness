from gateway_harness.catalog import CatalogModel
from gateway_harness.funnel.cluster import ClusterStats
from gateway_harness.funnel.value import score


def _make_dummy_stats(shape: str = "one_shot_templated", has_tools: bool = False, count: int = 1000):
    return ClusterStats(
        tenant_id="tenant_1",
        requested_model="claude-3-5-sonnet",
        workflow_sig="sig1",
        template_id="tpl1",
        count=count,
        distinct_days=5,
        total_cost=15.0,  # $0.015 per request
        p50_prompt_tokens=1000,
        p99_prompt_tokens=2000,
        p50_completion_tokens=500,
        p99_completion_tokens=1000,
        cached_token_share=0.0,
        shape_mode=shape,
        has_tools=has_tools,
        has_images=False,
        has_response_format=False,
        error_rate=0.01,
        length_trunc_rate=0.0,
        first_seen=None,
        last_seen=None,
    )


def test_score_eligible_cluster():
    catalog = [
        CatalogModel(
            "claude-3-5-sonnet",
            "anthropic/claude-3-5-sonnet",
            in_price=3.0,
            out_price=15.0,
            max_input_tokens=200000,
            supports_tools=True,
            supports_vision=True,
            supports_response_schema=True,
        ),
        CatalogModel(
            "gemini-2.5-flash",
            "google/gemini-2.5-flash",
            in_price=0.075,
            out_price=0.30,
            max_input_tokens=1000000,
            supports_tools=True,
            supports_vision=True,
            supports_response_schema=True,
        ),
    ]

    stats = _make_dummy_stats(shape="one_shot_templated")
    res = score(stats, catalog, window_days=30)

    assert res.eligible is True
    assert res.best_candidate_name == "gemini-2.5-flash"
    assert res.projected_monthly_savings > 10.0
    assert res.projected_savings_pct > 0.80


def test_score_ineligible_shape_or_tools():
    catalog = [
        CatalogModel(
            "claude-3-5-sonnet",
            "anthropic/claude-3-5-sonnet",
            in_price=3.0,
            out_price=15.0,
            max_input_tokens=200000,
            supports_tools=True,
            supports_vision=True,
            supports_response_schema=True,
        ),
        CatalogModel(
            "gemini-2.5-flash",
            "google/gemini-2.5-flash",
            in_price=0.075,
            out_price=0.30,
            max_input_tokens=1000000,
            supports_tools=True,
            supports_vision=True,
            supports_response_schema=True,
        ),
    ]

    # Tool calling -> ineligible
    s_tool = _make_dummy_stats(has_tools=True)
    assert score(s_tool, catalog).eligible is False

    # Multi turn -> ineligible in v1
    s_multi = _make_dummy_stats(shape="multi_turn")
    assert score(s_multi, catalog).eligible is False
