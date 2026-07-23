# Adapter and worker protocol

## Request

```json
{
  "protocol": "qsolai.worker/v1",
  "slot_id": "...",
  "role": "...",
  "prompt": "...",
  "prompt_sha256": "...",
  "task_sha256": "...",
  "policy_sha256": "..."
}
```

## Response

```json
{
  "protocol": "qsolai.worker-result/v1",
  "summary": "...",
  "claims": [],
  "uncertainties": [],
  "constraint_report": {
    "satisfied": [],
    "possibly_violated": []
  },
  "proposed_actions": [],
  "answer": "..."
}
```

Claims use `qsolai.claim/v1` and embed `qsolai.evidence-reference/v1` records. Unknown keys, floats, duplicate keys, invalid UTF-8, trailing data and schema mismatches become explicit normalization errors.

Raw response bytes are hashed and stored as both a base64 field in the observation receipt and an exact `.raw` artifact before parsing.

## Registry

- `MockAdapter`: deterministic fixtures and tests.
- `ReplayAdapter`: frozen observations only; never invokes a worker.
- `ManualAdapter`: imports explicitly supplied bytes.
- `SubprocessJsonlAdapter`: fixed-argv, policy- and CLI-gated local protocol adapter; not an OS sandbox.

Adapters translate I/O and never validate truth or execute `proposed_actions`.
