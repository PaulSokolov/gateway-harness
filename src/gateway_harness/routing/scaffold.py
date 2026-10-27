"""Pure functions for applying prompt scaffolding and parameter adjustments."""

import copy
from typing import Any

from gateway_harness.contracts import Scaffold

PARAM_ALLOWLIST = frozenset({"temperature", "top_p", "max_tokens", "reasoning_effort"})


def apply_scaffold(data: dict[str, Any], scaffold: Scaffold) -> dict[str, Any]:
    """Apply system prompt addendum and parameter overrides to request payload.

    Returns a modified copy, never mutating the original.
    """
    out = copy.deepcopy(data)

    # 1. System Prompt Addendum
    if scaffold.system_addendum and scaffold.system_addendum.strip():
        addendum = scaffold.system_addendum.strip()
        messages: list[dict[str, Any]] = out.get("messages", [])

        # Find existing system message
        sys_idx = -1
        for idx, msg in enumerate(messages):
            if msg.get("role") == "system":
                sys_idx = idx
                break

        if sys_idx == -1:
            # Insert at beginning
            messages.insert(0, {"role": "system", "content": addendum})
        else:
            sys_msg = messages[sys_idx]
            content = sys_msg.get("content")

            if isinstance(content, str):
                sys_msg["content"] = f"{content}\n\n{addendum}" if content else addendum
            elif isinstance(content, list):
                # Multipart content block list
                # Preserve existing blocks (including any cache_control blocks) and append text
                new_block: dict[str, Any] = {"type": "text", "text": f"\n\n{addendum}"}
                content.append(new_block)
            else:
                sys_msg["content"] = addendum

        out["messages"] = messages

    # 2. Parameter Allowlist & Overrides
    if scaffold.params:
        for key, val in scaffold.params.items():
            if key not in PARAM_ALLOWLIST:
                continue

            if key == "max_tokens":
                # Never override client's max_tokens with a larger one
                client_val = out.get("max_tokens")
                if client_val is not None:
                    out["max_tokens"] = min(int(client_val), int(val))
                else:
                    out["max_tokens"] = int(val)
            else:
                out[key] = val

    return out
