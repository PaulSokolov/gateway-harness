"""Internal Gateway Model Client with daily budget enforcement and retry mechanics."""

import asyncio
import logging
from typing import Any

import httpx

from gateway_harness.pricing import cost
from gateway_harness.settings import get_settings

logger = logging.getLogger("gateway_harness.probe.client")


class BudgetExceeded(Exception):
    """Raised when probe token spend exceeds allocated budget."""

    pass


class Budget:
    """Thread-safe budget tracker with hard ceiling."""

    def __init__(self, limit_usd: float):
        self.limit_usd = limit_usd
        self.spent_usd: float = 0.0
        self._lock = asyncio.Lock()

    async def charge(self, amount: float) -> None:
        async with self._lock:
            if self.spent_usd + amount > self.limit_usd:
                raise BudgetExceeded(
                    f"Daily probe budget exceeded: spent ${self.spent_usd + amount:.4f} "
                    f"> limit ${self.limit_usd:.4f}"
                )
            self.spent_usd += amount


class GatewayClient:
    """Async model client interacting with local LiteLLM gateway."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        budget: Budget | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        settings = get_settings()
        self.base_url = (base_url or str(settings.GATEWAY_URL)).rstrip("/")
        self.api_key = api_key or settings.INTERNAL_KEY
        self.budget = budget or Budget(limit_usd=settings.DAILY_OPTIMIZER_BUDGET_USD)
        self._client = client

    async def complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        params: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Send chat completion request to gateway with no_optimize flags and budget tracking."""
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "x-gh-no-optimize": "1",
        }

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "metadata": {
                "no_optimize": True,
                "tags": ["gh-internal"],
                "requester_metadata": {"gh_internal": True},
            },
        }
        if params:
            body.update(params)

        should_close = False
        client = self._client
        if client is None:
            client = httpx.AsyncClient(timeout=120.0)
            should_close = True

        max_retries = 2
        delay = 0.5
        last_exc: Exception | None = None

        try:
            for attempt in range(max_retries + 1):
                try:
                    resp = await client.post(url, headers=headers, json=body)
                    if resp.status_code in (429, 500, 502, 503, 504):
                        if attempt < max_retries:
                            await asyncio.sleep(delay)
                            delay *= 2
                            continue
                    resp.raise_for_status()
                    data = resp.json()

                    # Extract content
                    choices = data.get("choices") or []
                    text = ""
                    finish_reason = None
                    if choices:
                        first = choices[0]
                        text = (first.get("message") or {}).get("content") or ""
                        finish_reason = first.get("finish_reason")

                    # Extract or compute cost
                    usage = data.get("usage") or {}
                    p_toks = usage.get("prompt_tokens") or 0
                    c_toks = usage.get("completion_tokens") or 0

                    cost_hdr = resp.headers.get("x-litellm-response-cost")
                    if cost_hdr:
                        try:
                            req_cost = float(cost_hdr)
                        except ValueError:
                            req_cost = cost(model, p_toks, c_toks) or 0.0
                    else:
                        req_cost = cost(model, p_toks, c_toks) or 0.0

                    if self.budget:
                        await self.budget.charge(req_cost)

                    meta = {
                        "usage": usage,
                        "cost_usd": req_cost,
                        "finish_reason": finish_reason,
                    }
                    return text, meta

                except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        await asyncio.sleep(delay)
                        delay *= 2
                    else:
                        raise last_exc from exc

            raise last_exc or RuntimeError("Request failed after retries")

        finally:
            if should_close:
                await client.aclose()
