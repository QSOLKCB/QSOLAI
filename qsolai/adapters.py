"""Worker adapters and deterministic post-capture normalization."""

from __future__ import annotations

import subprocess
import threading
import time
from abc import ABC, abstractmethod
from typing import Mapping

from .canonical import canonical_bytes, domain_hash, parse_json_bytes, thaw
from .contracts import (
    AgentManifest,
    AgentSlot,
    Candidate,
    Claim,
    CompiledPrompt,
    PolicyPack,
    RawObservation,
    TaskEnvelope,
)
from .errors import QSOLAIError
from .prompting import worker_request


def _request_identity(prompt: CompiledPrompt) -> tuple[dict[str, str], str]:
    request = worker_request(prompt)
    return request, domain_hash("QSOLAI/WORKER-REQUEST/v1", request)


def _check_worker_json(raw: bytes) -> bool:
    try:
        value = parse_json_bytes(raw)
    except QSOLAIError:
        return False
    return type(value) is dict


class WorkerAdapter(ABC):
    adapter_id: str

    @abstractmethod
    def invoke(
        self,
        *,
        task: TaskEnvelope,
        policy: PolicyPack,
        agent: AgentManifest,
        slot: AgentSlot,
        prompt: CompiledPrompt,
    ) -> RawObservation:
        raise NotImplementedError


class MockAdapter(WorkerAdapter):
    adapter_id = "MOCK"

    def invoke(self, *, task: TaskEnvelope, policy: PolicyPack, agent: AgentManifest, slot: AgentSlot, prompt: CompiledPrompt) -> RawObservation:
        _, request_sha256 = _request_identity(prompt)
        response = thaw(agent.mock_response) if agent.mock_response is not None else {
            "protocol": "qsolai.worker-result/v1",
            "summary": f"Deterministic mock proposal for {task.task_id}",
            "claims": [],
            "uncertainties": ["MockAdapter output is synthetic."],
            "constraint_report": {"satisfied": [], "possibly_violated": []},
            "proposed_actions": [],
            "answer": task.goal,
        }
        raw = canonical_bytes(response)
        if len(raw) > policy.max_observation_bytes:
            return RawObservation.create(slot.slot_id, self.adapter_id, "OUTPUT_LIMIT", request_sha256, raw[: policy.max_observation_bytes], error_code="WORKER_OUTPUT_LIMIT")
        status = "OK" if _check_worker_json(raw) else "INVALID_OUTPUT"
        return RawObservation.create(slot.slot_id, self.adapter_id, status, request_sha256, raw, error_code=None if status == "OK" else "WORKER_JSON_INVALID")


class ReplayAdapter(WorkerAdapter):
    adapter_id = "REPLAY"

    def __init__(self, observations: Mapping[str, RawObservation]) -> None:
        self.observations = dict(observations)

    def invoke(self, *, task: TaskEnvelope, policy: PolicyPack, agent: AgentManifest, slot: AgentSlot, prompt: CompiledPrompt) -> RawObservation:
        _, request_sha256 = _request_identity(prompt)
        observation = self.observations.get(slot.slot_id)
        if observation is None:
            return RawObservation.create(slot.slot_id, self.adapter_id, "MISSING", request_sha256, b"", error_code="REPLAY_OBSERVATION_MISSING")
        if observation.slot_id != slot.slot_id or observation.request_sha256 != request_sha256:
            return RawObservation.create(slot.slot_id, self.adapter_id, "INVALID_OUTPUT", request_sha256, observation.response_bytes, observation.stderr_bytes, "REPLAY_REQUEST_MISMATCH")
        return observation


class ManualAdapter(WorkerAdapter):
    adapter_id = "MANUAL"

    def __init__(self, responses: Mapping[str, bytes] | None = None) -> None:
        self.responses = dict(responses or {})

    def invoke(self, *, task: TaskEnvelope, policy: PolicyPack, agent: AgentManifest, slot: AgentSlot, prompt: CompiledPrompt) -> RawObservation:
        _, request_sha256 = _request_identity(prompt)
        raw = self.responses.get(slot.slot_id)
        if raw is None:
            return RawObservation.create(slot.slot_id, self.adapter_id, "MISSING", request_sha256, b"", error_code="MANUAL_OBSERVATION_MISSING")
        if type(raw) is not bytes:
            return RawObservation.create(slot.slot_id, self.adapter_id, "INVALID_OUTPUT", request_sha256, b"", error_code="MANUAL_OBSERVATION_NOT_BYTES")
        if len(raw) > policy.max_observation_bytes:
            return RawObservation.create(slot.slot_id, self.adapter_id, "OUTPUT_LIMIT", request_sha256, raw[: policy.max_observation_bytes], error_code="WORKER_OUTPUT_LIMIT")
        status = "OK" if _check_worker_json(raw) else "INVALID_OUTPUT"
        return RawObservation.create(slot.slot_id, self.adapter_id, status, request_sha256, raw, error_code=None if status == "OK" else "WORKER_JSON_INVALID")


