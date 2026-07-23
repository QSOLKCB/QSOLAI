# Creative variation example

The task declares `mutation_index: 7` and a canonical history catalogue. The `repeat-proposer` emits a known normalized answer hash and is rejected. The novel proposal remains eligible. `task-mutation-8.json` changes only the explicit mutation index and nonce, demonstrating an intentional identity change without hidden randomness.

```sh
python -m qsolai run examples/creative_variation/task.json \
  --policy examples/creative_variation/policy.json \
  --runs-dir runs --run-name creative-m7
python -m qsolai run examples/creative_variation/task-mutation-8.json \
  --policy examples/creative_variation/policy.json \
  --runs-dir runs --run-name creative-m8
python -m qsolai diff runs/creative-m7 runs/creative-m8
```
