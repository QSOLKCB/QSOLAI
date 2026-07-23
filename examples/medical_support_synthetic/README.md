# Synthetic medical-support example

All facts and records are invented. This is not medical advice. Two independently declared synthetic backends disagree while citing the same frozen record. QSOLAI reports the disagreement and stops at `HUMAN_REVIEW_REQUIRED`; it cannot commit until a reviewer supplies a decision-bound approval receipt.

```sh
python -m qsolai run examples/medical_support_synthetic/task.json \
  --policy examples/medical_support_synthetic/policy.json \
  --runs-dir runs --run-name medical-synthetic
python -m qsolai inspect runs/medical-synthetic
python -m qsolai approve runs/medical-synthetic --reviewer "Example Reviewer" --decision accept
python -m qsolai replay runs/medical-synthetic
```
