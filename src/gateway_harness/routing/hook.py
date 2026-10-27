"""RoutingMixin implementing pre-call model rewriting and response header injection."""

import hashlib
import logging
import random
from typing import Any

from gateway_harness.fingerprint import fingerprint
from gateway_harness.metrics import DECISIONS_TOTAL
from gateway_harness.policy.matcher import decide
from gateway_harness.policy.snapshot import holder
from gateway_harness.routing.scaffold import apply_scaffold
from gateway_harness.settings import get_settings

logger = logging.getLogger("gateway_harness.routing")


class RoutingMixin:
    """LiteLLM CustomLogger mixin for intelligent model rewriting."""

    async def async_pre_call_hook(
        self,
        user_api_key_dict: dict[str, Any] | Any,
        cache: Any,
        data: dict[str, Any],
        call_type: str,
    ) -> dict[str, Any]:
        """Intercept and evaluate request against active policies."""
        try:
            # 1. Filter call_type
            if call_type not in (
                "completion",
                "acompletion",
                "chat_completion",
                "chat_completion_stream",
            ):
                return data

            settings = get_settings()

            # 2. Extract tenant identity
            tenant_id = None
            key_hash = "unknown"
            if user_api_key_dict:
                tenant_id = getattr(user_api_key_dict, "team_id", None) or (
                    user_api_key_dict.get("team_id") if isinstance(user_api_key_dict, dict) else None
                )
                raw_token = getattr(user_api_key_dict, "api_key", None) or (
                    user_api_key_dict.get("api_key") if isinstance(user_api_key_dict, dict) else None
                )
                if raw_token:
                    key_hash = hashlib.sha256(raw_token.encode()).hexdigest()[:16]

            if not tenant_id:
                tenant_id = f"key:{key_hash}"

            # 3. Resolve Mode
            key_meta = (
                getattr(user_api_key_dict, "metadata", {})
                or (user_api_key_dict.get("metadata", {}) if isinstance(user_api_key_dict, dict) else {})
                or {}
            )
            mode = key_meta.get("gh_mode") or holder.current.modes.get(tenant_id) or settings.DEFAULT_MODE

            # 4. Resolve Opt-Out
            headers = data.get("headers") or {}
            metadata = data.setdefault("metadata", {})
            if isinstance(metadata, dict):
                req_headers = metadata.get("headers") or {}
            else:
                req_headers = {}

            opt_out = (
                str(headers.get("x-gh-no-optimize", "")).lower() in ("1", "true", "yes")
                or str(req_headers.get("x-gh-no-optimize", "")).lower() in ("1", "true", "yes")
                or bool(metadata.get("no_optimize", False))
                if isinstance(metadata, dict)
                else False
            )

            # 5. Extract Session Pin if present
            session_id = data.get("session_id")
            if not session_id and isinstance(metadata, dict):
                session_id = metadata.get("session_id")

            # 6. Fingerprint
            messages = data.get("messages", [])
            tools = data.get("tools")
            response_format = data.get("response_format")
            requested_model = data.get("model", "")

            fp = fingerprint(
                messages=messages,
                tools=tools,
                response_format=response_format,
                requested_model=requested_model,
            )

            # 7. Matcher Decision
            rand_val = random.random()
            decision = decide(
                snapshot=holder.get_index(),
                tenant_id=tenant_id,
                mode=mode,
                requested_model=requested_model,
                fp=fp,
                opt_out=opt_out,
                session_pin=None,  # Handled in-memory / session pins table
                rand=rand_val,
            )
            DECISIONS_TOTAL.labels(reason=decision.reason).inc()

            # 8. Act on Decision
            if decision.apply and decision.target_model:
                original_model = requested_model
                data["model"] = decision.target_model

                if decision.scaffold:
                    data = apply_scaffold(data, decision.scaffold)

                # Metadata propagation
                metadata = data.setdefault("metadata", {})
                req_meta = metadata.setdefault("requester_metadata", {})
                req_meta["gh_policy_id"] = decision.policy_id
                req_meta["gh_requested_model"] = original_model
                req_meta["gh_optimized"] = True
                req_meta["gh_canary"] = decision.canary
                req_meta["gh_decision_reason"] = decision.reason

                tags = metadata.setdefault("tags", [])
                tags.append("gh_optimized")
                if decision.policy_id:
                    tags.append(f"gh:policy:{decision.policy_id}")

                # Internal markers for response header hook
                data["_gh_policy_id"] = decision.policy_id
                data["_gh_requested_model"] = original_model

            elif decision.reason == "shadow":
                req_meta = metadata.setdefault("requester_metadata", {})
                req_meta["gh_shadow_policy_id"] = decision.policy_id
                req_meta["gh_decision_reason"] = "shadow"

            return data

        except Exception as exc:
            # Fail safe: never crash proxy request
            logger.exception("Error in gateway_harness pre_call_hook: %s", exc)
            return data

    async def async_post_call_response_headers_hook(
        self,
        data: dict[str, Any],
        user_api_key_dict: dict[str, Any] | Any,
        response_headers: dict[str, Any],
    ) -> dict[str, str]:
        """Inject custom tracking headers for optimized responses."""
        headers: dict[str, str] = {}
        if isinstance(data, dict) and data.get("_gh_policy_id"):
            headers["x-gh-optimized-from"] = str(data.get("_gh_requested_model", ""))
            headers["x-gh-policy"] = str(data.get("_gh_policy_id", ""))
        return headers
