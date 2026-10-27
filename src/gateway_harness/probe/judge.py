"""Pairwise contrastive judge with position-swapping debiasing."""

import json
import logging
from pathlib import Path
from typing import Any

from gateway_harness.contracts import JudgeResult, ModelClient, Verdict
from gateway_harness.metrics import JUDGE_VERDICTS_TOTAL

logger = logging.getLogger("gateway_harness.probe.judge")

PROMPT_FILE = Path(__file__).parent / "prompts" / "judge.md"


def _format_task_context(task_messages: list[dict[str, Any]], max_chars: int = 6000) -> str:
    """Format system message and last user message into prompt context."""
    system_text = ""
    user_text = ""
    for m in task_messages:
        role = m.get("role")
        content = m.get("content")
        c_str = str(content) if isinstance(content, str) else json.dumps(content)
        if role == "system" and not system_text:
            system_text = c_str
        elif role == "user":
            user_text = c_str

    parts = []
    if system_text:
        parts.append(f"System Prompt:\n{system_text}")
    if user_text:
        parts.append(f"User Request:\n{user_text}")

    full = "\n\n".join(parts)
    return full[:max_chars]


async def _call_judge_single(
    client: ModelClient,
    judge_model: str,
    system_instruction: str,
    task_context: str,
    resp_1: str,
    resp_2: str,
) -> tuple[str, str, float]:
    """Execute single judge call with retry on JSON parse failure.

    Returns (better, reason, cost_usd).
    """
    user_content = (
        f"### Task\n{task_context}\n\n### Response 1\n{resp_1[:4000]}\n\n### Response 2\n{resp_2[:4000]}"
    )
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_content},
    ]
    params = {"temperature": 0.0, "response_format": {"type": "json_object"}}

    total_cost = 0.0
    for attempt in range(2):
        text, meta = await client.complete(judge_model, messages, params)
        total_cost += meta.get("cost_usd") or 0.0
        try:
            parsed = json.loads(text.strip())
            better = str(parsed.get("better", "tie")).strip().lower()
            if better not in ("1", "2", "tie"):
                better = "tie"
            reason = str(parsed.get("reason", ""))[:200]
            return better, reason, total_cost
        except Exception as exc:
            if attempt == 0:
                logger.warning("Judge JSON parse failed on first attempt: %s, retrying", exc)
                continue
            return "tie", "judge_parse_error", total_cost

    return "tie", "judge_parse_error", total_cost


async def judge(
    client: ModelClient,
    judge_model: str,
    task_messages: list[dict[str, Any]],
    baseline_text: str,
    candidate_text: str,
) -> JudgeResult:
    """Evaluate candidate vs baseline with position-swapped contrastive judging."""
    system_instruction = PROMPT_FILE.read_text(encoding="utf-8")
    task_context = _format_task_context(task_messages)

    # 1. Forward run: Response 1 = baseline, Response 2 = candidate
    b1, r1, cost1 = await _call_judge_single(
        client,
        judge_model,
        system_instruction,
        task_context,
        resp_1=baseline_text,
        resp_2=candidate_text,
    )

    # 2. Swapped run: Response 1 = candidate, Response 2 = baseline
    b2, r2, cost2 = await _call_judge_single(
        client,
        judge_model,
        system_instruction,
        task_context,
        resp_1=candidate_text,
        resp_2=baseline_text,
    )

    total_judge_cost = cost1 + cost2

    if r1 == "judge_parse_error" or r2 == "judge_parse_error":
        JUDGE_VERDICTS_TOTAL.labels(verdict=Verdict.TIE).inc()
        return JudgeResult(
            verdict=Verdict.TIE,
            reason="judge_parse_error",
            judge_cost_usd=total_judge_cost,
        )

    # In forward run: "2" means candidate is better, "1" means baseline is better
    # In swapped run: "1" means candidate is better, "2" means baseline is better
    cand_won_fwd = b1 == "2"
    base_won_fwd = b1 == "1"

    cand_won_rev = b2 == "1"
    base_won_rev = b2 == "2"

    if cand_won_fwd and cand_won_rev:
        verdict = Verdict.WIN
        reason = f"Candidate won both positions: {r1}"
    elif base_won_fwd and base_won_rev:
        verdict = Verdict.LOSS
        reason = f"Baseline won both positions: {r1}"
    else:
        verdict = Verdict.TIE
        reason = f"Position-swapped tie or conflict: fwd={b1}, rev={b2}"

    JUDGE_VERDICTS_TOTAL.labels(verdict=verdict).inc()
    return JudgeResult(
        verdict=verdict,
        reason=reason,
        judge_cost_usd=total_judge_cost,
    )
