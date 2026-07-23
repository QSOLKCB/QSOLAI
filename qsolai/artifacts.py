"""Fail-closed run artifact construction, writing and verification."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Mapping

from .canonical import DOMAINS, canonical_bytes, domain_hash, parse_json_bytes, sha256_bytes, without_self_hash
from .contracts import (
    Candidate,
    CompiledPlan,
    CompiledPrompt,
    DecisionReceipt,
    EventRecord,
    HumanApprovalReceipt,
    PolicyPack,
    RawObservation,
    RunManifest,
    TaskEnvelope,
    VerificationResult,
)
from .errors import QSOLAIError
from .implementation import validate_implementation_identity
from .prompting import worker_request
from .state import verify_event_chain


RUN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
README_ORIGIN = (
    "QSOLAI v0.1.0 deterministic orchestration run\n"
    "\n"
    "Worker outputs are untrusted captured proposals. QSOLAI performs no proposed action.\n"
    "The run uses SIM_ONLY authority and makes no claim of deterministic LLM inference or AGI.\n"
    "Identity excludes wall-clock timestamps and host paths. See manifest.json for exact hashes.\n"
).encode("utf-8")


def safe_run_directory(runs_root: Path, run_name: str, *, allow_existing_nonempty: bool = False) -> Path:
    if not RUN_NAME_RE.fullmatch(run_name) or run_name in {".", ".."}:
        raise QSOLAIError("OUTPUT_PATH_UNSAFE", "run name is unsafe")
    root = runs_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise QSOLAIError("OUTPUT_PATH_UNSAFE", "runs root cannot be a symbolic link")
    target = (root / run_name).resolve()
    if target.parent != root:
        raise QSOLAIError("OUTPUT_PATH_UNSAFE", "run directory must be a direct child of runs root")
    if target.exists():
        if target.is_symlink() or not target.is_dir():
            raise QSOLAIError("OUTPUT_PATH_UNSAFE", "run target is not a safe directory")
        if any(target.iterdir()) and not allow_existing_nonempty:
            raise QSOLAIError("OUTPUT_DIRECTORY_NOT_EMPTY", "run output directory already exists and is not empty")
    else:
        target.mkdir(mode=0o755)
    return target


def _final_documents(state: str, decision: DecisionReceipt, selected: Candidate | None) -> tuple[bytes, bytes]:
    if state == "COMMITTED" and selected is not None:
        answer = selected.answer
        text = (answer + ("" if answer.endswith("\n") else "\n")).encode("utf-8")
    elif state == "HUMAN_REVIEW_REQUIRED":
        answer = ""
        text = b"HUMAN REVIEW REQUIRED\n"
    elif state == "REJECTED":
        answer = ""
        text = b"RUN REJECTED\n"
    else:
        answer = ""
        text = f"RUN {state}\n".encode("utf-8")
    final = {
        "schema": "qsolai.final/v1",
        "state": state,
        "decision_sha256": decision.identity,
        "selected_candidate_sha256": decision.selected_candidate_sha256,
        "answer": answer,
        "simulation_only": True,
        "proposed_actions_executed": False,
    }
    return canonical_bytes(final), text


def build_artifact_map(
    *,
    run_id: str,
    task: TaskEnvelope,
    policy: PolicyPack,
    implementation: Mapping[str, object],
    plan: CompiledPlan,
    prompts: tuple[CompiledPrompt, ...],
    observations: tuple[RawObservation, ...],
    candidates: tuple[Candidate, ...],
    verification: tuple[VerificationResult, ...],
    decision: DecisionReceipt,
    approval: HumanApprovalReceipt | None,
    events: tuple[EventRecord, ...],
    final_state: str,
) -> dict[str, bytes]:
    selected = next((item for item in candidates if item.identity == decision.selected_candidate_sha256), None)
    final_json, final_text = _final_documents(final_state, decision, selected)
    files: dict[str, bytes] = {
        "README_ORIGIN.txt": README_ORIGIN,
        "task.json": task.to_canonical_bytes(),
        "policy.json": policy.to_canonical_bytes(),
        "implementation.json": canonical_bytes(dict(implementation)),
        "plan.json": plan.to_canonical_bytes(),
        "decision.json": decision.to_canonical_bytes(),
        "final.json": final_json,
        "final.txt": final_text,
        "event-log.jsonl": b"".join(item.to_canonical_bytes() + b"\n" for item in events),
    }
    if approval is not None:
        files["human-approval.json"] = approval.to_canonical_bytes()
    for prompt in prompts:
        files[f"prompts/{prompt.slot_id}.json"] = prompt.to_canonical_bytes()
    for observation in observations:
        files[f"observations/{observation.slot_id}.json"] = observation.to_canonical_bytes()
        files[f"observations/{observation.slot_id}.raw"] = observation.response_bytes
    for candidate in candidates:
        files[f"candidates/{candidate.slot_id}.json"] = candidate.to_canonical_bytes()
    for result, candidate in zip(verification, candidates):
        files[f"verification/{candidate.slot_id}.json"] = result.to_canonical_bytes()

    implementation_hash = str(implementation["source_bundle_sha256"])
    artifact_rows = [
        {"path": path, "byte_length": len(body), "sha256": sha256_bytes(body)}
        for path, body in sorted(files.items())
    ]
    manifest_core = {
        "schema": "qsolai.manifest/v1",
        "run_id": run_id,
        "task_sha256": task.identity,
        "policy_sha256": policy.identity,
        "implementation_sha256": implementation_hash,
        "final_state": final_state,
        "artifacts": artifact_rows,
        "manifest_core_sha256": "",
    }
    manifest_hash = domain_hash(DOMAINS["manifest"], without_self_hash(manifest_core, "manifest_core_sha256"))
    manifest_core["manifest_core_sha256"] = manifest_hash
    manifest = RunManifest.from_dict(manifest_core)
    files["manifest.json"] = manifest.to_canonical_bytes()
    return dict(sorted(files.items()))


def write_artifacts(run_dir: Path, files: Mapping[str, bytes], *, replace: bool = False) -> None:
    root = run_dir.resolve()
    if not root.is_dir() or root.is_symlink():
        raise QSOLAIError("OUTPUT_PATH_UNSAFE", "run directory is not safe")
    for relative, body in sorted(files.items()):
        if type(relative) is not str or relative.startswith("/") or ".." in Path(relative).parts:
            raise QSOLAIError("ARTIFACT_PATH_UNSAFE", "artifact path is unsafe")
        if type(body) is not bytes:
            raise QSOLAIError("ARTIFACT_BYTES_INVALID", "artifact body must be bytes")
        target = (root / relative).resolve()
        if root not in target.parents:
            raise QSOLAIError("ARTIFACT_PATH_UNSAFE", "artifact escapes run directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.parent.is_symlink() or target.is_symlink():
            raise QSOLAIError("ARTIFACT_PATH_UNSAFE", "artifact path uses a symbolic link")
        if replace:
            temporary = target.with_name(target.name + ".qsolai.tmp")
            if temporary.exists():
                raise QSOLAIError("ARTIFACT_TEMP_EXISTS", "artifact temporary path already exists")
            with temporary.open("xb") as handle:
                handle.write(body)
            os.replace(temporary, target)
        else:
            with target.open("xb") as handle:
                handle.write(body)


def load_event_log(path: Path) -> tuple[EventRecord, ...]:
    try:
        lines = path.read_bytes().splitlines()
    except OSError as exc:
        raise QSOLAIError("EVENT_LOG_READ_FAILED", "cannot read event log") from exc
    events = tuple(EventRecord.from_dict(parse_json_bytes(line)) for line in lines if line)
    verify_event_chain(events)
    return events


def verify_run_directory(run_dir: Path) -> dict[str, object]:
    root = run_dir.resolve()
    if not root.is_dir() or root.is_symlink():
        raise QSOLAIError("RUN_DIRECTORY_INVALID", "run directory is invalid")
    manifest_path = root / "manifest.json"
    try:
        manifest = RunManifest.from_dict(parse_json_bytes(manifest_path.read_bytes()))
    except OSError as exc:
        raise QSOLAIError("MANIFEST_MISSING", "manifest.json is missing") from exc
    declared = set()
    for row in manifest.artifacts:
        relative = str(row["path"])
        declared.add(relative)
        target = (root / relative).resolve()
        if root not in target.parents or not target.is_file() or target.is_symlink():
            raise QSOLAIError("MANIFEST_ARTIFACT_MISSING", f"manifest artifact is missing or unsafe: {relative}")
        body = target.read_bytes()
        if len(body) != row["byte_length"] or sha256_bytes(body) != row["sha256"]:
            raise QSOLAIError("MANIFEST_ARTIFACT_TAMPERED", f"artifact hash mismatch: {relative}")
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual != declared | {"manifest.json"}:
        raise QSOLAIError("MANIFEST_FILE_SET_MISMATCH", "run directory has missing or undeclared files")
    events = load_event_log(root / "event-log.jsonl")
    final_state = verify_event_chain(events)
    if final_state != manifest.final_state:
        raise QSOLAIError("MANIFEST_STATE_MISMATCH", "manifest final state differs from event chain")
    task = TaskEnvelope.from_dict(parse_json_bytes((root / "task.json").read_bytes()))
    policy = PolicyPack.from_dict(parse_json_bytes((root / "policy.json").read_bytes()))
    if task.identity != manifest.task_sha256 or policy.identity != manifest.policy_sha256:
        raise QSOLAIError("MANIFEST_INPUT_IDENTITY_MISMATCH", "manifest task or policy identity differs")
    plan = CompiledPlan.from_dict(parse_json_bytes((root / "plan.json").read_bytes()))
    if plan.task_sha256 != task.identity or plan.policy_sha256 != policy.identity:
        raise QSOLAIError("PLAN_LINEAGE_MISMATCH", "plan input lineage differs")
    decision = DecisionReceipt.from_dict(parse_json_bytes((root / "decision.json").read_bytes()))
    if decision.task_sha256 != task.identity or decision.policy_sha256 != policy.identity:
        raise QSOLAIError("DECISION_LINEAGE_MISMATCH", "decision input lineage differs")
    if decision.human_approval_required != policy.human_approval_required:
        raise QSOLAIError("DECISION_POLICY_MISMATCH", "decision human gate differs from policy")
    slots = {item.slot_id: item for item in plan.slots}
    prompts: dict[str, CompiledPrompt] = {}
    for path in sorted((root / "prompts").glob("*.json")):
        prompt = CompiledPrompt.from_dict(parse_json_bytes(path.read_bytes()))
        if path.stem != prompt.slot_id or prompt.slot_id in prompts or prompt.slot_id not in slots:
            raise QSOLAIError("PROMPT_SLOT_MISMATCH", "prompt file does not map uniquely to a planned slot")
        if prompt.task_sha256 != task.identity or prompt.policy_sha256 != policy.identity or prompt.role != slots[prompt.slot_id].role:
            raise QSOLAIError("PROMPT_LINEAGE_MISMATCH", "prompt lineage differs from its plan")
        prompts[prompt.slot_id] = prompt
    observations: dict[str, RawObservation] = {}
    for path in sorted((root / "observations").glob("*.json")):
        observation = RawObservation.from_dict(parse_json_bytes(path.read_bytes()))
        if path.stem != observation.slot_id or observation.slot_id in observations or observation.slot_id not in slots:
            raise QSOLAIError("OBSERVATION_SLOT_MISMATCH", "observation file does not map uniquely to a planned slot")
        raw_path = root / "observations" / f"{observation.slot_id}.raw"
        if not raw_path.is_file() or raw_path.read_bytes() != observation.response_bytes:
            raise QSOLAIError("OBSERVATION_RAW_MISMATCH", "observation receipt does not match captured raw bytes")
        if observation.request_sha256 != domain_hash("QSOLAI/WORKER-REQUEST/v1", worker_request(prompts[observation.slot_id])):
            raise QSOLAIError("OBSERVATION_REQUEST_MISMATCH", "observation does not bind its compiled worker request")
        observations[observation.slot_id] = observation
    candidates: dict[str, Candidate] = {}
    results: dict[str, VerificationResult] = {}
    for path in sorted((root / "candidates").glob("*.json")):
        candidate = Candidate.from_dict(parse_json_bytes(path.read_bytes()))
        if path.stem != candidate.slot_id or candidate.slot_id in candidates or candidate.slot_id not in slots:
            raise QSOLAIError("CANDIDATE_SLOT_MISMATCH", "candidate file does not map uniquely to a planned slot")
        slot = slots[candidate.slot_id]
        if candidate.role != slot.role or candidate.backend_id != slot.backend_id or candidate.observation_sha256 != observations[candidate.slot_id].identity:
            raise QSOLAIError("CANDIDATE_LINEAGE_MISMATCH", "candidate lineage differs from its slot or observation")
        candidates[candidate.slot_id] = candidate
    for path in sorted((root / "verification").glob("*.json")):
        result = VerificationResult.from_dict(parse_json_bytes(path.read_bytes()))
        slot_id = path.stem
        if slot_id in results or slot_id not in candidates or result.candidate_sha256 != candidates[slot_id].identity:
            raise QSOLAIError("VERIFICATION_LINEAGE_MISMATCH", "verification does not bind its candidate")
        results[slot_id] = result
    if set(slots) != set(prompts) or set(slots) != set(observations) or set(slots) != set(candidates) or set(slots) != set(results):
        raise QSOLAIError("RUN_CHILD_SET_MISMATCH", "run child artifact sets do not match planned slots")
    candidate_hashes = {item.identity for item in candidates.values()}
    if set(decision.eligible_candidates) | set(decision.rejected_candidates) != candidate_hashes or set(decision.eligible_candidates) & set(decision.rejected_candidates):
        raise QSOLAIError("DECISION_CANDIDATE_SET_MISMATCH", "decision does not partition all candidates")
    selected_candidate = None
    if decision.selected_candidate_sha256 is not None:
        selected_candidate = next((item for item in candidates.values() if item.identity == decision.selected_candidate_sha256), None)
        if selected_candidate is None or results[selected_candidate.slot_id].identity != decision.selected_verification_sha256:
            raise QSOLAIError("DECISION_SELECTION_LINEAGE_MISMATCH", "decision selection lineage is invalid")
    approval_path = root / "human-approval.json"
    approval = HumanApprovalReceipt.from_dict(parse_json_bytes(approval_path.read_bytes())) if approval_path.exists() else None
    if approval is not None and approval.decision_sha256 != decision.identity:
        raise QSOLAIError("APPROVAL_LINEAGE_MISMATCH", "human approval does not bind the decision")
    if policy.human_approval_required:
        if final_state == "COMMITTED" and (approval is None or approval.decision != "accept"):
            raise QSOLAIError("APPROVAL_REQUIRED", "committed high-stakes run lacks accepting human approval")
        if final_state == "HUMAN_REVIEW_REQUIRED" and approval is not None:
            raise QSOLAIError("APPROVAL_STATE_MISMATCH", "review-pending run already contains approval")
        if approval is not None and ((approval.decision == "accept" and final_state != "COMMITTED") or (approval.decision == "reject" and final_state != "REJECTED")):
            raise QSOLAIError("APPROVAL_STATE_MISMATCH", "human approval decision does not match final state")
    elif approval is not None:
        raise QSOLAIError("APPROVAL_UNEXPECTED", "run has approval although policy does not require it")
    expected_final_json, expected_final_text = _final_documents(final_state, decision, selected_candidate)
    if (root / "final.json").read_bytes() != expected_final_json or (root / "final.txt").read_bytes() != expected_final_text:
        raise QSOLAIError("FINAL_RENDER_MISMATCH", "final artifacts do not match deterministic rendering")
    implementation = validate_implementation_identity(parse_json_bytes((root / "implementation.json").read_bytes()))
    if implementation.get("source_bundle_sha256") != manifest.implementation_sha256:
        raise QSOLAIError("IMPLEMENTATION_IDENTITY_MISMATCH", "manifest implementation identity differs")
    return {
        "status": "PASS",
        "run_id": manifest.run_id,
        "final_state": final_state,
        "manifest_sha256": manifest.manifest_core_sha256,
        "event_count": len(events),
        "artifact_count": len(manifest.artifacts),
    }
