import time
from datetime import UTC, datetime, timedelta

from gateway_harness.contracts import Fingerprint, Policy, Scaffold, Snapshot
from gateway_harness.policy.matcher import SnapshotIndex, decide


def _make_policy(
    policy_id="pol_1",
    req="gpt-4o",
    target="gpt-4o-mini",
    wf="wf_1234",
    templates=None,
    tenant_id=None,
    expires_at=None,
    fp_ver=1,
    canary_rate=0.05,
):
    return Policy(
        policy_id=policy_id,
        tenant_id=tenant_id,
        requested_model=req,
        target_model=target,
        workflow_sig=wf,
        template_ids=templates or ["tpl_abc", "tpl_def"],
        fingerprint_version=fp_ver,
        scaffold=Scaffold(system_addendum="Short summary."),
        status="active",
        expected_nonloss=0.85,
        expected_savings_pct=0.70,
        canary_rate=canary_rate,
        created_at=datetime.now(UTC),
        expires_at=expires_at or (datetime.now(UTC) + timedelta(days=1)),
    )


def test_rule_1_kill_switch():
    snap = Snapshot(global_kill=True)
    fp = Fingerprint(template_id="tpl_abc", workflow_sig="wf_1234", shape="one_shot_templated")
    d = decide(snap, "tenant_1", "auto", "gpt-4o", fp)
    assert d.apply is False
    assert d.reason == "kill_switch"


def test_rule_2_opt_out():
    snap = Snapshot(global_kill=False)
    fp = Fingerprint(template_id="tpl_abc", workflow_sig="wf_1234", shape="one_shot_templated")
    d = decide(snap, "tenant_1", "auto", "gpt-4o", fp, opt_out=True)
    assert d.apply is False
    assert d.reason == "opt_out"


def test_rule_3_modes():
    snap = Snapshot()
    fp = Fingerprint(template_id="tpl_abc", workflow_sig="wf_1234", shape="one_shot_templated")
    d_off = decide(snap, "tenant_1", "off", "gpt-4o", fp)
    assert d_off.apply is False
    assert d_off.reason == "mode_off"

    d_obs = decide(snap, "tenant_1", "observe", "gpt-4o", fp)
    assert d_obs.apply is False
    assert d_obs.reason == "mode_observe"


def test_rule_4_and_5_matching_and_filtering():
    pol = _make_policy(policy_id="pol_main", templates=["tpl_target"])
    pol_expired = _make_policy(
        policy_id="pol_exp",
        templates=["tpl_target"],
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    pol_other_tenant = _make_policy(policy_id="pol_other", templates=["tpl_target"], tenant_id="t_other")

    snap = Snapshot(policies_active=[pol_expired, pol_other_tenant, pol])
    fp_match = Fingerprint(template_id="tpl_target", workflow_sig="wf_1234", shape="one_shot_templated")
    fp_unmatched = Fingerprint(template_id="tpl_nomatch", workflow_sig="wf_1234", shape="one_shot_templated")

    # Match found
    d = decide(snap, "tenant_1", "auto", "gpt-4o", fp_match)
    assert d.apply is True
    assert d.policy_id == "pol_main"
    assert d.target_model == "gpt-4o-mini"
    assert d.reason == "optimized"

    # No match due to template_id
    d_no = decide(snap, "tenant_1", "auto", "gpt-4o", fp_unmatched)
    assert d_no.apply is False
    assert d_no.reason == "no_match"


def test_rule_6_shadow_suggest():
    pol = _make_policy(templates=["tpl_target"])
    snap = Snapshot(policies_active=[pol])
    fp = Fingerprint(template_id="tpl_target", workflow_sig="wf_1234", shape="one_shot_templated")

    d_shad = decide(snap, "tenant_1", "shadow", "gpt-4o", fp)
    assert d_shad.apply is False
    assert d_shad.reason == "shadow"
    assert d_shad.policy_id == "pol_1"
    assert d_shad.target_model == "gpt-4o-mini"

    d_sug = decide(snap, "tenant_1", "suggest", "gpt-4o", fp)
    assert d_sug.apply is False
    assert d_sug.reason == "shadow"


def test_rule_7_session_pin():
    pol = _make_policy(templates=["tpl_target"])
    snap = Snapshot(policies_active=[pol])
    fp = Fingerprint(template_id="tpl_target", workflow_sig="wf_1234", shape="one_shot_templated")

    d = decide(snap, "tenant_1", "auto", "gpt-4o", fp, session_pin="gpt-4o")
    assert d.apply is False
    assert d.reason == "session_pinned_original"


def test_rule_8_canary_rate():
    pol = _make_policy(templates=["tpl_target"], canary_rate=0.10)
    snap = Snapshot(policies_active=[pol])
    fp = Fingerprint(template_id="tpl_target", workflow_sig="wf_1234", shape="one_shot_templated")

    # rand=0.05 < 0.10 -> canary True
    d_canary = decide(snap, "tenant_1", "auto", "gpt-4o", fp, rand=0.05)
    assert d_canary.apply is True
    assert d_canary.canary is True

    # rand=0.20 >= 0.10 -> canary False
    d_prod = decide(snap, "tenant_1", "auto", "gpt-4o", fp, rand=0.20)
    assert d_prod.apply is True
    assert d_prod.canary is False


def test_matcher_benchmark_10k_policies():
    """Benchmark: 10,000 policies in index, median lookup < 20 µs."""
    policies = []
    for i in range(10000):
        policies.append(
            _make_policy(
                policy_id=f"pol_{i}",
                req=f"model_{i % 50}",
                wf=f"wf_{i % 200}",
                templates=[f"tpl_{i}"],
            )
        )
    # Add target match policy
    target_pol = _make_policy(
        policy_id="pol_target",
        req="claude-3-5-sonnet",
        wf="wf_target",
        templates=["tpl_target_query"],
    )
    policies.append(target_pol)

    snap = Snapshot(policies_active=policies)
    indexed = SnapshotIndex(snap)

    fp = Fingerprint(template_id="tpl_target_query", workflow_sig="wf_target", shape="one_shot_templated")

    # Warmup
    for _ in range(50):
        decide(indexed, "t1", "auto", "claude-3-5-sonnet", fp)

    times = []
    for _ in range(1000):
        t0 = time.perf_counter()
        decide(indexed, "t1", "auto", "claude-3-5-sonnet", fp)
        times.append(time.perf_counter() - t0)

    times.sort()
    median_us = times[len(times) // 2] * 1_000_000
    assert median_us < 20.0, f"Matcher median latency was {median_us:.2f} µs (expected < 20 µs)"
