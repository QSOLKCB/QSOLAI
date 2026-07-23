"""Conventional deterministic planner for fixed QSOLAI workflow DAGs."""

from __future__ import annotations

from .contracts import AgentSlot, CompiledPlan, PolicyPack, ROLES, TaskEnvelope
from .errors import QSOLAIError


def compile_plan(task: TaskEnvelope, policy: PolicyPack) -> CompiledPlan:
    if task.execution_profile != policy.execution_profile:
        raise QSOLAIError("PROFILE_MISMATCH", "task and policy execution profiles differ")

    slots: list[AgentSlot] = []
    ordinal = 0
    for role in ROLES:
        eligible = sorted((agent for agent in policy.agents if role in agent.roles), key=lambda item: item.agent_id)
        if not eligible:
            raise QSOLAIError("PLANNER_ROLE_UNFILLED", f"no declared agent can fill role {role}")
        for agent in eligible:
            slot_id = f"{ordinal:04d}-{role.lower().replace('_', '-')}-{agent.agent_id}"
            slots.append(
                AgentSlot(
                    schema="qsolai.agent-slot/v1",
                    slot_id=slot_id,
                    role=role,
                    agent_id=agent.agent_id,
                    backend_id=agent.backend_id,
                    adapter=agent.adapter,
                    ordinal=ordinal,
                    mutation_index=task.mutation_index,
                )
            )
            ordinal += 1

    by_role = {role: [slot for slot in slots if slot.role == role] for role in ROLES}
    edges: list[tuple[str, str]] = []
    for left_role, right_role in zip(ROLES, ROLES[1:]):
        for left in by_role[left_role]:
            for right in by_role[right_role]:
                edges.append((left.slot_id, right.slot_id))

    return CompiledPlan(
        schema="qsolai.plan/v1",
        task_sha256=task.identity,
        policy_sha256=policy.identity,
        task_class=task.task_class,
        risk_tier=task.risk_tier,
        required_evidence_ids=tuple(sorted(item.requirement_id for item in task.evidence_requirements if item.required)),
        agent_manifest_sha256s=tuple(sorted(item.identity for item in policy.agents)),
        history_catalogue_sha256=task.history_catalogue_sha256,
        determinism_mode=task.determinism_mode,
        execution_profile=task.execution_profile,
        mutation_index=task.mutation_index,
        slots=tuple(slots),
        edges=tuple(sorted(edges)),
    )
