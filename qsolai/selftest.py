"""Small runtime self-test independent of the repository test suite."""

from __future__ import annotations

from .canonical import canonical_json, domain_hash
from .contracts import (
    AgentManifest,
    CapabilityGrant,
    Constraint,
    PolicyPack,
    ROLES,
    StyleContract,
    TaskEnvelope,
)
from .engine import execute_pipeline
from .state import RunStateMachine, verify_event_chain


def run_selftest() -> dict[str, object]:
    if canonical_json({"z": [3, 2, 1], "a": {"b": True}}) != '{"a":{"b":true},"z":[3,2,1]}':
        raise AssertionError("canonical JSON known answer failed")
    if domain_hash("QSOLAI/SELFTEST/v1", {"x": 1}) != "13b6072de7438bc4dd417bed0e42ae0799fc00fa80fd91c97c773cd09de56a0b":
        raise AssertionError("domain-separated hash known answer failed")

    machine = RunStateMachine()
    for state in ("CREATED", "VALIDATED", "PLANNED", "DISPATCH_READY", "OBSERVATIONS_CAPTURED", "CANDIDATES_NORMALIZED", "VERIFIED", "ADJUDICATED", "COMMITTED"):
        machine.transition(state)
    if verify_event_chain(machine.events) != "COMMITTED":
        raise AssertionError("event chain self-test failed")

    response = {
        "protocol": "qsolai.worker-result/v1",
        "summary": "Native implementation proposal",
        "claims": [],
        "uncertainties": [],
        "constraint_report": {"satisfied": ["native"], "possibly_violated": []},
        "proposed_actions": [],
        "answer": "Use native C99 with the Win32 API.",
    }
    grant = CapabilityGrant("qsolai.capability-grant/v1", "mock-only", "SIM_ONLY", ("MOCK",), False, (), {})
    agent = AgentManifest("qsolai.agent/v1", "selftest-agent", "selftest-backend", "MOCK", ROLES, "mock-only", response)
    style = StyleContract("qsolai.style/v1", (), (), 4096, 2)
    policy = PolicyPack("qsolai.policy/v1", "selftest", "SIM_ONLY", "NONE", False, 1, 65536, 1000, (grant,), (agent,), style, (), False, 8)
    task = TaskEnvelope(
        "qsolai.task/v1",
        "selftest",
        "implementation",
        "Produce a native implementation.",
        "LOW",
        "CAPTURED_LIVE",
        "SIM_ONLY",
        (Constraint("qsolai.constraint/v1", "native", "REQUIRED", ("C99", "Win32"), False),),
        (),
        (),
        0,
        "selftest",
        (),
    )
    result = execute_pipeline(task, policy)
    if result.final_state != "COMMITTED" or not result.decision.selected_candidate_sha256:
        raise AssertionError("end-to-end self-test failed")
    return {
        "status": "PASS",
        "engine_version": "0.1.0",
        "event_count": len(result.events),
        "decision_sha256": result.decision.identity,
        "selected_candidate_sha256": result.decision.selected_candidate_sha256,
    }
