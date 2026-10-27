from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import litellm
import yaml


@dataclass
class CatalogModel:
    name: str
    underlying_model: str
    in_price: float
    out_price: float
    max_input_tokens: int
    supports_tools: bool
    supports_vision: bool
    supports_response_schema: bool

    @property
    def blended_cost_per_mtok(self) -> float:
        # Standard 3:1 input-to-output token ratio for typical enterprise traffic
        return (3 * self.in_price + 1 * self.out_price) / 4.0


@dataclass
class Needs:
    p99_prompt_tokens: int = 1000
    needs_tools: bool = False
    needs_vision: bool = False
    needs_response_schema: bool = False


def load_catalog(litellm_config_path: Path | str) -> list[CatalogModel]:
    """Parse LiteLLM yaml config and construct available model catalog with capabilities."""
    p = Path(litellm_config_path)
    if not p.exists():
        return []

    try:
        content = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        model_list: list[dict[str, Any]] = content.get("model_list", [])
        catalog: list[CatalogModel] = []

        for m in model_list:
            model_name = m.get("model_name")
            params = m.get("litellm_params", {})
            underlying = params.get("model", model_name)
            if not model_name or not underlying:
                continue

            cost_entry = litellm.model_cost.get(underlying) or litellm.model_cost.get(
                underlying.split("/", 1)[-1], {}
            )

            in_p = float(cost_entry.get("input_cost_per_token", 0.0) * 1_000_000)
            out_p = float(cost_entry.get("output_cost_per_token", 0.0) * 1_000_000)
            max_in = int(cost_entry.get("max_input_tokens", 8192) or 8192)
            tools = bool(cost_entry.get("supports_function_calling", False))
            vision = bool(cost_entry.get("supports_vision", False))
            schema = bool(cost_entry.get("supports_response_schema", False))

            catalog.append(
                CatalogModel(
                    name=model_name,
                    underlying_model=underlying,
                    in_price=in_p,
                    out_price=out_p,
                    max_input_tokens=max_in,
                    supports_tools=tools,
                    supports_vision=vision,
                    supports_response_schema=schema,
                )
            )

        return catalog

    except Exception:
        return []


def candidates_for(
    requested: str,
    needs: Needs,
    catalog: list[CatalogModel],
    denylist: set[str] | None = None,
) -> list[CatalogModel]:
    """Find valid candidate downgrade models that satisfy capability requirements and reduce cost."""
    if denylist is None:
        denylist = set()

    # Find requested model in catalog
    req_entry = next((c for c in catalog if c.name == requested or c.underlying_model == requested), None)
    if not req_entry:
        return []

    req_cost = req_entry.blended_cost_per_mtok
    min_context = int(needs.p99_prompt_tokens * 1.2)

    valid_candidates: list[CatalogModel] = []

    for c in catalog:
        if c.name == req_entry.name or c.name in denylist:
            continue

        # Must be strictly cheaper
        if c.blended_cost_per_mtok >= req_cost:
            continue

        # Context capacity
        if c.max_input_tokens < min_context:
            continue

        # Tool calling capability
        if needs.needs_tools and not c.supports_tools:
            continue

        # Vision capability
        if needs.needs_vision and not c.supports_vision:
            continue

        # Structured schema capability
        if needs.needs_response_schema and not c.supports_response_schema:
            continue

        valid_candidates.append(c)

    # Sort strictly by blended price ascending (cheapest first)
    valid_candidates.sort(key=lambda m: m.blended_cost_per_mtok)
    return valid_candidates
