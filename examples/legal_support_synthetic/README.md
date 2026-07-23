# Synthetic legal-support example

The jurisdiction, authority and facts are invented. This is not legal advice. Two independently declared synthetic backends disagree over an invented provision in `Fictionalia-X`; QSOLAI preserves the disagreement and requires a human approval receipt before commitment.

```sh
python -m qsolai run examples/legal_support_synthetic/task.json \
  --policy examples/legal_support_synthetic/policy.json \
  --runs-dir runs --run-name legal-synthetic
python -m qsolai inspect runs/legal-synthetic
python -m qsolai approve runs/legal-synthetic --reviewer "Example Reviewer" --decision accept
python -m qsolai replay runs/legal-synthetic
```
