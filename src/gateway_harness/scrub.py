from __future__ import annotations

import re
from typing import Any

# Precompiled regexes for maximum performance (< 2ms per 10KB)
_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_RE_IP = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    r"|\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"
)
_RE_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9._-]+\.[A-Za-z0-9._-]+\b")
_RE_SECRET_SPECIFIC = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|xox[baprs]-[0-9a-zA-Z-]{20,})\b"
)
_RE_SECRET_GENERIC = re.compile(
    r'(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*["\']?([A-Za-z0-9_\-\.]{8,})["\']?'
)
_RE_PHONE = re.compile(
    r"(?<!\w)(?:\+|00)\d{1,3}[-.\s]\d{1,4}[-.\s]\d{3,4}[-.\s]\d{3,4}\b"
    r"|(?<!\w)(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]\d{3}[-.\s]\d{4}\b"
    r"|(?<!\w)(?:\+?1[-.\s]?)?\([2-9]\d{2}\)\s*\d{3}[-.\s]?\d{4}\b"
)
_RE_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_RE_CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def _is_luhn_valid(num_str: str) -> bool:
    """Validate credit card number using Luhn algorithm."""
    digits = [int(c) for c in num_str if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, digit in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = digit * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += digit
    return checksum % 10 == 0


def scrub_text(s: str) -> str:
    """Scrub PII, secrets, and credentials from text and replace with typed tokens."""
    if not s:
        return s

    # 1. JWT tokens
    s = _RE_JWT.sub("<JWT>", s)

    # 2. Specific API keys (OpenAI, Anthropic, AWS, GitHub, Slack)
    s = _RE_SECRET_SPECIFIC.sub("<SECRET>", s)

    # 3. Generic key-value secrets
    s = _RE_SECRET_GENERIC.sub(r"\1: <SECRET>", s)

    # 4. Emails
    s = _RE_EMAIL.sub("<EMAIL>", s)

    # 5. IP Addresses
    s = _RE_IP.sub("<IP>", s)

    # 6. Credit cards (Luhn validated to avoid false positives on numbers)
    def _card_replace(match: re.Match[str]) -> str:
        matched = match.group(0)
        digits = re.sub(r"\D", "", matched)
        if _is_luhn_valid(digits):
            return "<CARD>"
        return matched

    s = _RE_CARD_CANDIDATE.sub(_card_replace, s)

    # 7. IBAN
    s = _RE_IBAN.sub("<IBAN>", s)

    # 8. Phone numbers
    s = _RE_PHONE.sub("<PHONE>", s)

    return s


def scrub_obj(obj: Any) -> Any:
    """Recursively scrub string values in nested dictionaries and lists without altering keys."""
    if isinstance(obj, str):
        return scrub_text(obj)
    if isinstance(obj, dict):
        return {k: scrub_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub_obj(item) for item in obj]
    return obj
