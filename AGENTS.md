# QSOLAI agent rules

These rules apply to every file and future coding agent in this repository.

## Product identity

QSOLAI is a deterministic orchestration kernel for bounded agent systems. Workers are untrusted proposal generators. They are never the final validator, adjudicator or action authority.

Do not turn this repository into a chatbot, browser application, frontend, generic agent framework, documentation-only receipt collection, or autonomous action system.

## Non-negotiable runtime architecture

- Python 3.11+ and standard-library-only runtime.
- No HTML, CSS, JavaScript, WebAssembly, React, Electron, Node.js or browser frontend.
- No third-party runtime package or provider SDK.
- No cloud, database server, telemetry service or default network access.
- No `eval`, `exec`, pickle, dynamic code execution or `shell=True`.
- No hidden entropy, hidden state or wall-clock value in canonical identity.
- No floats in identity-bearing structures.
- No unrestricted external process execution.
- `SIM_ONLY` is the only implemented execution profile in v0.1.x.
- Never execute worker-proposed file, network, system, medical, legal or financial actions.

Deferred labels `READ_ONLY_EXTERNAL`, `WORKSPACE_WRITE` and `CONTROLLED_EXECUTION` must remain documentation-only until a separately reviewed release explicitly implements them.

## Determinism rules

- Preserve recursively sorted canonical object keys and list order.
- Accept only null, strings, exact booleans, exact integers, lists and plain string-keyed mappings in canonical identity.
- Reject floats, bool/int aliases in integer fields, non-string keys, duplicate JSON keys, cycles and unexpected contract fields.
- Use explicit domain-separated SHA-256; never silently reuse a hash domain.
- Validate child contracts before aggregate receipts.
- Capture raw worker bytes before parsing.
- Keep canonical slot order independent of worker completion order.
- Use hard rejection before the fixed integer lexicographic rank vector.
- Use the candidate hash only as the final stable tie-break.
- Render the winner deterministically; never request a post-adjudication LLM rewrite.
- Every state transition must append a validated hash-chained event.
- Exact replay must fail closed on any missing, duplicate, reordered or changed byte.
- Intentional identity-byte changes require an engine/version review and updated golden vectors.

## Adapter boundary

Adapters translate worker I/O; they do not grant authority. New adapters must be explicitly registered, policy-granted, bounded and tested. `SubprocessJsonlAdapter` must retain fixed argv, an explicit environment, timeout/output limits, `shell=False`, a CLI opt-in and the warning that it is not an OS sandbox.

## Artifacts and paths

- Run directories must be direct children of a configured runs directory.
- Reject unsafe paths and existing non-empty output directories.
- Never recursively delete a caller-selected path.
- Keep manifests self-hash-excluded and bind every other artifact by exact bytes.
- Deterministic archives use lexical order, `ZIP_STORED`, fixed timestamps, fixed permissions, no comments and no host extras.
- `dist/qsolai.pyz` must remain at or below 1,350,000 bytes.

## Claim and high-stakes boundary

- Consensus is not truth.
- Unsupported claims, authority escalation and unresolved disagreement must remain visible.
- `MEDICAL_SUPPORT`, `LEGAL_SUPPORT` and `MISSION_CRITICAL_SUPPORT` are decision support only.
- High-stakes commitment requires two independently declared backends, explicit evidence, deterministic verification and a decision-bound human approval receipt.
- Never describe QSOLAI as validating consciousness, RES=RAG, deterministic LLM inference, AGI, scientific truth, diagnosis or legal authority.

## Required checks

Run all of these before reporting completion:

```sh
python -m unittest discover -s tests -v
python -m qsolai selftest
python scripts/audit_architecture.py
python scripts/audit_network.py
python scripts/build_zipapp.py
python scripts/verify_size.py dist/qsolai.pyz
```

Also run and replay at least one complete example. Do not hide or delete failing results.
