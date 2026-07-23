"""Frozen validated data contracts for the QSOLAI v0.1.0 kernel."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, ClassVar, Mapping

from .canonical import DOMAINS, MAX_SAFE_INTEGER, canonical_bytes, domain_hash, freeze, sha256_bytes, thaw, without_self_hash
from .errors import QSOLAIError


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
MODES = {"CANONICAL_REPLAY", "CAPTURED_LIVE", "EXPLORATORY"}
ROLES = (
    "SUBSTRATE",
    "GENERATOR",
    "CRITIC",
    "ADVERSARY",
    "CONSTRAINT_AUDITOR",
    "SYNTHESIS_CANDIDATE",
)
SUPPORT_PROFILES = {"NONE", "MEDICAL_SUPPORT", "LEGAL_SUPPORT", "MISSION_CRITICAL_SUPPORT"}
ADAPTERS = {"MOCK", "REPLAY", "MANUAL", "SUBPROCESS_JSONL"}


def _bad(message: str) -> QSOLAIError:
    return QSOLAIError("CONTRACT_INVALID", message)


def _expect(data: Mapping[str, Any], required: set[str], optional: set[str] | None = None) -> None:
    if type(data) is not dict:
        raise _bad("contract input must be a plain mapping")
    allowed = required | (optional or set())
    actual = set(data)
    if actual != required and not (required <= actual <= allowed):
        missing = sorted(required - actual)
        unexpected = sorted(actual - allowed)
        raise _bad(f"contract keys mismatch; missing={missing}; unexpected={unexpected}")


def _string(value: Any, name: str, *, allow_empty: bool = False, maximum: int = 65536) -> str:
    if type(value) is not str or (not allow_empty and not value) or len(value) > maximum:
        raise _bad(f"{name} must be a valid string")
    return value


def _optional_string(value: Any, name: str, maximum: int = 4096) -> str | None:
    if value is None:
        return None
    return _string(value, name, maximum=maximum)


def _identifier(value: Any, name: str, maximum: int = 128) -> str:
    value = _string(value, name, maximum=maximum)
    if IDENTIFIER_RE.fullmatch(value) is None:
        raise _bad(f"{name} must be a path-safe identifier")
    return value


def _exact_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise _bad(f"{name} must have exact bool type")
    return value


def _exact_int(value: Any, name: str, minimum: int = 0, maximum: int = MAX_SAFE_INTEGER) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise _bad(f"{name} must have exact bounded int type")
    return value


def _enum(value: Any, name: str, values: set[str]) -> str:
    value = _string(value, name, maximum=128)
    if value not in values:
        raise _bad(f"{name} has an unsupported value")
    return value


def _strings(value: Any, name: str, *, allow_empty: bool = True, sorted_unique: bool = False) -> tuple[str, ...]:
    if type(value) not in (list, tuple):
        raise _bad(f"{name} must be a list")
    output = tuple(_string(item, name, maximum=8192) for item in value)
    if not allow_empty and not output:
        raise _bad(f"{name} cannot be empty")
    if len(set(output)) != len(output):
        raise _bad(f"{name} cannot contain duplicates")
    if sorted_unique and output != tuple(sorted(output)):
        raise _bad(f"{name} must be sorted")
    return output


def _sha(value: Any, name: str) -> str:
    if type(value) is not str or SHA256_RE.fullmatch(value) is None:
        raise _bad(f"{name} must be lowercase SHA-256 hex")
    return value


class IdentityContract:
    DOMAIN: ClassVar[str]

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    @property
    def identity(self) -> str:
        return domain_hash(self.DOMAIN, self.to_dict())

    def to_canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())


@dataclass(frozen=True)
class Constraint(IdentityContract):
    schema: str
    constraint_id: str
    kind: str
    terms: tuple[str, ...]
    case_sensitive: bool = False
    DOMAIN: ClassVar[str] = "QSOLAI/CONSTRAINT/v1"

    def __post_init__(self) -> None:
        if self.schema != "qsolai.constraint/v1":
            raise _bad("invalid Constraint schema")
        _identifier(self.constraint_id, "constraint_id")
        _enum(self.kind, "kind", {"REQUIRED", "FORBIDDEN"})
        object.__setattr__(self, "terms", _strings(self.terms, "terms", allow_empty=False))
        _exact_bool(self.case_sensitive, "case_sensitive")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "constraint_id": self.constraint_id, "kind": self.kind, "terms": list(self.terms), "case_sensitive": self.case_sensitive}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Constraint":
        _expect(data, {"schema", "constraint_id", "kind", "terms", "case_sensitive"})
        return cls(data["schema"], data["constraint_id"], data["kind"], _strings(data["terms"], "terms", allow_empty=False), data["case_sensitive"])


@dataclass(frozen=True)
class EvidenceRequirement(IdentityContract):
    schema: str
    requirement_id: str
    description: str
    required: bool
    record_ids: tuple[str, ...]
    source_date: str | None = None
    jurisdiction: str | None = None
    DOMAIN: ClassVar[str] = "QSOLAI/EVIDENCE-REQUIREMENT/v1"

    def __post_init__(self) -> None:
        if self.schema != "qsolai.evidence-requirement/v1":
            raise _bad("invalid EvidenceRequirement schema")
        _identifier(self.requirement_id, "requirement_id")
        _string(self.description, "description", maximum=8192)
        _exact_bool(self.required, "required")
        object.__setattr__(self, "record_ids", _strings(self.record_ids, "record_ids", allow_empty=not self.required, sorted_unique=True))
        _optional_string(self.source_date, "source_date", 64)
        _optional_string(self.jurisdiction, "jurisdiction", 256)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "requirement_id": self.requirement_id, "description": self.description, "required": self.required, "record_ids": list(self.record_ids), "source_date": self.source_date, "jurisdiction": self.jurisdiction}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceRequirement":
        _expect(data, {"schema", "requirement_id", "description", "required", "record_ids", "source_date", "jurisdiction"})
        return cls(data["schema"], data["requirement_id"], data["description"], data["required"], _strings(data["record_ids"], "record_ids", sorted_unique=True), data["source_date"], data["jurisdiction"])


@dataclass(frozen=True)
class StyleContract(IdentityContract):
    schema: str
    required_phrases: tuple[str, ...]
    forbidden_phrases: tuple[str, ...]
    max_output_bytes: int
    max_repeated_line_count: int
    DOMAIN: ClassVar[str] = "QSOLAI/STYLE/v1"

    def __post_init__(self) -> None:
        if self.schema != "qsolai.style/v1":
            raise _bad("invalid StyleContract schema")
        object.__setattr__(self, "required_phrases", _strings(self.required_phrases, "required_phrases"))
        object.__setattr__(self, "forbidden_phrases", _strings(self.forbidden_phrases, "forbidden_phrases"))
        _exact_int(self.max_output_bytes, "max_output_bytes", 1, 10_000_000)
        _exact_int(self.max_repeated_line_count, "max_repeated_line_count", 1, 1000)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "required_phrases": list(self.required_phrases), "forbidden_phrases": list(self.forbidden_phrases), "max_output_bytes": self.max_output_bytes, "max_repeated_line_count": self.max_repeated_line_count}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StyleContract":
        _expect(data, {"schema", "required_phrases", "forbidden_phrases", "max_output_bytes", "max_repeated_line_count"})
        return cls(data["schema"], _strings(data["required_phrases"], "required_phrases"), _strings(data["forbidden_phrases"], "forbidden_phrases"), data["max_output_bytes"], data["max_repeated_line_count"])


@dataclass(frozen=True)
class CapabilityGrant(IdentityContract):
    schema: str
    grant_id: str
    execution_profile: str
    allowed_adapters: tuple[str, ...]
    allow_subprocess: bool
    argv: tuple[str, ...]
    environment: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    DOMAIN: ClassVar[str] = "QSOLAI/CAPABILITY-GRANT/v1"

    def __post_init__(self) -> None:
        if self.schema != "qsolai.capability-grant/v1":
            raise _bad("invalid CapabilityGrant schema")
        _identifier(self.grant_id, "grant_id")
        if self.execution_profile != "SIM_ONLY":
            raise _bad("v0.1.0 implements SIM_ONLY capability grants")
        adapters = _strings(self.allowed_adapters, "allowed_adapters", allow_empty=False, sorted_unique=True)
        object.__setattr__(self, "allowed_adapters", adapters)
        if any(item not in ADAPTERS for item in adapters):
            raise _bad("capability grant contains an unknown adapter")
        _exact_bool(self.allow_subprocess, "allow_subprocess")
        object.__setattr__(self, "argv", _strings(self.argv, "argv"))
        if self.allow_subprocess and (not self.argv or not self.argv[0].startswith("/")):
            raise _bad("subprocess argv must begin with an absolute executable path")
        if not isinstance(self.environment, Mapping):
            raise _bad("environment must be a mapping")
        clean: dict[str, str] = {}
        for key, value in self.environment.items():
            clean[_string(key, "environment key", maximum=128)] = _string(value, "environment value", allow_empty=True, maximum=8192)
        object.__setattr__(self, "environment", MappingProxyType(dict(sorted(clean.items()))))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "grant_id": self.grant_id, "execution_profile": self.execution_profile, "allowed_adapters": list(self.allowed_adapters), "allow_subprocess": self.allow_subprocess, "argv": list(self.argv), "environment": dict(self.environment)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CapabilityGrant":
        _expect(data, {"schema", "grant_id", "execution_profile", "allowed_adapters", "allow_subprocess", "argv", "environment"})
        return cls(data["schema"], data["grant_id"], data["execution_profile"], _strings(data["allowed_adapters"], "allowed_adapters", sorted_unique=True), data["allow_subprocess"], _strings(data["argv"], "argv"), data["environment"])


@dataclass(frozen=True)
class AgentManifest(IdentityContract):
    schema: str
    agent_id: str
    backend_id: str
    adapter: str
    roles: tuple[str, ...]
    capability_grant_id: str
    mock_response: Mapping[str, Any] | None = None
    DOMAIN: ClassVar[str] = "QSOLAI/AGENT/v1"

    def __post_init__(self) -> None:
        if self.schema != "qsolai.agent/v1":
            raise _bad("invalid AgentManifest schema")
        _identifier(self.agent_id, "agent_id")
        _identifier(self.backend_id, "backend_id")
        _enum(self.adapter, "adapter", ADAPTERS)
        roles = _strings(self.roles, "roles", allow_empty=False)
        object.__setattr__(self, "roles", roles)
        if any(role not in ROLES for role in roles):
            raise _bad("agent has an unsupported role")
        _identifier(self.capability_grant_id, "capability_grant_id")
        if self.mock_response is not None:
            if type(self.mock_response) is not dict and not isinstance(self.mock_response, MappingProxyType):
                raise _bad("mock_response must be a plain mapping")
            response = thaw(self.mock_response)
            canonical_bytes(response)
            object.__setattr__(self, "mock_response", freeze(response))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "agent_id": self.agent_id, "backend_id": self.backend_id, "adapter": self.adapter, "roles": list(self.roles), "capability_grant_id": self.capability_grant_id, "mock_response": thaw(self.mock_response) if self.mock_response is not None else None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentManifest":
        _expect(data, {"schema", "agent_id", "backend_id", "adapter", "roles", "capability_grant_id", "mock_response"})
        return cls(data["schema"], data["agent_id"], data["backend_id"], data["adapter"], _strings(data["roles"], "roles", allow_empty=False), data["capability_grant_id"], data["mock_response"])


@dataclass(frozen=True)
class TaskEnvelope(IdentityContract):
    schema: str
    task_id: str
    task_class: str
    goal: str
    risk_tier: str
    determinism_mode: str
    execution_profile: str
    constraints: tuple[Constraint, ...]
    evidence_requirements: tuple[EvidenceRequirement, ...]
    forbidden_actions: tuple[str, ...]
    mutation_index: int
    run_nonce: str
    history_catalogue: tuple[str, ...]
    DOMAIN: ClassVar[str] = DOMAINS["task"]

    def __post_init__(self) -> None:
        if self.schema != "qsolai.task/v1":
            raise _bad("invalid TaskEnvelope schema")
        _identifier(self.task_id, "task_id")
        _identifier(self.task_class, "task_class")
        _string(self.goal, "goal", maximum=65536)
        _enum(self.risk_tier, "risk_tier", {"LOW", "MEDIUM", "HIGH", "MISSION_CRITICAL"})
        _enum(self.determinism_mode, "determinism_mode", MODES)
        if self.execution_profile != "SIM_ONLY":
            raise _bad("v0.1.0 implements SIM_ONLY only")
        if type(self.constraints) is not tuple or any(type(item) is not Constraint for item in self.constraints):
            raise _bad("constraints must contain Constraint contracts")
        if type(self.evidence_requirements) is not tuple or any(type(item) is not EvidenceRequirement for item in self.evidence_requirements):
            raise _bad("evidence requirements must contain contracts")
        if len({item.constraint_id for item in self.constraints}) != len(self.constraints):
            raise _bad("constraint ids must be unique")
        if len({item.requirement_id for item in self.evidence_requirements}) != len(self.evidence_requirements):
            raise _bad("evidence requirement ids must be unique")
        object.__setattr__(self, "forbidden_actions", _strings(self.forbidden_actions, "forbidden_actions"))
        _exact_int(self.mutation_index, "mutation_index", 0, 2**31 - 1)
        _string(self.run_nonce, "run_nonce", maximum=256)
        history = _strings(self.history_catalogue, "history_catalogue", sorted_unique=True)
        object.__setattr__(self, "history_catalogue", history)
        for item in history:
            _sha(item, "history_catalogue entry")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "task_id": self.task_id, "task_class": self.task_class, "goal": self.goal, "risk_tier": self.risk_tier, "determinism_mode": self.determinism_mode, "execution_profile": self.execution_profile, "constraints": [item.to_dict() for item in self.constraints], "evidence_requirements": [item.to_dict() for item in self.evidence_requirements], "forbidden_actions": list(self.forbidden_actions), "mutation_index": self.mutation_index, "run_nonce": self.run_nonce, "history_catalogue": list(self.history_catalogue)}

    @property
    def history_catalogue_sha256(self) -> str:
        return domain_hash("QSOLAI/HISTORY/v1", list(self.history_catalogue))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskEnvelope":
        _expect(data, {"schema", "task_id", "task_class", "goal", "risk_tier", "determinism_mode", "execution_profile", "constraints", "evidence_requirements", "forbidden_actions", "mutation_index", "run_nonce", "history_catalogue"})
        if type(data["constraints"]) is not list or type(data["evidence_requirements"]) is not list:
            raise _bad("task child contracts must be lists")
        constraints = tuple(Constraint.from_dict(item) for item in data["constraints"])
        evidence = tuple(EvidenceRequirement.from_dict(item) for item in data["evidence_requirements"])
        return cls(data["schema"], data["task_id"], data["task_class"], data["goal"], data["risk_tier"], data["determinism_mode"], data["execution_profile"], constraints, evidence, _strings(data["forbidden_actions"], "forbidden_actions"), data["mutation_index"], data["run_nonce"], _strings(data["history_catalogue"], "history_catalogue", sorted_unique=True))


DEFAULT_RANKING = (
    "required_constraint_passes",
    "evidence_supported_claims",
    "deterministic_verifier_passes",
    "unsupported_claim_count",
    "contradiction_count",
    "risk_flag_count",
    "style_violation_count",
    "excess_output_bytes",
    "candidate_sha256",
)


@dataclass(frozen=True)
class PolicyPack(IdentityContract):
    schema: str
    policy_id: str
    execution_profile: str
    support_profile: str
    human_approval_required: bool
    required_independent_backends: int
    max_observation_bytes: int
    worker_timeout_ms: int
    capability_grants: tuple[CapabilityGrant, ...]
    agents: tuple[AgentManifest, ...]
    style: StyleContract
    forbidden_authority_phrases: tuple[str, ...]
    anti_repetition_enabled: bool
    maximum_attempts: int
    ranking: tuple[str, ...] = DEFAULT_RANKING
    DOMAIN: ClassVar[str] = DOMAINS["policy"]

    def __post_init__(self) -> None:
        if self.schema != "qsolai.policy/v1":
            raise _bad("invalid PolicyPack schema")
        _identifier(self.policy_id, "policy_id")
        if self.execution_profile != "SIM_ONLY":
            raise _bad("v0.1.0 policies must use SIM_ONLY")
        _enum(self.support_profile, "support_profile", SUPPORT_PROFILES)
        _exact_bool(self.human_approval_required, "human_approval_required")
        _exact_int(self.required_independent_backends, "required_independent_backends", 1, 64)
        _exact_int(self.max_observation_bytes, "max_observation_bytes", 128, 10_000_000)
        _exact_int(self.worker_timeout_ms, "worker_timeout_ms", 1, 600_000)
        if type(self.capability_grants) is not tuple or any(type(item) is not CapabilityGrant for item in self.capability_grants):
            raise _bad("capability grants must be validated contracts")
        if type(self.agents) is not tuple or not self.agents or any(type(item) is not AgentManifest for item in self.agents):
            raise _bad("agents must contain validated manifests")
        if type(self.style) is not StyleContract:
            raise _bad("style must be a StyleContract")
        object.__setattr__(self, "forbidden_authority_phrases", _strings(self.forbidden_authority_phrases, "forbidden_authority_phrases"))
        _exact_bool(self.anti_repetition_enabled, "anti_repetition_enabled")
        _exact_int(self.maximum_attempts, "maximum_attempts", 1, 1000)
        object.__setattr__(self, "ranking", tuple(self.ranking))
        if self.ranking != DEFAULT_RANKING:
            raise _bad("v0.1.0 ranking order is fixed")
        grant_ids = {item.grant_id for item in self.capability_grants}
        if len(grant_ids) != len(self.capability_grants):
            raise _bad("capability grant ids must be unique")
        if len({item.agent_id for item in self.agents}) != len(self.agents):
            raise _bad("agent ids must be unique")
        for agent in self.agents:
            if agent.capability_grant_id not in grant_ids:
                raise _bad("agent refers to an unknown capability grant")
            grant = next(item for item in self.capability_grants if item.grant_id == agent.capability_grant_id)
            if agent.adapter not in grant.allowed_adapters:
                raise _bad("agent adapter is not allowed by its capability grant")
        if self.support_profile != "NONE":
            if not self.human_approval_required or self.required_independent_backends < 2:
                raise _bad("high-stakes support requires two backends and human approval")
            if len({item.backend_id for item in self.agents}) < self.required_independent_backends:
                raise _bad("policy lacks independently declared worker backends")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "policy_id": self.policy_id, "execution_profile": self.execution_profile, "support_profile": self.support_profile, "human_approval_required": self.human_approval_required, "required_independent_backends": self.required_independent_backends, "max_observation_bytes": self.max_observation_bytes, "worker_timeout_ms": self.worker_timeout_ms, "capability_grants": [item.to_dict() for item in self.capability_grants], "agents": [item.to_dict() for item in self.agents], "style": self.style.to_dict(), "forbidden_authority_phrases": list(self.forbidden_authority_phrases), "anti_repetition_enabled": self.anti_repetition_enabled, "maximum_attempts": self.maximum_attempts, "ranking": list(self.ranking)}

    def grant_for(self, agent: AgentManifest) -> CapabilityGrant:
        return next(item for item in self.capability_grants if item.grant_id == agent.capability_grant_id)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PolicyPack":
        _expect(data, {"schema", "policy_id", "execution_profile", "support_profile", "human_approval_required", "required_independent_backends", "max_observation_bytes", "worker_timeout_ms", "capability_grants", "agents", "style", "forbidden_authority_phrases", "anti_repetition_enabled", "maximum_attempts", "ranking"})
        if type(data["capability_grants"]) is not list or type(data["agents"]) is not list:
            raise _bad("policy child contracts must be lists")
        grants = tuple(CapabilityGrant.from_dict(item) for item in data["capability_grants"])
        agents = tuple(AgentManifest.from_dict(item) for item in data["agents"])
        return cls(data["schema"], data["policy_id"], data["execution_profile"], data["support_profile"], data["human_approval_required"], data["required_independent_backends"], data["max_observation_bytes"], data["worker_timeout_ms"], grants, agents, StyleContract.from_dict(data["style"]), _strings(data["forbidden_authority_phrases"], "forbidden_authority_phrases"), data["anti_repetition_enabled"], data["maximum_attempts"], _strings(data["ranking"], "ranking", allow_empty=False))


@dataclass(frozen=True)
class AgentSlot(IdentityContract):
    schema: str
    slot_id: str
    role: str
    agent_id: str
    backend_id: str
    adapter: str
    ordinal: int
    mutation_index: int
    DOMAIN: ClassVar[str] = "QSOLAI/AGENT-SLOT/v1"

    def __post_init__(self) -> None:
        if self.schema != "qsolai.agent-slot/v1":
            raise _bad("invalid AgentSlot schema")
        _identifier(self.slot_id, "slot_id", 256)
        _enum(self.role, "role", set(ROLES))
        _identifier(self.agent_id, "agent_id")
        _identifier(self.backend_id, "backend_id")
        _enum(self.adapter, "adapter", ADAPTERS)
        _exact_int(self.ordinal, "ordinal", 0, 100_000)
        _exact_int(self.mutation_index, "mutation_index", 0, 2**31 - 1)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "slot_id": self.slot_id, "role": self.role, "agent_id": self.agent_id, "backend_id": self.backend_id, "adapter": self.adapter, "ordinal": self.ordinal, "mutation_index": self.mutation_index}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentSlot":
        _expect(data, {"schema", "slot_id", "role", "agent_id", "backend_id", "adapter", "ordinal", "mutation_index"})
        return cls(**data)


@dataclass(frozen=True)
class CompiledPlan(IdentityContract):
    schema: str
    task_sha256: str
    policy_sha256: str
    task_class: str
    risk_tier: str
    required_evidence_ids: tuple[str, ...]
    agent_manifest_sha256s: tuple[str, ...]
    history_catalogue_sha256: str
    determinism_mode: str
    execution_profile: str
    mutation_index: int
    slots: tuple[AgentSlot, ...]
    edges: tuple[tuple[str, str], ...]
    DOMAIN: ClassVar[str] = DOMAINS["plan"]

    def __post_init__(self) -> None:
        if self.schema != "qsolai.plan/v1":
            raise _bad("invalid CompiledPlan schema")
        _sha(self.task_sha256, "task_sha256")
        _sha(self.policy_sha256, "policy_sha256")
        _identifier(self.task_class, "task_class")
        _enum(self.risk_tier, "risk_tier", {"LOW", "MEDIUM", "HIGH", "MISSION_CRITICAL"})
        object.__setattr__(self, "required_evidence_ids", _strings(self.required_evidence_ids, "required_evidence_ids", sorted_unique=True))
        object.__setattr__(self, "agent_manifest_sha256s", _strings(self.agent_manifest_sha256s, "agent_manifest_sha256s", allow_empty=False, sorted_unique=True))
        for item in self.agent_manifest_sha256s:
            _sha(item, "agent_manifest_sha256")
        _sha(self.history_catalogue_sha256, "history_catalogue_sha256")
        _enum(self.determinism_mode, "determinism_mode", MODES)
        if self.execution_profile != "SIM_ONLY":
            raise _bad("plan execution profile must be SIM_ONLY")
        _exact_int(self.mutation_index, "mutation_index", 0, 2**31 - 1)
        if type(self.slots) is not tuple or any(type(item) is not AgentSlot for item in self.slots):
            raise _bad("plan slots must be AgentSlot contracts")
        if type(self.edges) is not tuple:
            raise _bad("plan edges must be an immutable tuple")
        if tuple(sorted(self.slots, key=lambda item: (ROLES.index(item.role), item.agent_id))) != self.slots:
            raise _bad("plan slot order is not canonical")
        known = {item.slot_id for item in self.slots}
        for edge in self.edges:
            if type(edge) is not tuple or len(edge) != 2 or edge[0] not in known or edge[1] not in known:
                raise _bad("plan edge is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "task_sha256": self.task_sha256, "policy_sha256": self.policy_sha256, "task_class": self.task_class, "risk_tier": self.risk_tier, "required_evidence_ids": list(self.required_evidence_ids), "agent_manifest_sha256s": list(self.agent_manifest_sha256s), "history_catalogue_sha256": self.history_catalogue_sha256, "determinism_mode": self.determinism_mode, "execution_profile": self.execution_profile, "mutation_index": self.mutation_index, "slots": [item.to_dict() for item in self.slots], "edges": [list(item) for item in self.edges]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompiledPlan":
        _expect(data, {"schema", "task_sha256", "policy_sha256", "task_class", "risk_tier", "required_evidence_ids", "agent_manifest_sha256s", "history_catalogue_sha256", "determinism_mode", "execution_profile", "mutation_index", "slots", "edges"})
        if type(data["slots"]) is not list or type(data["edges"]) is not list:
            raise _bad("plan slots and edges must be lists")
        return cls(data["schema"], data["task_sha256"], data["policy_sha256"], data["task_class"], data["risk_tier"], _strings(data["required_evidence_ids"], "required_evidence_ids", sorted_unique=True), _strings(data["agent_manifest_sha256s"], "agent_manifest_sha256s", allow_empty=False, sorted_unique=True), data["history_catalogue_sha256"], data["determinism_mode"], data["execution_profile"], data["mutation_index"], tuple(AgentSlot.from_dict(item) for item in data["slots"]), tuple(tuple(item) for item in data["edges"]))


@dataclass(frozen=True)
class CompiledPrompt(IdentityContract):
    schema: str
    slot_id: str
    role: str
    task_sha256: str
    policy_sha256: str
    mutation_index: int
    prompt: str
    DOMAIN: ClassVar[str] = DOMAINS["prompt"]

    def __post_init__(self) -> None:
        if self.schema != "qsolai.prompt/v1":
            raise _bad("invalid CompiledPrompt schema")
        _identifier(self.slot_id, "slot_id", 256)
        _enum(self.role, "role", set(ROLES))
        _sha(self.task_sha256, "task_sha256")
        _sha(self.policy_sha256, "policy_sha256")
        _exact_int(self.mutation_index, "mutation_index", 0, 2**31 - 1)
        _string(self.prompt, "prompt", maximum=1_000_000)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "slot_id": self.slot_id, "role": self.role, "task_sha256": self.task_sha256, "policy_sha256": self.policy_sha256, "mutation_index": self.mutation_index, "prompt": self.prompt}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompiledPrompt":
        _expect(data, {"schema", "slot_id", "role", "task_sha256", "policy_sha256", "mutation_index", "prompt"})
        return cls(**data)


@dataclass(frozen=True)
class RawObservation(IdentityContract):
    schema: str
    slot_id: str
    adapter: str
    status: str
    request_sha256: str
    response_b64: str
    response_sha256: str
    stderr_b64: str
    error_code: str | None
    DOMAIN: ClassVar[str] = DOMAINS["observation"]

    def __post_init__(self) -> None:
        if self.schema != "qsolai.observation/v1":
            raise _bad("invalid RawObservation schema")
        _identifier(self.slot_id, "slot_id", 256)
        _enum(self.adapter, "adapter", ADAPTERS)
        _enum(self.status, "status", {"OK", "INVALID_OUTPUT", "TIMEOUT", "OUTPUT_LIMIT", "MISSING", "ADAPTER_ERROR"})
        _sha(self.request_sha256, "request_sha256")
        _string(self.response_b64, "response_b64", allow_empty=True, maximum=20_000_000)
        _sha(self.response_sha256, "response_sha256")
        _string(self.stderr_b64, "stderr_b64", allow_empty=True, maximum=20_000_000)
        _optional_string(self.error_code, "error_code", 128)
        if sha256_bytes(self.response_bytes) != self.response_sha256:
            raise _bad("raw observation response hash mismatch")

    @property
    def response_bytes(self) -> bytes:
        try:
            return base64.b64decode(self.response_b64.encode("ascii"), validate=True)
        except (ValueError, UnicodeError) as exc:
            raise _bad("response_b64 is invalid") from exc

    @property
    def stderr_bytes(self) -> bytes:
        try:
            return base64.b64decode(self.stderr_b64.encode("ascii"), validate=True)
        except (ValueError, UnicodeError) as exc:
            raise _bad("stderr_b64 is invalid") from exc

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "slot_id": self.slot_id, "adapter": self.adapter, "status": self.status, "request_sha256": self.request_sha256, "response_b64": self.response_b64, "response_sha256": self.response_sha256, "stderr_b64": self.stderr_b64, "error_code": self.error_code}

    @classmethod
    def create(cls, slot_id: str, adapter: str, status: str, request_sha256: str, response: bytes, stderr: bytes = b"", error_code: str | None = None) -> "RawObservation":
        if type(response) is not bytes or type(stderr) is not bytes:
            raise _bad("observation byte fields must be exact bytes")
        return cls("qsolai.observation/v1", slot_id, adapter, status, request_sha256, base64.b64encode(response).decode("ascii"), sha256_bytes(response), base64.b64encode(stderr).decode("ascii"), error_code)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RawObservation":
        _expect(data, {"schema", "slot_id", "adapter", "status", "request_sha256", "response_b64", "response_sha256", "stderr_b64", "error_code"})
        return cls(**data)


@dataclass(frozen=True)
class EvidenceReference(IdentityContract):
    schema: str
    requirement_id: str
    record_id: str
    source_date: str | None
    jurisdiction: str | None
    DOMAIN: ClassVar[str] = "QSOLAI/EVIDENCE-REFERENCE/v1"

    def __post_init__(self) -> None:
        if self.schema != "qsolai.evidence-reference/v1":
            raise _bad("invalid EvidenceReference schema")
        _identifier(self.requirement_id, "requirement_id")
        _string(self.record_id, "record_id", maximum=256)
        _optional_string(self.source_date, "source_date", 64)
        _optional_string(self.jurisdiction, "jurisdiction", 256)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "requirement_id": self.requirement_id, "record_id": self.record_id, "source_date": self.source_date, "jurisdiction": self.jurisdiction}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceReference":
        _expect(data, {"schema", "requirement_id", "record_id", "source_date", "jurisdiction"})
        return cls(**data)


@dataclass(frozen=True)
class Claim(IdentityContract):
    schema: str
    claim_id: str
    text: str
    polarity: str
    evidence_references: tuple[EvidenceReference, ...]
    DOMAIN: ClassVar[str] = "QSOLAI/CLAIM/v1"

    def __post_init__(self) -> None:
        if self.schema != "qsolai.claim/v1":
            raise _bad("invalid Claim schema")
        _identifier(self.claim_id, "claim_id")
        _string(self.text, "claim text", maximum=65536)
        _enum(self.polarity, "polarity", {"SUPPORT", "DENY", "NEUTRAL"})
        if type(self.evidence_references) is not tuple or any(type(item) is not EvidenceReference for item in self.evidence_references):
            raise _bad("claim evidence references are invalid")
        if len({item.identity for item in self.evidence_references}) != len(self.evidence_references):
            raise _bad("claim evidence references cannot contain exact duplicates")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "claim_id": self.claim_id, "text": self.text, "polarity": self.polarity, "evidence_references": [item.to_dict() for item in self.evidence_references]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Claim":
        _expect(data, {"schema", "claim_id", "text", "polarity", "evidence_references"})
        if type(data["evidence_references"]) is not list:
            raise _bad("claim evidence references must be a list")
        return cls(data["schema"], data["claim_id"], data["text"], data["polarity"], tuple(EvidenceReference.from_dict(item) for item in data["evidence_references"]))


@dataclass(frozen=True)
class Candidate(IdentityContract):
    schema: str
    slot_id: str
    role: str
    backend_id: str
    observation_sha256: str
    summary: str
    claims: tuple[Claim, ...]
    uncertainties: tuple[str, ...]
    satisfied_constraints: tuple[str, ...]
    possibly_violated_constraints: tuple[str, ...]
    proposed_actions: tuple[str, ...]
    answer: str
    normalization_errors: tuple[str, ...]
    DOMAIN: ClassVar[str] = DOMAINS["candidate"]

    def __post_init__(self) -> None:
        if self.schema != "qsolai.candidate/v1":
            raise _bad("invalid Candidate schema")
        _identifier(self.slot_id, "slot_id", 256)
        _enum(self.role, "role", set(ROLES))
        _identifier(self.backend_id, "backend_id")
        _sha(self.observation_sha256, "observation_sha256")
        _string(self.summary, "summary", allow_empty=True, maximum=65536)
        if type(self.claims) is not tuple or any(type(item) is not Claim for item in self.claims):
            raise _bad("candidate claims are invalid")
        if len({item.claim_id for item in self.claims}) != len(self.claims):
            raise _bad("candidate claim ids must be unique")
        object.__setattr__(self, "uncertainties", _strings(self.uncertainties, "uncertainties"))
        object.__setattr__(self, "satisfied_constraints", _strings(self.satisfied_constraints, "satisfied_constraints"))
        object.__setattr__(self, "possibly_violated_constraints", _strings(self.possibly_violated_constraints, "possibly_violated_constraints"))
        object.__setattr__(self, "proposed_actions", _strings(self.proposed_actions, "proposed_actions"))
        _string(self.answer, "answer", allow_empty=True, maximum=2_000_000)
        object.__setattr__(self, "normalization_errors", _strings(self.normalization_errors, "normalization_errors"))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "slot_id": self.slot_id, "role": self.role, "backend_id": self.backend_id, "observation_sha256": self.observation_sha256, "summary": self.summary, "claims": [item.to_dict() for item in self.claims], "uncertainties": list(self.uncertainties), "constraint_report": {"satisfied": list(self.satisfied_constraints), "possibly_violated": list(self.possibly_violated_constraints)}, "proposed_actions": list(self.proposed_actions), "answer": self.answer, "normalization_errors": list(self.normalization_errors)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Candidate":
        _expect(data, {"schema", "slot_id", "role", "backend_id", "observation_sha256", "summary", "claims", "uncertainties", "constraint_report", "proposed_actions", "answer", "normalization_errors"})
        report = data["constraint_report"]
        _expect(report, {"satisfied", "possibly_violated"})
        return cls(data["schema"], data["slot_id"], data["role"], data["backend_id"], data["observation_sha256"], data["summary"], tuple(Claim.from_dict(item) for item in data["claims"]), _strings(data["uncertainties"], "uncertainties"), _strings(report["satisfied"], "satisfied"), _strings(report["possibly_violated"], "possibly_violated"), _strings(data["proposed_actions"], "proposed_actions"), data["answer"], _strings(data["normalization_errors"], "normalization_errors"))


@dataclass(frozen=True)
class VerificationResult(IdentityContract):
    schema: str
    candidate_sha256: str
    passed: bool
    hard_rejections: tuple[str, ...]
    warnings: tuple[str, ...]
    metrics: Mapping[str, int]
    DOMAIN: ClassVar[str] = DOMAINS["verification"]

    def __post_init__(self) -> None:
        if self.schema != "qsolai.verification/v1":
            raise _bad("invalid VerificationResult schema")
        _sha(self.candidate_sha256, "candidate_sha256")
        _exact_bool(self.passed, "passed")
        object.__setattr__(self, "hard_rejections", _strings(self.hard_rejections, "hard_rejections", sorted_unique=True))
        object.__setattr__(self, "warnings", _strings(self.warnings, "warnings", sorted_unique=True))
        if not isinstance(self.metrics, Mapping):
            raise _bad("verification metrics must be a mapping")
        clean: dict[str, int] = {}
        for key, value in self.metrics.items():
            clean[_string(key, "metric key", maximum=128)] = _exact_int(value, "metric value", 0, MAX_SAFE_INTEGER)
        object.__setattr__(self, "metrics", MappingProxyType(dict(sorted(clean.items()))))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "candidate_sha256": self.candidate_sha256, "passed": self.passed, "hard_rejections": list(self.hard_rejections), "warnings": list(self.warnings), "metrics": dict(self.metrics)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VerificationResult":
        _expect(data, {"schema", "candidate_sha256", "passed", "hard_rejections", "warnings", "metrics"})
        return cls(data["schema"], data["candidate_sha256"], data["passed"], _strings(data["hard_rejections"], "hard_rejections", sorted_unique=True), _strings(data["warnings"], "warnings", sorted_unique=True), data["metrics"])


@dataclass(frozen=True)
class DecisionReceipt(IdentityContract):
    schema: str
    task_sha256: str
    policy_sha256: str
    selected_candidate_sha256: str | None
    selected_verification_sha256: str | None
    eligible_candidates: tuple[str, ...]
    rejected_candidates: tuple[str, ...]
    ranking_rows: tuple[Mapping[str, Any], ...]
    unresolved_disagreements: tuple[str, ...]
    human_approval_required: bool
    status: str
    DOMAIN: ClassVar[str] = DOMAINS["decision"]

    def __post_init__(self) -> None:
        if self.schema != "qsolai.decision/v1":
            raise _bad("invalid DecisionReceipt schema")
        _sha(self.task_sha256, "task_sha256")
        _sha(self.policy_sha256, "policy_sha256")
        if self.selected_candidate_sha256 is not None:
            _sha(self.selected_candidate_sha256, "selected_candidate_sha256")
        if self.selected_verification_sha256 is not None:
            _sha(self.selected_verification_sha256, "selected_verification_sha256")
        object.__setattr__(self, "eligible_candidates", _strings(self.eligible_candidates, "eligible_candidates", sorted_unique=True))
        object.__setattr__(self, "rejected_candidates", _strings(self.rejected_candidates, "rejected_candidates", sorted_unique=True))
        rows: list[Mapping[str, Any]] = []
        for row in self.ranking_rows:
            if not isinstance(row, Mapping):
                raise _bad("ranking rows must be mappings")
            plain = thaw(row)
            canonical_bytes(plain)
            rows.append(freeze(plain))
        object.__setattr__(self, "ranking_rows", tuple(rows))
        object.__setattr__(self, "unresolved_disagreements", _strings(self.unresolved_disagreements, "unresolved_disagreements", sorted_unique=True))
        _exact_bool(self.human_approval_required, "human_approval_required")
        _enum(self.status, "status", {"SELECTED", "NO_ELIGIBLE_CANDIDATE"})

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "task_sha256": self.task_sha256, "policy_sha256": self.policy_sha256, "selected_candidate_sha256": self.selected_candidate_sha256, "selected_verification_sha256": self.selected_verification_sha256, "eligible_candidates": list(self.eligible_candidates), "rejected_candidates": list(self.rejected_candidates), "ranking_rows": [thaw(item) for item in self.ranking_rows], "unresolved_disagreements": list(self.unresolved_disagreements), "human_approval_required": self.human_approval_required, "status": self.status}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DecisionReceipt":
        _expect(data, {"schema", "task_sha256", "policy_sha256", "selected_candidate_sha256", "selected_verification_sha256", "eligible_candidates", "rejected_candidates", "ranking_rows", "unresolved_disagreements", "human_approval_required", "status"})
        return cls(data["schema"], data["task_sha256"], data["policy_sha256"], data["selected_candidate_sha256"], data["selected_verification_sha256"], _strings(data["eligible_candidates"], "eligible_candidates", sorted_unique=True), _strings(data["rejected_candidates"], "rejected_candidates", sorted_unique=True), tuple(data["ranking_rows"]), _strings(data["unresolved_disagreements"], "unresolved_disagreements", sorted_unique=True), data["human_approval_required"], data["status"])


@dataclass(frozen=True)
class HumanApprovalReceipt(IdentityContract):
    schema: str
    reviewer: str
    decision: str
    decision_sha256: str
    notes: str
    DOMAIN: ClassVar[str] = "QSOLAI/HUMAN-APPROVAL/v1"

    def __post_init__(self) -> None:
        if self.schema != "qsolai.human-approval/v1":
            raise _bad("invalid HumanApprovalReceipt schema")
        _string(self.reviewer, "reviewer", maximum=256)
        _enum(self.decision, "decision", {"accept", "reject"})
        _sha(self.decision_sha256, "decision_sha256")
        _string(self.notes, "notes", allow_empty=True, maximum=8192)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "reviewer": self.reviewer, "decision": self.decision, "decision_sha256": self.decision_sha256, "notes": self.notes}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HumanApprovalReceipt":
        _expect(data, {"schema", "reviewer", "decision", "decision_sha256", "notes"})
        return cls(**data)


@dataclass(frozen=True)
class EventRecord(IdentityContract):
    schema: str
    sequence: int
    event_type: str
    previous_event_hash: str
    payload_hash: str
    payload: Mapping[str, Any]
    event_hash: str
    DOMAIN: ClassVar[str] = DOMAINS["event"]

    def __post_init__(self) -> None:
        if self.schema != "qsolai.event/v1":
            raise _bad("invalid EventRecord schema")
        _exact_int(self.sequence, "sequence", 0, MAX_SAFE_INTEGER)
        _string(self.event_type, "event_type", maximum=128)
        _sha(self.previous_event_hash, "previous_event_hash")
        _sha(self.payload_hash, "payload_hash")
        _sha(self.event_hash, "event_hash")
        if not isinstance(self.payload, Mapping):
            raise _bad("event payload must be a mapping")
        plain = thaw(self.payload)
        canonical_bytes(plain)
        object.__setattr__(self, "payload", freeze(plain))
        if domain_hash("QSOLAI/EVENT-PAYLOAD/v1", plain) != self.payload_hash:
            raise _bad("event payload hash mismatch")
        if domain_hash(self.DOMAIN, without_self_hash(self.to_dict(), "event_hash")) != self.event_hash:
            raise _bad("event hash mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "sequence": self.sequence, "event_type": self.event_type, "previous_event_hash": self.previous_event_hash, "payload_hash": self.payload_hash, "payload": thaw(self.payload), "event_hash": self.event_hash}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventRecord":
        _expect(data, {"schema", "sequence", "event_type", "previous_event_hash", "payload_hash", "payload", "event_hash"})
        return cls(**data)


@dataclass(frozen=True)
class RunManifest(IdentityContract):
    schema: str
    run_id: str
    task_sha256: str
    policy_sha256: str
    implementation_sha256: str
    final_state: str
    artifacts: tuple[Mapping[str, Any], ...]
    manifest_core_sha256: str
    DOMAIN: ClassVar[str] = DOMAINS["manifest"]

    def __post_init__(self) -> None:
        if self.schema != "qsolai.manifest/v1":
            raise _bad("invalid RunManifest schema")
        _identifier(self.run_id, "run_id")
        _sha(self.task_sha256, "task_sha256")
        _sha(self.policy_sha256, "policy_sha256")
        _sha(self.implementation_sha256, "implementation_sha256")
        _string(self.final_state, "final_state", maximum=128)
        _sha(self.manifest_core_sha256, "manifest_core_sha256")
        rows: list[Mapping[str, Any]] = []
        paths: list[str] = []
        for row in self.artifacts:
            if not isinstance(row, Mapping):
                raise _bad("manifest artifact must be a mapping")
            plain = thaw(row)
            _expect(plain, {"path", "byte_length", "sha256"})
            paths.append(_string(plain["path"], "artifact path", maximum=1024))
            _exact_int(plain["byte_length"], "artifact byte_length", 0, MAX_SAFE_INTEGER)
            _sha(plain["sha256"], "artifact sha256")
            rows.append(freeze(plain))
        if paths != sorted(paths) or len(set(paths)) != len(paths):
            raise _bad("manifest artifacts must be sorted and unique")
        object.__setattr__(self, "artifacts", tuple(rows))
        if domain_hash(self.DOMAIN, without_self_hash(self.to_dict(), "manifest_core_sha256")) != self.manifest_core_sha256:
            raise _bad("manifest core hash mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "run_id": self.run_id, "task_sha256": self.task_sha256, "policy_sha256": self.policy_sha256, "implementation_sha256": self.implementation_sha256, "final_state": self.final_state, "artifacts": [thaw(item) for item in self.artifacts], "manifest_core_sha256": self.manifest_core_sha256}

    @property
    def identity(self) -> str:
        return self.manifest_core_sha256

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunManifest":
        _expect(data, {"schema", "run_id", "task_sha256", "policy_sha256", "implementation_sha256", "final_state", "artifacts", "manifest_core_sha256"})
        return cls(data["schema"], data["run_id"], data["task_sha256"], data["policy_sha256"], data["implementation_sha256"], data["final_state"], tuple(data["artifacts"]), data["manifest_core_sha256"])
