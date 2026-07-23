"""Hard rejection followed by exact integer lexicographic adjudication."""

from __future__ import annotations

from typing import Iterable

from .contracts import Candidate, DecisionReceipt, PolicyPack, TaskEnvelope, VerificationResult
from .errors import QSOLAIError


def _rank_key(candidate: Candidate, verification: VerificationResult) -> tuple[object, ...]:
    metrics = verification.metrics
    return (
        -metrics["required_constraint_passes"],
        -metrics["evidence_supported_claims"],
        -metrics["deterministic_verifier_passes"],
        metrics["unsupported_claim_count"],
        metrics["contradiction_count"],
        metrics["risk_flag_count"],
        metrics["style_violation_count"],
        metrics["excess_output_bytes"],
        candidate.identity,
    )


def _disagreements(candidates: Iterable[Candidate]) -> tuple[str, ...]:
    declarations: dict[str, set[str]] = {}
    display: dict[str, str] = {}
    for candidate in candidates:
        for claim in candidate.claims:
            key = " ".join(claim.text.casefold().split())
            declarations.setdefault(key, set()).add(claim.polarity)
            display.setdefault(key, " ".join(claim.text.split()))
    return tuple(sorted(display[key] for key, values in declarations.items() if "SUPPORT" in values and "DENY" in values))


def adjudicate(task: TaskEnvelope, policy: PolicyPack, candidates: tuple[Candidate, ...], results: tuple[VerificationResult, ...]) -> DecisionReceipt:
    if len(candidates) != len(results):
        raise QSOLAIError("ADJUDICATION_INPUT_MISMATCH", "candidate and verification counts differ")
    if len(candidates) > policy.maximum_attempts:
        raise QSOLAIError("ATTEMPT_LIMIT_EXCEEDED", "candidate count exceeds deterministic maximum-attempt limit")
    by_hash = {candidate.identity: candidate for candidate in candidates}
    result_by_hash = {result.candidate_sha256: result for result in results}
    if set(by_hash) != set(result_by_hash):
        raise QSOLAIError("ADJUDICATION_LINEAGE", "verification lineage does not match candidates")

    eligible = [candidate for candidate in candidates if result_by_hash[candidate.identity].passed]
    ranked = sorted(eligible, key=lambda candidate: _rank_key(candidate, result_by_hash[candidate.identity]))
    ranking_rows = []
    for index, candidate in enumerate(ranked):
        result = result_by_hash[candidate.identity]
        ranking_rows.append(
            {
                "rank": index + 1,
                "candidate_sha256": candidate.identity,
                "verification_sha256": result.identity,
                "integer_vector": list(_rank_key(candidate, result)[:-1]),
                "tie_break_sha256": candidate.identity,
            }
        )
    selected = ranked[0] if ranked else None
    selected_result = result_by_hash[selected.identity] if selected is not None else None
    rejected = sorted(candidate.identity for candidate in candidates if candidate not in eligible)
    return DecisionReceipt(
        schema="qsolai.decision/v1",
        task_sha256=task.identity,
        policy_sha256=policy.identity,
        selected_candidate_sha256=selected.identity if selected else None,
        selected_verification_sha256=selected_result.identity if selected_result else None,
        eligible_candidates=tuple(sorted(candidate.identity for candidate in eligible)),
        rejected_candidates=tuple(rejected),
        ranking_rows=tuple(ranking_rows),
        unresolved_disagreements=_disagreements(eligible),
        human_approval_required=policy.human_approval_required,
        status="SELECTED" if selected else "NO_ELIGIBLE_CANDIDATE",
    )
