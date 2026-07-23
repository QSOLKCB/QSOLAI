# Research adjudication example

Two synthetic research candidates compete. The supported proposal cites the only declared evidence record with the configured source date. The unsupported proposal has no valid evidence reference and fails closed. No empirical conclusion is inferred from worker consensus.

```sh
python -m qsolai run examples/research_adjudication/task.json \
  --policy examples/research_adjudication/policy.json \
  --runs-dir runs --run-name research
python -m qsolai inspect runs/research
python -m qsolai replay runs/research
```
