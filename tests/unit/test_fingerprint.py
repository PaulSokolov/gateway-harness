import time

from gateway_harness.fingerprint import (
    fingerprint,
    normalize,
    shape,
    template_id,
    workflow_sig,
)


def test_normalize_volatile_tokens():
    text = (
        "Order 'ORD-1234' on 2026-10-26 with uuid 12345678-1234-1234-1234-123456789abc "
        "at https://example.com/order?id=123 by user@domain.com, total $49.99 (0x12345678)"
    )
    norm = normalize(text)
    assert "<q>" in norm
    assert "<dt>" in norm
    assert "<uuid>" in norm
    assert "<url>" in norm
    assert "<email>" in norm
    assert "<n>" in norm
    assert "<hex>" in norm


def test_template_id_invariance():
    m1 = [{"role": "user", "content": "Book table for 4 people on 2026-10-27 at 'Bistro 42'"}]
    m2 = [{"role": "user", "content": "Book table for 2 people on 2026-11-01 at 'Restaurant ABC'"}]
    t1 = template_id(m1)
    t2 = template_id(m2)
    assert t1 == t2
    assert len(t1) == 16


def test_workflow_sig_differences():
    m1 = [
        {"role": "system", "content": "You are a customer support agent."},
        {"role": "user", "content": "Help me"},
    ]
    m2 = [
        {"role": "system", "content": "You are a financial advisor."},
        {"role": "user", "content": "Help me"},
    ]
    sig1 = workflow_sig(m1, tools=None, response_format=None, requested_model="claude-3-5-sonnet")
    sig2 = workflow_sig(m2, tools=None, response_format=None, requested_model="claude-3-5-sonnet")
    assert sig1 != sig2
    assert len(sig1) == 16


def test_all_seven_shapes():
    # 1. tool_calling
    tool = {"type": "function", "function": {"name": "get_weather", "parameters": {}}}
    assert shape([{"role": "user", "content": "hi"}], tools=[tool], response_format=None) == "tool_calling"
    assert shape([{"role": "tool", "content": "sunny"}], tools=None, response_format=None) == "tool_calling"

    # 2. multimodal
    img_msg = [{"role": "user", "content": [{"type": "text", "text": "look"}, {"type": "image_url"}]}]
    assert shape(img_msg, tools=None, response_format=None) == "multimodal"

    # 3. structured_output
    assert (
        shape([{"role": "user", "content": "hi"}], tools=None, response_format={"type": "json_object"})
        == "structured_output"
    )

    # 4. multi_turn (user turns > 2)
    multi = [
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "2"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "3"},
    ]
    assert shape(multi, tools=None, response_format=None) == "multi_turn"

    # 5. one_shot_templated (system present, 1-2 user turns)
    templated = [{"role": "system", "content": "System prompt"}, {"role": "user", "content": "Do task"}]
    assert shape(templated, tools=None, response_format=None) == "one_shot_templated"

    # 6. one_shot_simple (1 user turn, no system)
    simple = [{"role": "user", "content": "Hello"}]
    assert shape(simple, tools=None, response_format=None) == "one_shot_simple"

    # 7. other (e.g. 0 user turns or empty)
    assert shape([], tools=None, response_format=None) == "other"


def test_fingerprint_benchmark():
    # 20-message conversation
    messages = [{"role": "system", "content": "You are a helpful coding assistant."}]
    for i in range(19):
        role = "user" if i % 2 == 0 else "assistant"
        messages.append({"role": role, "content": f"Message {i} with order 'ORD-{i}' and price ${i}.50"})

    durations = []
    for _ in range(50):
        t0 = time.perf_counter()
        fingerprint(messages, tools=None, response_format=None, requested_model="gpt-4o")
        t1 = time.perf_counter()
        durations.append(t1 - t0)

    durations.sort()
    median_ms = durations[len(durations) // 2] * 1000
    assert median_ms < 0.3, f"Fingerprinting took {median_ms:.3f}ms, expected < 0.3ms"
