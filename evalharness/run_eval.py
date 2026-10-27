"""End-to-end evaluation harness runner verifying savings and quality on synthetic workloads."""

import asyncio
import json
import logging
from typing import Any

import httpx

from evalharness.generator import generate_batch

logger = logging.getLogger("evalharness")


async def run_eval(
    gateway_url: str = "http://localhost:4000",
    api_key: str = "sk-test-master-key",
    num_requests: int = 30,
) -> dict[str, Any]:
    """Execute end-to-end evaluation against running appliance."""
    requests = generate_batch(count=num_requests, seed=42)
    successful = 0
    total_cost = 0.0

    async with httpx.AsyncClient(timeout=60.0) as client:
        for idx, req in enumerate(requests, start=1):
            try:
                resp = await client.post(
                    f"{gateway_url.rstrip('/')}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=req,
                )
                if resp.status_code == 200:
                    successful += 1
                    cost_hdr = resp.headers.get("x-litellm-response-cost")
                    if cost_hdr:
                        total_cost += float(cost_hdr)
            except Exception as exc:
                logger.warning("Request %d failed: %s", idx, exc)

    summary = {
        "total_sent": num_requests,
        "successful": successful,
        "success_rate": round(successful / max(1, num_requests), 3),
        "total_cost_usd": round(total_cost, 4),
    }
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    res = asyncio.run(run_eval())
    print(json.dumps(res, indent=2))