class SubprocessJsonlAdapter(WorkerAdapter):
    adapter_id = "SUBPROCESS_JSONL"

    def __init__(self, *, cli_granted: bool) -> None:
        self.cli_granted = cli_granted

    def invoke(self, *, task: TaskEnvelope, policy: PolicyPack, agent: AgentManifest, slot: AgentSlot, prompt: CompiledPrompt) -> RawObservation:
        request, request_sha256 = _request_identity(prompt)
        grant = policy.grant_for(agent)
        if not self.cli_granted or not grant.allow_subprocess or self.adapter_id not in grant.allowed_adapters:
            return RawObservation.create(slot.slot_id, self.adapter_id, "ADAPTER_ERROR", request_sha256, b"", error_code="SUBPROCESS_NOT_GRANTED")
        if task.execution_profile != "SIM_ONLY":
            return RawObservation.create(slot.slot_id, self.adapter_id, "ADAPTER_ERROR", request_sha256, b"", error_code="PROFILE_NOT_SIM_ONLY")
        input_bytes = canonical_bytes(request) + b"\n"
        try:
            process = subprocess.Popen(
                list(grant.argv),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=dict(grant.environment),
                shell=False,
            )
        except (OSError, ValueError) as exc:
            return RawObservation.create(slot.slot_id, self.adapter_id, "ADAPTER_ERROR", request_sha256, b"", type(exc).__name__.encode("ascii"), "SUBPROCESS_START_FAILED")

        limit = policy.max_observation_bytes
        exceeded = threading.Event()
        stdout_buffer = bytearray()
        stderr_buffer = bytearray()

        def read_bounded(pipe: object, target: bytearray) -> None:
            try:
                while True:
                    chunk = pipe.read(4096)  # type: ignore[attr-defined]
                    if not chunk:
                        return
                    remaining = limit - len(target)
                    if remaining > 0:
                        target.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        exceeded.set()
                        return
            finally:
                pipe.close()  # type: ignore[attr-defined]

        def write_request() -> None:
            try:
                if process.stdin is not None:
                    process.stdin.write(input_bytes)
                    process.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
            finally:
                if process.stdin is not None:
                    process.stdin.close()

        assert process.stdout is not None and process.stderr is not None
        threads = (
            threading.Thread(target=read_bounded, args=(process.stdout, stdout_buffer), daemon=True),
            threading.Thread(target=read_bounded, args=(process.stderr, stderr_buffer), daemon=True),
            threading.Thread(target=write_request, daemon=True),
        )
        for worker in threads:
            worker.start()
        deadline = time.monotonic() + policy.worker_timeout_ms / 1000
        terminal_status: str | None = None
        while process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                terminal_status = "TIMEOUT"
                process.kill()
                break
            if exceeded.wait(min(0.01, remaining)):
                terminal_status = "OUTPUT_LIMIT"
                process.kill()
                break
        process.wait()
        for worker in threads:
            worker.join(timeout=1)
        stdout = bytes(stdout_buffer)
        stderr = bytes(stderr_buffer)
        if terminal_status == "TIMEOUT":
            return RawObservation.create(slot.slot_id, self.adapter_id, "TIMEOUT", request_sha256, stdout, stderr, "WORKER_TIMEOUT")
        if terminal_status == "OUTPUT_LIMIT" or exceeded.is_set():
            return RawObservation.create(slot.slot_id, self.adapter_id, "OUTPUT_LIMIT", request_sha256, stdout, stderr, "WORKER_OUTPUT_LIMIT")
        status = "OK" if process.returncode == 0 and _check_worker_json(stdout) else "INVALID_OUTPUT"
        error = None if status == "OK" else "WORKER_PROCESS_OR_JSON_INVALID"
        return RawObservation.create(slot.slot_id, self.adapter_id, status, request_sha256, stdout, stderr, error)


ADAPTER_REGISTRY = {
    "MOCK": MockAdapter,
    "REPLAY": ReplayAdapter,
    "MANUAL": ManualAdapter,
    "SUBPROCESS_JSONL": SubprocessJsonlAdapter,
}


