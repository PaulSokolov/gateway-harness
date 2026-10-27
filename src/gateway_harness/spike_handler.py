from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from litellm.integrations.custom_logger import CustomLogger


class SpikeHandler(CustomLogger):
    """Spike handler to test and verify LiteLLM hook seams and metadata propagation."""

    def __init__(self, log_path: Path = Path("/tmp/spike_events.jsonl")) -> None:
        super().__init__()
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    async def async_pre_call_hook(
        self,
        user_api_key_dict: Any,
        cache: Any,
        data: dict,
        call_type: str,
    ) -> dict | None:
        if data.get("model") == "spike-src":
            data["model"] = "spike-dst"
            metadata = data.setdefault("metadata", {})
            metadata["gh_policy_id"] = "pol_test"
            metadata["gh_original_model"] = "spike-src"
            tags = metadata.setdefault("tags", [])
            tags.append("gh:policy:pol_test")
            # Also test requester_metadata
            req_meta = metadata.setdefault("requester_metadata", {})
            req_meta["gh_policy_id"] = "pol_test"
        return data

    async def async_post_call_response_headers_hook(
        self,
        data: dict,
        user_api_key_dict: Any,
        response: Any,
        request_headers: dict[str, str] | None = None,
        litellm_call_info: dict[str, Any] | None = None,
    ) -> dict[str, str] | None:
        if data.get("metadata", {}).get("gh_original_model") == "spike-src":
            return {
                "x-gh-optimized-from": "spike-src",
                "x-gh-policy": "pol_test",
            }
        return None

    async def async_log_success_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        slo = kwargs.get("standard_logging_object", {})
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(slo, default=str) + "\n")

    async def async_log_failure_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        slo = kwargs.get("standard_logging_object", {})
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(slo, default=str) + "\n")


spike_handler = SpikeHandler()
