import json
from unittest.mock import AsyncMock

import pytest

from gateway_harness.probe.runner import LossExample
from gateway_harness.proposer.propose import propose


@pytest.fixture
def dummy_losses():
    return [
        LossExample(
            event_id="ev_1",
            request_messages=[{"role": "user", "content": "Extract customer age"}],
            baseline_text='{"age": 35}',
            candidate_text="Customer is 35 years old",
            validator_codes=["json_invalid"],
            judge_reason="Did not format as JSON",
        )
    ]


@pytest.mark.asyncio
async def test_propose_success(dummy_losses):
    client = AsyncMock()
    mock_payload = {
        "variants": [
            {
                "system_addendum": "Always format output strictly as JSON.",
                "params": {"temperature": 0.1, "forbidden_param": 123},
                "rationale": "Enforces JSON compliance",
            },
            {
                "system_addendum": "Be concise and return only the requested schema.",
                "params": {"top_p": 0.95},
                "rationale": "Prevents conversational filler",
            },
        ]
    }
    client.complete.return_value = (json.dumps(mock_payload), {})

    scaffolds = await propose(client, "gpt-4o", dummy_losses, [], k=2)
    assert len(scaffolds) == 2
    assert scaffolds[0].system_addendum == "Always format output strictly as JSON."
    assert scaffolds[0].params == {"temperature": 0.1}
    assert "forbidden_param" not in scaffolds[0].params
    assert scaffolds[1].params == {"top_p": 0.95}


@pytest.mark.asyncio
async def test_propose_filters_invalid_variants(dummy_losses):
    client = AsyncMock()
    mock_payload = {
        "variants": [
            # 1. Contains forbidden model mention
            {
                "system_addendum": "Answer exactly like GPT-4 would answer.",
                "params": {},
            },
            # 2. Exceeds 120 words
            {
                "system_addendum": " ".join(["word"] * 125),
                "params": {},
            },
            # 3. Valid variant
            {
                "system_addendum": "Valid concise instruction.",
                "params": {},
            },
        ]
    }
    client.complete.return_value = (json.dumps(mock_payload), {})

    scaffolds = await propose(client, "gpt-4o", dummy_losses, [], k=3)
    assert len(scaffolds) == 1
    assert scaffolds[0].system_addendum == "Valid concise instruction."
