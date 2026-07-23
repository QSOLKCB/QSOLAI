# Determinism and replay

## Modes

- `CANONICAL_REPLAY`: frozen observations are mandatory and no live adapter may run.
- `CAPTURED_LIVE`: workers may vary; original bytes are frozen, and everything after capture replays exactly.
- `EXPLORATORY`: the explicit `mutation_index` changes task, plan and prompt identity; output is not mission-critical commitment material without the normal gates.

## Canonical JSON ABI

Identity-bearing JSON permits null, strings, exact booleans, exact integers, lists and string-keyed plain mappings. Object keys sort recursively; list order is preserved. Encoding is compact UTF-8. Floats, non-finite values, bool-as-int aliases, duplicate keys, non-string keys, unsupported objects and cycles fail closed.

Hash preimages use:

```text
UTF-8(domain) || NUL || canonical-payload-bytes
```

Digests are lowercase SHA-256 hexadecimal.

## Event chain

Every transition records schema, sequence, event type, previous event hash, payload hash and payload. The event hash covers those fields except itself. The first previous hash is 64 zeroes. Replay rejects missing, duplicate, reordered or tampered events and validates the forward-only state transition represented by each payload.

## Implementation identity

`implementation.json` hashes normalized UTF-8/LF bytes of the exact runtime modules that define semantics. The domain-separated source-bundle hash participates in the run ID and manifest. A source change therefore prevents a false claim that a historical run was replayed by identical implementation bytes.

## Archive identity

Run ZIPs use lexical entry order, `ZIP_STORED`, 1980-01-01 timestamps, fixed Unix file permissions, no comment and empty extra fields. Identical run directories produce identical archive bytes.

## Exclusions

Wall clocks, host paths, file modification times, locales, network state, worker completion order and presentation details do not participate in canonical identity.
