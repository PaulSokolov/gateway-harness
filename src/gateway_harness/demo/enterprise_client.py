from __future__ import annotations

import argparse
import asyncio
import logging
import random
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Sample enterprise synthetic datasets
MERCHANTS = [
    {"name": "Apex Cloud Hosting", "mcc": "7372", "category": "Cloud Services"},
    {"name": "OmniGlobal Airlines", "mcc": "4511", "category": "Travel"},
    {"name": "Metro Grocery Express", "mcc": "5411", "category": "Retail"},
    {"name": "SaaS Platform Pro", "mcc": "7372", "category": "Software Subscription"},
    {"name": "Nordic Electronics Hub", "mcc": "5732", "category": "Electronics"},
]

DISPUTE_REASONS = [
    "Recurring subscription was cancelled 14 days prior but card was charged anyway.",
    "Cardholder claims unauthorized transaction while travelling internationally.",
    "Goods received were damaged in transit and seller refused RMA return.",
    "Card charged twice for the same merchant POS authorization on Oct 14.",
    "Subscription price increased without 30-day prior written notice per Terms of Service.",
]


def generate_enterprise_payload(
    workflow: str = "dispute",
    model: str = "meta/muse-wonder",
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate a realistic enterprise request payload with strict schema requirements."""
    rng = random.Random(seed) if seed is not None else random.Random()
    merchant = rng.choice(MERCHANTS)
    amount = round(rng.uniform(15.0, 1850.0), 2)
    tx_id = f"tx_live_{rng.randint(100000, 999999)}"
    dispute_statement = rng.choice(DISPUTE_REASONS)

    system_prompt = (
        "You are an enterprise autonomous financial dispute compliance auditor. "
        "Evaluate the following cardholder dispute against regulatory guidelines (Visa/Mastercard rules). "
        "You MUST respond ONLY with a valid JSON object matching this schema:\n"
        "{\n"
        '  "dispute_id": string,\n'
        '  "decision": "ACCEPT" | "REJECT" | "ESCALATE",\n'
        '  "confidence": number,\n'
        '  "risk_score": number (0 to 1),\n'
        '  "chargeback_code": string,\n'
        '  "reasoning": string\n'
        "}"
    )

    user_prompt = (
        f"TRANSACTION RECORD:\n"
        f"ID: {tx_id}\n"
        f"Merchant: {merchant['name']} (MCC: {merchant['mcc']})\n"
        f"Amount: ${amount} USD\n"
        f"Date: 2026-10-14 18:22:04 UTC\n\n"
        f"CARDHOLDER STATEMENT:\n"
        f'"{dispute_statement}"\n\n'
        f"Determine regulatory liability and return the structured decision object."
    )

    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "metadata": {
            "enterprise_client": "acme_fintech",
            "workflow": workflow,
            "environment": "production",
        },
    }


async def send_single_request(
    client: httpx.AsyncClient,
    gateway_url: str,
    api_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Send a single enterprise chat completion request to the proxy gateway."""
    url = f"{gateway_url.rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    t0 = time.perf_counter()
    try:
        resp = await client.post(url, json=payload, headers=headers, timeout=15.0)
        dur_ms = (time.perf_counter() - t0) * 1000.0
        routed_model = resp.headers.get("x-gh-routed-model", payload.get("model", "unknown"))
        scaffold_applied = resp.headers.get("x-gh-scaffold-applied", "false")
        status = resp.status_code
        data = resp.json() if status == 200 else {}
        return {
            "status_code": status,
            "duration_ms": round(dur_ms, 2),
            "requested_model": payload.get("model"),
            "routed_model": routed_model,
            "scaffold_applied": scaffold_applied == "true",
            "response": data,
        }
    except Exception as e:
        dur_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "status_code": 0,
            "duration_ms": round(dur_ms, 2),
            "error": str(e),
            "requested_model": payload.get("model"),
            "routed_model": "error",
            "scaffold_applied": False,
        }


async def run_enterprise_traffic(
    gateway_url: str = "http://localhost:4000",
    api_key: str = "sk-test-master-key",
    count: int = 25,
    rps: float = 5.0,
    model: str = "meta/muse-wonder",
    workflow: str = "dispute",
) -> list[dict[str, Any]]:
    """Simulate realistic enterprise burst or continuous stream traffic."""
    results: list[dict[str, Any]] = []
    interval = 1.0 / max(rps, 0.1)

    async with httpx.AsyncClient() as client:
        for i in range(count):
            payload = generate_enterprise_payload(workflow=workflow, model=model, seed=1000 + i)
            res = await send_single_request(client, gateway_url, api_key, payload)
            results.append(res)
            logger.info(
                "[%d/%d] Status: %s | Model: %s -> %s | Duration: %.1fms | Scaffold: %s",
                i + 1,
                count,
                res.get("status_code"),
                res.get("requested_model"),
                res.get("routed_model"),
                res.get("duration_ms", 0.0),
                res.get("scaffold_applied"),
            )
            if i < count - 1:
                await asyncio.sleep(interval)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate enterprise client traffic against Gateway-Harness")
    parser.add_argument("--gateway", default="http://localhost:4000", help="Gateway URL")
    parser.add_argument("--key", default="sk-test-master-key", help="Gateway API Key")
    parser.add_argument("--count", type=int, default=10, help="Number of requests")
    parser.add_argument("--rps", type=float, default=2.0, help="Target requests per second")
    parser.add_argument("--model", default="meta/muse-wonder", help="Target enterprise model")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print(
        f"Starting Enterprise Client Simulator for {args.model} "
        f"via {args.gateway} ({args.count} requests @ {args.rps} RPS)..."
    )
    res = asyncio.run(
        run_enterprise_traffic(
            gateway_url=args.gateway,
            api_key=args.key,
            count=args.count,
            rps=args.rps,
            model=args.model,
        )
    )

    success = sum(1 for r in res if r.get("status_code") == 200)
    print(f"\nFinished: {success}/{len(res)} succeeded.")


if __name__ == "__main__":
    main()
