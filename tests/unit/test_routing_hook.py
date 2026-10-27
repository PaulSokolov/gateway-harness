from datetime import UTC, datetime, timedelta

import pytest

from gateway_harness.contracts import Policy, Scaffold, Snapshot
from gateway_harness.fingerprint import fingerprint
from gateway_harness.policy.matcher import SnapshotIndex
from gateway_harness.policy.snapshot import holder
from gateway_harness.routing.hook import RoutingMixin


class DummyHandler(RoutingMixin):
    pass


@pytest.fixture
def routing_handler():
    return DummyHandler()


@pytest.mark.asyncio
async def test_routing_passthrough_non_chat(routing_handler):
    data = {"model": "gpt-4o", "input": "embed this"}
    res = await routing_handler.async_pre_call_hook(
        user_api_key_dict=None, cache=None, data=data, call_type="embedding"
    )
    assert res == data
    assert res["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_routing_opt_out_header(routing_handler):
    # Setup active policy
    msg = [{"role": "user", "content": "hello world"}]
    fp = fingerprint(messages=msg, requested_model="gpt-4o")
    pol = Policy(
        policy_id="pol_test_opt_out",
        requested_model="gpt-4o",
        target_model="gpt-4o-mini",
        workflow_sig=fp.workflow_sig,
        template_ids=[fp.template_id],
        scaffold=Scaffold(),
        status="active",
        expected_nonloss=0.85,
        expected_savings_pct=0.7,
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    snap = Snapshot(version=1, policies_active=[pol], modes={}, global_kill=False)
    holder.current = snap
    holder.indexed = SnapshotIndex(snap)

    # With opt-out header
    data = {
        "model": "gpt-4o",
        "messages": msg,
        "headers": {"x-gh-no-optimize": "1"},
    }
    res = await routing_handler.async_pre_call_hook(
        user_api_key_dict=None, cache=None, data=data, call_type="chat_completion"
    )
    assert res["model"] == "gpt-4o"  # Not rewritten!


@pytest.mark.asyncio
async def test_routing_rewriting_and_headers(routing_handler):
    msg = [{"role": "user", "content": "analyze this contract"}]
    fp = fingerprint(messages=msg, requested_model="claude-3-5-sonnet")
    pol = Policy(
        policy_id="pol_rewrite_1",
        requested_model="claude-3-5-sonnet",
        target_model="claude-3-haiku",
        workflow_sig=fp.workflow_sig,
        template_ids=[fp.template_id],
        scaffold=Scaffold(system_addendum="Act as legal reviewer.", params={"temperature": 0.2}),
        status="active",
        expected_nonloss=0.85,
        expected_savings_pct=0.7,
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    snap = Snapshot(
        version=2,
        policies_active=[pol],
        modes={"legal_team": "auto"},
        global_kill=False,
    )
    holder.current = snap
    holder.indexed = SnapshotIndex(snap)

    data = {
        "model": "claude-3-5-sonnet",
        "messages": msg,
        "temperature": 0.8,
    }
    user_api_key = {"team_id": "legal_team", "api_key": "sk-12345"}

    res = await routing_handler.async_pre_call_hook(
        user_api_key_dict=user_api_key, cache=None, data=data, call_type="chat_completion"
    )

    # Model rewritten
    assert res["model"] == "claude-3-haiku"
    assert res["temperature"] == 0.2
    assert len(res["messages"]) == 2
    assert res["messages"][0]["content"] == "Act as legal reviewer."

    # Requester metadata populated
    req_meta = res["metadata"]["requester_metadata"]
    assert req_meta["gh_policy_id"] == "pol_rewrite_1"
    assert req_meta["gh_requested_model"] == "claude-3-5-sonnet"
    assert req_meta["gh_optimized"] is True

    # Check response headers
    headers = await routing_handler.async_post_call_response_headers_hook(
        data=res, user_api_key_dict=user_api_key, response_headers={}
    )
    assert headers["x-gh-optimized-from"] == "claude-3-5-sonnet"
    assert headers["x-gh-policy"] == "pol_rewrite_1"


@pytest.mark.asyncio
async def test_routing_exception_safety(routing_handler):
    # Pass malformed data that could fail
    data = {"model": 12345}  # non-string model
    res = await routing_handler.async_pre_call_hook(
        user_api_key_dict=None, cache=None, data=data, call_type="chat_completion"
    )
    assert res is data  # Graceful fallback, no uncaught exception
