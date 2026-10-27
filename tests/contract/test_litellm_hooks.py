import inspect

import litellm
from litellm.integrations.custom_logger import CustomLogger
from litellm.types.utils import StandardLoggingPayload

# Keys verified in P0.3 SPIKE_FINDINGS as required for capture & telemetry
REQUIRED_LOGGING_KEYS = {
    "id",
    "call_type",
    "status",
    "model",
    "model_group",
    "messages",
    "response",
    "total_tokens",
    "prompt_tokens",
    "completion_tokens",
    "startTime",
    "endTime",
    "response_time",
    "metadata",
    "request_tags",
    "session_id",
}


def test_custom_logger_signatures():
    # 1. async_pre_call_hook
    sig_pre = inspect.signature(CustomLogger.async_pre_call_hook)
    expected_pre = ["self", "user_api_key_dict", "cache", "data", "call_type"]
    assert list(sig_pre.parameters.keys()) == expected_pre

    # 2. async_post_call_response_headers_hook
    sig_headers = inspect.signature(CustomLogger.async_post_call_response_headers_hook)
    expected_headers = [
        "self",
        "data",
        "user_api_key_dict",
        "response",
        "request_headers",
        "litellm_call_info",
    ]
    assert list(sig_headers.parameters.keys()) == expected_headers

    # 3. async_log_success_event
    sig_success = inspect.signature(CustomLogger.async_log_success_event)
    expected_success = ["self", "kwargs", "response_obj", "start_time", "end_time"]
    assert list(sig_success.parameters.keys()) == expected_success

    # 4. async_log_failure_event
    sig_failure = inspect.signature(CustomLogger.async_log_failure_event)
    expected_failure = ["self", "kwargs", "response_obj", "start_time", "end_time"]
    assert list(sig_failure.parameters.keys()) == expected_failure


def test_standard_logging_payload_annotations():
    annotations = StandardLoggingPayload.__annotations__
    missing = REQUIRED_LOGGING_KEYS - set(annotations.keys())
    assert not missing, f"StandardLoggingPayload is missing required fields: {missing}"


def test_cost_per_token_callable():
    assert callable(litellm.cost_per_token)
