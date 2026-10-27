import httpx
import pytest

from gateway_harness.probe.client import Budget, BudgetExceeded, GatewayClient


@pytest.mark.asyncio
async def test_budget_enforcement():
    b = Budget(limit_usd=1.0)
    await b.charge(0.6)
    assert b.spent_usd == pytest.approx(0.6)

    with pytest.raises(BudgetExceeded):
        await b.charge(0.5)  # 0.6 + 0.5 = 1.1 > 1.0


@pytest.mark.asyncio
async def test_gateway_client_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-gh-no-optimize"] == "1"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Sample output"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
            headers={"x-litellm-response-cost": "0.0015"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = GatewayClient(
            base_url="http://test-gw",
            api_key="sk-test",
            budget=Budget(limit_usd=10.0),
            client=mock_http,
        )
        text, meta = await client.complete("gpt-4o", [{"role": "user", "content": "hi"}])
        assert text == "Sample output"
        assert meta["cost_usd"] == pytest.approx(0.0015)
        assert meta["finish_reason"] == "stop"
        assert client.budget.spent_usd == pytest.approx(0.0015)


@pytest.mark.asyncio
async def test_gateway_client_retry_on_429():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, json={"error": "rate limit"})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Retry success"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = GatewayClient(
            base_url="http://test-gw",
            api_key="sk-test",
            budget=Budget(limit_usd=10.0),
            client=mock_http,
        )
        text, meta = await client.complete("gpt-4o", [{"role": "user", "content": "hi"}])
        assert text == "Retry success"
        assert attempts == 2
