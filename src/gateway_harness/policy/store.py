"""PostgreSQL-backed Policy Store with audited mutations and version tracking."""

import json
from typing import Any

import asyncpg

from gateway_harness.contracts import Policy, Snapshot
from gateway_harness.db.pg import get_pool


async def _bump_version_and_audit(
    conn: asyncpg.Connection,
    actor: str,
    action: str,
    target: str | None = None,
    detail: dict[str, Any] | None = None,
) -> int:
    """Increment policy_version in gh_settings and append an entry to gh_audit."""
    # Bump policy_version
    row = await conn.fetchrow(
        """
        UPDATE gh_settings
        SET value = to_jsonb((value::text)::bigint + 1)
        WHERE key = 'policy_version'
        RETURNING (value::text)::bigint as ver
        """
    )
    if not row:
        await conn.execute(
            """
            INSERT INTO gh_settings (key, value)
            VALUES ('policy_version', '2'::jsonb)
            ON CONFLICT (key) DO UPDATE
            SET value = to_jsonb((gh_settings.value::text)::bigint + 1)
            """
        )
        ver = 2
    else:
        ver = row["ver"]

    # Write audit log
    await conn.execute(
        """
        INSERT INTO gh_audit (actor, action, target, detail)
        VALUES ($1, $2, $3, $4::jsonb)
        """,
        actor,
        action,
        target,
        json.dumps(detail or {}),
    )
    return ver


async def create_proposal(
    policy: Policy,
    evidence: dict[str, Any],
    actor: str = "optimizer",
    pool: asyncpg.Pool | None = None,
) -> str:
    """Persist a new optimization proposal."""
    p = pool or await get_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO gh_proposals (proposal_id, policy, evidence, status)
                VALUES ($1, $2::jsonb, $3::jsonb, 'proposed')
                ON CONFLICT (proposal_id) DO UPDATE
                SET policy = EXCLUDED.policy, evidence = EXCLUDED.evidence, status = 'proposed'
                """,
                policy.policy_id,
                policy.model_dump_json(),
                json.dumps(evidence),
            )
            await _bump_version_and_audit(
                conn,
                actor=actor,
                action="create_proposal",
                target=policy.policy_id,
                detail={"target_model": policy.target_model},
            )
    return policy.policy_id


async def approve_proposal(
    proposal_id: str,
    actor: str,
    pool: asyncpg.Pool | None = None,
) -> None:
    """Approve a proposal and activate its policy."""
    p = pool or await get_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT policy FROM gh_proposals WHERE proposal_id = $1",
                proposal_id,
            )
            if not row:
                raise ValueError(f"Proposal {proposal_id} not found")

            pol_data = json.loads(row["policy"]) if isinstance(row["policy"], str) else row["policy"]
            policy = Policy.model_validate(pol_data)
            policy.status = "active"

            # Update proposal status
            await conn.execute(
                """
                UPDATE gh_proposals
                SET status = 'approved', decided_by = $1, decided_at = NOW()
                WHERE proposal_id = $2
                """,
                actor,
                proposal_id,
            )

            # Insert or update active policy
            await conn.execute(
                """
                INSERT INTO gh_policies (
                    policy_id, cluster_key, requested_model, target_model, scaffold,
                    template_ids, canary_rate, expected_nonloss, status, tenant_id,
                    fingerprint_version, created_at, expires_at
                ) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, 'active', $9, $10, $11, $12)
                ON CONFLICT (policy_id) DO UPDATE
                SET status = 'active', expires_at = EXCLUDED.expires_at, scaffold = EXCLUDED.scaffold
                """,
                policy.policy_id,
                f"{policy.requested_model}:{policy.workflow_sig}",
                policy.requested_model,
                policy.target_model,
                policy.scaffold.model_dump_json(),
                policy.template_ids,
                policy.canary_rate,
                policy.expected_nonloss,
                policy.tenant_id,
                policy.fingerprint_version,
                policy.created_at,
                policy.expires_at,
            )

            await _bump_version_and_audit(
                conn,
                actor=actor,
                action="approve_proposal",
                target=proposal_id,
                detail={"policy_id": policy.policy_id, "target_model": policy.target_model},
            )


async def activate_policy(
    policy: Policy,
    actor: str,
    pool: asyncpg.Pool | None = None,
) -> None:
    """Directly insert and activate a policy."""
    p = pool or await get_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO gh_policies (
                    policy_id, cluster_key, requested_model, target_model, scaffold,
                    template_ids, canary_rate, expected_nonloss, status, tenant_id,
                    fingerprint_version, created_at, expires_at
                ) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, 'active', $9, $10, $11, $12)
                ON CONFLICT (policy_id) DO UPDATE
                SET status = 'active', expires_at = EXCLUDED.expires_at, scaffold = EXCLUDED.scaffold
                """,
                policy.policy_id,
                f"{policy.requested_model}:{policy.workflow_sig}",
                policy.requested_model,
                policy.target_model,
                policy.scaffold.model_dump_json(),
                policy.template_ids,
                policy.canary_rate,
                policy.expected_nonloss,
                policy.tenant_id,
                policy.fingerprint_version,
                policy.created_at,
                policy.expires_at,
            )
            await _bump_version_and_audit(
                conn,
                actor=actor,
                action="activate_policy",
                target=policy.policy_id,
                detail={"target_model": policy.target_model},
            )


