from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

FINGERPRINT_VERSION = 1


class Mode(StrEnum):
    OFF = "off"  # no capture, no routing
    OBSERVE = "observe"  # capture only
    SHADOW = "shadow"  # capture + compute decision, never apply
    SUGGEST = "suggest"  # shadow + proposals need human approval
    AUTO = "auto"  # approved/auto-approved policies applied


Shape = Literal[
    "one_shot_simple",
    "one_shot_templated",
    "structured_output",
    "multi_turn",
    "tool_calling",
    "multimodal",
    "other",
]


class Fingerprint(BaseModel):
    version: int = FINGERPRINT_VERSION
    template_id: str  # 16 hex chars
    workflow_sig: str  # 16 hex chars
    shape: Shape


class TraceEvent(BaseModel):
    event_id: str
    ts: datetime
    tenant_id: str  # LiteLLM team_id, else "key:<hash8>"
    api_key_hash: str
    session_id: str | None = None
    call_type: str
    stream: bool
    requested_model: str
    served_model: str
    provider: str | None = None
    status: Literal["success", "failure"]
    error_class: str | None = None
    finish_reason: str | None = None
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int = 0
    cost_usd: float
    latency_ms: float
    ttft_ms: float | None = None
    optimized: bool = False
    policy_id: str | None = None
    canary: bool = False
    internal: bool = False  # traffic produced by our own worker
    has_tools: bool = False
    has_images: bool = False
    response_format: str | None = None  # "json_object" | "json_schema" | None
    n_messages: int = 1
    fingerprint: Fingerprint
    request_hash: str  # sha256 of scrubbed canonical request
    response_hash: str | None = None


class Payload(BaseModel):  # stored separately, content-addressed
    hash: str
    kind: Literal["request", "response"]
    body: dict  # scrubbed


class Scaffold(BaseModel):
    system_addendum: str | None = None
    params: dict[str, float | int | str] = Field(default_factory=dict)


class Policy(BaseModel):
    policy_id: str
    tenant_id: str | None = None  # None = all tenants of this deployment
    requested_model: str
    target_model: str
    workflow_sig: str
    template_ids: list[str]
    fingerprint_version: int = FINGERPRINT_VERSION
    scaffold: Scaffold
    status: Literal["proposed", "approved", "active", "disabled", "rolled_back"] = "proposed"
    expected_nonloss: float
    expected_savings_pct: float
    canary_rate: float = 0.03
    created_at: datetime
    expires_at: datetime


class Proposal(BaseModel):
    proposal_id: str
    policy: Policy
    evidence: dict[str, Any] = Field(default_factory=dict)
    status: Literal["proposed", "approved", "rejected"] = "proposed"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Decision(BaseModel):
    apply: bool
    target_model: str | None = None
    scaffold: Scaffold | None = None
    policy_id: str | None = None
    canary: bool = False
    reason: str  # "no_match" | "mode_shadow" | "kill_switch" | "opt_out" | "applied" | ...


class Snapshot(BaseModel):
    version: int = 0
    policies_active: list[Policy] = Field(default_factory=list)
    modes: dict[str, str] = Field(default_factory=dict)
    global_kill: bool = False


class Verdict(StrEnum):
    WIN = "win"
    LOSS = "loss"
    TIE = "tie"


class JudgeResult(BaseModel):
    verdict: Verdict
    reason: str
    judge_cost_usd: float


class ModelClient(Protocol):
    async def complete(self, model: str, messages: list[dict], params: dict) -> tuple[str, dict]:
        """Returns (text, usage_and_meta)."""
        ...
