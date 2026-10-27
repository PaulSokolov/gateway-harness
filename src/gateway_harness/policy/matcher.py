"""Pure in-memory routing decision matcher."""

from datetime import UTC, datetime

from gateway_harness.contracts import Decision, Fingerprint, Policy, Snapshot


class SnapshotIndex:
    """Pre-indexed lookup structure for high-speed policy matching (<20 µs)."""

    __slots__ = ("snapshot", "_index")

    def __init__(self, snapshot: Snapshot):
        self.snapshot = snapshot
        # Map (requested_model, workflow_sig) -> list of policies
        self._index: dict[tuple[str, str], list[Policy]] = {}
        for pol in snapshot.policies_active:
            key = (pol.requested_model, pol.workflow_sig)
            if key not in self._index:
                self._index[key] = []
            self._index[key].append(pol)

    def find_candidates(self, requested_model: str, workflow_sig: str) -> list[Policy]:
        return self._index.get((requested_model, workflow_sig), [])


def decide(
    snapshot: Snapshot | SnapshotIndex,
    tenant_id: str,
    mode: str,
    requested_model: str,
    fp: Fingerprint,
    opt_out: bool = False,
    session_pin: str | None = None,
    rand: float = 0.5,
    now: datetime | None = None,
) -> Decision:
    """Evaluate routing policy rules in priority order."""
    # 1. Global kill switch
    snap = snapshot.snapshot if isinstance(snapshot, SnapshotIndex) else snapshot
    if snap.global_kill:
        return Decision(apply=False, reason="kill_switch")

    # 2. Client explicit opt-out
    if opt_out:
        return Decision(apply=False, reason="opt_out")

    # 3. Passive modes
    mode_clean = mode.lower()
    if mode_clean in ("off", "observe"):
        return Decision(apply=False, reason=f"mode_{mode_clean}")

    # Index or scan active policies
    if isinstance(snapshot, SnapshotIndex):
        candidates = snapshot.find_candidates(requested_model, fp.workflow_sig)
    else:
        candidates = [
            p
            for p in snap.policies_active
            if p.requested_model == requested_model and p.workflow_sig == fp.workflow_sig
        ]

    current_time = now or datetime.now(UTC)
    matched_policy: Policy | None = None

    for pol in candidates:
        # Rule 4: fingerprint version check
        if pol.fingerprint_version != fp.version:
            continue

        # Rule 5: Status, expiration, tenant check, template match
        if pol.status != "active":
            continue

        if pol.expires_at and pol.expires_at <= current_time:
            continue

        if pol.tenant_id is not None and pol.tenant_id != tenant_id:
            continue

        if fp.template_id not in pol.template_ids:
            continue

        matched_policy = pol
        break

    if not matched_policy:
        return Decision(apply=False, reason="no_match")

    # 6. Shadow or Suggest mode
    if mode_clean in ("shadow", "suggest"):
        return Decision(
            apply=False,
            reason="shadow",
            policy_id=matched_policy.policy_id,
            target_model=matched_policy.target_model,
            scaffold=matched_policy.scaffold,
        )

    # 7. Session pin to original requested model
    if session_pin and session_pin == requested_model:
        return Decision(apply=False, reason="session_pinned_original")

    # 8. Active rerouting with canary evaluation
    is_canary = rand < matched_policy.canary_rate
    return Decision(
        apply=True,
        target_model=matched_policy.target_model,
        scaffold=matched_policy.scaffold,
        policy_id=matched_policy.policy_id,
        canary=is_canary,
        reason="optimized",
    )