async def disable_policy(
    policy_id: str,
    actor: str,
    reason: str,
    pool: asyncpg.Pool | None = None,
) -> None:
    """Disable an active policy."""
    p = pool or await get_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE gh_policies SET status = 'disabled' WHERE policy_id = $1",
                policy_id,
            )
            await _bump_version_and_audit(
                conn,
                actor=actor,
                action="disable_policy",
                target=policy_id,
                detail={"reason": reason},
            )


async def set_mode(
    tenant_id: str,
    mode: str,
    actor: str,
    pool: asyncpg.Pool | None = None,
) -> None:
    """Update tenant operating mode."""
    p = pool or await get_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO gh_tenant_modes (tenant_id, mode, updated_by, updated_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (tenant_id) DO UPDATE
                SET mode = EXCLUDED.mode, updated_by = EXCLUDED.updated_by, updated_at = NOW()
                """,
                tenant_id,
                mode,
                actor,
            )
            await _bump_version_and_audit(
                conn,
                actor=actor,
                action="set_mode",
                target=tenant_id,
                detail={"mode": mode},
            )


async def set_global_kill(
    enabled: bool,
    actor: str,
    pool: asyncpg.Pool | None = None,
) -> None:
    """Set global kill-switch status."""
    p = pool or await get_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO gh_settings (key, value)
                VALUES ('global_kill', $1::jsonb)
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value
                """,
                "true" if enabled else "false",
            )
            await _bump_version_and_audit(
                conn,
                actor=actor,
                action="set_global_kill",
                target="global_kill",
                detail={"enabled": enabled},
            )


async def get_policy_version(pool: asyncpg.Pool | None = None) -> int:
    """Read the current policy version scalar."""
    p = pool or await get_pool()
    row = await p.fetchrow(
        "SELECT (value::text)::bigint as ver FROM gh_settings WHERE key = 'policy_version'"
    )
    return row["ver"] if row else 1


async def load_snapshot(pool: asyncpg.Pool | None = None) -> Snapshot:
    """Load the full policy snapshot from Postgres."""
    p = pool or await get_pool()
    async with p.acquire() as conn:
        # 1. Version
        v_row = await conn.fetchrow(
            "SELECT (value::text)::bigint as ver FROM gh_settings WHERE key = 'policy_version'"
        )
        version = v_row["ver"] if v_row else 1

        # 2. Global kill
        k_row = await conn.fetchrow("SELECT value FROM gh_settings WHERE key = 'global_kill'")
        global_kill = False
        if k_row and k_row["value"]:
            val = k_row["value"]
            if isinstance(val, str):
                global_kill = val.lower() == "true"
            elif isinstance(val, bool):
                global_kill = val

        # 3. Tenant modes
        m_rows = await conn.fetch("SELECT tenant_id, mode FROM gh_tenant_modes")
        modes = {r["tenant_id"]: r["mode"] for r in m_rows}

        # 4. Active policies
        p_rows = await conn.fetch(
            """
            SELECT policy_id, cluster_key, requested_model, target_model, scaffold,
                   template_ids, canary_rate, expected_nonloss, status, tenant_id,
                   fingerprint_version, created_at, expires_at
            FROM gh_policies
            WHERE status = 'active' AND (expires_at IS NULL OR expires_at > NOW())
            """
        )

        policies: list[Policy] = []
        for r in p_rows:
            scaffold_data = r["scaffold"]
            if isinstance(scaffold_data, str):
                scaffold_data = json.loads(scaffold_data)
            pol = Policy(
                policy_id=r["policy_id"],
                tenant_id=r["tenant_id"],
                requested_model=r["requested_model"],
                target_model=r["target_model"],
                workflow_sig=r["cluster_key"].split(":")[-1] if ":" in r["cluster_key"] else "",
                template_ids=r["template_ids"] or [],
                fingerprint_version=r["fingerprint_version"],
                scaffold=scaffold_data,
                status=r["status"],
                expected_nonloss=r["expected_nonloss"],
                expected_savings_pct=0.0,
                canary_rate=r["canary_rate"],
                created_at=r["created_at"],
                expires_at=r["expires_at"],
            )
            policies.append(pol)

        return Snapshot(
            version=version,
            policies_active=policies,
            modes=modes,
            global_kill=global_kill,
        )
