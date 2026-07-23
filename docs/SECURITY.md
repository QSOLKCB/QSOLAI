# Security model

QSOLAI v0.1.0 is a bounded simulation kernel, not a security sandbox.

## Default protections

- no direct network-client module in the runtime;
- no provider SDK or external framework;
- no dynamic code execution, pickle or `shell=True`;
- no worker-proposed action execution;
- strict input schemas and byte limits;
- safe direct-child run directories;
- refusal of existing non-empty output directories;
- no recursive deletion of caller-selected paths;
- manifest and event-chain tamper detection; and
- high-stakes human commitment gates.

## Subprocess adapter

`SubprocessJsonlAdapter` is disabled unless all of the following are true: the agent selects it, its `CapabilityGrant` permits it, the grant provides an absolute executable in a fixed argv vector, and the CLI receives `--allow-subprocess`.

The adapter supplies only the explicit grant environment, uses `shell=False`, imposes timeout and accepted-output byte limits, and captures stdout/stderr. These controls do not isolate the child at the operating-system level and cannot prevent a separately trusted executable from using capabilities available to its host account. Use an external OS sandbox when that threat model matters.

## Disclosure

Report vulnerabilities privately to the repository owner before publishing operational exploit details. Include the engine version, source-bundle hash and a minimal deterministic reproduction where possible.
