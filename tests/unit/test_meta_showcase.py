from pathlib import Path

import pytest

from gateway_harness.demo.enterprise_client import generate_enterprise_payload
from gateway_harness.demo.meta_showcase import run_meta_hackathon_showcase
from gateway_harness.pricing import cost, price_per_mtok


def test_meta_pricing():
    assert cost("meta/muse-wonder", 1_000_000, 1_000_000) == pytest.approx(24.0, 0.01)
    assert cost("meta/muse-spark", 1_000_000, 1_000_000) == pytest.approx(5.50, 0.01)
    assert cost("meta/llama-3.1-8b-instruct", 1_000_000, 1_000_000) == pytest.approx(0.10, 0.01)

    prices = price_per_mtok("meta/muse-wonder")
    assert prices == (4.0, 20.0)

    spark_prices = price_per_mtok("openrouter/meta/muse-spark")
    assert spark_prices == (1.25, 4.25)


def test_enterprise_payload_generation():
    payload = generate_enterprise_payload(workflow="dispute", model="meta/muse-wonder", seed=42)
    assert payload["model"] == "meta/muse-wonder"
    assert len(payload["messages"]) == 2
    assert "dispute" in payload["messages"][0]["content"].lower()
    assert payload["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_meta_showcase_headless(tmp_path: Path):
    result = await run_meta_hackathon_showcase(
        data_dir=tmp_path,
        db_url=None,
        interactive=False,
    )
    assert result["baseline_cost"] > 0
    assert result["selected_proposal"].policy.target_model in (
        "meta/muse-spark",
        "meta/llama-3.1-8b-instruct",
    )
    assert result["net_savings"] > 0
    assert result["canary_requests"] == 100
