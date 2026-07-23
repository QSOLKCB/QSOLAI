# Technical specification

## Architecture

QSOLAI separates nondeterministic generation from deterministic authority:

1. a validated `TaskEnvelope` and `PolicyPack` establish the complete identity-bearing input;
2. the conventional planner compiles a fixed role DAG and canonical slot order;
3. the prompt compiler emits exact prompt contracts;
4. adapters capture raw worker response bytes before parsing;
5. normalization creates frozen candidates or explicit normalization failures;
6. deterministic verifiers apply schema, byte, constraint, evidence, claim, authority, style, repetition and simulation checks;
7. hard rejection removes ineligible candidates;
8. an integer-only lexicographic rank selects among survivors;
9. a deterministic renderer copies the winning answer without another model call;
10. events, artifacts, implementation identity and a manifest make the result replayable.

## Data contracts

Version 0.1.0 implements validated frozen contracts for all types named in the project brief: tasks, constraints, evidence requirements, policy/style/capability records, agent manifests/slots, plans/prompts, raw observations, candidates/claims/evidence references, verification and decision receipts, human approvals, run manifests and event records.

External task, policy and worker JSON reject unexpected fields. Aggregate construction validates child contracts first. Python tuples and read-only mappings prevent nested identity mutation after validation.

## Planner DAG

Canonical role order is:

```text
SUBSTRATE → GENERATOR → CRITIC → ADVERSARY
          → CONSTRAINT_AUDITOR → SYNTHESIS_CANDIDATE
```

Every declared agent eligible for a role receives a slot. Within a role, agents are ordered by `agent_id`; worker completion order never changes slot order. Adjacent stages form the fixed DAG. The explicit policy `maximum_attempts` bounds total slots.

All outputs are normalized and verified, but `SUBSTRATE`, `CRITIC`, `ADVERSARY` and `CONSTRAINT_AUDITOR` are observation roles and receive a deterministic `NON_FINAL_WORKER_ROLE` rejection for final-output adjudication. Only `GENERATOR` and `SYNTHESIS_CANDIDATE` proposals may survive into the final rank. Agent criticism therefore remains evidence for inspection and never replaces the deterministic verifier.

## Verification and ranking

Hard rejection covers malformed candidates, missing/forbidden constraints, byte-limit failures, required-evidence failures, authority escalation, forbidden proposed actions and exact catalogue repetition.

Eligible candidates are ordered by the fixed vector:

1. more required-constraint passes;
2. more evidence-supported claims;
3. more deterministic-verifier passes;
4. fewer unsupported claims;
5. fewer contradictions;
6. fewer risk flags;
7. fewer style violations;
8. fewer excess bytes; and
9. lexically smaller candidate SHA-256 as final tie-break.

No floating-point score or worker consensus participates in authority.

## Runtime profiles

Implemented: `SIM_ONLY`.

Documented but not implemented: `READ_ONLY_EXTERNAL`, `WORKSPACE_WRITE`, `CONTROLLED_EXECUTION`.
