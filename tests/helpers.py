from __future__ import annotations

from typing import Any

from qsolai.contracts import (
    DEFAULT_RANKING,
    AgentManifest,
    CapabilityGrant,
    Constraint,
    EvidenceRequirement,
    PolicyPack,
    ROLES,
    StyleContract,
    TaskEnvelope,
)


def response(
    answer: str = "Bounded synthetic answer.",
    *,
    claims: list[dict[str, Any]] | None = None,
    actions: list[str] | None = None,
    satisfied: list[str] | None = None,
    violated: list[str] | None = None,
    uncertainties: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "protocol": "qsolai.worker-result/v1",
        "summary": "Synthetic worker response",
        "claims": claims or [],
        "uncertainties": uncertainties or [],
        "constraint_report": {"satisfied": satisfied or [], "possibly_violated": violated or []},
        "proposed_actions": actions or [],
        "answer": answer,
    }


def task(
    *,
    constraints: tuple[Constraint, ...] = (),
    evidence: tuple[EvidenceRequirement, ...] = (),
    mode: str = "CAPTURED_LIVE",
    mutation_index: int = 0,
    nonce: str = "test-run",
    history: tuple[str, ...] = (),
    risk: str = "LOW",
) -> TaskEnvelope:
    return TaskEnvelope(
        "qsolai.task/v1",
        "test-task",
        "test",
        "Produce a bounded synthetic answer.",
        risk,
        mode,
        "SIM_ONLY",
        constraints,
        evidence,
        (),
        mutation_index,
        nonce,
        history,
    )


def policy(
    responses: tuple[dict[str, Any], ...] | None = None,
    *,
    support_profile: str = "NONE",
    human: bool = False,
    required_backends: int = 1,
    style: StyleContract | None = None,
    anti_repetition: bool = False,
    forbidden_authority: tuple[str, ...] = (),
    adapter: str = "MOCK",
    argv: tuple[str, ...] = (),
    timeout_ms: int = 1000,
    max_bytes: int = 65536,
) -> PolicyPack:
    payloads = responses or (response(),)
    allow_subprocess = adapter == "SUBPROCESS_JSONL"
    grant = CapabilityGrant(
        "qsolai.capability-grant/v1",
        "test-grant",
        "SIM_ONLY",
        (adapter,),
        allow_subprocess,
        argv,
        {},
    )
    agents = tuple(
        AgentManifest(
            "qsolai.agent/v1",
            f"agent-{index}",
            f"backend-{index}",
            adapter,
            ROLES,
            "test-grant",
            payload if adapter == "MOCK" else None,
        )
        for index, payload in enumerate(payloads)
    )
    return PolicyPack(
        "qsolai.policy/v1",
        "test-policy",
        "SIM_ONLY",
        support_profile,
        human,
        required_backends,
        max_bytes,
        timeout_ms,
        (grant,),
        agents,
        style or StyleContract("qsolai.style/v1", (), (), 32768, 2),
        forbidden_authority,
        anti_repetition,
        64,
        DEFAULT_RANKING,
    )
