"""Deterministic candidate verification and fail-closed constraint checks."""

from __future__ import annotations

import re
import unicodedata

from .canonical import domain_hash
from .contracts import Candidate, PolicyPack, TaskEnvelope, VerificationResult


DEFAULT_AUTHORITY_PHRASES = (
    "i executed",
    "i have executed",
    "i sent",
    "i have sent",
    "legally guaranteed",
    "medically guaranteed",
    "scientifically proven",
    "autonomous final decision",
    "consensus proves",
)


def normalized_answer(value: str) -> str:
    text = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(" ".join(line.split()) for line in text.split("\n")).strip()


def normalized_answer_hash(value: str) -> str:
    return domain_hash("QSOLAI/FINAL-ANSWER-NORMALIZED/v1", normalized_answer(value))


def _contains(text: str, term: str, case_sensitive: bool) -> bool:
    if case_sensitive:
        return term in text
    return term.casefold() in text.casefold()


def verify_candidate(candidate: Candidate, task: TaskEnvelope, policy: PolicyPack) -> VerificationResult:
    hard: set[str] = set()
    warnings: set[str] = set()
    answer_bytes = candidate.answer.encode("utf-8")
    required_passes = 0
    style_violations = 0
    risk_flags = 0

    if candidate.normalization_errors:
        hard.add("SCHEMA_INVALID")
        warnings.update(candidate.normalization_errors)
    if not candidate.answer:
        hard.add("EMPTY_ANSWER")
    if candidate.role not in {"GENERATOR", "SYNTHESIS_CANDIDATE"}:
        hard.add("NON_FINAL_WORKER_ROLE")

    for constraint in task.constraints:
        matches = [_contains(candidate.answer, term, constraint.case_sensitive) for term in constraint.terms]
        if constraint.kind == "REQUIRED":
            if all(matches):
                required_passes += 1
            else:
                hard.add(f"REQUIRED_CONSTRAINT:{constraint.constraint_id}")
        elif any(matches):
            hard.add(f"FORBIDDEN_CONSTRAINT:{constraint.constraint_id}")

    if len(answer_bytes) > policy.style.max_output_bytes:
        hard.add("MAX_OUTPUT_BYTES")
    excess_bytes = max(0, len(answer_bytes) - policy.style.max_output_bytes)

    for phrase in policy.style.required_phrases:
        if phrase.casefold() not in candidate.answer.casefold():
            style_violations += 1
            warnings.add(f"STYLE_REQUIRED_MISSING:{phrase}")
    for phrase in policy.style.forbidden_phrases:
        if phrase.casefold() in candidate.answer.casefold():
            style_violations += 1
            warnings.add(f"STYLE_FORBIDDEN:{phrase}")
    line_counts: dict[str, int] = {}
    for line in normalized_answer(candidate.answer).split("\n"):
        if line:
            line_counts[line] = line_counts.get(line, 0) + 1
    if any(count > policy.style.max_repeated_line_count for count in line_counts.values()):
        style_violations += 1
        warnings.add("STYLE_REPEATED_LINES")

    authority_phrases = tuple(DEFAULT_AUTHORITY_PHRASES) + tuple(policy.forbidden_authority_phrases)
    searchable = "\n".join([candidate.answer, candidate.summary, *(claim.text for claim in candidate.claims)]).casefold()
    for phrase in authority_phrases:
        if phrase.casefold() in searchable:
            risk_flags += 1
            hard.add("FORBIDDEN_AUTHORITY_LANGUAGE")

    if candidate.proposed_actions:
        risk_flags += len(candidate.proposed_actions)
        warnings.add("PROPOSED_ACTIONS_CAPTURED_SIMULATION_ONLY")
    for forbidden in task.forbidden_actions:
        if any(forbidden.casefold() in action.casefold() for action in candidate.proposed_actions):
            hard.add("FORBIDDEN_PROPOSED_ACTION")

    requirements = {item.requirement_id: item for item in task.evidence_requirements}
    supported_claims = 0
    unsupported_claims = 0
    covered_requirements: set[str] = set()
    valid_reference_keys: set[tuple[str, str]] = set()
    for claim in candidate.claims:
        claim_supported = False
        for reference in claim.evidence_references:
            requirement = requirements.get(reference.requirement_id)
            valid = requirement is not None and reference.record_id in requirement.record_ids
            if valid and requirement is not None and requirement.source_date is not None:
                valid = reference.source_date == requirement.source_date
            if valid and requirement is not None and requirement.jurisdiction is not None:
                valid = reference.jurisdiction == requirement.jurisdiction
            if valid:
                claim_supported = True
                covered_requirements.add(reference.requirement_id)
                valid_reference_keys.add((reference.requirement_id, reference.record_id))
        if claim_supported:
            supported_claims += 1
        else:
            unsupported_claims += 1
    for requirement in task.evidence_requirements:
        if requirement.required and requirement.requirement_id not in covered_requirements:
            hard.add(f"REQUIRED_EVIDENCE_MISSING:{requirement.requirement_id}")
    if unsupported_claims:
        warnings.add("UNSUPPORTED_CLAIMS")

    normalized_claims = [(" ".join(claim.text.casefold().split()), claim.polarity) for claim in candidate.claims]
    duplicate_count = len(normalized_claims) - len(set(normalized_claims))
    if duplicate_count:
        warnings.add("EXACT_DUPLICATE_CLAIMS")
    polarities: dict[str, set[str]] = {}
    for text, polarity in normalized_claims:
        polarities.setdefault(text, set()).add(polarity)
    contradiction_count = sum(1 for values in polarities.values() if "SUPPORT" in values and "DENY" in values)
    if contradiction_count:
        warnings.add("CONTRADICTORY_DECLARED_CLAIMS")

    if policy.anti_repetition_enabled and normalized_answer_hash(candidate.answer) in task.history_catalogue:
        hard.add("EXACT_HISTORY_REPETITION")

    checks = 10
    verifier_passes = checks - min(checks, len(hard))
    metrics = {
        "required_constraint_passes": required_passes,
        "evidence_supported_claims": supported_claims,
        "deterministic_verifier_passes": verifier_passes,
        "unsupported_claim_count": unsupported_claims,
        "contradiction_count": contradiction_count,
        "duplicate_claim_count": duplicate_count,
        "risk_flag_count": risk_flags,
        "style_violation_count": style_violations,
        "excess_output_bytes": excess_bytes,
        "valid_evidence_reference_count": len(valid_reference_keys),
    }
    return VerificationResult(
        schema="qsolai.verification/v1",
        candidate_sha256=candidate.identity,
        passed=not hard,
        hard_rejections=tuple(sorted(hard)),
        warnings=tuple(sorted(warnings)),
        metrics=metrics,
    )
