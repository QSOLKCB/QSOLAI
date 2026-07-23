# QSOLAI v0.1.0

**A deterministic orchestration kernel for bounded agent systems.**

QSOLAI treats nondeterministic AI workers as untrusted proposal generators. It captures their original output bytes, then applies conventional deterministic planning, normalization, evidence checks, constraint enforcement, adjudication, human-review gates, artifact generation, SHA-256 identities and exact replay.

> The agents may vary. The orchestration boundary must not.

QSOLAI does **not** claim deterministic model inference, artificial general intelligence, autonomous authority, or real-world action capability. Version 0.1.0 implements `SIM_ONLY` authority exclusively.

## What is implemented

- Python 3.11+ standard-library-only runtime;
- strict canonical JSON with exact integers, exact booleans, sorted object keys, preserved list order, cycle rejection and float rejection;
- domain-separated SHA-256 identities for tasks, policies, plans, prompts, observations, candidates, verification, decisions, events, manifests and implementation source;
- frozen validated contracts with unexpected-key rejection and immutable nested identity data;
- conventional fixed-DAG planner with six worker roles;
- deterministic prompt compiler with untrusted-source and simulation-only boundaries;
- `MockAdapter`, `ReplayAdapter`, `ManualAdapter` and explicitly gated `SubprocessJsonlAdapter`;
- raw stdout/response-byte preservation before parsing;
- deterministic verification of constraints, evidence, claim support, contradictions, authority language, style, repetition and action boundaries;
- hard rejection followed by integer lexicographic ranking and stable hash tie-breaking;
- medical, legal and mission-critical decision-support profiles with independent-backend and human-approval gates;
- forward-only hash-chained state transitions;
- fail-closed run directories, deterministic manifests and byte-exact replay;
- deterministic `ZIP_STORED` run archives;
- a deterministic Python zipapp below the internal 1,350,000-byte limit; and
- a comprehensive standard-library `unittest` suite plus architecture and network audits.

## Determinism contract

For one engine/source-bundle version:

```text
same canonical task envelope
+ same canonical policy pack
+ same mutation index and run nonce
+ same agent manifests
+ same captured worker-output bytes
= same normalized candidates
+ same verification results
+ same decision
+ same event chain
+ same final output bytes
+ same manifest hashes
+ same deterministic archive bytes
```

Live worker generation in `CAPTURED_LIVE` or `EXPLORATORY` is outside this equality. QSOLAI commits only to exact post-capture processing. `CANONICAL_REPLAY` never invokes a live worker.

## Quick start

No package installation is required:

```sh
python -m qsolai selftest
python -m qsolai init demo
python -m qsolai run demo/task.json --policy demo/policy.json --runs-dir runs
```

Build and run the constrained artifact:

```sh
python scripts/build_zipapp.py
python scripts/verify_size.py dist/qsolai.pyz
python dist/qsolai.pyz selftest
```

## CLI

```text
qsolai init [DIRECTORY]
qsolai validate TASK [--policy POLICY]
qsolai plan TASK --policy POLICY
qsolai run TASK --policy POLICY [--runs-dir RUNS] [--run-name NAME]
qsolai import-observation RUN SLOT FILE
qsolai approve RUN --reviewer REVIEWER --decision {accept,reject}
qsolai verify RUN
qsolai replay RUN
qsolai inspect RUN
qsolai diff RUN_A RUN_B
qsolai pack RUN
qsolai selftest
qsolai size [ARTIFACT]
```

`--allow-subprocess` is additionally required for a policy-granted `SubprocessJsonlAdapter`. The adapter uses a fixed argv vector, explicit environment mapping, timeout and byte limits, and `shell=False`; it is not an operating-system sandbox.

## Run artifacts

Each completed or review-pending run contains:

```text
task.json                 policy.json
implementation.json       plan.json
prompts/                   observations/
candidates/                verification/
decision.json              final.json
final.txt                  event-log.jsonl
manifest.json              README_ORIGIN.txt
human-approval.json        # only after applicable review
```

The manifest commits to every other file by exact byte length and SHA-256. The implementation record hashes normalized source bytes of the modules defining canonicalization, contracts, state, planning, prompting, adapters, verification, adjudication, artifact production, replay, archive generation and the CLI.

## Runnable examples

- [`c99_win32_constraint`](examples/c99_win32_constraint/) — deterministically rejects a browser candidate;
- [`creative_variation`](examples/creative_variation/) — explicit mutation indices and history-catalogue anti-repetition;
- [`research_adjudication`](examples/research_adjudication/) — evidence-bound competing candidates;
- [`medical_support_synthetic`](examples/medical_support_synthetic/) — invented facts, disagreement and mandatory human approval; and
- [`legal_support_synthetic`](examples/legal_support_synthetic/) — invented jurisdiction/authorities and mandatory human approval.

The medical and legal examples are synthetic gate demonstrations, not medical or legal advice.

## Quality gates

From a clean checkout:

```sh
python -m unittest discover -s tests -v
python -m qsolai selftest
python scripts/audit_architecture.py
python scripts/audit_network.py
python scripts/build_zipapp.py
python scripts/verify_size.py dist/qsolai.pyz
```

## Security and authority boundary

QSOLAI does not execute worker-proposed actions. It has no default network client, cloud requirement, database server, telemetry service, dynamic code execution, pickle path or unrestricted process launcher. Deferred profiles—`READ_ONLY_EXTERNAL`, `WORKSPACE_WRITE` and `CONTROLLED_EXECUTION`—are documentation labels only and are not implemented in v0.1.0.

See [technical specification](docs/TECHNICAL_SPEC.md), [determinism](docs/DETERMINISM.md), [security](docs/SECURITY.md), [claim boundaries](docs/CLAIM_BOUNDARIES.md) and [high-stakes support](docs/HIGH_STAKES.md).

## Licence and lineage

QSOLAI is licensed under the [Mozilla Public License 2.0](LICENSE). It is a clean implementation informed conceptually by QEC, RES=RAG, SONIFICATION, SPECTRAL and Ternary Drift. Attribution and boundaries are recorded in [SOURCE_LINEAGE](docs/SOURCE_LINEAGE.md) and [NOTICE](NOTICE.md).
