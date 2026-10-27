from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from gateway_harness.capture.spool import SpoolWriter
from gateway_harness.contracts import Payload, TraceEvent
from gateway_harness.fingerprint import fingerprint
from gateway_harness.metrics import CAPTURE_ERRORS_TOTAL, REQUESTS_TOTAL
from gateway_harness.scrub import scrub_obj
from gateway_harness.settings import get_settings

logger = logging.getLogger(__name__)

_spool_writer: SpoolWriter | None = None


def get_spool_writer() -> SpoolWriter:
    global _spool_writer
    if _spool_writer is None:
        settings = get_settings()
        spool_dir = settings.DATA_DIR / "spool"
        _spool_writer = SpoolWriter(spool_dir)
    return _spool_writer


class CaptureMixin:
    """Non-blocking telemetry capture mixin for LiteLLM CustomLogger."""

    async def _capture_from_slo(
        self,
        slo: dict[str, Any],
        status: str,
        error_class: str | None = None,
    ) -> None:
        try:
            settings = get_settings()
            if settings.DEFAULT_MODE == "off":
                return

            event_id = str(slo.get("id") or slo.get("litellm_call_id") or "")
            if not event_id:
                return

            meta = slo.get("metadata") or {}
            req_meta = meta.get("requester_metadata") or {}
            tags = list(slo.get("request_tags") or [])

            # Check if internal worker call
            is_internal = "gh-internal" in tags or meta.get("user_api_key_alias") == "gh-internal"

            # Tenant resolution
            team_id = meta.get("user_api_key_team_id") or meta.get("team_id")
            if team_id:
                tenant_id = str(team_id)
            else:
                key_hash = str(meta.get("user_api_key_hash") or "unknown")
                tenant_id = f"key:{key_hash[:8]}"

            # Messages and payload scrubbing
            raw_messages = slo.get("messages") or []
            scrubbed_messages = scrub_obj(raw_messages)
            req_canonical = json.dumps(scrubbed_messages, sort_keys=True)
            req_hash = hashlib.sha256(req_canonical.encode("utf-8")).hexdigest()

            payloads: list[Payload] = [
                Payload(
                    hash=req_hash,
                    kind="request",
                    body={"messages": scrubbed_messages},
                )
            ]

            # Response scrubbing
            raw_response = slo.get("response")
            resp_hash: str | None = None
            if raw_response:
                scrubbed_response = scrub_obj(raw_response)
                resp_canonical = json.dumps(scrubbed_response, sort_keys=True)
                resp_hash = hashlib.sha256(resp_canonical.encode("utf-8")).hexdigest()
                resp_body = (
                    scrubbed_response
                    if isinstance(scrubbed_response, dict)
                    else {"content": scrubbed_response}
                )
                payloads.append(
                    Payload(
                        hash=resp_hash,
                        kind="response",
                        body=resp_body,
                    )
                )

            # Fingerprinting
            tools = slo.get("model_parameters", {}).get("tools")
            resp_fmt = slo.get("model_parameters", {}).get("response_format")
            requested_model = str(slo.get("model_group") or slo.get("model") or "")
            fp = fingerprint(
                messages=raw_messages if isinstance(raw_messages, list) else [],
                tools=tools,
                response_format=resp_fmt,
                requested_model=requested_model,
            )

            # Token and cost metrics
            prompt_tokens = int(slo.get("prompt_tokens") or 0)
            completion_tokens = int(slo.get("completion_tokens") or 0)
            cached_tokens = 0
            usage_obj = meta.get("usage_object") or {}
            pt_details = usage_obj.get("prompt_tokens_details") or slo.get("prompt_tokens_details") or {}
            if isinstance(pt_details, dict):
                cached_tokens = int(pt_details.get("cached_tokens") or 0)

            cost_usd = float(slo.get("response_cost") or 0.0)
            latency_ms = float(slo.get("response_time") or 0.0) * 1000.0

            # Policy and optimization tags
            policy_id = req_meta.get("gh_policy_id")
            if not policy_id:
                for tag in tags:
                    if tag.startswith("gh:policy:"):
                        policy_id = tag.split("gh:policy:", 1)[1]
                        break

            optimized = bool(policy_id)
            canary = req_meta.get("gh_canary", False) or "gh:canary" in tags

            # Finish reason
            finish_reason = None
            if isinstance(raw_response, dict):
                choices = raw_response.get("choices")
                if isinstance(choices, list) and choices:
                    finish_reason = choices[0].get("finish_reason")

            event = TraceEvent(
                event_id=event_id,
                ts=datetime.now(UTC),
                tenant_id=tenant_id,
                api_key_hash=str(meta.get("user_api_key_hash") or ""),
                session_id=str(slo.get("session_id") or "") or None,
                call_type=str(slo.get("call_type") or "chat_completion"),
                stream=bool(slo.get("stream") or slo.get("model_parameters", {}).get("stream")),
                requested_model=requested_model,
                served_model=str(slo.get("model") or ""),
                provider=str(slo.get("custom_llm_provider") or ""),
                status="success" if status == "success" else "failure",
                error_class=error_class,
                finish_reason=finish_reason,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=cached_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                optimized=optimized,
                policy_id=policy_id,
                canary=canary,
                internal=is_internal,
                has_tools=bool(tools),
                has_images=fp.shape == "multimodal",
                response_format=str(resp_fmt) if resp_fmt else None,
                n_messages=len(raw_messages) if isinstance(raw_messages, list) else 1,
                fingerprint=fp,
                request_hash=req_hash,
                response_hash=resp_hash,
            )

            record = {
                "event": event.model_dump(mode="json"),
                "payloads": [p.model_dump(mode="json") for p in payloads],
            }

            spool = get_spool_writer()
            spool.submit(record)
            REQUESTS_TOTAL.labels(
                status=event.status,
                model=event.requested_model,
                optimized=str(event.optimized).lower(),
            ).inc()

        except Exception as e:
            CAPTURE_ERRORS_TOTAL.inc()
            logger.debug("Telemetry capture error: %s", e, exc_info=True)

    async def async_log_success_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        slo = kwargs.get("standard_logging_object")
        if isinstance(slo, dict):
            await self._capture_from_slo(slo, status="success")

    async def async_log_failure_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        slo = kwargs.get("standard_logging_object")
        if isinstance(slo, dict):
            exc = kwargs.get("exception")
            error_class = str(exc.__class__.__name__ if exc else "Unknown")
            await self._capture_from_slo(slo, status="failure", error_class=error_class)
