from datetime import UTC, datetime

from gateway_harness.contracts import (
    Decision,
    Fingerprint,
    JudgeResult,
    Payload,
    Policy,
    Scaffold,
    TraceEvent,
)


def test_roundtrip_fingerprint():
    fp = Fingerprint(
        template_id="0123456789abcdef",
        workflow_sig="fedcba9876543210",
        shape="one_shot_templated",
    )
    json_str = fp.model_dump_json()
    fp2 = Fingerprint.model_validate_json(json_str)
    assert fp == fp2


def test_roundtrip_trace_event():
    now = datetime.now(UTC)
    ev = TraceEvent(
        event_id="evt_123",
        ts=now,
        tenant_id="tenant_a",
        api_key_hash="hash8888",
        session_id="sess_abc",
        call_type="chat_completion",
        stream=True,
        requested_model="claude-3-5-sonnet",
        served_model="gemini-2.5-flash",
        provider="vertex_ai",
        status="success",
        prompt_tokens=100,
        completion_tokens=50,
        cached_tokens=20,
        cost_usd=0.0015,
        latency_ms=450.0,
        optimized=True,
        policy_id="pol_999",
        canary=False,
        fingerprint=Fingerprint(template_id="tpl123", workflow_sig="sig456", shape="one_shot_templated"),
        request_hash="sha_req",
        response_hash="sha_resp",
    )
    json_str = ev.model_dump_json()
    ev2 = TraceEvent.model_validate_json(json_str)
    assert ev == ev2


def test_roundtrip_payload():
    payload = Payload(
        hash="abc123hash",
        kind="request",
        body={"messages": [{"role": "user", "content": "hi"}]},
    )
    json_str = payload.model_dump_json()
    payload2 = Payload.model_validate_json(json_str)
    assert payload == payload2


def test_roundtrip_policy_and_decision():
    now = datetime.now(UTC)
    scaffold = Scaffold(system_addendum="Follow strict schema", params={"temperature": 0.2})
    policy = Policy(
        policy_id="pol_1",
        requested_model="claude-3-5-sonnet",
        target_model="gemini-2.5-flash",
        workflow_sig="sig_test",
        template_ids=["tpl_1", "tpl_2"],
        scaffold=scaffold,
        expected_nonloss=0.98,
        expected_savings_pct=0.75,
        created_at=now,
        expires_at=now,
    )
    p2 = Policy.model_validate_json(policy.model_dump_json())
    assert policy == p2

    dec = Decision(
        apply=True,
        target_model="gemini-2.5-flash",
        scaffold=scaffold,
        policy_id="pol_1",
        reason="applied",
    )
    d2 = Decision.model_validate_json(dec.model_dump_json())
    assert dec == d2


def test_roundtrip_judge_result():
    jr = JudgeResult(verdict="win", reason="Candidate is more structured", judge_cost_usd=0.0004)
    jr2 = JudgeResult.model_validate_json(jr.model_dump_json())
    assert jr == jr2
