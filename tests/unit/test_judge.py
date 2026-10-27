import json
from unittest.mock import AsyncMock

import pytest

from gateway_harness.contracts import Verdict
from gateway_harness.probe.judge import judge


@pytest.mark.asyncio
async def test_judge_candidate_win():
    client = AsyncMock()
    # Fwd: candidate is resp 2 ("2"). Swapped: candidate is resp 1 ("1").
    client.complete.side_effect = [
        (json.dumps({"better": "2", "reason": "more concise"}), {"cost_usd": 0.001}),
        (json.dumps({"better": "1", "reason": "more concise"}), {"cost_usd": 0.001}),
    ]

    res = await judge(client, "gpt-4o", [{"role": "user", "content": "hi"}], "base", "cand")
    assert res.verdict == Verdict.WIN
    assert res.judge_cost_usd == pytest.approx(0.002)


@pytest.mark.asyncio
async def test_judge_baseline_win_is_loss():
    client = AsyncMock()
    # Fwd: baseline is resp 1 ("1"). Swapped: baseline is resp 2 ("2").
    client.complete.side_effect = [
        (json.dumps({"better": "1", "reason": "more accurate"}), {"cost_usd": 0.001}),
        (json.dumps({"better": "2", "reason": "more accurate"}), {"cost_usd": 0.001}),
    ]

    res = await judge(client, "gpt-4o", [{"role": "user", "content": "hi"}], "base", "cand")
    assert res.verdict == Verdict.LOSS


@pytest.mark.asyncio
async def test_judge_positional_bias_results_in_tie():
    client = AsyncMock()
    # Judge has positional bias and always picks Response 1 ("1")
    client.complete.side_effect = [
        (json.dumps({"better": "1", "reason": "prefer first"}), {"cost_usd": 0.001}),
        (json.dumps({"better": "1", "reason": "prefer first"}), {"cost_usd": 0.001}),
    ]

    res = await judge(client, "gpt-4o", [{"role": "user", "content": "hi"}], "base", "cand")
    assert res.verdict == Verdict.TIE
    assert "Position-swapped tie or conflict" in res.reason


@pytest.mark.asyncio
async def test_judge_json_parse_error():
    client = AsyncMock()
    # Non-JSON responses
    client.complete.side_effect = [
        ("Invalid JSON 1", {"cost_usd": 0.001}),
        ("Invalid JSON 2", {"cost_usd": 0.001}),
        ("Invalid JSON 3", {"cost_usd": 0.001}),
        ("Invalid JSON 4", {"cost_usd": 0.001}),
    ]

    res = await judge(client, "gpt-4o", [{"role": "user", "content": "hi"}], "base", "cand")
    assert res.verdict == Verdict.TIE
    assert res.reason == "judge_parse_error"
