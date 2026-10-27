from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from typing import Any

from gateway_harness.contracts import FINGERPRINT_VERSION, Fingerprint, Shape

# Precompiled regexes for fast normalization (< 0.3ms per request)
_RE_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)
_RE_ISO_DT = re.compile(
    r"\b\d{4}-\d{2}-\d{2}(?:[t\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:z|[+-]\d{2}:?\d{2})?)?\b",
    re.IGNORECASE,
)
_RE_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_RE_HEX = re.compile(r"\b(?:0x)?[0-9a-f]{8,}\b", re.IGNORECASE)
_RE_QUOTED = re.compile(r"""(?:'([^'\n\r]{1,200})'|"([^"\n\r]{1,200})")""")
_RE_NUM = re.compile(r"\b\d+(?:\.\d+)?\b")
_RE_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Normalize text into a structural template representation by masking volatile tokens."""
    if not text:
        return ""

    s = text.lower()
    s = _RE_UUID.sub("<uuid>", s)
    s = _RE_ISO_DT.sub("<dt>", s)
    s = _RE_URL.sub("<url>", s)
    s = _RE_EMAIL.sub("<email>", s)
    s = _RE_HEX.sub("<hex>", s)
    s = _RE_QUOTED.sub("<q>", s)
    s = _RE_NUM.sub("<n>", s)
    s = _RE_WHITESPACE.sub(" ", s).strip()
    return s[:2000]


def _extract_message_text(content: Any) -> str:
    """Extract plain text from message content string or multipart structure."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                part_type = part.get("type")
                if part_type == "text":
                    parts.append(str(part.get("text", "")))
                elif part_type in ("image_url", "image"):
                    parts.append("<img>")
            elif isinstance(part, str):
                parts.append(part)
        return " ".join(parts)
    return str(content) if content is not None else ""


def _has_image_content(content: Any) -> bool:
    """Check if message content contains an image."""
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                if part.get("type") in ("image_url", "image"):
                    return True
    return False


def template_id(messages: Sequence[dict[str, Any]]) -> str:
    """Calculate 16-hex template_id from the normalized last user message."""
    last_user_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_text = _extract_message_text(msg.get("content"))
            break

    norm = normalize(last_user_text)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def workflow_sig(
    messages: Sequence[dict[str, Any]],
    tools: Sequence[dict[str, Any]] | None,
    response_format: Any | None,
    requested_model: str,
) -> str:
    """Calculate 16-hex workflow signature identifying the structural scaffolding."""
    # 1. Normalized system messages
    sys_texts: list[str] = []
    for msg in messages:
        if msg.get("role") == "system":
            sys_texts.append(normalize(_extract_message_text(msg.get("content"))))
    norm_sys = " ".join(sys_texts)

    # 2. Sorted tools + tool schema hashes
    tool_signatures: list[tuple[str, str]] = []
    if tools:
        for tool in tools:
            if isinstance(tool, dict):
                function = tool.get("function") if tool.get("type") == "function" else tool
                name = str(function.get("name", "")) if isinstance(function, dict) else ""
                params = function.get("parameters", {}) if isinstance(function, dict) else {}
                param_hash = hashlib.sha256(json.dumps(params, sort_keys=True).encode("utf-8")).hexdigest()[
                    :16
                ]
                tool_signatures.append((name, param_hash))
    tool_signatures.sort()

    # 3. response_format descriptor
    fmt_type = ""
    fmt_schema_hash = ""
    if isinstance(response_format, dict):
        fmt_type = str(response_format.get("type", ""))
        schema = response_format.get("json_schema") or response_format.get("schema") or {}
        fmt_schema_hash = hashlib.sha256(json.dumps(schema, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    elif response_format:
        fmt_type = str(response_format)

    canonical = {
        "sys": norm_sys,
        "tools": tool_signatures,
        "fmt": [fmt_type, fmt_schema_hash],
        "model": requested_model,
    }
    canon_bytes = json.dumps(canonical, sort_keys=True).encode("utf-8")
    return hashlib.sha256(canon_bytes).hexdigest()[:16]


def shape(
    messages: Sequence[dict[str, Any]],
    tools: Sequence[dict[str, Any]] | None,
    response_format: Any | None,
) -> Shape:
    """Classify the structural interaction shape using priority rules."""
    # 1. tools present or any tool role
    if tools:
        return "tool_calling"
    for msg in messages:
        if msg.get("role") in ("tool", "function") or msg.get("tool_calls"):
            return "tool_calling"

    # 2. any image part
    for msg in messages:
        if _has_image_content(msg.get("content")):
            return "multimodal"

    # 3. response_format set
    if response_format:
        return "structured_output"

    # Count user and system messages
    user_turns = sum(1 for m in messages if m.get("role") == "user")
    has_system = any(m.get("role") == "system" for m in messages)

    # 4. user turns > 2
    if user_turns > 2:
        return "multi_turn"

    # 5. system message present with 1-2 user turns
    if has_system:
        return "one_shot_templated"

    # 6. one user message, no system message
    if user_turns == 1:
        return "one_shot_simple"

    return "other"


def fingerprint(
    messages: Sequence[dict[str, Any]],
    tools: Sequence[dict[str, Any]] | None = None,
    response_format: Any | None = None,
    requested_model: str = "",
) -> Fingerprint:
    """Compute structural fingerprint containing template_id, workflow_sig, and shape."""
    return Fingerprint(
        version=FINGERPRINT_VERSION,
        template_id=template_id(messages),
        workflow_sig=workflow_sig(messages, tools, response_format, requested_model),
        shape=shape(messages, tools, response_format),
    )
