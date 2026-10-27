"""Harness² Scaffolding Proposer generating targeted system prompt addenda from failure traces."""

import json
import logging
import re
from pathlib import Path
from typing import Any

from gateway_harness.contracts import ModelClient, Scaffold
from gateway_harness.probe.runner import LossExample

logger = logging.getLogger("gateway_harness.proposer.propose")

PROMPT_FILE = Path(__file__).parent / "prompts" / "propose.md"

_FORBIDDEN_MODEL_MENTIONS = re.compile(
    r"(?i)\b(gpt-4|gpt-4o|claude|gemini|openai|anthropic|llama|deepseek)\b"
)


def _validate_variant(variant: dict[str, Any]) -> Scaffold | None:
    """Validate a single proposed scaffold variant against constraints."""
    addendum = str(variant.get("system_addendum") or "").strip()
    if not addendum:
        return None

    # Constraint 1: Length <= 120 words
    words = addendum.split()
    if len(words) > 120:
        logger.debug("Rejected variant: word count %d > 120", len(words))
        return None

    # Constraint 2: No model names
    if _FORBIDDEN_MODEL_MENTIONS.search(addendum):
        logger.debug("Rejected variant: contains forbidden model mention")
        return None

    # Filter params to allowlist
    raw_params = variant.get("params") or {}
    clean_params: dict[str, Any] = {}
    allowed = {"temperature", "top_p", "max_tokens", "reasoning_effort"}
    if isinstance(raw_params, dict):
        for k, v in raw_params.items():
            if k in allowed:
                clean_params[k] = v

    return Scaffold(system_addendum=addendum, params=clean_params)


async def propose(
    client: ModelClient,
    model: str,
    losses: list[LossExample],
    lessons: list[dict[str, Any]],
    k: int = 3,
) -> list[Scaffold]:
    """Generate k candidate scaffold variants from observed contrastive probe losses."""
    if not PROMPT_FILE.exists():
        return [Scaffold()]

    template = PROMPT_FILE.read_text(encoding="utf-8")

    # Format loss examples
    loss_lines = []
    for idx, loss in enumerate(losses[:5], start=1):
        task_preview = ""
        for m in loss.request_messages:
            if m.get("role") == "user":
                task_preview = str(m.get("content", ""))[:200]
                break
        reasons = []
        if loss.validator_codes:
            reasons.append(f"Validators failed: {', '.join(loss.validator_codes)}")
        if loss.judge_reason:
            reasons.append(f"Judge feedback: {loss.judge_reason}")

        loss_lines.append(
            f"Example {idx}:\n"
            f"- Task: {task_preview}\n"
            f"- Candidate Output: {loss.candidate_text[:200]}\n"
            f"- Baseline Output: {loss.baseline_text[:200]}\n"
            f"- Issues: {'; '.join(reasons)}"
        )

    losses_summary = "\n\n".join(loss_lines) if loss_lines else "None provided."

    # Format lessons
    lesson_lines = []
    for l_item in lessons[:3]:
        lesson_lines.append(f"- [{l_item.get('archetype')}]: {l_item.get('lesson')}")
    lessons_summary = "\n".join(lesson_lines) if lesson_lines else "None available."

    prompt_content = (
        template.replace("{losses_summary}", losses_summary)
        .replace("{lessons_summary}", lessons_summary)
        .replace("{k}", str(k))
    )

    messages = [
        {"role": "user", "content": prompt_content},
    ]
    params = {"temperature": 0.4, "response_format": {"type": "json_object"}}

    try:
        raw_text, _ = await client.complete(model, messages, params)
        data = json.loads(raw_text.strip())
        raw_variants = data.get("variants") or []

        valid_scaffolds: list[Scaffold] = []
        for v in raw_variants:
            sc = _validate_variant(v)
            if sc:
                valid_scaffolds.append(sc)

        if valid_scaffolds:
            return valid_scaffolds[:k]

    except Exception as exc:
        logger.warning("Scaffold proposal generation failed: %s", exc)

    return [Scaffold()]
