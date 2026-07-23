# High-stakes decision support

`MEDICAL_SUPPORT`, `LEGAL_SUPPORT` and `MISSION_CRITICAL_SUPPORT` are bounded decision-support profiles.

Policies for these profiles must declare at least two distinct backend IDs, require human approval and set `required_independent_backends` to at least two. Tasks must supply explicit required evidence records. Configured source dates and jurisdictions must match candidate evidence references exactly.

The deterministic verifier still applies every ordinary schema, constraint, authority and simulation check. Adjudication preserves unresolved SUPPORT/DENY disagreement across eligible candidates. A selected candidate moves the state machine only to `HUMAN_REVIEW_REQUIRED`. `COMMITTED` requires a `HumanApprovalReceipt` that hashes the exact current `DecisionReceipt`.

Approval records contain no hidden timestamp. Rejection is also explicit and terminal. The system never converts approval into autonomous external action.

The bundled medical and legal examples use entirely invented facts and authorities. They are not medical or legal advice.