def invoke_slot(
    *,
    task: TaskEnvelope,
    policy: PolicyPack,
    agent: AgentManifest,
    slot: AgentSlot,
    prompt: CompiledPrompt,
    captured: Mapping[str, RawObservation] | None,
    manual: Mapping[str, bytes] | None,
    allow_subprocess: bool,
) -> RawObservation:
    if captured is not None:
        return ReplayAdapter(captured).invoke(task=task, policy=policy, agent=agent, slot=slot, prompt=prompt)
    if task.determinism_mode == "CANONICAL_REPLAY":
        raise QSOLAIError("REPLAY_OBSERVATIONS_REQUIRED", "CANONICAL_REPLAY cannot invoke live workers")
    if agent.adapter == "MOCK":
        adapter: WorkerAdapter = MockAdapter()
    elif agent.adapter == "MANUAL":
        adapter = ManualAdapter(manual)
    elif agent.adapter == "SUBPROCESS_JSONL":
        adapter = SubprocessJsonlAdapter(cli_granted=allow_subprocess)
    elif agent.adapter == "REPLAY":
        raise QSOLAIError("REPLAY_OBSERVATIONS_REQUIRED", "ReplayAdapter requires frozen observations")
    else:
        raise QSOLAIError("ADAPTER_UNKNOWN", f"unknown adapter {agent.adapter}")
    return adapter.invoke(task=task, policy=policy, agent=agent, slot=slot, prompt=prompt)


def _string_list(value: object, name: str) -> tuple[str, ...]:
    if type(value) is not list or any(type(item) is not str or not item for item in value):
        raise QSOLAIError("WORKER_SCHEMA_INVALID", f"{name} must be a list of non-empty strings")
    if len(set(value)) != len(value):
        raise QSOLAIError("WORKER_SCHEMA_INVALID", f"{name} contains duplicates")
    return tuple(value)


def normalize_observation(observation: RawObservation, slot: AgentSlot) -> Candidate:
    errors: list[str] = []
    summary = ""
    claims: tuple[Claim, ...] = ()
    uncertainties: tuple[str, ...] = ()
    satisfied: tuple[str, ...] = ()
    violated: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    answer = ""
    if observation.status != "OK":
        errors.append(observation.error_code or f"OBSERVATION_{observation.status}")
    try:
        value = parse_json_bytes(observation.response_bytes)
        if type(value) is not dict:
            raise QSOLAIError("WORKER_SCHEMA_INVALID", "worker response must be an object")
        required = {"protocol", "summary", "claims", "uncertainties", "constraint_report", "proposed_actions", "answer"}
        if set(value) != required:
            raise QSOLAIError("WORKER_SCHEMA_INVALID", "worker response keys do not match protocol")
        if value["protocol"] != "qsolai.worker-result/v1":
            raise QSOLAIError("WORKER_PROTOCOL_INVALID", "worker response protocol is invalid")
        if type(value["summary"]) is not str or type(value["answer"]) is not str:
            raise QSOLAIError("WORKER_SCHEMA_INVALID", "worker summary and answer must be strings")
        if type(value["claims"]) is not list:
            raise QSOLAIError("WORKER_SCHEMA_INVALID", "worker claims must be a list")
        summary = value["summary"]
        claims = tuple(Claim.from_dict(item) for item in value["claims"])
        uncertainties = _string_list(value["uncertainties"], "uncertainties")
        report = value["constraint_report"]
        if type(report) is not dict or set(report) != {"satisfied", "possibly_violated"}:
            raise QSOLAIError("WORKER_SCHEMA_INVALID", "constraint_report is invalid")
        satisfied = _string_list(report["satisfied"], "constraint_report.satisfied")
        violated = _string_list(report["possibly_violated"], "constraint_report.possibly_violated")
        actions = _string_list(value["proposed_actions"], "proposed_actions")
        answer = value["answer"]
    except QSOLAIError as exc:
        errors.append(exc.code)
    except (TypeError, ValueError) as exc:
        errors.append(f"WORKER_NORMALIZATION_ERROR:{type(exc).__name__}")
    return Candidate(
        schema="qsolai.candidate/v1",
        slot_id=slot.slot_id,
        role=slot.role,
        backend_id=slot.backend_id,
        observation_sha256=observation.identity,
        summary=summary,
        claims=claims,
        uncertainties=uncertainties,
        satisfied_constraints=satisfied,
        possibly_violated_constraints=violated,
        proposed_actions=actions,
        answer=answer,
        normalization_errors=tuple(sorted(set(errors))),
    )
