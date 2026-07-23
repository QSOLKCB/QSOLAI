"""End-to-end deterministic QSOLAI orchestration pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .adapters import ManualAdapter, invoke_slot, normalize_observation
from .adjudication import adjudicate
from .artifacts import build_artifact_map, safe_run_directory, verify_run_directory, write_artifacts
from .canonical import domain_hash, parse_json_bytes, sha256_bytes
from .contracts import (
    Candidate,
    CompiledPlan,
    CompiledPrompt,
    DecisionReceipt,
    HumanApprovalReceipt,
    PolicyPack,
    RawObservation,
    TaskEnvelope,
    VerificationResult,
)
from .errors import QSOLAIError
from .implementation import build_implementation_identity
from .planner import compile_plan
from .prompting import compile_prompts
from .state import RunStateMachine
from .verification import verify_candidate


@dataclass(frozen=True)
class PipelineResult:
    run_id: str
    task: TaskEnvelope
    policy: PolicyPack
    implementation: Mapping[str, object]
    plan: CompiledPlan
    prompts: tuple[CompiledPrompt, ...]
    observations: tuple[RawObservation, ...]
    candidates: tuple[Candidate, ...]
    verification: tuple[VerificationResult, ...]
    decision: DecisionReceipt
    approval: HumanApprovalReceipt | None
    events: tuple
    final_state: str


def load_task(path: Path) -> TaskEnvelope:
    try:
        value = parse_json_bytes(path.read_bytes())
    except OSError as exc:
        raise QSOLAIError("TASK_READ_FAILED", f"cannot read task file: {path}") from exc
    return TaskEnvelope.from_dict(value)


def load_policy(path: Path) -> PolicyPack:
    try:
        value = parse_json_bytes(path.read_bytes())
    except OSError as exc:
        raise QSOLAIError("POLICY_READ_FAILED", f"cannot read policy file: {path}") from exc
    return PolicyPack.from_dict(value)


def _run_id(task: TaskEnvelope, policy: PolicyPack, implementation: Mapping[str, object]) -> str:
    return domain_hash(
        "QSOLAI/RUN/v1",
        {
            "engine_version": implementation["engine_version"],
            "implementation_sha256": implementation["source_bundle_sha256"],
            "task_sha256": task.identity,
            "policy_sha256": policy.identity,
            "mutation_index": task.mutation_index,
            "run_nonce": task.run_nonce,
        },
    )[:24]


def _validate_support(task: TaskEnvelope, policy: PolicyPack) -> None:
    if task.execution_profile != "SIM_ONLY" or policy.execution_profile != "SIM_ONLY":
        raise QSOLAIError("PROFILE_NOT_SIM_ONLY", "v0.1.0 refuses non-simulation authority")
    if policy.support_profile != "NONE":
        if task.risk_tier not in {"HIGH", "MISSION_CRITICAL"}:
            raise QSOLAIError("HIGH_STAKES_RISK_TIER_INVALID", "high-stakes support requires HIGH or MISSION_CRITICAL risk tier")
        if policy.support_profile == "MISSION_CRITICAL_SUPPORT" and task.risk_tier != "MISSION_CRITICAL":
            raise QSOLAIError("MISSION_CRITICAL_RISK_TIER_REQUIRED", "mission-critical support requires MISSION_CRITICAL risk tier")
        if not task.evidence_requirements:
            raise QSOLAIError("HIGH_STAKES_EVIDENCE_REQUIRED", "high-stakes support requires explicit evidence records")
        if not all(item.required and item.record_ids for item in task.evidence_requirements):
            raise QSOLAIError("HIGH_STAKES_EVIDENCE_REQUIRED", "all high-stakes evidence requirements must be explicit and required")


def execute_pipeline(
    task: TaskEnvelope,
    policy: PolicyPack,
    *,
    captured: Mapping[str, RawObservation] | None = None,
    manual: Mapping[str, bytes] | None = None,
    allow_subprocess: bool = False,
    approval: HumanApprovalReceipt | None = None,
) -> PipelineResult:
    implementation = build_implementation_identity()
    run_id = _run_id(task, policy, implementation)
    machine = RunStateMachine()
    machine.transition("CREATED", {"run_id": run_id})
    _validate_support(task, policy)
    machine.transition("VALIDATED", {"task_sha256": task.identity, "policy_sha256": policy.identity, "execution_profile": "SIM_ONLY"})

    plan = compile_plan(task, policy)
    if len(plan.slots) > policy.maximum_attempts:
        raise QSOLAIError("ATTEMPT_LIMIT_EXCEEDED", "compiled worker slots exceed deterministic maximum-attempt limit")
    prompts = compile_prompts(task, policy, plan)
    machine.transition("PLANNED", {"plan_sha256": plan.identity, "slot_count": len(plan.slots)})
    machine.transition("DISPATCH_READY", {"prompt_sha256": [item.identity for item in prompts]})

    agent_by_id = {item.agent_id: item for item in policy.agents}
    prompt_by_slot = {item.slot_id: item for item in prompts}
    observations = tuple(
        invoke_slot(
            task=task,
            policy=policy,
            agent=agent_by_id[slot.agent_id],
            slot=slot,
            prompt=prompt_by_slot[slot.slot_id],
            captured=captured,
            manual=manual,
            allow_subprocess=allow_subprocess,
        )
        for slot in plan.slots
    )
    machine.transition("OBSERVATIONS_CAPTURED", {"observation_sha256": [item.identity for item in observations]})

    candidates = tuple(normalize_observation(observation, slot) for observation, slot in zip(observations, plan.slots))
    machine.transition("CANDIDATES_NORMALIZED", {"candidate_sha256": [item.identity for item in candidates]})
    results = tuple(verify_candidate(candidate, task, policy) for candidate in candidates)
    machine.transition("VERIFIED", {"verification_sha256": [item.identity for item in results]})
    decision = adjudicate(task, policy, candidates, results)
    machine.transition("ADJUDICATED", {"decision_sha256": decision.identity, "selected_candidate_sha256": decision.selected_candidate_sha256})

    missing_slots = sorted(item.slot_id for item in observations if item.status == "MISSING")
    eligible_hashes = set(decision.eligible_candidates)
    eligible_backends = {item.backend_id for item in candidates if item.identity in eligible_hashes}
    if missing_slots:
        machine.transition("INCOMPLETE", {"reason": "OBSERVATIONS_MISSING", "slot_ids": missing_slots})
    elif policy.support_profile != "NONE" and len(eligible_backends) < policy.required_independent_backends:
        machine.transition("INCOMPLETE", {"reason": "INDEPENDENT_BACKEND_RESULTS_INSUFFICIENT", "eligible_backend_ids": sorted(eligible_backends)})
    elif decision.status == "NO_ELIGIBLE_CANDIDATE":
        machine.transition("REJECTED", {"reason": "NO_ELIGIBLE_CANDIDATE"})
    elif policy.human_approval_required:
        machine.transition("HUMAN_REVIEW_REQUIRED", {"decision_sha256": decision.identity})
        if approval is not None:
            if approval.decision_sha256 != decision.identity:
                raise QSOLAIError("APPROVAL_LINEAGE_MISMATCH", "human approval does not bind the current decision")
            if approval.decision == "accept":
                machine.transition("COMMITTED", {"human_approval_sha256": approval.identity})
            else:
                machine.transition("REJECTED", {"human_approval_sha256": approval.identity, "reason": "HUMAN_REJECTED"})
    else:
        if approval is not None:
            raise QSOLAIError("APPROVAL_UNEXPECTED", "policy does not require human approval")
        machine.transition("COMMITTED", {"decision_sha256": decision.identity})

    assert machine.state is not None
    return PipelineResult(run_id, task, policy, implementation, plan, prompts, observations, candidates, results, decision, approval, tuple(machine.events), machine.state)


def files_for_result(result: PipelineResult) -> dict[str, bytes]:
    return build_artifact_map(
        run_id=result.run_id,
        task=result.task,
        policy=result.policy,
        implementation=result.implementation,
        plan=result.plan,
        prompts=result.prompts,
        observations=result.observations,
        candidates=result.candidates,
        verification=result.verification,
        decision=result.decision,
        approval=result.approval,
        events=result.events,
        final_state=result.final_state,
    )


def run_to_directory(
    task: TaskEnvelope,
    policy: PolicyPack,
    runs_root: Path,
    *,
    run_name: str | None = None,
    allow_subprocess: bool = False,
    manual: Mapping[str, bytes] | None = None,
) -> tuple[Path, PipelineResult]:
    predicted_implementation = build_implementation_identity()
    predicted_run_id = _run_id(task, policy, predicted_implementation)
    target = safe_run_directory(runs_root, run_name or predicted_run_id)
    result = execute_pipeline(task, policy, manual=manual, allow_subprocess=allow_subprocess)
    if result.run_id != predicted_run_id:
        raise QSOLAIError("RUN_ID_DRIFT", "run identity changed between output validation and execution")
    write_artifacts(target, files_for_result(result))
    verify_run_directory(target)
    return target, result


def _load_run(run_dir: Path) -> tuple[TaskEnvelope, PolicyPack, dict[str, RawObservation], HumanApprovalReceipt | None]:
    task = TaskEnvelope.from_dict(parse_json_bytes((run_dir / "task.json").read_bytes()))
    policy = PolicyPack.from_dict(parse_json_bytes((run_dir / "policy.json").read_bytes()))
    observations: dict[str, RawObservation] = {}
    for path in sorted((run_dir / "observations").glob("*.json")):
        observation = RawObservation.from_dict(parse_json_bytes(path.read_bytes()))
        if path.stem != observation.slot_id or observation.slot_id in observations:
            raise QSOLAIError("OBSERVATION_SLOT_MISMATCH", "observation file does not map uniquely to its slot")
        observations[observation.slot_id] = observation
    approval_path = run_dir / "human-approval.json"
    approval = HumanApprovalReceipt.from_dict(parse_json_bytes(approval_path.read_bytes())) if approval_path.exists() else None
    return task, policy, observations, approval


def replay_run(run_dir: Path) -> dict[str, object]:
    verify_run_directory(run_dir)
    task, policy, observations, approval = _load_run(run_dir)
    result = execute_pipeline(task, policy, captured=observations, approval=approval)
    expected = files_for_result(result)
    actual_paths = {path.relative_to(run_dir).as_posix() for path in run_dir.rglob("*") if path.is_file()}
    if actual_paths != set(expected):
        raise QSOLAIError("REPLAY_FILE_SET_MISMATCH", "replayed artifact file set differs")
    for relative, body in expected.items():
        if (run_dir / relative).read_bytes() != body:
            raise QSOLAIError("REPLAY_BYTE_MISMATCH", f"replayed bytes differ: {relative}")
    return {
        "status": "PASS",
        "run_id": result.run_id,
        "final_state": result.final_state,
        "manifest_file_sha256": sha256_bytes(expected["manifest.json"]),
        "final_txt_sha256": sha256_bytes(expected["final.txt"]),
        "decision_sha256": result.decision.identity,
        "event_log_sha256": sha256_bytes(expected["event-log.jsonl"]),
    }


def approve_run(run_dir: Path, reviewer: str, decision_value: str, notes: str = "") -> dict[str, object]:
    report = verify_run_directory(run_dir)
    if report["final_state"] != "HUMAN_REVIEW_REQUIRED":
        raise QSOLAIError("APPROVAL_STATE_INVALID", "run is not awaiting human review")
    task, policy, observations, current_approval = _load_run(run_dir)
    if current_approval is not None:
        raise QSOLAIError("APPROVAL_ALREADY_EXISTS", "run already has a human approval receipt")
    decision = DecisionReceipt.from_dict(parse_json_bytes((run_dir / "decision.json").read_bytes()))
    approval = HumanApprovalReceipt("qsolai.human-approval/v1", reviewer, decision_value, decision.identity, notes)
    result = execute_pipeline(task, policy, captured=observations, approval=approval)
    write_artifacts(run_dir, files_for_result(result), replace=True)
    verified = verify_run_directory(run_dir)
    return {**verified, "human_approval_sha256": approval.identity}


def import_observation(run_dir: Path, slot_id: str, source: Path) -> dict[str, object]:
    report = verify_run_directory(run_dir)
    if report["final_state"] == "COMMITTED":
        raise QSOLAIError("RUN_IMMUTABLE", "committed runs cannot import observations")
    task, policy, observations, approval = _load_run(run_dir)
    if approval is not None:
        raise QSOLAIError("RUN_IMMUTABLE", "reviewed runs cannot import observations")
    result_before = execute_pipeline(task, policy, captured=observations)
    slot = next((item for item in result_before.plan.slots if item.slot_id == slot_id), None)
    if slot is None or slot.adapter != "MANUAL":
        raise QSOLAIError("IMPORT_SLOT_INVALID", "slot is unknown or not a ManualAdapter slot")
    prompt = next(item for item in result_before.prompts if item.slot_id == slot_id)
    agent = next(item for item in policy.agents if item.agent_id == slot.agent_id)
    raw = source.read_bytes()
    imported = ManualAdapter({slot_id: raw}).invoke(task=task, policy=policy, agent=agent, slot=slot, prompt=prompt)
    observations[slot_id] = imported
    result = execute_pipeline(task, policy, captured=observations)
    write_artifacts(run_dir, files_for_result(result), replace=True)
    verified = verify_run_directory(run_dir)
    return {**verified, "observation_sha256": imported.identity}
