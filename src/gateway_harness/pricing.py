from __future__ import annotations

import logging

import litellm

logger = logging.getLogger(__name__)


# Explicit pricing overrides for Meta Muse and Llama models ($ per million tokens)
# Ensures accurate pricing even if the pinned litellm version lacks recent 2026 models.
CUSTOM_PRICING: dict[str, dict[str, float]] = {
    "meta/muse-wonder": {
        "input_cost_per_token": 4.00 / 1_000_000,
        "output_cost_per_token": 20.00 / 1_000_000,
        "cache_read_input_token_cost": 0.20 / 1_000_000,
    },
    "meta/muse-spark": {
        "input_cost_per_token": 1.25 / 1_000_000,
        "output_cost_per_token": 4.25 / 1_000_000,
        "cache_read_input_token_cost": 0.15 / 1_000_000,
    },
    "meta/muse-spark-open": {
        "input_cost_per_token": 1.25 / 1_000_000,
        "output_cost_per_token": 4.25 / 1_000_000,
        "cache_read_input_token_cost": 0.15 / 1_000_000,
    },
    "meta/llama-3.3-70b-instruct": {
        "input_cost_per_token": 0.40 / 1_000_000,
        "output_cost_per_token": 0.40 / 1_000_000,
        "cache_read_input_token_cost": 0.10 / 1_000_000,
    },
    "meta/llama-3.1-70b-instruct": {
        "input_cost_per_token": 0.40 / 1_000_000,
        "output_cost_per_token": 0.40 / 1_000_000,
        "cache_read_input_token_cost": 0.10 / 1_000_000,
    },
    "meta/llama-3.1-8b-instruct": {
        "input_cost_per_token": 0.05 / 1_000_000,
        "output_cost_per_token": 0.05 / 1_000_000,
        "cache_read_input_token_cost": 0.01 / 1_000_000,
    },
}


def _lookup_entry(model: str) -> dict[str, float] | None:
    norm = model.lower()
    if norm in CUSTOM_PRICING:
        return CUSTOM_PRICING[norm]
    # Check stripped provider prefixes (e.g., openrouter/meta/muse-spark -> meta/muse-spark)
    for k, v in CUSTOM_PRICING.items():
        if norm.endswith(k) or k.endswith(norm):
            return v
    entry = litellm.model_cost.get(model)
    if not entry and "/" in model:
        entry = litellm.model_cost.get(model.split("/", 1)[-1])
    return entry


def cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int = 0,
) -> float | None:
    """Calculate USD cost for a given model and token usage, accounting for prompt caching.

    Returns None if model pricing is not found. Never raises.
    """
    try:
        entry = _lookup_entry(model)

        if not entry:
            # Try litellm.cost_per_token directly
            res = litellm.cost_per_token(
                model=model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
            )
            if isinstance(res, tuple) and len(res) == 2:
                return float(res[0] + res[1])
            return None

        in_cost = entry.get("input_cost_per_token") or 0.0
        out_cost = entry.get("output_cost_per_token") or 0.0
        cache_cost = entry.get("cache_read_input_token_cost") or in_cost

        uncached = max(0, prompt_tokens - cached_tokens)
        total = (uncached * in_cost) + (cached_tokens * cache_cost) + (completion_tokens * out_cost)
        return float(total)

    except Exception as e:
        logger.debug("Failed to calculate cost for %s: %s", model, e)
        return None


def price_per_mtok(model: str) -> tuple[float, float] | None:
    """Return (input_price_per_mtok, output_price_per_mtok) in USD, or None."""
    try:
        entry = _lookup_entry(model)
        if not entry:
            return None

        in_cost = (entry.get("input_cost_per_token") or 0.0) * 1_000_000
        out_cost = (entry.get("output_cost_per_token") or 0.0) * 1_000_000
        return (float(in_cost), float(out_cost))

    except Exception:
        return None
