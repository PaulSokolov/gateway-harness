import copy

from gateway_harness.contracts import Scaffold
from gateway_harness.routing.scaffold import apply_scaffold


def test_apply_scaffold_immutability():
    original = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.7,
    }
    snapshot = copy.deepcopy(original)
    scaffold = Scaffold(system_addendum="Answer in French.", params={"temperature": 0.1})

    res = apply_scaffold(original, scaffold)
    assert original == snapshot  # Unmodified!
    assert res is not original
    assert res["temperature"] == 0.1
    assert len(res["messages"]) == 2


def test_system_prompt_missing():
    data = {"messages": [{"role": "user", "content": "What is 2+2?"}]}
    scaffold = Scaffold(system_addendum="Be concise.")
    res = apply_scaffold(data, scaffold)

    assert len(res["messages"]) == 2
    assert res["messages"][0]["role"] == "system"
    assert res["messages"][0]["content"] == "Be concise."
    assert res["messages"][1]["role"] == "user"


def test_system_prompt_string_append():
    data = {
        "messages": [
            {"role": "system", "content": "You are a calculator."},
            {"role": "user", "content": "Calculate 5 * 5"},
        ]
    }
    scaffold = Scaffold(system_addendum="Format as markdown table.")
    res = apply_scaffold(data, scaffold)

    sys_content = res["messages"][0]["content"]
    assert sys_content == "You are a calculator.\n\nFormat as markdown table."


def test_system_prompt_multipart_blocks():
    data = {
        "messages": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": "Initial context",
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            }
        ]
    }
    scaffold = Scaffold(system_addendum="Addendum rule.")
    res = apply_scaffold(data, scaffold)

    content_blocks = res["messages"][0]["content"]
    assert len(content_blocks) == 2
    # Verify cache_control on block 0 is preserved intact
    assert content_blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert content_blocks[1]["type"] == "text"
    assert "Addendum rule." in content_blocks[1]["text"]


def test_param_allowlist_and_max_tokens():
    data = {"max_tokens": 500, "temperature": 0.9}
    scaffold = Scaffold(
        params={
            "temperature": 0.2,
            "top_p": 0.95,
            "reasoning_effort": "low",
            "max_tokens": 1000,  # Larger than client! Must NOT override
            "malicious_internal_param": "bypass",
        }
    )
    res = apply_scaffold(data, scaffold)

    assert res["temperature"] == 0.2
    assert res["top_p"] == 0.95
    assert res["reasoning_effort"] == "low"
    assert res["max_tokens"] == 500  # Kept client's smaller limit!
    assert "malicious_internal_param" not in res

    # If scaffold sets smaller max_tokens, it should reduce it
    scaffold_smaller = Scaffold(params={"max_tokens": 250})
    res_smaller = apply_scaffold(data, scaffold_smaller)
    assert res_smaller["max_tokens"] == 250
