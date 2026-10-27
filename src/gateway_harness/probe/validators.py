"""Zero-cost deterministic output validators for quality and contract verification."""

import json
import re
from typing import Any

import jsonschema

_RE_REFUSAL = re.compile(
    r"(?i)\b("
    r"i (?:cannot|can't|am unable to) (?:assist|help|comply|fulfill|do that)|"
    r"as an ai (?:language model|assistant)|"
    r"my apologies, but i (?:cannot|can't)"
    r")\b"
)

_RE_LATIN = re.compile(r"[a-zA-Z]")
_RE_CYRILLIC = re.compile(r"[\u0400-\u04FF]")
_RE_CJK = re.compile(r"[\u4E00-\u9FFF\u3040-\u30FF]")


def _script_shares(text: str) -> dict[str, float]:
    """Calculate share of Latin, Cyrillic, and CJK characters."""
    total_letters = 0
    counts = {"latin": 0, "cyrillic": 0, "cjk": 0}
    for ch in text:
        if _RE_LATIN.match(ch):
            counts["latin"] += 1
            total_letters += 1
        elif _RE_CYRILLIC.match(ch):
            counts["cyrillic"] += 1
            total_letters += 1
        elif _RE_CJK.match(ch):
            counts["cjk"] += 1
            total_letters += 1
    if total_letters == 0:
        return {}
    return {k: v / total_letters for k, v in counts.items()}


def validate(
    request_body: dict[str, Any],
    baseline_text: str,
    candidate_text: str,
    finish_reason: str | None = None,
) -> list[str]:
    """Validate candidate output against baseline and contract rules.

    Returns a list of violation codes (empty list = all passed).
    """
    failures: list[str] = []

    # 1. Empty Check
    if not candidate_text or not candidate_text.strip():
        failures.append("empty")
        return failures  # Nothing more to validate if completely empty

    # 2. Truncation Check
    if finish_reason == "length":
        failures.append("truncated")

    # 3. Refusal Check
    if _RE_REFUSAL.search(candidate_text):
        failures.append("refusal")

    # Check for JSON expectations
    resp_fmt = request_body.get("response_format")
    is_json_requested = False
    json_schema = None
    if isinstance(resp_fmt, dict):
        fmt_type = resp_fmt.get("type")
        if fmt_type in ("json_object", "json_schema"):
            is_json_requested = True
        if fmt_type == "json_schema":
            json_schema = resp_fmt.get("json_schema", {}).get("schema")

    # Baseline JSON parse check
    baseline_json = None
    try:
        baseline_json = json.loads(baseline_text.strip())
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # 4. JSON Valid Check
    candidate_json = None
    if is_json_requested or baseline_json is not None:
        try:
            candidate_json = json.loads(candidate_text.strip())
        except (json.JSONDecodeError, TypeError, ValueError):
            failures.append("json_invalid")

    # 5. Schema Valid Check
    if candidate_json is not None and json_schema:
        try:
            jsonschema.validate(instance=candidate_json, schema=json_schema)
        except jsonschema.ValidationError:
            failures.append("schema_invalid")

    # 6. JSON Keys Mismatch Check
    if isinstance(baseline_json, dict) and isinstance(candidate_json, dict) and baseline_json:
        base_keys = set(baseline_json.keys())
        cand_keys = set(candidate_json.keys())
        if base_keys != cand_keys:
            failures.append("json_keys_mismatch")

    # 7. Length Ratio Check (only for substantial text > 200 chars)
    if len(baseline_text) > 200:
        ratio = len(candidate_text) / len(baseline_text)
        if ratio < 0.3 or ratio > 3.0:
            failures.append("length_ratio")

    # 8. Language / Script Mismatch Check
    base_shares = _script_shares(baseline_text)
    if base_shares:
        # Find dominant script in baseline (must be >= 40%)
        dom_script, dom_share = max(base_shares.items(), key=lambda kv: kv[1])
        if dom_share >= 0.4:
            cand_shares = _script_shares(candidate_text)
            cand_share = cand_shares.get(dom_script, 0.0)
            if (dom_share - cand_share) > 0.50:
                failures.append("language_mismatch")

    return failures
