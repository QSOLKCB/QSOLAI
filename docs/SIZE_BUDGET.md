# Size budget

The runnable core is `dist/qsolai.pyz`. The Python interpreter is external and is not counted.

Hard limit:

```text
1,350,000 bytes
```

The deterministic builder includes only the `qsolai` Python package and a minimal zipapp entrypoint. Documentation, examples, tests, repository metadata and build scripts are excluded.

`scripts/verify_size.py` exits nonzero above the limit. The size constraint is a product invariant, inspired by the same compact-engineering ethos used for Ternary Drift; it is not a claim that Python itself fits on a floppy.
